FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100 \
    RUFF_CACHE_DIR=/tmp/ruff_cache

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libpq5 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app

COPY requirements.txt .
RUN pip install --retries 5 -r requirements.txt

COPY --chown=app:app . .

# /app itself must belong to the runtime user too, so tools run via
# `docker compose exec` (ruff, pytest, makemigrations) can write caches/files.
RUN chmod +x docker/entrypoint.sh \
    && DJANGO_SETTINGS_MODULE=config.settings.prod \
       DJANGO_SECRET_KEY=build-only \
       python manage.py collectstatic --noinput \
    && chown app:app /app \
    && chown -R app:app /app/staticfiles

USER app

EXPOSE 8000

ENTRYPOINT ["docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
