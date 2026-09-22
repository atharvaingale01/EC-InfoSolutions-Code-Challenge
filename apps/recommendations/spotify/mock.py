"""
Offline stand-in for SpotifyClient, enabled with SPOTIFY_MOCK=1.

Since February 2026 every development-mode Spotify app requires its owner to
hold an active Premium subscription; without one the dashboard shows the app
as blocked and API calls return 403. This client serves the same response
shapes from a local fixture so the whole pipeline (Celery, persistent cache,
Redis, analytics) can be exercised end-to-end without credentials or network.
"""

import logging

from django.conf import settings

from .cache import cached_get
from .mock_data import ARTIST_TOP_TRACKS, TRACKS_BY_GENRE

logger = logging.getLogger(__name__)

SOURCE = "mock_v1"


class MockSpotifyClient:
    source = SOURCE

    def __init__(self):
        self.market = settings.SPOTIFY_MARKET
        logger.info("SPOTIFY_MOCK=1: serving fixture data instead of the Spotify Web API")

    # Same call signatures as SpotifyClient. Responses still flow through the
    # persistent cache so SpotifyCache behaviour is identical in mock mode.

    def search_tracks(self, query: str, limit: int = 10, offset: int = 0) -> list[dict]:
        params = {"q": query, "type": "track", "limit": limit, "market": self.market, "mock": True}
        if offset:
            params["offset"] = offset
        data = cached_get("search_tracks", params, lambda: self._search(query, limit, offset))
        return data.get("tracks", {}).get("items", []) or []

    def search_tracks_paged(self, query: str, wanted: int) -> list[dict]:
        items: list[dict] = []
        offset = 0
        while len(items) < wanted:
            page = self.search_tracks(query, limit=10, offset=offset)
            items.extend(page)
            if len(page) < 10:
                break
            offset += 10
        return items[:wanted]

    def search_artist(self, name: str) -> dict | None:
        params = {"q": name, "type": "artist", "limit": 1, "market": self.market, "mock": True}
        data = cached_get("search_artist", params, lambda: self._artist(name))
        items = data.get("artists", {}).get("items", []) or []
        return items[0] if items else None

    def artist_tracks(self, artist_name: str, limit: int = 10) -> list[dict]:
        return self.search_tracks_paged(f'artist:"{artist_name}"', wanted=limit)

    def artist_top_tracks(self, artist_id: str) -> list[dict]:
        params = {"market": self.market, "mock": True}
        data = cached_get(
            "artist_top_tracks", {**params, "artist_id": artist_id}, lambda: self._top(artist_id)
        )
        return data.get("tracks", []) or []

    # -- fixture lookups ----------------------------------------------------

    @staticmethod
    def _search(query: str, limit: int, offset: int = 0) -> dict:
        if query.startswith('artist:"'):
            name = query[len('artist:"') :].rstrip('"').strip().lower()
            items = next((t for k, t in ARTIST_TOP_TRACKS.items() if k.lower() == name), [])
            return {"tracks": {"items": items[offset : offset + limit]}}
        term = query.replace('genre:"', "").rstrip('"').strip().lower()
        items = TRACKS_BY_GENRE.get(term)
        if items is None:
            # Free-text search: match on track or artist name.
            items = [
                t
                for tracks in TRACKS_BY_GENRE.values()
                for t in tracks
                if term in t["name"].lower() or term in t["artists"][0]["name"].lower()
            ]
        return {"tracks": {"items": items[offset : offset + limit]}}

    @staticmethod
    def _artist(name: str) -> dict:
        for known in ARTIST_TOP_TRACKS:
            if known.lower() == name.strip().lower():
                return {"artists": {"items": [{"id": _artist_id(known), "name": known}]}}
        return {"artists": {"items": []}}

    @staticmethod
    def _top(artist_id: str) -> dict:
        for known, tracks in ARTIST_TOP_TRACKS.items():
            if _artist_id(known) == artist_id:
                return {"tracks": tracks}
        return {"tracks": []}


def _artist_id(name: str) -> str:
    return "mock-" + name.lower().replace(" ", "-").replace(".", "")
