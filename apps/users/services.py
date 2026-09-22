"""Side effects that run when a user's preferences change."""

import logging
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

# Rebuilds triggered by profile edits are coalesced: at most one build per user
# per this interval, so toggling preferences cannot multiply Spotify calls past
# what the explicit refresh endpoint allows.
REBUILD_MIN_INTERVAL = timedelta(seconds=60)


def on_preferences_changed(user) -> None:
    """Invalidate cached recommendations and make sure a rebuild is queued."""
    # Imported lazily so the users app does not pull Celery machinery at load time.
    from apps.recommendations.models import Recommendation
    from apps.recommendations.tasks import enqueue_refresh, recs_cache_key

    cache.delete(recs_cache_key(user.pk))

    if Recommendation.objects.filter(user=user).live_pending().exists():
        # A build is queued or running. If it is already running it will notice
        # the change on completion and re-queue itself (see the task).
        return

    # No cache gate here on purpose: a change must never be dropped. Two parallel
    # edits can at worst create two builds, and the newer one owns the result.
    countdown = 0
    last = Recommendation.objects.filter(user=user).order_by("-created_at").first()
    if last is not None:
        elapsed = timezone.now() - last.created_at
        if elapsed < REBUILD_MIN_INTERVAL:
            countdown = int((REBUILD_MIN_INTERVAL - elapsed).total_seconds()) + 1

    try:
        enqueue_refresh(user, countdown=countdown)
    except Exception:  # a broker outage must never break a profile write
        logger.exception("Could not enqueue recommendation refresh for %s", user.pk)
        Recommendation.objects.filter(user=user).live_pending().filter(
            started_at__isnull=True
        ).update(
            status=Recommendation.Status.FAILED,
            error="Could not enqueue background refresh (broker unavailable).",
            completed_at=timezone.now(),
        )
