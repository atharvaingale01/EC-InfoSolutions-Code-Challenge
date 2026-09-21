"""
Per-user throttle buckets. All key on the authenticated user's primary key
(falling back to client IP for anonymous callers), so limits follow the
account rather than the network address.

Rates live in REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] and are env-driven.
"""

from rest_framework.throttling import UserRateThrottle


class RefreshThrottle(UserRateThrottle):
    """Tight bucket for recommendation refresh triggers (each costs Spotify calls)."""

    scope = "refresh"


class ActivityThrottle(UserRateThrottle):
    """Bucket for activity writes; higher than refresh, lower than general reads."""

    scope = "activity"
