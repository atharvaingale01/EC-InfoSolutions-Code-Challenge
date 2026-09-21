import pytest

from apps.recommendations import engine
from apps.recommendations.models import Recommendation, SpotifyCache
from apps.recommendations.spotify import get_client
from apps.recommendations.spotify.client import SpotifyClient
from apps.recommendations.spotify.mock import MockSpotifyClient
from apps.recommendations.spotify.mock_data import ARTIST_TOP_TRACKS, TRACKS_BY_GENRE
from apps.recommendations.spotify.moods import MOOD_MAP


def test_factory_respects_setting(settings):
    settings.SPOTIFY_MOCK = False
    assert isinstance(get_client(), SpotifyClient)
    settings.SPOTIFY_MOCK = True
    assert isinstance(get_client(), MockSpotifyClient)


def test_every_mood_term_has_fixture_tracks():
    for mood, terms in MOOD_MAP.items():
        for term in terms:
            assert TRACKS_BY_GENRE.get(term), f"mood {mood!r} term {term!r} has no fixture tracks"


@pytest.mark.django_db
def test_mock_search_and_artist_flow(settings):
    settings.SPOTIFY_MOCK = True
    client = MockSpotifyClient()

    rock = client.search_tracks('genre:"rock"', limit=3)
    assert [t["id"] for t in rock] == [t["id"] for t in TRACKS_BY_GENRE["rock"][:3]]

    artist = client.search_artist("radiohead")
    assert artist["name"] == "Radiohead"
    assert client.artist_tracks("Radiohead") == ARTIST_TOP_TRACKS["Radiohead"]
    assert client.artist_top_tracks(artist["id"]) == ARTIST_TOP_TRACKS["Radiohead"]

    assert client.search_artist("Nobody Known") is None
    assert client.search_tracks('genre:"polka"') == []
    assert client.search_tracks("creep")[0]["name"] == "Creep"

    # Responses go through the same persistent cache as the real client.
    assert SpotifyCache.objects.filter(endpoint="search_tracks").count() == 4
    client.search_tracks('genre:"rock"', limit=3)
    assert SpotifyCache.objects.filter(endpoint="search_tracks").count() == 4


@pytest.mark.django_db
def test_mock_end_to_end_marks_source(settings, monkeypatch, user, auth_client):
    settings.SPOTIFY_MOCK = True
    monkeypatch.setattr(engine, "get_client", get_client)  # undo the FakeSpotifyClient patch

    resp = auth_client.post(f"/recommendations/{user.pk}/refresh/")
    assert resp.status_code == 202
    rec = Recommendation.objects.get(pk=resp.json()["recommendation_id"])
    assert rec.status == "ready"
    assert rec.source == "mock_v1"
    assert rec.seed_params["source"] == "mock_v1"
    names = {t["name"] for t in rec.tracks}
    assert "Creep" in names  # Radiohead is one of alice's favourite artists

    body = auth_client.get(f"/recommendations/{user.pk}/").json()
    assert body["source"] == "mock_v1"
    assert body["count"] == len(rec.tracks) > 0
