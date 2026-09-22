import pytest
import responses
from django.conf import settings

from apps.recommendations.models import SpotifyCache
from apps.recommendations.spotify.client import TOKEN_CACHE_KEY, SpotifyClient
from apps.recommendations.spotify.exceptions import (
    SpotifyAuthError,
    SpotifyForbidden,
    SpotifyNotFound,
    SpotifyRateLimited,
    SpotifyUnavailable,
)

TOKEN_URL = settings.SPOTIFY_TOKEN_URL
SEARCH_URL = f"{settings.SPOTIFY_API_BASE}/search"


def mock_token(expires_in=3600):
    responses.add(
        responses.POST,
        TOKEN_URL,
        json={"access_token": "tok", "expires_in": expires_in},
        status=200,
    )


def search_payload(n=2):
    return {
        "tracks": {"items": [{"id": f"t{i}", "name": f"T{i}", "artists": []} for i in range(n)]}
    }


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("apps.recommendations.spotify.client.time.sleep", lambda *_: None)


@pytest.mark.django_db
@responses.activate
def test_token_is_cached():
    mock_token()
    client = SpotifyClient()
    assert client.get_token() == "tok"
    assert client.get_token() == "tok"
    assert len(responses.calls) == 1
    from django.core.cache import cache

    assert cache.get(TOKEN_CACHE_KEY) == "tok"


@pytest.mark.django_db
@responses.activate
def test_missing_credentials_raise(settings):
    settings.SPOTIFY_CLIENT_ID = ""
    with pytest.raises(SpotifyAuthError):
        SpotifyClient().get_token()


@pytest.mark.django_db
@responses.activate
def test_search_persists_to_db_cache_and_skips_network_on_repeat():
    mock_token()
    responses.add(responses.GET, SEARCH_URL, json=search_payload(), status=200)
    client = SpotifyClient()

    first = client.search_tracks('genre:"rock"', limit=5)
    second = client.search_tracks('genre:"rock"', limit=5)

    assert [t["id"] for t in first] == ["t0", "t1"]
    assert first == second
    assert SpotifyCache.objects.filter(endpoint="search_tracks").count() == 1
    # one token call + exactly one search call
    assert sum(1 for c in responses.calls if c.request.method == "GET") == 1


@pytest.mark.django_db
@responses.activate
def test_expired_db_cache_refetches():
    from datetime import timedelta

    from django.utils import timezone

    mock_token()
    responses.add(responses.GET, SEARCH_URL, json=search_payload(1), status=200)
    responses.add(responses.GET, SEARCH_URL, json=search_payload(3), status=200)
    client = SpotifyClient()

    assert len(client.search_tracks("q")) == 1
    SpotifyCache.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    assert len(client.search_tracks("q")) == 3


@pytest.mark.django_db
@responses.activate
def test_429_is_retried_honouring_retry_after():
    mock_token()
    responses.add(responses.GET, SEARCH_URL, status=429, headers={"Retry-After": "2"})
    responses.add(responses.GET, SEARCH_URL, json=search_payload(1), status=200)
    assert len(SpotifyClient().search_tracks("q")) == 1
    assert sum(1 for c in responses.calls if c.request.method == "GET") == 2


@pytest.mark.django_db
@responses.activate
def test_persistent_429_raises_rate_limited():
    mock_token()
    for _ in range(3):
        responses.add(responses.GET, SEARCH_URL, status=429, headers={"Retry-After": "1"})
    with pytest.raises(SpotifyRateLimited):
        SpotifyClient().search_tracks("q")


@pytest.mark.django_db
@responses.activate
def test_5xx_retries_then_raises_unavailable():
    mock_token()
    for _ in range(3):
        responses.add(responses.GET, SEARCH_URL, status=503)
    with pytest.raises(SpotifyUnavailable):
        SpotifyClient().search_tracks("q")


@pytest.mark.django_db
@responses.activate
def test_404_raises_not_found():
    mock_token()
    responses.add(responses.GET, f"{settings.SPOTIFY_API_BASE}/artists/x/top-tracks", status=404)
    with pytest.raises(SpotifyNotFound):
        SpotifyClient().artist_top_tracks("x")


@pytest.mark.django_db
@responses.activate
def test_401_refreshes_token_once():
    mock_token()
    responses.add(responses.GET, SEARCH_URL, status=401)
    responses.add(responses.POST, TOKEN_URL, json={"access_token": "tok2", "expires_in": 60})
    responses.add(responses.GET, SEARCH_URL, json=search_payload(1), status=200)
    assert len(SpotifyClient().search_tracks("q")) == 1
    assert responses.calls[-1].request.headers["Authorization"] == "Bearer tok2"


@pytest.mark.django_db
@responses.activate
def test_403_fails_fast_as_forbidden():
    mock_token()
    responses.add(responses.GET, SEARCH_URL, status=403)
    with pytest.raises(SpotifyForbidden, match="SPOTIFY_MOCK"):
        SpotifyClient().search_tracks("q")
    assert sum(1 for c in responses.calls if c.request.method == "GET") == 1  # no retries


@pytest.mark.django_db
@responses.activate
def test_artist_tracks_uses_filtered_search():
    mock_token()
    responses.add(responses.GET, SEARCH_URL, json=search_payload(2), status=200)
    assert len(SpotifyClient().artist_tracks("Radiohead", limit=5)) == 2
    sent = responses.calls[-1].request.url
    assert "artist%3A%22Radiohead%22" in sent and "type=track" in sent


@pytest.mark.django_db
@responses.activate
def test_search_limit_is_clamped_to_spotify_maximum():
    mock_token()
    responses.add(responses.GET, SEARCH_URL, json=search_payload(1), status=200)
    SpotifyClient().search_tracks("q", limit=50)
    assert "limit=10" in responses.calls[-1].request.url


@pytest.mark.django_db
@responses.activate
def test_paged_search_uses_offset_and_stops_on_short_page():
    mock_token()
    responses.add(responses.GET, SEARCH_URL, json=search_payload(10), status=200)
    responses.add(responses.GET, SEARCH_URL, json=search_payload(4), status=200)
    items = SpotifyClient().search_tracks_paged("q", wanted=30)
    assert len(items) == 14
    gets = [c.request.url for c in responses.calls if c.request.method == "GET"]
    assert len(gets) == 2 and "offset=10" in gets[1] and "offset" not in gets[0]


@pytest.mark.django_db
def test_cache_write_race_is_tolerated(monkeypatch):
    from django.db import IntegrityError

    from apps.recommendations.spotify import cache as cache_mod

    def collide(*a, **k):
        raise IntegrityError("duplicate key")

    monkeypatch.setattr(cache_mod.SpotifyCache.objects, "update_or_create", collide)
    assert cache_mod.cached_get("search_tracks", {"q": "x"}, lambda: {"ok": 1}) == {"ok": 1}


@pytest.mark.django_db
@responses.activate
def test_network_errors_are_retried_then_raised_as_unavailable():
    import requests as rq

    mock_token()
    for _ in range(3):
        responses.add(responses.GET, SEARCH_URL, body=rq.exceptions.ConnectTimeout("boom"))
    with pytest.raises(SpotifyUnavailable, match="ConnectTimeout"):
        SpotifyClient().search_tracks("q")
    assert sum(1 for c in responses.calls if c.request.method == "GET") == 3


@pytest.mark.django_db
@responses.activate
def test_long_retry_after_is_raised_immediately_not_slept():
    mock_token()
    responses.add(responses.GET, SEARCH_URL, status=429, headers={"Retry-After": "60"})
    with pytest.raises(SpotifyRateLimited) as info:
        SpotifyClient().search_tracks("q")
    assert info.value.retry_after == 60
    assert sum(1 for c in responses.calls if c.request.method == "GET") == 1


@pytest.mark.django_db
@responses.activate
def test_garbage_retry_after_header_defaults_to_one_second():
    mock_token()
    responses.add(responses.GET, SEARCH_URL, status=429, headers={"Retry-After": "soon"})
    responses.add(responses.GET, SEARCH_URL, json=search_payload(1), status=200)
    assert len(SpotifyClient().search_tracks("q")) == 1


@pytest.mark.django_db
@responses.activate
def test_second_401_is_an_auth_error_not_retried_forever():
    mock_token()
    responses.add(responses.GET, SEARCH_URL, status=401)
    responses.add(responses.POST, TOKEN_URL, json={"access_token": "tok2", "expires_in": 60})
    responses.add(responses.GET, SEARCH_URL, status=401)
    with pytest.raises(SpotifyAuthError):
        SpotifyClient().search_tracks("q")
