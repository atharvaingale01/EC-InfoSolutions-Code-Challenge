import base64

import pytest

from apps.recommendations.models import Recommendation
from apps.users.models import User

from .conftest import PASSWORD

REGISTER_BODY = {
    "email": "New@Example.com",
    "password": PASSWORD,
    "name": "New User",
    "favorite_genres": ["Rock", "rock", " Indie "],
    "favorite_artists": ["Radiohead"],
    "moods": ["Chill"],
}


@pytest.mark.django_db
class TestRegister:
    def test_anonymous_post_registers(self, api_client):
        resp = api_client.post("/users/", REGISTER_BODY, format="json")
        assert resp.status_code == 201, resp.content
        body = resp.json()
        assert body["email"] == "new@example.com"
        assert "password" not in body
        assert body["favorite_genres"] == ["rock", "indie"]  # lowercased, trimmed, deduped
        assert body["moods"] == ["chill"]
        assert User.objects.filter(email="new@example.com").exists()

    def test_register_triggers_recommendation_build(self, api_client):
        resp = api_client.post("/users/", REGISTER_BODY, format="json")
        user = User.objects.get(pk=resp.json()["id"])
        rec = Recommendation.objects.get(user=user)
        assert rec.status == Recommendation.Status.READY
        assert len(rec.tracks) > 0

    def test_duplicate_email_rejected(self, api_client, user):
        body = {**REGISTER_BODY, "email": user.email.upper()}
        resp = api_client.post("/users/", body, format="json")
        assert resp.status_code == 400
        assert "email" in resp.json()["errors"]

    def test_weak_password_rejected(self, api_client):
        resp = api_client.post("/users/", {**REGISTER_BODY, "password": "12345678"}, format="json")
        assert resp.status_code == 400
        assert "password" in resp.json()["errors"]

    def test_unknown_mood_rejected(self, api_client):
        resp = api_client.post("/users/", {**REGISTER_BODY, "moods": ["angry"]}, format="json")
        assert resp.status_code == 400
        assert "moods" in resp.json()["errors"]

    def test_password_similar_to_email_rejected(self, api_client):
        body = {**REGISTER_BODY, "email": "supersecret@example.com", "password": "supersecret1"}
        resp = api_client.post("/users/", body, format="json")
        assert resp.status_code == 400
        assert "password" in resp.json()["errors"]

    def test_concurrent_duplicate_registration_is_400(self, api_client, monkeypatch):
        from django.db import IntegrityError

        from apps.users import serializers as user_serializers

        def race(*a, **k):
            raise IntegrityError("duplicate key value violates unique constraint")

        monkeypatch.setattr(user_serializers.User.objects, "create_user", race)
        resp = api_client.post("/users/", REGISTER_BODY, format="json")
        assert resp.status_code == 400
        assert "email" in resp.json()["errors"]

    def test_missing_password_rejected(self, api_client):
        body = {k: v for k, v in REGISTER_BODY.items() if k != "password"}
        resp = api_client.post("/users/", body, format="json")
        assert resp.status_code == 400


@pytest.mark.django_db
class TestUpdate:
    def test_authenticated_post_updates_own_profile(self, auth_client, user):
        resp = auth_client.post(
            "/users/",
            {"name": "Alice B", "moods": ["party"], "email": "hacker@example.com"},
            format="json",
        )
        assert resp.status_code == 200, resp.content
        user.refresh_from_db()
        assert user.name == "Alice B"
        assert user.moods == ["party"]
        assert user.email == "alice@example.com"  # email is read-only on update
        assert user.favorite_genres == ["rock", "indie"]  # partial update kept the rest

    def test_update_requeues_recommendations(self, auth_client, user):
        assert Recommendation.objects.filter(user=user).count() == 0
        auth_client.post("/users/", {"moods": ["happy"]}, format="json")
        rec = Recommendation.objects.get(user=user)
        assert rec.status == "ready" and rec.task_id  # row created up front, then built

    def test_noop_update_does_not_queue_a_rebuild(self, auth_client, user):
        auth_client.post("/users/", {}, format="json")
        auth_client.post("/users/", {"name": "Alice"}, format="json")  # non-preference field
        auth_client.post("/users/", {"favorite_genres": ["rock", "indie"]}, format="json")  # same
        assert Recommendation.objects.filter(user=user).count() == 0

    def test_update_reuses_inflight_pending_build(self, auth_client, user):
        Recommendation.objects.create(user=user)  # a rebuild already queued
        auth_client.post("/users/", {"moods": ["party"]}, format="json")
        assert Recommendation.objects.filter(user=user).count() == 1

    def test_artist_dedupe_is_case_insensitive(self, auth_client, user):
        resp = auth_client.post(
            "/users/", {"favorite_artists": ["Drake", "drake", " DRAKE "]}, format="json"
        )
        assert resp.json()["favorite_artists"] == ["Drake"]

    def test_update_marks_failed_when_broker_is_down(self, auth_client, user, monkeypatch):
        from apps.recommendations import tasks

        def boom(*a, **k):
            raise ConnectionError("broker down")

        monkeypatch.setattr(tasks.refresh_user_recommendations, "apply_async", boom)
        resp = auth_client.post("/users/", {"moods": ["happy"]}, format="json")
        assert resp.status_code == 200  # profile write still succeeds
        assert Recommendation.objects.get(user=user).status == "failed"

    def test_rapid_changes_are_coalesced_with_a_countdown(self, auth_client, user, monkeypatch):
        from apps.users import services

        calls = []

        def fake_enqueue(u, countdown=0, expires=None):
            calls.append(countdown)
            return Recommendation.objects.create(user=u, status="ready")  # completes instantly

        monkeypatch.setattr("apps.recommendations.tasks.enqueue_refresh", fake_enqueue)
        auth_client.post("/users/", {"moods": ["happy"]}, format="json")
        auth_client.post("/users/", {"moods": ["party"]}, format="json")
        assert calls[0] == 0
        assert 0 < calls[1] <= services.REBUILD_MIN_INTERVAL.total_seconds() + 1


@pytest.mark.django_db
class TestDetail:
    def test_anonymous_is_401(self, api_client, user):
        assert api_client.get(f"/users/{user.pk}/").status_code == 401

    def test_owner_can_read(self, auth_client, user):
        resp = auth_client.get(f"/users/{user.pk}/")
        assert resp.status_code == 200
        assert resp.json()["email"] == user.email

    def test_other_user_is_403(self, other_client, user):
        assert other_client.get(f"/users/{user.pk}/").status_code == 403

    def test_staff_can_read_anyone(self, staff_client, user):
        assert staff_client.get(f"/users/{user.pk}/").status_code == 200

    def test_unknown_user_404_for_staff(self, staff_client):
        assert staff_client.get("/users/00000000-0000-0000-0000-000000000000/").status_code == 404


@pytest.mark.django_db
class TestAuth:
    def test_token_obtain_and_refresh(self, api_client, user):
        resp = api_client.post(
            "/auth/token/", {"email": user.email, "password": PASSWORD}, format="json"
        )
        assert resp.status_code == 200
        tokens = resp.json()
        assert {"access", "refresh"} <= tokens.keys()

        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        assert api_client.get(f"/users/{user.pk}/").status_code == 200

        api_client.credentials()
        resp = api_client.post("/auth/token/refresh/", {"refresh": tokens["refresh"]})
        assert resp.status_code == 200
        assert "access" in resp.json()

    def test_bad_credentials(self, api_client, user):
        resp = api_client.post("/auth/token/", {"email": user.email, "password": "nope"})
        assert resp.status_code == 401

    def test_basic_auth_works(self, api_client, user):
        raw = f"{user.email}:{PASSWORD}".encode()
        api_client.credentials(HTTP_AUTHORIZATION="Basic " + base64.b64encode(raw).decode())
        assert api_client.get(f"/users/{user.pk}/").status_code == 200
