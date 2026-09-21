import pytest

from apps.activity.models import UserActivity

BODY = {"track_id": "trk1", "track_name": "Creep", "artist_name": "Radiohead", "action": "play"}


@pytest.mark.django_db
def test_create_activity(auth_client, user):
    resp = auth_client.post("/activity/", BODY, format="json")
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["user_id"] == str(user.pk)
    assert body["action"] == "play"
    assert UserActivity.objects.filter(user=user, track_id="trk1").exists()


@pytest.mark.django_db
def test_user_comes_from_token_not_body(auth_client, user, other_user):
    resp = auth_client.post("/activity/", {**BODY, "user_id": str(other_user.pk)}, format="json")
    assert resp.status_code == 201
    assert UserActivity.objects.get().user_id == user.pk


@pytest.mark.django_db
def test_invalid_action(auth_client):
    resp = auth_client.post("/activity/", {**BODY, "action": "dance"}, format="json")
    assert resp.status_code == 400
    assert "action" in resp.json()["errors"]


@pytest.mark.django_db
def test_anonymous_401(api_client):
    assert api_client.post("/activity/", BODY, format="json").status_code == 401
