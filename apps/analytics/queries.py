"""
Pure ORM aggregations behind the analytics endpoints. Kept free of DRF so
they are trivially unit-testable and reusable from management commands.
"""

from collections import Counter
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, F, Func, IntegerField, Max, Q, Sum
from django.utils import timezone

from apps.activity.models import UserActivity
from apps.recommendations.models import Recommendation, SpotifyCache

User = get_user_model()
ACTIONS = [choice for choice, _ in UserActivity.Action.choices]


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _by_action(qs) -> dict[str, int]:
    counts = {row["action"]: row["n"] for row in qs.values("action").annotate(n=Count("id"))}
    return {action: counts.get(action, 0) for action in ACTIONS}


def summary() -> dict:
    now = timezone.now()
    activities = UserActivity.objects.all()
    by_action = _by_action(activities)
    total_activity = sum(by_action.values())

    recs = Recommendation.objects.all()
    ready_recs = recs.filter(status=Recommendation.Status.READY)
    agg = ready_recs.aggregate(
        n=Count("id"),
        # jsonb_array_length runs in Postgres, so rows never stream into Python.
        tracks=Sum(Func(F("tracks"), function="jsonb_array_length", output_field=IntegerField())),
    )
    ready_count = agg["n"] or 0
    total_tracks = agg["tracks"] or 0

    return {
        "users": {
            "total": User.objects.filter(is_active=True).count(),
            "active_7d": activities.filter(created_at__gte=now - timedelta(days=7))
            .values("user_id")
            .distinct()
            .count(),
        },
        "activity": {
            "total": total_activity,
            "by_action": by_action,
            "like_rate": _ratio(by_action["like"], by_action["play"]),
            "skip_rate": _ratio(by_action["skip"], by_action["play"]),
        },
        "recommendations": {
            "total_generated": recs.count(),
            "ready": ready_count,
            "failed": recs.filter(status=Recommendation.Status.FAILED).count(),
            "pending": recs.filter(status=Recommendation.Status.PENDING).count(),
            "avg_tracks": round(total_tracks / ready_count, 2) if ready_count else 0.0,
        },
        "cache": {"spotify_cache_entries": SpotifyCache.objects.live().count()},
        "generated_at": now,
    }


def trends(days: int = 7, limit: int = 10) -> dict:
    since = timezone.now() - timedelta(days=days)
    recent = UserActivity.objects.filter(created_at__gte=since)

    genre_counter: Counter[str] = Counter()
    for genres in User.objects.filter(is_active=True).values_list("favorite_genres", flat=True):
        genre_counter.update(g for g in (genres or []) if g)
    top_genres = [{"genre": g, "users": n} for g, n in genre_counter.most_common(limit)]

    top_artists = list(
        recent.exclude(artist_name="")
        .values("artist_name")
        .annotate(
            interactions=Count("id"),
            likes=Count("id", filter=Q(action=UserActivity.Action.LIKE)),
            plays=Count("id", filter=Q(action=UserActivity.Action.PLAY)),
        )
        .order_by("-interactions", "-likes", "artist_name")[:limit]
    )

    top_tracks = list(
        recent.values("track_id", "track_name", "artist_name")
        .annotate(
            plays=Count("id", filter=Q(action=UserActivity.Action.PLAY)),
            likes=Count("id", filter=Q(action=UserActivity.Action.LIKE)),
            skips=Count("id", filter=Q(action=UserActivity.Action.SKIP)),
            interactions=Count("id"),
        )
        .order_by("-interactions", "-likes", "track_name")[:limit]
    )

    return {
        "window_days": days,
        "top_genres": top_genres,
        "top_artists": top_artists,
        "top_tracks": top_tracks,
    }


def user_summary(user, limit: int = 5) -> dict:
    activities = UserActivity.objects.filter(user=user)
    by_action = _by_action(activities)
    total = sum(by_action.values())

    top_artists = list(
        activities.exclude(artist_name="")
        .values("artist_name")
        .annotate(interactions=Count("id"))
        .order_by("-interactions", "artist_name")[:limit]
    )

    recs = Recommendation.objects.filter(user=user)
    ready = recs.filter(status=Recommendation.Status.READY)
    latest = ready.order_by("-completed_at").first()

    recommended_ids: set[str] = set()
    for tracks in ready.values_list("tracks", flat=True):
        recommended_ids.update(t.get("spotify_id") for t in (tracks or []) if t.get("spotify_id"))

    interacted_ids = set(activities.values_list("track_id", flat=True).distinct())
    engaged = len(recommended_ids & interacted_ids)

    return {
        "user_id": user.pk,
        "activity": {
            "total": total,
            "by_action": by_action,
            "like_rate": _ratio(by_action["like"], by_action["play"]),
            "skip_rate": _ratio(by_action["skip"], by_action["play"]),
        },
        "top_artists": top_artists,
        "recommendations": {
            "generated": recs.count(),
            "last_generated_at": latest.completed_at if latest else None,
            "tracks_recommended": len(recommended_ids),
        },
        "engagement_rate": _ratio(engaged, len(recommended_ids)),
        "last_active_at": activities.aggregate(last=Max("created_at"))["last"],
    }
