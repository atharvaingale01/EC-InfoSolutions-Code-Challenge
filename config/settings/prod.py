import warnings

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import INSECURE_SECRET_KEYS, LOGGING, REST_FRAMEWORK, SECRET_KEY
from .env import env, env_bool

DEBUG = False

# Structured logs by default in production; override with LOG_FORMAT=text.
LOGGING["handlers"]["console"]["formatter"] = env("LOG_FORMAT", "json").lower()  # noqa: F405

if SECRET_KEY in INSECURE_SECRET_KEYS:
    if env_bool("DJANGO_ALLOW_INSECURE_SECRET", False):
        warnings.warn("DJANGO_SECRET_KEY is a placeholder; do not deploy like this.", stacklevel=1)
    else:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is missing or still the placeholder. Set a long random value in "
            ".env (or DJANGO_ALLOW_INSECURE_SECRET=1 for a throwaway local run)."
        )

# nginx is the single trusted hop: it overwrites X-Forwarded-For/-Proto, so DRF
# may take the last forwarded address as the client identity for throttling.
REST_FRAMEWORK["NUM_PROXIES"] = 1
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = False  # nginx terminates plain HTTP in this assignment
CSRF_COOKIE_SECURE = False
