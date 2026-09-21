import pytest


@pytest.mark.django_db
def test_health_ok(api_client):
    resp = api_client.get("/health/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["checks"] == {"database": True, "cache": True}
