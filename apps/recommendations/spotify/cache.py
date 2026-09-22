"""Persistent (PostgreSQL) cache around raw Spotify GET responses."""

import hashlib
import json
import logging
from collections.abc import Callable
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from ..models import SpotifyCache

logger = logging.getLogger(__name__)


def make_cache_key(endpoint: str, params: dict) -> str:
    payload = json.dumps({"e": endpoint, "p": params}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def cached_get(endpoint: str, params: dict, fetch: Callable[[], dict]) -> dict:
    """
    Return the cached response for (endpoint, params) if live, otherwise call
    `fetch()`, persist its result and return it.
    """
    key = make_cache_key(endpoint, params)
    entry = SpotifyCache.objects.filter(cache_key=key).first()
    if entry and not entry.is_expired:
        return entry.response

    response = fetch()
    ttl = timedelta(seconds=settings.SPOTIFY_CACHE_TTL_SECONDS)
    defaults = {
        "endpoint": endpoint,
        "params": params,
        "response": response,
        "expires_at": timezone.now() + ttl,
    }
    try:
        with transaction.atomic():
            SpotifyCache.objects.update_or_create(cache_key=key, defaults=defaults)
    except IntegrityError:
        # Another worker inserted the same key between our lookup and write.
        # Its response is equivalent; keep ours for this call and move on.
        logger.debug("SpotifyCache race on %s; another worker won", key[:8])
    return response
