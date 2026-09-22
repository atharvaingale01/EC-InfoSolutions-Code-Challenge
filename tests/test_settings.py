import importlib

import pytest
from django.core.exceptions import ImproperlyConfigured


def _load_prod(monkeypatch, key, allow=None):
    monkeypatch.setenv("DJANGO_SECRET_KEY", key)
    if allow is None:
        monkeypatch.delenv("DJANGO_ALLOW_INSECURE_SECRET", raising=False)
    else:
        monkeypatch.setenv("DJANGO_ALLOW_INSECURE_SECRET", allow)
    import config.settings.base as base
    import config.settings.prod as prod

    importlib.reload(base)
    return importlib.reload(prod)


def test_prod_rejects_placeholder_secret(monkeypatch):
    with pytest.raises(ImproperlyConfigured):
        _load_prod(monkeypatch, "change-me-to-a-long-random-string")


def test_prod_allows_placeholder_when_explicitly_permitted(monkeypatch):
    with pytest.warns(UserWarning):
        _load_prod(monkeypatch, "change-me-to-a-long-random-string", allow="1")


def test_prod_accepts_a_real_secret(monkeypatch):
    mod = _load_prod(monkeypatch, "a-genuinely-random-secret-value-0123456789abcdef")
    assert mod.DEBUG is False
