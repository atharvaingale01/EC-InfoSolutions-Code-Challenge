import logging
from datetime import timedelta

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import F, Window
from django.db.models.functions import RowNumber
from django.utils import timezone

from .engine import build_recommendations
from .models import QUEUE_TTL, Recommendation, SpotifyCache
from .spotify.exceptions import (
    SpotifyAuthError,
    SpotifyForbidden,
    SpotifyRateLimited,
    SpotifyUnavailable,
)

logger = logging.getLogger(__name__)
User = get_user_model()

SOFT_TIME_LIMIT = 240  # seconds; below CELERY_TASK_TIME_LIMIT so we can still mark the row
MAX_RETRIES = 3
MAX_RATE_LIMIT_WAIT = 900  # cap on honouring Spotify's Retry-After between task retries
FAILED_RETENTION = timedelta(days=7)
KEEP_READY_PER_USER = 5
FANOUT_LOCK_KEY = "beat:refresh-all"


def recs_cache_key(user_id) -> str:
    return f"recs:{user_id}"


def cache_payload(rec: Recommendation) -> dict:
    return {
        "recommendation_id": str(rec.id),
        "generated_at": rec.completed_at.isoformat() if rec.completed_at else None,
        "source": rec.source,
        "tracks": rec.tracks,
    }


def enqueue_refresh(user, countdown: int = 0, expires: int | None = None) -> Recommendation:
    """Create the pending row first so the API can report it, then queue the task."""
    rec = Recommendation.objects.create(user=user)
    result = refresh_user_recommendations.apply_async(
        args=[str(user.pk), str(rec.pk)], countdown=countdown, expires=expires
    )
    task_id = getattr(result, "id", None)
    if task_id:
        Recommendation.objects.filter(pk=rec.pk, task_id__isnull=True).update(task_id=task_id)
    return rec


@shared_task(
    bind=True,
    autoretry_for=(SpotifyUnavailable,),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
    max_retries=MAX_RETRIES,
    acks_late=True,
    soft_time_limit=SOFT_TIME_LIMIT,
)
def refresh_user_recommendations(self, user_id: str, recommendation_id: str | None = None):
    """
    Build recommendations for one user. Always leaves the Recommendation row in
    a terminal state once retries are exhausted, never overwrites a newer build,
    and re-queues itself if the preferences changed while it was running.
    """
    rec = None
    if recommendation_id:
        rec = Recommendation.objects.filter(pk=recommendation_id).first()

    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        logger.warning("refresh_user_recommendations: user %s missing/inactive", user_id)
        if rec is not None and rec.status == Recommendation.Status.PENDING:
            rec.mark_failed("User is inactive or was deleted.")
        return {"status": "skipped"}

    if rec is None:
        rec = Recommendation.objects.create(user=user)
    prefs_before = user.preferences_hash
    rec.mark_started(self.request.id, prefs_before)

    try:
        tracks, seed_params = build_recommendations(user)
    except SpotifyRateLimited as exc:
        # Honour Spotify's Retry-After between attempts instead of hammering it.
        if self.request.retries >= MAX_RETRIES:
            rec.mark_failed(str(exc))
            return {"status": "failed", "error": str(exc)}
        wait = min(max(exc.retry_after, 1), MAX_RATE_LIMIT_WAIT)
        raise self.retry(exc=exc, countdown=wait) from exc
    except SpotifyUnavailable as exc:
        if self.request.retries >= MAX_RETRIES:
            rec.mark_failed(str(exc))
            return {"status": "failed", "error": str(exc)}
        raise
    except (SpotifyAuthError, SpotifyForbidden) as exc:
        rec.mark_failed(str(exc))
        return {"status": "failed", "error": str(exc)}
    except SoftTimeLimitExceeded:
        rec.mark_failed(f"Build exceeded {SOFT_TIME_LIMIT}s and was stopped.")
        return {"status": "failed", "error": "timeout"}
    except Exception as exc:  # noqa: BLE001 — never leave the row pending
        logger.exception("Unexpected error building recommendations for %s", user_id)
        # Keep internals out of the API; the traceback is in the worker log.
        rec.mark_failed(f"Unexpected {type(exc).__name__} while building; see worker logs.")
        return {"status": "failed", "error": type(exc).__name__}

    rec.mark_ready(tracks, seed_params, source=seed_params.get("source", "search_v1"))

    # Supersession: a build created after this one owns the cache, even if it
    # finished first (slow Spotify call, redelivered message, second worker).
    superseded = (
        Recommendation.objects.filter(user=user, created_at__gt=rec.created_at)
        .exclude(pk=rec.pk)
        .exists()
    )
    if not superseded:
        cache.set(recs_cache_key(user.pk), cache_payload(rec), settings.RECS_CACHE_TTL_SECONDS)

    # Preferences changed while we were building: the dedupe in the API assumed
    # this run would pick them up, so queue one more build now.
    user.refresh_from_db(fields=["favorite_genres", "favorite_artists", "moods"])
    if (
        user.preferences_hash != prefs_before
        and not Recommendation.objects.filter(user=user).live_pending().exclude(pk=rec.pk).exists()
    ):
        enqueue_refresh(user, countdown=5)
        logger.info("Preferences changed during build for %s; re-queued", user.email)

    logger.info("Recommendations ready for %s: %d tracks", user.email, len(tracks))
    return {"status": "ready", "recommendation_id": str(rec.id), "count": len(tracks)}


@shared_task(soft_time_limit=SOFT_TIME_LIMIT)
def refresh_all_recommendations():
    """
    Beat: fan out one refresh task per active user, plus housekeeping.

    * A cache lock stops two fan-outs overlapping if the previous one is still queued.
    * Rows that can no longer be running (never started within the queue TTL, or
      started more than 15 minutes ago) are marked failed so `refresh_pending`
      cannot stick.
    * Old rows are pruned: failed rows after 7 days, ready rows beyond the last 5
      per user.
    * Users that already have a live pending build are skipped; queued tasks
      expire after one interval so a backlog never compounds.
    """
    ttl = int(QUEUE_TTL.total_seconds())
    if not cache.add(FANOUT_LOCK_KEY, timezone.now().isoformat(), ttl):
        logger.warning("refresh_all_recommendations: previous fan-out still active; skipping")
        return {"skipped": "locked"}

    now = timezone.now()
    lost = Recommendation.objects.lost().update(
        status=Recommendation.Status.FAILED,
        error="Build never completed (task lost or worker killed); superseded by the next refresh.",
        completed_at=now,
    )
    pruned_failed, _ = Recommendation.objects.filter(
        status=Recommendation.Status.FAILED, completed_at__lt=now - FAILED_RETENTION
    ).delete()
    surplus_ids = list(
        Recommendation.objects.filter(status=Recommendation.Status.READY)
        .annotate(
            rn=Window(RowNumber(), partition_by=[F("user_id")], order_by=F("created_at").desc())
        )
        .filter(rn__gt=KEEP_READY_PER_USER)
        .values_list("pk", flat=True)
    )
    pruned_ready = 0
    for i in range(0, len(surplus_ids), 1000):
        deleted, _ = Recommendation.objects.filter(pk__in=surplus_ids[i : i + 1000]).delete()
        pruned_ready += deleted

    busy = set(Recommendation.objects.live_pending().values_list("user_id", flat=True))
    queued = 0
    for user in User.objects.filter(is_active=True).exclude(pk__in=busy).iterator(chunk_size=500):
        enqueue_refresh(user, expires=ttl)
        queued += 1

    logger.info(
        "Scheduled refresh: queued=%d busy=%d lost=%d pruned_failed=%d pruned_ready=%d",
        queued,
        len(busy),
        lost,
        pruned_failed,
        pruned_ready,
    )
    return {
        "queued": queued,
        "skipped_busy": len(busy),
        "stale_failed": lost,
        "pruned_failed": pruned_failed,
        "pruned_ready": pruned_ready,
    }


@shared_task
def purge_expired_spotify_cache():
    deleted, _ = SpotifyCache.objects.expired().delete()
    logger.info("Purged %d expired Spotify cache rows at %s", deleted, timezone.now())
    return {"deleted": deleted}
