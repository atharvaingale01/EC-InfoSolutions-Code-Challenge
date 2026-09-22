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

    def test_refresh_pending_flag_while_rebuilding(self, auth_client, user):
        auth_client.post(f"/recommendations/{user.pk}/refresh/")  # eager -> ready
        assert auth_client.get(f"/recommendations/{user.pk}/").json()["refresh_pending"] is False
        Recommendation.objects.create(user=user)  # a rebuild in flight
        body = auth_client.get(f"/recommendations/{user.pk}/").json()
        assert body["refresh_pending"] is True
        assert body["count"] > 0  # previous list still served

    def test_lost_builds_do_not_flag_refresh_pending(self, auth_client, user):
        auth_client.post(f"/recommendations/{user.pk}/refresh/")
        # started 30 minutes ago and never finished -> worker died
        died = Recommendation.objects.create(user=user)
        Recommendation.objects.filter(pk=died.pk).update(
            started_at=timezone.now() - timedelta(minutes=30)
        )
        # never started and older than the queue TTL -> task lost
        lost = Recommendation.objects.create(user=user)
        Recommendation.objects.filter(pk=lost.pk).update(
            created_at=timezone.now() - timedelta(hours=7)
        )
        assert auth_client.get(f"/recommendations/{user.pk}/").json()["refresh_pending"] is False
        # queued 30 minutes ago but not yet started is still a live build (deep queue)
        queued = Recommendation.objects.create(user=user)
        Recommendation.objects.filter(pk=queued.pk).update(
            created_at=timezone.now() - timedelta(minutes=30)
        )
        assert auth_client.get(f"/recommendations/{user.pk}/").json()["refresh_pending"] is True

    def test_newest_requested_build_wins_over_one_that_finished_later(self, auth_client, user):
        older = Recommendation.objects.create(
            user=user, status="ready", tracks=[{"spotify_id": "old"}]
        )
        newer = Recommendation.objects.create(
            user=user, status="ready", tracks=[{"spotify_id": "new"}]
        )
        # the older build finished last
        Recommendation.objects.filter(pk=older.pk).update(completed_at=timezone.now())
        Recommendation.objects.filter(pk=newer.pk).update(
            completed_at=timezone.now() - timedelta(minutes=5)
        )
        body = auth_client.get(f"/recommendations/{user.pk}/").json()
        assert body["recommendation_id"] == str(newer.pk)

    def test_concurrent_triggers_share_one_build(self, auth_client, user, monkeypatch):
        from apps.recommendations import views

        created = []
        real = views.enqueue_refresh

        def counting(u, **kw):
            rec = real(u, **kw)
            created.append(rec.pk)
            return rec

        monkeypatch.setattr(views, "enqueue_refresh", counting)
        # simulate a second request arriving while the first still holds the gate
        cache.add(f"recs:enqueue:{user.pk}", 1, 5)
        resp = auth_client.post(f"/recommendations/{user.pk}/refresh/")
        assert resp.status_code == 202 and created == []

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

    def test_refresh_all_fails_lost_builds_and_skips_busy_users(self, user, other_user):
        from apps.recommendations.tasks import refresh_all_recommendations

        died = Recommendation.objects.create(user=user)
        Recommendation.objects.filter(pk=died.pk).update(
            started_at=timezone.now() - timedelta(hours=1)
        )
        Recommendation.objects.create(user=other_user)  # fresh, in flight

        result = refresh_all_recommendations.apply().get()
        died.refresh_from_db()
        assert died.status == "failed" and "never completed" in died.error
        assert (result["queued"], result["skipped_busy"], result["stale_failed"]) == (1, 1, 1)
        assert Recommendation.objects.filter(user=user, status="ready").count() == 1
        assert Recommendation.objects.filter(user=other_user).count() == 1  # untouched

    def test_refresh_all_is_locked_against_overlap(self, user):
        from apps.recommendations.tasks import FANOUT_LOCK_KEY, refresh_all_recommendations

        cache.add(FANOUT_LOCK_KEY, "running", 60)
        assert refresh_all_recommendations.apply().get() == {"skipped": "locked"}
        assert Recommendation.objects.count() == 0

    def test_refresh_all_prunes_old_rows(self, user):
        from apps.recommendations.tasks import (
            FAILED_RETENTION,
            KEEP_READY_PER_USER,
            refresh_all_recommendations,
        )

        for _ in range(KEEP_READY_PER_USER + 3):
            Recommendation.objects.create(user=user, status="ready", tracks=[])
        old_fail = Recommendation.objects.create(user=user, status="failed", error="x")
        Recommendation.objects.filter(pk=old_fail.pk).update(
            completed_at=timezone.now() - FAILED_RETENTION - timedelta(days=1)
        )
        result = refresh_all_recommendations.apply().get()
        assert result["pruned_failed"] == 1
        assert result["pruned_ready"] == 3
        # the fan-out itself added one fresh ready build
        assert (
            Recommendation.objects.filter(user=user, status="ready").count()
            == KEEP_READY_PER_USER + 1
        )

    def test_older_build_does_not_overwrite_cache_of_newer_one(self, fake_spotify, user):
        older = Recommendation.objects.create(user=user)
        Recommendation.objects.create(user=user)  # requested later; still pending
        refresh_user_recommendations.apply(args=[str(user.pk), str(older.pk)]).get()
        older.refresh_from_db()
        assert older.status == "ready"
        assert cache.get(recs_cache_key(user.pk)) is None  # superseded: cache left alone

    def test_preference_change_during_build_requeues(self, fake_spotify, user, monkeypatch):
        from apps.recommendations import tasks

        real_build = tasks.build_recommendations

        def build_and_change_prefs(u, *a, **k):
            type(u).objects.filter(pk=u.pk).update(moods=["party"])  # changed mid-build
            return real_build(u, *a, **k)

        monkeypatch.setattr(tasks, "build_recommendations", build_and_change_prefs)
        queued = []
        monkeypatch.setattr(
            tasks, "enqueue_refresh", lambda u, **kw: queued.append(kw.get("countdown"))
        )
        refresh_user_recommendations.apply(args=[str(user.pk)]).get()
        assert queued == [5]

    def test_rate_limit_retry_honours_retry_after(self, fake_spotify, user, monkeypatch):
        from apps.recommendations import tasks
        from apps.recommendations.spotify.exceptions import SpotifyRateLimited

        fake_spotify.raise_on_search = SpotifyRateLimited(retry_after=120)
        seen = {}

        def fake_retry(exc=None, countdown=None, **kw):
            seen["countdown"] = countdown
            raise RuntimeError("retry-called")

        # shared_task returns a proxy; patch the underlying task instance
        monkeypatch.setattr(tasks.refresh_user_recommendations, "retry", fake_retry)
        with pytest.raises(RuntimeError, match="retry-called"):
            refresh_user_recommendations.apply(args=[str(user.pk)]).get()
        assert seen["countdown"] == 120

    def test_inactive_user_marks_passed_row_failed(self, user):
        user.is_active = False
        user.save()
        rec = Recommendation.objects.create(user=user)
        result = refresh_user_recommendations.apply(args=[str(user.pk), str(rec.pk)]).get()
        rec.refresh_from_db()
        assert result == {"status": "skipped"} and rec.status == "failed"

    def test_soft_time_limit_marks_failed(self, user, monkeypatch):
        from celery.exceptions import SoftTimeLimitExceeded

        from apps.recommendations import tasks

        def slow(*a, **k):
            raise SoftTimeLimitExceeded()

        monkeypatch.setattr(tasks, "build_recommendations", slow)
        result = refresh_user_recommendations.apply(args=[str(user.pk)]).get()
        assert result["status"] == "failed"
        assert "exceeded" in Recommendation.objects.get(user=user).error

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
