from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.recommendations.models import Recommendation
from apps.recommendations.spotify.exceptions import SpotifyAuthError
from apps.recommendations.tasks import recs_cache_key, refresh_user_recommendations


@pytest.mark.django_db
class TestRefresh:
    def test_refresh_queues_and_completes(self, auth_client, user):
        resp = auth_client.post(f"/recommendations/{user.pk}/refresh/")
        assert resp.status_code == 202, resp.content
        body = resp.json()
        rec = Recommendation.objects.get(pk=body["recommendation_id"])
        assert rec.status == Recommendation.Status.READY  # eager celery in tests
        assert rec.task_id == body["task_id"]
        assert cache.get(recs_cache_key(user.pk))["recommendation_id"] == str(rec.pk)

    def test_recent_pending_is_reused(self, auth_client, user):
        pending = Recommendation.objects.create(user=user, task_id="abc")
        resp = auth_client.post(f"/recommendations/{user.pk}/refresh/")
        assert resp.status_code == 202
        assert resp.json()["recommendation_id"] == str(pending.pk)
        assert Recommendation.objects.filter(user=user).count() == 1

    def test_stale_pending_is_not_reused(self, auth_client, user):
        stale = Recommendation.objects.create(user=user)
        Recommendation.objects.filter(pk=stale.pk).update(
            created_at=timezone.now() - timedelta(minutes=10)
        )
        resp = auth_client.post(f"/recommendations/{user.pk}/refresh/")
        assert resp.json()["recommendation_id"] != str(stale.pk)

    def test_other_user_forbidden(self, other_client, user):
        assert other_client.post(f"/recommendations/{user.pk}/refresh/").status_code == 403

    def test_staff_allowed(self, staff_client, user):
        assert staff_client.post(f"/recommendations/{user.pk}/refresh/").status_code == 202

    def test_anonymous_401(self, api_client, user):
        assert api_client.post(f"/recommendations/{user.pk}/refresh/").status_code == 401


@pytest.mark.django_db
class TestRetrieve:
    def test_no_recommendations_404(self, auth_client, user):
        resp = auth_client.get(f"/recommendations/{user.pk}/")
        assert resp.status_code == 404
        assert "refresh" in resp.json()["detail"]

    def test_failed_only_404_with_reason(self, auth_client, user):
        Recommendation.objects.create(user=user, status="failed", error="creds missing")
        resp = auth_client.get(f"/recommendations/{user.pk}/")
        assert resp.status_code == 404
        assert "creds missing" in resp.json()["detail"]

    def test_pending_only_202(self, auth_client, user):
        Recommendation.objects.create(user=user)
        resp = auth_client.get(f"/recommendations/{user.pk}/")
        assert resp.status_code == 202
        assert resp.json()["status"] == "pending"

    def test_served_from_redis_then_db(self, auth_client, user):
        auth_client.post(f"/recommendations/{user.pk}/refresh/")

        resp = auth_client.get(f"/recommendations/{user.pk}/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["cached"] is True
        assert body["count"] == len(body["tracks"]) > 0
        assert body["user_id"] == str(user.pk)
        assert {"spotify_id", "name", "artists", "score", "seed"} <= body["tracks"][0].keys()

        cache.delete(recs_cache_key(user.pk))
        resp = auth_client.get(f"/recommendations/{user.pk}/")
        assert resp.json()["cached"] is False  # DB fallback

        resp = auth_client.get(f"/recommendations/{user.pk}/")
        assert resp.json()["cached"] is True  # re-warmed

    def test_limit_param(self, auth_client, user):
        auth_client.post(f"/recommendations/{user.pk}/refresh/")
        resp = auth_client.get(f"/recommendations/{user.pk}/?limit=2")
        assert resp.json()["count"] == 2
        resp = auth_client.get(f"/recommendations/{user.pk}/?limit=abc")
        assert resp.status_code == 200

    def test_other_user_forbidden(self, other_client, user):
        assert other_client.get(f"/recommendations/{user.pk}/").status_code == 403


@pytest.mark.django_db
class TestTask:
    def test_auth_error_marks_failed(self, fake_spotify, user):
        fake_spotify.raise_on_search = SpotifyAuthError("bad creds")
        result = refresh_user_recommendations.apply(args=[str(user.pk)]).get()
        assert result["status"] == "failed"
        rec = Recommendation.objects.get(user=user)
        assert rec.status == Recommendation.Status.FAILED
        assert "bad creds" in rec.error
        assert cache.get(recs_cache_key(user.pk)) is None

    def test_forbidden_marks_failed_without_retry(self, fake_spotify, user):
        from apps.recommendations.spotify.exceptions import SpotifyForbidden

        fake_spotify.raise_on_search = SpotifyForbidden("403 for /search")
        result = refresh_user_recommendations.apply(args=[str(user.pk)]).get()
        assert result["status"] == "failed"
        assert "403" in Recommendation.objects.get(user=user).error

    def test_unexpected_error_marks_failed(self, fake_spotify, user):
        fake_spotify.raise_on_search = RuntimeError("boom")
        result = refresh_user_recommendations.apply(args=[str(user.pk)]).get()
        assert result["status"] == "failed"
        assert Recommendation.objects.get(user=user).status == "failed"

    def test_missing_user_is_skipped(self, db):
        result = refresh_user_recommendations.apply(
            args=["00000000-0000-0000-0000-000000000000"]
        ).get()
        assert result == {"status": "skipped"}

    def test_refresh_all_fans_out(self, user, other_user):
        from apps.recommendations.tasks import refresh_all_recommendations

        result = refresh_all_recommendations.apply().get()
        assert result["queued"] == 2
        assert Recommendation.objects.filter(status="ready").count() == 2

    def test_purge_expired_cache(self, db):
        from apps.recommendations.models import SpotifyCache
        from apps.recommendations.tasks import purge_expired_spotify_cache

        now = timezone.now()
        SpotifyCache.objects.create(
            cache_key="a", endpoint="e", response={}, expires_at=now - timedelta(1)
        )
        SpotifyCache.objects.create(
            cache_key="b", endpoint="e", response={}, expires_at=now + timedelta(1)
        )
        assert purge_expired_spotify_cache.apply().get() == {"deleted": 1}
        assert SpotifyCache.objects.get().cache_key == "b"
