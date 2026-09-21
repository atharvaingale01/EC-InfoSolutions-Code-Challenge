from django.conf import settings


def get_client():
    """Return the configured Spotify client (real or SPOTIFY_MOCK fixture-backed)."""
    if settings.SPOTIFY_MOCK:
        from .mock import MockSpotifyClient

        return MockSpotifyClient()
    from .client import SpotifyClient

    return SpotifyClient()
