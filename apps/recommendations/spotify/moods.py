"""
Static mood -> Spotify search-term mapping.

Spotify's recommendation seeds/audio-features endpoints are deprecated for new
apps, so moods are translated into genre-flavoured track searches instead.

The mapping is market-aware: the same mood should mean Bollywood and Sufi in
India but pop and dance elsewhere. `MOOD_MAP` (the default) also defines the
mood vocabulary that profile validation accepts; market maps must use the same
keys.
"""

MOOD_MAP: dict[str, list[str]] = {
    "happy": ["pop", "dance"],
    "sad": ["acoustic", "singer-songwriter"],
    "chill": ["chill", "ambient", "lo-fi"],
    "energetic": ["edm", "rock", "hip-hop"],
    "focus": ["classical", "instrumental"],
    "romantic": ["r-n-b", "soul"],
    "party": ["dance", "reggaeton"],
    "workout": ["hip-hop", "electronic"],
}

MOOD_MAP_BY_MARKET: dict[str, dict[str, list[str]]] = {
    "IN": {
        "happy": ["indian pop", "bollywood"],
        "sad": ["ghazal", "sufi"],
        "chill": ["indian indie", "sufi"],
        "energetic": ["bhangra", "punjabi"],
        "focus": ["hindustani classical", "carnatic"],
        "romantic": ["bollywood", "filmi"],
        "party": ["bhangra", "punjabi pop"],
        "workout": ["punjabi", "desi pop"],
    },
}

for _market, _mapping in MOOD_MAP_BY_MARKET.items():
    assert set(_mapping) == set(MOOD_MAP), f"mood map for {_market} must cover the same moods"


def mood_terms(mood: str, market: str | None = None) -> list[str]:
    """Genre terms to search for a mood, localised to the Spotify market when known."""
    mapping = MOOD_MAP_BY_MARKET.get((market or "").upper(), MOOD_MAP)
    return mapping.get(mood, MOOD_MAP.get(mood, []))
