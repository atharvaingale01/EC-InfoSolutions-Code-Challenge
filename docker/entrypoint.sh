#!/usr/bin/env sh
set -e

# Wait for Postgres.
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
  sleep 2
done

# Only the web service runs migrations; workers just start.
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  python manage.py migrate --noinput
fi

exec "$@"
