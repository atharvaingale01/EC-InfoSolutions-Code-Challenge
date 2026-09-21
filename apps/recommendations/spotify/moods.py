"""
Static mood -> Spotify search-term mapping.

Spotify's recommendation seeds/audio-features endpoints are deprecated for new
apps, so moods are translated into genre-flavoured track searches instead.
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
