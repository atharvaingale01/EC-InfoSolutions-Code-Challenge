import pytest

from apps.recommendations import engine
from apps.recommendations.spotify.moods import MOOD_MAP
from apps.users.models import User

from .conftest import make_track


def test_rank_dedupes_and_boosts_tracks_found_by_distinct_queries():
    shared = engine.normalise_track(
        make_track("x", "Shared", "A", popularity=10), "genre:rock", query='genre:"rock"'
    )
    shared2 = dict(shared, seed="mood:chill", query='genre:"chill"')
    solo = engine.normalise_track(
        make_track("y", "Solo", "B", popularity=90), "genre:rock", query='genre:"rock"'
    )

    ranked = engine.rank([shared, shared2, solo], limit=10)

    assert [t["spotify_id"] for t in ranked] == ["x", "y"]
    assert ranked[0]["seed"] == "genre:rock, mood:chill"
    assert ranked[0]["score"] > ranked[1]["score"]
    assert "query" not in ranked[0] and "position" not in ranked[0]


def test_same_query_from_two_seeds_counts_once():
    """genre 'hip-hop' + mood 'energetic' both search genre:"hip-hop" -> one hit, not two."""
    q = 'genre:"hip-hop"'
    a = engine.normalise_track(make_track("g", "G", "GA"), "genre:hip-hop", 0, q)
    b = dict(a, seed="mood:energetic")
    artist = engine.normalise_track(
        make_track("k", "K", "Kendrick"), "artist:Kendrick Lamar", 0, 'artist:"Kendrick Lamar"'
    )
    ranked = engine.rank([a, b, artist], limit=10)
    assert ranked[0]["spotify_id"] == "k"  # favourite artist outranks a double-labelled genre hit
    assert ranked[1]["seed"] == "genre:hip-hop, mood:energetic"


def test_rank_caps_tracks_per_artist():
    cands = [
        engine.normalise_track(make_track(f"a{i}", f"A{i}", "SameArtist", 90), "genre:x")
        for i in range(6)
    ] + [engine.normalise_track(make_track("b0", "B0", "Other", 10), "genre:x")]

    ranked = engine.rank(cands, limit=10)

    assert sum(1 for t in ranked if t["artists"] == ["SameArtist"]) == engine.MAX_PER_ARTIST
    assert any(t["spotify_id"] == "b0" for t in ranked)


def test_artist_seed_bonus_applied():
    genre_hit = engine.normalise_track(make_track("g", "G", "GA", 50), "genre:rock")
    artist_hit = engine.normalise_track(make_track("a", "A", "AA", 50), "artist:Radiohead")
    ranked = engine.rank([genre_hit, artist_hit], limit=10)
    assert ranked[0]["spotify_id"] == "a"


@pytest.mark.django_db
def test_collect_candidates_uses_all_seed_types(fake_spotify, user):
    tracks, params = engine.build_recommendations(user, client=fake_spotify)

    queries = [c[1] for c in fake_spotify.calls if c[0] == "search_tracks"]
    assert 'genre:"rock"' in queries and 'genre:"indie"' in queries
    for term in MOOD_MAP["chill"]:
        assert f'genre:"{term}"' in queries
    assert ("search_artist", "Radiohead") in fake_spotify.calls
    assert 'artist:"Radiohead"' in queries  # top-tracks endpoint is 403 for new apps

    assert params["genres"] == ["rock", "indie"]
    assert params["artist_ids"] == {"Radiohead": "artist-radiohead"}
    assert params["used_fallback"] is False
    assert 0 < len(tracks) <= 20
    assert all(t["score"] > 0 for t in tracks)


@pytest.mark.django_db
def test_empty_preferences_fall_back_to_pop(fake_spotify):
    user = User.objects.create_user(email="empty@example.com", password="Password123!", name="E")
    tracks, params = engine.build_recommendations(user, client=fake_spotify)
    assert params["used_fallback"] is True
    assert tracks and all(t["seed"].startswith("fallback:") for t in tracks)


@pytest.mark.django_db
def test_unknown_artist_is_skipped(fake_spotify, user):
    fake_spotify.artists["Radiohead"] = None
    _, params = engine.build_recommendations(user, client=fake_spotify)
    assert params["artist_ids"] == {"Radiohead": None}
    assert not any(
        c[1] == 'artist:"Radiohead"' for c in fake_spotify.calls if c[0] == "search_tracks"
    )


@pytest.mark.django_db
def test_forbidden_artist_tracks_do_not_fail_the_build(fake_spotify, user, monkeypatch):
    from apps.recommendations.spotify.exceptions import SpotifyForbidden

    def boom(name, limit=10):
        raise SpotifyForbidden("403")

    monkeypatch.setattr(fake_spotify, "artist_tracks", boom)
    tracks, params = engine.build_recommendations(user, client=fake_spotify)
    assert tracks  # genre + mood seeds still produced results
    assert not any(t["seed"].startswith("artist:") for t in tracks)


def test_missing_popularity_uses_search_position():
    items = [make_track(f"p{i}", f"P{i}", f"A{i}") for i in range(3)]
    for item in items:
        del item["popularity"]
    cands = [engine.normalise_track(it, "genre:x", position=i) for i, it in enumerate(items)]
    ranked = engine.rank(cands, limit=10)
    assert [t["spotify_id"] for t in ranked] == ["p0", "p1", "p2"]
    assert ranked[0]["score"] > ranked[1]["score"] > ranked[2]["score"]
    assert "position" not in ranked[0]
