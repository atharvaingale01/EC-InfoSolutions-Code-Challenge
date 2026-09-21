"""
Minimal Spotify Web API client using the Client Credentials flow.

Only endpoints verified to work for a newly created (development-mode) app:
  * POST accounts.spotify.com/api/token
  * GET  /v1/search            (type=track with genre:/artist: filters, type=artist)

Notes from live testing (Sep 2026):
  * /v1/recommendations returns 404 and /v1/artists/{id}/top-tracks returns
    403 for new apps, so artist seeds are expanded with a track search
    filtered by artist name instead.
  * Track objects returned by search omit `popularity` and `preview_url`.

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

        resp = self.session.post(
            settings.SPOTIFY_TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret),
            timeout=10,
        )
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
        for attempt in range(1, MAX_ATTEMPTS + 1):
            resp = self.session.get(
                url, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=10
            )
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 401 and attempt == 1:
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
                retry_after = int(resp.headers.get("Retry-After", "1"))
                if attempt == MAX_ATTEMPTS or retry_after > 30:
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

    def search_tracks(self, query: str, limit: int = 10) -> list[dict]:
        params = {"q": query, "type": "track", "limit": limit, "market": self.market}
        data = self._cached("search_tracks", "/search", params)
        return data.get("tracks", {}).get("items", []) or []

    def search_artist(self, name: str) -> dict | None:
        params = {"q": name, "type": "artist", "limit": 1, "market": self.market}
        data = self._cached("search_artist", "/search", params)
        items = data.get("artists", {}).get("items", []) or []
        return items[0] if items else None

    def artist_tracks(self, artist_name: str, limit: int = 10) -> list[dict]:
        """Tracks by an artist via search (top-tracks endpoint is 403 for new apps)."""
        return self.search_tracks(f'artist:"{artist_name}"', limit=limit)

    def artist_top_tracks(self, artist_id: str) -> list[dict]:
        """Legacy endpoint kept for apps that still have access; 403 -> SpotifyForbidden."""
        params = {"market": self.market}
        data = self._cached("artist_top_tracks", f"/artists/{artist_id}/top-tracks", params)
        return data.get("tracks", []) or []
