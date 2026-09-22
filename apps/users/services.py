"""Side effects that run when a user's preferences change."""

import logging
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)
PENDING_REUSE_WINDOW = timedelta(minutes=2)


def on_preferences_changed(user) -> None:
    """Invalidate cached recommendations and queue a fresh build."""
    # Imported lazily so the users app does not pull Celery machinery at load time.
    from apps.recommendations.models import Recommendation
    from apps.recommendations.tasks import recs_cache_key, refresh_user_recommendations

    cache.delete(recs_cache_key(user.pk))
    if Recommendation.objects.filter(
        user=user,
        status=Recommendation.Status.PENDING,
        created_at__gte=timezone.now() - PENDING_REUSE_WINDOW,
    ).exists():
        return  # a rebuild is already queued; it will pick up the new preferences
    rec = Recommendation.objects.create(user=user)  # visible as "pending" straight away
    try:
        result = refresh_user_recommendations.delay(str(user.pk), str(rec.pk))
        task_id = getattr(result, "id", None)
        if task_id:
            Recommendation.objects.filter(pk=rec.pk, task_id__isnull=True).update(task_id=task_id)
    except Exception:  # a broker outage must never break a profile write
        logger.exception("Could not enqueue recommendation refresh for %s", user.pk)
        rec.mark_failed("Could not enqueue background refresh (broker unavailable).")
