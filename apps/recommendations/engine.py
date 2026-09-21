"""
Turns a user's stated preferences into a ranked list of Spotify tracks.

Strategy (Spotify's /recommendations and artist top-tracks endpoints are
unavailable to newly created apps):
  * each favourite genre  -> track search  `genre:"<g>"`
  * each favourite artist -> artist search to confirm/canonicalise the name,
                             then track search `artist:"<name>"`
  * each mood             -> MOOD_MAP terms -> genre searches
Results are normalised, de-duplicated, scored and diversity-capped. Search
results no longer include `popularity`, so the position within each result
list (Spotify's relevance order) feeds the score as well.
"""

import logging
from collections import defaultdict

from django.conf import settings

from .spotify import get_client
from .spotify.exceptions import SpotifyForbidden, SpotifyNotFound
from .spotify.moods import MOOD_MAP

logger = logging.getLogger(__name__)

GENRE_SEARCH_LIMIT = 10
ARTIST_TOP_LIMIT = 10
MOOD_SEARCH_LIMIT = 5
MAX_PER_ARTIST = 3
FALLBACK_GENRE = "pop"

SEED_HIT_WEIGHT = 10.0
ARTIST_SEED_BONUS = 5.0
POSITION_WEIGHT = 0.3  # per rank step from the top of a search result list


def normalise_track(item: dict, seed: str, position: int = 0) -> dict | None:
    if not item or not item.get("id"):
        return None
    return {
        "spotify_id": item["id"],
        "name": item.get("name", ""),
        "artists": [a.get("name", "") for a in item.get("artists", []) if a.get("name")],
        "album": (item.get("album") or {}).get("name", ""),
        "preview_url": item.get("preview_url"),
        "external_url": (item.get("external_urls") or {}).get("spotify", ""),
        "popularity": int(item.get("popularity") or 0),
        "duration_ms": int(item.get("duration_ms") or 0),
        "seed": seed,
        "position": position,
        "score": 0.0,
    }


def collect_candidates(user, client) -> tuple[list[dict], dict]:
    """Return (raw candidate tracks tagged by seed, seed_params snapshot)."""
    genres = list(user.favorite_genres or [])
    artists = list(user.favorite_artists or [])
    moods = list(user.moods or [])

    candidates: list[dict] = []
    resolved_artists: dict[str, str | None] = {}

    def add(items, seed):
        for position, item in enumerate(items):
            if track := normalise_track(item, seed, position):
                candidates.append(track)

    for genre in genres:
        add(client.search_tracks(f'genre:"{genre}"', limit=GENRE_SEARCH_LIMIT), f"genre:{genre}")

    for artist_name in artists:
        try:
            artist = client.search_artist(artist_name)
        except (SpotifyNotFound, SpotifyForbidden):
            artist = None
        resolved_artists[artist_name] = artist["id"] if artist else None
        if not artist:
            logger.info("Artist %r not found on Spotify; skipping", artist_name)
            continue
        canonical = artist.get("name") or artist_name
        try:
            items = client.artist_tracks(canonical, limit=ARTIST_TOP_LIMIT)
        except (SpotifyNotFound, SpotifyForbidden) as exc:
            logger.warning("Artist tracks unavailable for %r: %s", canonical, exc)
            items = []
        add(items, f"artist:{artist_name}")

    for mood in moods:
        for term in MOOD_MAP.get(mood, []):
            add(client.search_tracks(f'genre:"{term}"', limit=MOOD_SEARCH_LIMIT), f"mood:{mood}")

    used_fallback = False
    if not candidates:
        used_fallback = True
        add(
            client.search_tracks(f'genre:"{FALLBACK_GENRE}"', limit=GENRE_SEARCH_LIMIT),
            f"fallback:{FALLBACK_GENRE}",
        )

    seed_params = {
        "genres": genres,
        "artists": artists,
        "artist_ids": resolved_artists,
        "moods": moods,
        "used_fallback": used_fallback,
        "market": client.market,
        "source": getattr(client, "source", "search_v1"),
    }
    return candidates, seed_params


def rank(candidates: list[dict], limit: int) -> list[dict]:
    """De-duplicate by track id, score, cap per artist, sort, truncate."""
    merged: dict[str, dict] = {}
    seed_hits: dict[str, set[str]] = defaultdict(set)
    best_position: dict[str, int] = {}
    artist_seeded: set[str] = set()

    for track in candidates:
        tid = track["spotify_id"]
        seed_hits[tid].add(track["seed"])
        best_position[tid] = min(best_position.get(tid, track["position"]), track["position"])
        if track["seed"].startswith("artist:"):
            artist_seeded.add(tid)
        if tid not in merged:
            merged[tid] = dict(track)

    for tid, track in merged.items():
        hits = len(seed_hits[tid])
        relevance = max(0, ARTIST_TOP_LIMIT - best_position[tid]) * POSITION_WEIGHT
        score = hits * SEED_HIT_WEIGHT + track["popularity"] / 10.0 + relevance
        if tid in artist_seeded:
            score += ARTIST_SEED_BONUS
        track["score"] = round(score, 2)
        track["seed"] = ", ".join(sorted(seed_hits[tid]))
        track.pop("position", None)

    ordered = sorted(merged.values(), key=lambda t: (-t["score"], t["name"]))

    per_artist: dict[str, int] = defaultdict(int)
    result: list[dict] = []
    for track in ordered:
        primary = track["artists"][0] if track["artists"] else ""
        if per_artist[primary] >= MAX_PER_ARTIST:
            continue
        per_artist[primary] += 1
        result.append(track)
        if len(result) >= limit:
            break
    return result


def build_recommendations(user, client=None, limit: int | None = None):
    """Return (ranked tracks, seed_params). seed_params["source"] names the client used."""
    client = client or get_client()
    limit = limit or settings.RECS_DEFAULT_LIMIT
    candidates, seed_params = collect_candidates(user, client)
    tracks = rank(candidates, limit)
    seed_params["candidates"] = len(candidates)
    return tracks, seed_params
