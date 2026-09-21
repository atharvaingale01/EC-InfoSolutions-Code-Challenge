from .base import *  # noqa: F401,F403

DEBUG = False
SECRET_KEY = "test-secret-key-that-is-long-enough-for-hs256-signing-0123456789"

# Fast, isolated cache; throttles and recs cache both live here in tests.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "tests",
    }
}

# Run Celery tasks inline.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

LOGGING["root"]["level"] = "WARNING"  # noqa: F405
LOGGING["loggers"]["apps"]["level"] = "WARNING"  # noqa: F405

SPOTIFY_MOCK = False
SPOTIFY_CLIENT_ID = "test-client-id"
SPOTIFY_CLIENT_SECRET = "test-client-secret"
