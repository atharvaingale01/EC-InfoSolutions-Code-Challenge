class SpotifyError(Exception):
    """Base class for Spotify client failures."""


class SpotifyAuthError(SpotifyError):
    """Client credentials rejected or missing."""


class SpotifyRateLimited(SpotifyError):
    def __init__(self, retry_after: int = 1):
        super().__init__(f"Spotify rate limit hit; retry after {retry_after}s")
        self.retry_after = retry_after


class SpotifyUnavailable(SpotifyError):
    """5xx or network failure after retries."""


class SpotifyForbidden(SpotifyError):
    """403 — endpoint not available to this app (development-mode / Premium restrictions)."""


class SpotifyNotFound(SpotifyError):
    """404 — endpoint deprecated for this app or resource missing."""
