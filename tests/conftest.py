import pytest
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User

PASSWORD = "Password123!"


# ---------------------------------------------------------------------------
# Fake Spotify client (installed for every test so nothing hits the network)
# ---------------------------------------------------------------------------
def make_track(track_id, name, artist, popularity=50, album="Album"):
    return {
        "id": track_id,
        "name": name,
        "artists": [{"name": artist}],
        "album": {"name": album},
        "preview_url": None,
        "external_urls": {"spotify": f"https://open.spotify.com/track/{track_id}"},
        "popularity": popularity,
        "duration_ms": 200_000,
    }


class FakeSpotifyClient:
    """Deterministic stand-in for SpotifyClient used by the engine."""

    market = "US"
    source = "search_v1"

    def __init__(self):
        self.calls: list[tuple] = []
        self.search_results: dict[str, list[dict]] = {}
        self.artists: dict[str, dict | None] = {}
        self.top_tracks: dict[str, list[dict]] = {}
        self.raise_on_search: Exception | None = None

    def search_tracks(self, query, limit=10):
        self.calls.append(("search_tracks", query, limit))
        if self.raise_on_search:
            raise self.raise_on_search
        if query in self.search_results:
            return self.search_results[query][:limit]
        if query.startswith('artist:"'):
            name = query[len('artist:"') :].rstrip('"')
            return self.artist_top_tracks(f"artist-{name.lower().replace(' ', '-')}")[:limit]
        term = query.replace('genre:"', "").rstrip('"')
        return [
            make_track(f"{term}-{i}", f"{term.title()} Song {i}", f"{term.title()} Artist {i}")
            for i in range(3)
        ]

    def search_artist(self, name):
        self.calls.append(("search_artist", name))
        if name in self.artists:
            return self.artists[name]
        return {"id": f"artist-{name.lower().replace(' ', '-')}", "name": name}

    def artist_tracks(self, artist_name, limit=10):
        return self.search_tracks(f'artist:"{artist_name}"', limit=limit)

    def artist_top_tracks(self, artist_id):
        self.calls.append(("artist_top_tracks", artist_id))
        if artist_id in self.top_tracks:
            return self.top_tracks[artist_id]
        label = artist_id.removeprefix("artist-").replace("-", " ").title()
        return [make_track(f"{artist_id}-top-{i}", f"{label} Hit {i}", label, 80) for i in range(3)]


@pytest.fixture(autouse=True)
def fake_spotify(monkeypatch):
    client = FakeSpotifyClient()
    monkeypatch.setattr("apps.recommendations.engine.get_client", lambda: client)
    return client


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


# ---------------------------------------------------------------------------
# Users / clients
# ---------------------------------------------------------------------------
@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="alice@example.com",
        password=PASSWORD,
        name="Alice",
        favorite_genres=["rock", "indie"],
        favorite_artists=["Radiohead"],
        moods=["chill"],
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(email="bob@example.com", password=PASSWORD, name="Bob")


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        email="admin@example.com", password=PASSWORD, name="Admin", is_staff=True
    )


def bearer_client(user) -> APIClient:
    client = APIClient()
    access = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


@pytest.fixture
def auth_client(user):
    return bearer_client(user)


@pytest.fixture
def other_client(other_user):
    return bearer_client(other_user)


@pytest.fixture
def staff_client(staff_user):
    return bearer_client(staff_user)
