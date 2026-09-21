import logging

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone

from .engine import build_recommendations
from .models import Recommendation, SpotifyCache
from .spotify.exceptions import SpotifyAuthError, SpotifyRateLimited, SpotifyUnavailable

logger = logging.getLogger(__name__)
User = get_user_model()


def recs_cache_key(user_id) -> str:
    return f"recs:{user_id}"


def cache_payload(rec: Recommendation) -> dict:
    return {
        "recommendation_id": str(rec.id),
        "generated_at": rec.completed_at.isoformat() if rec.completed_at else None,
        "source": rec.source,
        "tracks": rec.tracks,
    }


@shared_task(
    bind=True,
    autoretry_for=(SpotifyUnavailable, SpotifyRateLimited),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
    acks_late=True,
)
def refresh_user_recommendations(self, user_id: str, recommendation_id: str | None = None):
    """
    Build recommendations for one user. Always leaves the Recommendation row in
    a terminal state (ready/failed) once retries are exhausted.
    """
    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        logger.warning("refresh_user_recommendations: user %s missing/inactive", user_id)
        return {"status": "skipped"}

    rec = None
    if recommendation_id:
        rec = Recommendation.objects.filter(pk=recommendation_id, user=user).first()
    if rec is None:
        rec = Recommendation.objects.create(user=user, task_id=self.request.id)
    elif rec.task_id != self.request.id:
        rec.task_id = self.request.id
        rec.save(update_fields=["task_id"])

    try:
        tracks, seed_params = build_recommendations(user)
    except (SpotifyUnavailable, SpotifyRateLimited) as exc:
        if self.request.retries >= self.max_retries:
            rec.mark_failed(str(exc))
            return {"status": "failed", "error": str(exc)}
        raise
    except SpotifyAuthError as exc:
        rec.mark_failed(str(exc))
        return {"status": "failed", "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 — never leave the row pending
        logger.exception("Unexpected error building recommendations for %s", user_id)
        rec.mark_failed(f"{type(exc).__name__}: {exc}")
        return {"status": "failed", "error": str(exc)}

    rec.mark_ready(tracks, seed_params)
    cache.set(recs_cache_key(user.pk), cache_payload(rec), settings.RECS_CACHE_TTL_SECONDS)
    logger.info("Recommendations ready for %s: %d tracks", user.email, len(tracks))
    return {"status": "ready", "recommendation_id": str(rec.id), "count": len(tracks)}


@shared_task
def refresh_all_recommendations():
    """Beat: fan out one refresh task per active user."""
    ids = list(User.objects.filter(is_active=True).values_list("pk", flat=True))
    for user_id in ids:
        refresh_user_recommendations.delay(str(user_id))
    logger.info("Queued recommendation refresh for %d users", len(ids))
    return {"queued": len(ids)}


@shared_task
def purge_expired_spotify_cache():
    deleted, _ = SpotifyCache.objects.expired().delete()
    logger.info("Purged %d expired Spotify cache rows at %s", deleted, timezone.now())
    return {"deleted": deleted}
