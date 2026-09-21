import pytest


@pytest.mark.django_db
def test_refresh_is_throttled_per_user(auth_client, other_client, user, other_user):
    url = f"/recommendations/{user.pk}/refresh/"
    codes = [auth_client.post(url).status_code for _ in range(6)]
    assert codes[:5] == [202] * 5
    assert codes[5] == 429

    # The other user has their own bucket.
    assert other_client.post(f"/recommendations/{other_user.pk}/refresh/").status_code == 202


@pytest.mark.django_db
def test_throttled_response_has_retry_after(auth_client, user):
    url = f"/recommendations/{user.pk}/refresh/"
    for _ in range(5):
        auth_client.post(url)
    resp = auth_client.post(url)
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
