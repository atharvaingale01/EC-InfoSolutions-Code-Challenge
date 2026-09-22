"""
Minimal Spotify Web API client using the Client Credentials flow.

Only endpoints verified to work for a newly created (development-mode) app:
  * POST accounts.spotify.com/api/token
  * GET  /v1/search            (type=track with genre:/artist: filters, type=artist)

Per Spotify's February 2026 development-mode changes (confirmed live, Sep 2026):
  * /v1/recommendations (removed Nov 2024) returns 404 and
    /v1/artists/{id}/top-tracks (removed Feb 2026) returns 403, so artist
    seeds are expanded with a track search filtered by artist name instead.
  * Track objects no longer include `popularity`; `preview_url` is deprecated.
  * /v1/search `limit` is capped at 10 (was 50); the client clamps to that.
  * The app owner must hold an active Spotify Premium subscription.
  https://developer.spotify.com/documentation/web-api/references/changes/february-2026

Every GET is routed through the persistent SpotifyCache table.
"""

import logging
import time

import requests
from django.conf import settings
from django.core.cache import cache

from .cache import cached_get
from .exceptions import (
    SpotifyAuthError,
    SpotifyForbidden,
    SpotifyNotFound,
    SpotifyRateLimited,
    SpotifyUnavailable,
)

logger = logging.getLogger(__name__)

TOKEN_CACHE_KEY = "spotify:token"
MAX_ATTEMPTS = 3
SEARCH_MAX_LIMIT = 10  # Spotify reduced the search limit ceiling from 50 to 10 in Feb 2026
MAX_INLINE_RATE_LIMIT_WAIT = 5  # seconds we are willing to sleep inside a request


def _retry_after_seconds(raw: str | None) -> int:
    try:
        return max(1, int(float(raw))) if raw else 1
    except (TypeError, ValueError):
        return 1


class SpotifyClient:
    source = "search_v1"

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.client_id = settings.SPOTIFY_CLIENT_ID
        self.client_secret = settings.SPOTIFY_CLIENT_SECRET
        self.base_url = settings.SPOTIFY_API_BASE
        self.market = settings.SPOTIFY_MARKET

    # -- auth ---------------------------------------------------------------

    def get_token(self, force: bool = False) -> str:
        if not force:
            token = cache.get(TOKEN_CACHE_KEY)
            if token:
                return token
        if not self.client_id or not self.client_secret:
            raise SpotifyAuthError("SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET are not configured.")

        try:
            resp = self.session.post(
                settings.SPOTIFY_TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(self.client_id, self.client_secret),
                timeout=10,
            )
        except requests.RequestException as exc:
            raise SpotifyUnavailable(f"Spotify token endpoint unreachable: {exc}") from exc
        if resp.status_code in (400, 401):
            raise SpotifyAuthError(f"Spotify rejected client credentials: {resp.text[:200]}")
        if resp.status_code >= 500:
            raise SpotifyUnavailable(f"Spotify token endpoint returned {resp.status_code}")
        resp.raise_for_status()
        payload = resp.json()
        token = payload["access_token"]
        ttl = max(int(payload.get("expires_in", 3600)) - 60, 60)
        cache.set(TOKEN_CACHE_KEY, token, ttl)
        return token

    # -- transport ----------------------------------------------------------

    def _get(self, path: str, params: dict) -> dict:
        url = f"{self.base_url}{path}"
        token = self.get_token()
        refreshed = False
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                resp = self.session.get(
                    url, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=10
                )
            except requests.RequestException as exc:
                # Timeouts / connection resets: back off in-process, then let Celery retry.
                if attempt == MAX_ATTEMPTS:
                    raise SpotifyUnavailable(f"{path}: {type(exc).__name__}: {exc}") from exc
                time.sleep(0.5 * 2 ** (attempt - 1))
                continue
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 401:
                if refreshed:
                    raise SpotifyAuthError("Spotify rejected a freshly issued access token.")
                refreshed = True
                token = self.get_token(force=True)
                continue
            if resp.status_code == 403:
                # Either the whole Web API is blocked for this app (owner has no
                # Premium subscription) or this endpoint is restricted for
                # development-mode apps. Retrying cannot help.
                raise SpotifyForbidden(
                    f"Spotify returned 403 for {path}. The endpoint is not available to "
                    "this app (Premium-owner requirement or development-mode restriction). "
                    "Set SPOTIFY_MOCK=1 for fixture-backed recommendations."
                )
            if resp.status_code == 404:
                raise SpotifyNotFound(f"{path} returned 404")
            if resp.status_code == 429:
                retry_after = _retry_after_seconds(resp.headers.get("Retry-After"))
                # Short waits are absorbed here; anything longer is handed to Celery,
                # which retries with that countdown instead of blocking a worker slot.
                if attempt == MAX_ATTEMPTS or retry_after > MAX_INLINE_RATE_LIMIT_WAIT:
                    raise SpotifyRateLimited(retry_after)
                logger.warning("Spotify 429 on %s; sleeping %ss", path, retry_after)
                time.sleep(retry_after)
                continue
            if resp.status_code >= 500:
                if attempt == MAX_ATTEMPTS:
                    raise SpotifyUnavailable(f"{path} returned {resp.status_code}")
                time.sleep(0.5 * 2 ** (attempt - 1))
                continue
            raise SpotifyUnavailable(f"{path} returned {resp.status_code}: {resp.text[:200]}")
        raise SpotifyUnavailable(f"{path}: exhausted retries")

    def _cached(self, endpoint: str, path: str, params: dict) -> dict:
        return cached_get(endpoint, params, lambda: self._get(path, params))

    # -- endpoints ----------------------------------------------------------

    def search_tracks(self, query: str, limit: int = 10, offset: int = 0) -> list[dict]:
        limit = max(1, min(limit, SEARCH_MAX_LIMIT))
        params = {"q": query, "type": "track", "limit": limit, "market": self.market}
        if offset:
            params["offset"] = offset
        data = self._cached("search_tracks", "/search", params)
        return data.get("tracks", {}).get("items", []) or []

    def search_tracks_paged(self, query: str, wanted: int) -> list[dict]:
        """Collect up to `wanted` tracks by paging through 10-item search results."""
        items: list[dict] = []
        offset = 0
        while len(items) < wanted:
            page = self.search_tracks(query, limit=SEARCH_MAX_LIMIT, offset=offset)
            items.extend(page)
            if len(page) < SEARCH_MAX_LIMIT:
                break
            offset += SEARCH_MAX_LIMIT
        return items[:wanted]

    def search_artist(self, name: str) -> dict | None:
        params = {"q": name, "type": "artist", "limit": 1, "market": self.market}
        data = self._cached("search_artist", "/search", params)
        items = data.get("artists", {}).get("items", []) or []
        return items[0] if items else None

    def artist_tracks(self, artist_name: str, limit: int = 10) -> list[dict]:
        """Tracks by an artist via search (top-tracks endpoint is 403 for new apps)."""
        return self.search_tracks_paged(f'artist:"{artist_name}"', wanted=limit)

    def artist_top_tracks(self, artist_id: str) -> list[dict]:
        """Legacy endpoint kept for apps that still have access; 403 -> SpotifyForbidden."""
        params = {"market": self.market}
        data = self._cached("artist_top_tracks", f"/artists/{artist_id}/top-tracks", params)
        return data.get("tracks", []) or []
