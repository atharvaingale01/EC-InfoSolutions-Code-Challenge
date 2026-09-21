from datetime import timedelta

import pytest
from django.utils import timezone

from apps.activity.models import UserActivity
from apps.recommendations.models import Recommendation


def log(user, action, track_id="t1", artist="Radiohead", days_ago=0):
    row = UserActivity.objects.create(
        user=user,
        track_id=track_id,
        track_name=f"Track {track_id}",
        artist_name=artist,
        action=action,
    )
    if days_ago:
        UserActivity.objects.filter(pk=row.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago)
        )
    return row


@pytest.mark.django_db
class TestSummary:
    def test_empty(self, auth_client):
        resp = auth_client.get("/analytics/summary/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["activity"]["total"] == 0
        assert body["activity"]["like_rate"] == 0.0
        assert body["users"]["total"] == 1

    def test_counts_and_rates(self, auth_client, user, other_user):
        log(user, "play")
        log(user, "play", "t2")
        log(user, "like")
        log(other_user, "skip", days_ago=10)
        Recommendation.objects.create(user=user, status="ready", tracks=[{"spotify_id": "t1"}] * 4)
        Recommendation.objects.create(user=user, status="failed")

        body = auth_client.get("/analytics/summary/").json()
        assert body["activity"]["by_action"] == {"play": 2, "like": 1, "skip": 1}
        assert body["activity"]["like_rate"] == 0.5
        assert body["users"]["active_7d"] == 1  # other_user's activity is 10 days old
        assert body["recommendations"] == {
            "total_generated": 2,
            "ready": 1,
            "failed": 1,
            "pending": 0,
            "avg_tracks": 4.0,
        }

    def test_requires_auth(self, api_client):
        assert api_client.get("/analytics/summary/").status_code == 401


@pytest.mark.django_db
class TestTrends:
    def test_window_and_ranking(self, auth_client, user, other_user):
        log(user, "play", "a", "Artist A")
        log(user, "like", "a", "Artist A")
        log(other_user, "play", "b", "Artist B")
        log(other_user, "play", "old", "Old Artist", days_ago=30)

        body = auth_client.get("/analytics/trends/?days=7&limit=5").json()
        assert body["window_days"] == 7
        assert [a["artist_name"] for a in body["top_artists"]] == ["Artist A", "Artist B"]
        assert body["top_artists"][0] == {
            "artist_name": "Artist A",
            "interactions": 2,
            "likes": 1,
            "plays": 1,
        }
        assert body["top_tracks"][0]["track_id"] == "a"
        assert "Old Artist" not in [a["artist_name"] for a in body["top_artists"]]

        body = auth_client.get("/analytics/trends/?days=60").json()
        assert "Old Artist" in [a["artist_name"] for a in body["top_artists"]]

    def test_top_genres_from_preferences(self, auth_client, user, other_user):
        other_user.favorite_genres = ["rock"]
        other_user.save()
        body = auth_client.get("/analytics/trends/").json()
        assert body["top_genres"][0] == {"genre": "rock", "users": 2}

    def test_other_authenticated_user_allowed(self, other_client):
        assert other_client.get("/analytics/trends/").status_code == 200


@pytest.mark.django_db
class TestUserSummary:
    def test_engagement_rate(self, auth_client, user):
        Recommendation.objects.create(
            user=user,
            status="ready",
            tracks=[
                {"spotify_id": "r1"},
                {"spotify_id": "r2"},
                {"spotify_id": "r3"},
                {"spotify_id": "r4"},
            ],
            completed_at=timezone.now(),
        )
        log(user, "play", "r1")
        log(user, "like", "r1")
        log(user, "play", "r2")
        log(user, "skip", "unrelated")

        body = auth_client.get(f"/analytics/user/{user.pk}/").json()
        assert body["activity"]["by_action"] == {"play": 2, "like": 1, "skip": 1}
        assert body["recommendations"]["tracks_recommended"] == 4
        assert body["engagement_rate"] == 0.5  # r1, r2 of 4 recommended
        assert body["top_artists"][0]["artist_name"] == "Radiohead"
        assert body["last_active_at"] is not None

    def test_ownership(self, other_client, staff_client, user):
        assert other_client.get(f"/analytics/user/{user.pk}/").status_code == 403
        assert staff_client.get(f"/analytics/user/{user.pk}/").status_code == 200
