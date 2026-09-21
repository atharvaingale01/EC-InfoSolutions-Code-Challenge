"""Side effects that run when a user's preferences change."""

import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)


def on_preferences_changed(user) -> None:
    """Invalidate cached recommendations and queue a fresh build."""
    # Imported lazily so the users app does not pull Celery machinery at load time.
    from apps.recommendations.tasks import recs_cache_key, refresh_user_recommendations

    cache.delete(recs_cache_key(user.pk))
    try:
        refresh_user_recommendations.delay(str(user.pk))
    except Exception:  # a broker outage must never break a profile write
        logger.exception("Could not enqueue recommendation refresh for %s", user.pk)
