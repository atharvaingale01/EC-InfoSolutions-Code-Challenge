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
import re
from collections import defaultdict
from datetime import date

from django.conf import settings

from .spotify import get_client
from .spotify.exceptions import SpotifyForbidden, SpotifyNotFound
from .spotify.moods import mood_terms

logger = logging.getLogger(__name__)

# Spotify caps each search at 10 results, so wider pools are paged (offset).
GENRE_SEARCH_LIMIT = 20  # two pages per favourite genre
ARTIST_TOP_LIMIT = 10  # one page per favourite artist
MOOD_SEARCH_LIMIT = 10  # one page per mood term
SIMILAR_ARTISTS = 3  # discovery expansion when the pool is thin
SIMILAR_TRACK_LIMIT = 10
MAX_PER_ARTIST = 3  # diversity cap for artists the user did not ask for
MAX_PER_FAVOURITE_ARTIST = 5  # the user asked for these; let more through
FALLBACK_GENRE = "pop"

SEED_HIT_WEIGHT = 10.0
ARTIST_SEED_BONUS = 5.0  # ordering is by tier first (see rank()); this only orders within a tier
POSITION_WEIGHT = 0.3  # per rank step from the top of a search result list
RELEVANCE_SPAN = 10  # positions beyond this add nothing
# Moods describe the present, so their searches are limited to recent releases.
MOOD_RECENT_YEARS = 15


_TITLE_NOISE = re.compile(
    r"\s*(\(|\[|-\s)"
    r"(from|feat\.?|featuring|remaster(ed)?|radio edit|single version|album version|"
    r"slowed|sped up|live|acoustic|original mix|bonus track|deluxe|\d{4} remaster)"
    r"[^)\]]*(\)|\])?\s*$",
    re.IGNORECASE,
)


def song_key(track: dict) -> tuple[str, str]:
    """
    Same song, different Spotify id (film version, album version, single,
    remaster) collapses to one key: normalised title + primary artist.
    """
    title = track.get("name", "").casefold()
    # strip one or two trailing qualifiers such as ' (From "Film")' or ' - 2004 Remaster'
    for _ in range(2):
        title = _TITLE_NOISE.sub("", title).strip()
    title = re.sub(r"[^\w\s]", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    primary = (track.get("artists") or [""])[0].casefold()
    return title, primary


def normalise_track(item: dict, seed: str, position: int = 0, query: str = "") -> dict | None:
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
        "query": query or seed,
        "score": 0.0,
    }


def collect_candidates(user, client, limit: int | None = None) -> tuple[list[dict], dict]:
    """Return (raw candidate tracks tagged by seed, seed_params snapshot)."""
    genres = list(user.favorite_genres or [])
    artists = list(user.favorite_artists or [])
    moods = list(user.moods or [])

    candidates: list[dict] = []
    resolved_artists: dict[str, str | None] = {}

    def search(query, limit, seed):
        for position, item in enumerate(client.search_tracks_paged(query, wanted=limit)):
            if track := normalise_track(item, seed, position, query):
                candidates.append(track)

    for genre in genres:
        search(f'genre:"{genre}"', GENRE_SEARCH_LIMIT, f"genre:{genre}")

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
        query = f'artist:"{canonical}"'
        try:
            items = client.artist_tracks(canonical, limit=ARTIST_TOP_LIMIT)
        except (SpotifyNotFound, SpotifyForbidden) as exc:
            logger.warning("Artist tracks unavailable for %r: %s", canonical, exc)
            items = []
        for position, item in enumerate(items):
            if track := normalise_track(item, f"artist:{artist_name}", position, query):
                candidates.append(track)

    year_window = f"year:{date.today().year - MOOD_RECENT_YEARS}-{date.today().year}"
    for mood in moods:
        for term in mood_terms(mood, client.market):
            search(f'genre:"{term}" {year_window}', MOOD_SEARCH_LIMIT, f"mood:{mood}")

    # Discovery expansion: when the pool is thin (few seeds, or Spotify's 10-per-search
    # cap), pull tracks from the artists that surfaced most often but were not asked for.
    similar: list[str] = []
    wanted_pool = 2 * (limit or settings.RECS_DEFAULT_LIMIT)
    if candidates and len(candidates) < wanted_pool:
        favourites = {a.lower() for a in artists}
        counts = defaultdict(int)
        for track in candidates:
            if track["artists"] and track["artists"][0].lower() not in favourites:
                counts[track["artists"][0]] += 1
        similar = [name for name, _ in sorted(counts.items(), key=lambda kv: -kv[1])][
            :SIMILAR_ARTISTS
        ]
        for name in similar:
            try:
                items = client.artist_tracks(name, limit=SIMILAR_TRACK_LIMIT)
            except (SpotifyNotFound, SpotifyForbidden):
                items = []
            query = f'artist:"{name}"'
            for position, item in enumerate(items):
                if track := normalise_track(item, f"similar:{name}", position, query):
                    candidates.append(track)

    used_fallback = False
    if len(candidates) < (limit or settings.RECS_DEFAULT_LIMIT):
        used_fallback = True
        search(f'genre:"{FALLBACK_GENRE}"', GENRE_SEARCH_LIMIT, f"fallback:{FALLBACK_GENRE}")

    seed_params = {
        "genres": genres,
        "artists": artists,
        "artist_ids": resolved_artists,
        "moods": moods,
        "similar_artists": similar,
        "used_fallback": used_fallback,
        "market": client.market,
        "source": getattr(client, "source", "search_v1"),
    }
    return candidates, seed_params


def rank(candidates: list[dict], limit: int) -> list[dict]:
    """
    De-duplicate by track id, score, cap per artist, sort, truncate.

    A track earns one "hit" per *distinct search query* that returned it. Two
    seeds that expand to the same query (e.g. genre "hip-hop" and the
    "energetic" mood) are one piece of evidence, not two; the seed label still
    lists both so the reason is visible in the API response.
    """
    merged: dict[str, dict] = {}
    seed_labels: dict[str, set[str]] = defaultdict(set)
    query_hits: dict[str, set[str]] = defaultdict(set)
    best_position: dict[str, int] = {}
    artist_seeded: set[str] = set()

    for track in candidates:
        tid = track["spotify_id"]
        seed_labels[tid].add(track["seed"])
        query_hits[tid].add(track.get("query") or track["seed"])
        position = track.get("position", 0)
        best_position[tid] = min(best_position.get(tid, position), position)
        if track["seed"].startswith("artist:"):
            artist_seeded.add(tid)
        if tid not in merged:
            merged[tid] = dict(track)

    # Ordinal tiers, then score within a tier. A named artist is the clearest
    # intent, so their tracks lead regardless of how many overlapping genre and
    # mood searches an unrelated catalogue track happened to match.
    def priority(tid):
        labels = seed_labels[tid]
        if tid in artist_seeded:
            return 0
        if any(s.startswith(("genre:", "mood:")) for s in labels):
            return 1
        if any(s.startswith("similar:") for s in labels):
            return 2
        return 3  # fallback

    for tid, track in merged.items():
        hits = len(query_hits[tid])
        relevance = max(0, RELEVANCE_SPAN - best_position[tid]) * POSITION_WEIGHT
        score = hits * SEED_HIT_WEIGHT + track["popularity"] / 10.0 + relevance
        if tid in artist_seeded:
            score += ARTIST_SEED_BONUS
        track["score"] = round(score, 2)
        track["seed"] = ", ".join(sorted(seed_labels[tid]))
        track.pop("position", None)
        track.pop("query", None)

    ordered = sorted(
        merged.values(), key=lambda t: (priority(t["spotify_id"]), -t["score"], t["name"])
    )

    per_artist: dict[str, int] = defaultdict(int)
    seen_songs: set[tuple[str, str]] = set()
    result: list[dict] = []
    for track in ordered:
        key = song_key(track)
        if key in seen_songs:
            continue  # another release of a song we already have
        primary = track["artists"][0] if track["artists"] else ""
        cap = MAX_PER_FAVOURITE_ARTIST if track["spotify_id"] in artist_seeded else MAX_PER_ARTIST
        if per_artist[primary] >= cap:
            continue
        seen_songs.add(key)
        per_artist[primary] += 1
        result.append(track)
        if len(result) >= limit:
            break
    return result


def build_recommendations(user, client=None, limit: int | None = None):
    """Return (ranked tracks, seed_params). seed_params["source"] names the client used."""
    client = client or get_client()
    limit = limit or settings.RECS_DEFAULT_LIMIT
    candidates, seed_params = collect_candidates(user, client, limit)
    tracks = rank(candidates, limit)
    seed_params["candidates"] = len(candidates)
    return tracks, seed_params
