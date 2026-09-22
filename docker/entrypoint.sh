#!/usr/bin/env sh
set -e

# Fail fast on configuration errors (e.g. placeholder DJANGO_SECRET_KEY under the
# production settings) before we start waiting on the database.
python -c "import django; django.setup()"

# Wait for Postgres, but not forever: a wrong password after the volume was
# initialised should surface as an error, not an endless "waiting" loop.
attempt=0
until python - <<'PY'
import os, sys
import psycopg
try:
    psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "db"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", "musicdb"),
        user=os.environ.get("POSTGRES_USER", "music"),
        password=os.environ.get("POSTGRES_PASSWORD", "music"),
        connect_timeout=3,
    ).close()
except Exception as exc:  # noqa: BLE001
    print(f"waiting for postgres: {exc}", file=sys.stderr)
    sys.exit(1)
PY
do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 45 ]; then
    echo "postgres not reachable after 90s; giving up. If you changed POSTGRES_* after the" >&2
    echo "first run, the volume still holds the old credentials: run 'make clean' and retry." >&2
    exit 1
  fi
  sleep 2
done

# Only the web service migrates and refreshes static files; workers just start.
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  python manage.py migrate --noinput
  if [ "${RUN_COLLECTSTATIC:-1}" = "1" ]; then
    # The static volume is only seeded from the image when empty; re-collect so a
    # rebuilt image (new Django/DRF/Swagger assets) is actually what nginx serves.
    python manage.py collectstatic --noinput --clear >/dev/null
  fi
fi

exec "$@"
