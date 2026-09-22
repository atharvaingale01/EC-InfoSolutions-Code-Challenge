"""
Base settings shared by every environment.

Values come from environment variables (see .env.example). A `.env` file at the
project root is loaded if present so local runs outside Docker work too.
"""

from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

from .env import env, env_bool, env_int, env_list

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
INSECURE_SECRET_KEYS = {"", "insecure-dev-key-change-me", "change-me-to-a-long-random-string"}
SECRET_KEY = env("DJANGO_SECRET_KEY", "insecure-dev-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third party
    "rest_framework",
    "rest_framework_simplejwt",
    "drf_spectacular",
    "corsheaders",
    # project
    "apps.core",
    "apps.users",
    "apps.recommendations",
    "apps.activity",
    "apps.analytics",
]

MIDDLEWARE = [
    "apps.core.middleware.RequestIDMiddleware",  # first: every later log line carries the id
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "musicdb"),
        "USER": env("POSTGRES_USER", "music"),
        "PASSWORD": env("POSTGRES_PASSWORD", "music"),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env_int("POSTGRES_PORT", 5432),
        "CONN_MAX_AGE": 60,
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "users.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Cache (Redis)
# ---------------------------------------------------------------------------
CACHE_REDIS_URL = env("CACHE_REDIS_URL", "redis://localhost:6379/1")
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": CACHE_REDIS_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        "KEY_PREFIX": "music",
    }
}
# A Redis outage degrades to cache misses (DB fallback) instead of 500s.
DJANGO_REDIS_IGNORE_EXCEPTIONS = True
DJANGO_REDIS_LOG_IGNORED_EXCEPTIONS = True

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
CELERY_RESULT_EXPIRES = 3600
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 300

RECS_REFRESH_INTERVAL_MINUTES = env_int("RECS_REFRESH_INTERVAL_MINUTES", 360)
CELERY_BEAT_SCHEDULE = {
    "refresh-all-recommendations": {
        "task": "apps.recommendations.tasks.refresh_all_recommendations",
        "schedule": timedelta(minutes=RECS_REFRESH_INTERVAL_MINUTES),
    },
    "purge-expired-spotify-cache": {
        "task": "apps.recommendations.tasks.purge_expired_spotify_cache",
        "schedule": timedelta(hours=24),
    },
}

# ---------------------------------------------------------------------------
# REST framework / auth / throttling
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("THROTTLE_ANON", "20/min"),
        "user": env("THROTTLE_USER", "120/min"),
        "refresh": env("THROTTLE_REFRESH", "5/min"),
        "activity": env("THROTTLE_ACTIVITY", "60/min"),
    },
    # Number of trusted proxies in front of Django; prod sets 1 (nginx). With this
    # unset DRF would key anonymous throttles on the whole X-Forwarded-For string,
    # which a client controls.
    "NUM_PROXIES": 0,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "apps.core.exceptions.exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env_int("JWT_ACCESS_MINUTES", 60)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env_int("JWT_REFRESH_DAYS", 7)),
    "ROTATE_REFRESH_TOKENS": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Music Discovery API",
    "DESCRIPTION": "Spotify-backed music recommendations, activity tracking and analytics.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SECURITY": [{"jwtAuth": []}, {"basicAuth": []}],
}

CORS_ALLOW_ALL_ORIGINS = env_bool("CORS_ALLOW_ALL_ORIGINS", False)
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "")

# ---------------------------------------------------------------------------
# Spotify / recommendations
# ---------------------------------------------------------------------------
SPOTIFY_CLIENT_ID = env("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = env("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_MARKET = env("SPOTIFY_MARKET", "US")
SPOTIFY_CACHE_TTL_SECONDS = env_int("SPOTIFY_CACHE_TTL_SECONDS", 21600)
# Serve fixture data instead of calling Spotify (for evaluation without a Premium-owned app).
SPOTIFY_MOCK = env_bool("SPOTIFY_MOCK", False)
SPOTIFY_API_BASE = "https://api.spotify.com/v1"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"

RECS_CACHE_TTL_SECONDS = env_int("RECS_CACHE_TTL_SECONDS", 3600)
RECS_DEFAULT_LIMIT = env_int("RECS_DEFAULT_LIMIT", 20)
RECS_MAX_LIMIT = 50

# ---------------------------------------------------------------------------
# I18N / static
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = env("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = env("LOG_FORMAT", "text").lower()  # "text" for humans, "json" for aggregators
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"context": {"()": "apps.core.logging.ContextFilter"}},
    "formatters": {
        "text": {
            "format": (
                "%(asctime)s %(levelname)s %(name)s rid=%(request_id)s task=%(task_id)s %(message)s"
            )
        },
        "json": {"()": "apps.core.logging.JsonFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": LOG_FORMAT if LOG_FORMAT in ("text", "json") else "text",
            "filters": ["context"],
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.request": {"level": "WARNING"},
        "apps": {"level": LOG_LEVEL},
        "apps.requests": {"level": "INFO"},
        "apps.audit": {"level": "WARNING"},
    },
}
