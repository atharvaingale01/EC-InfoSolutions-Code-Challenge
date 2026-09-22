# Music Discovery Backend

Django REST backend that recommends songs to users from their favourite genres, artists and moods, using the Spotify Web API as the catalogue. Recommendations are built asynchronously by Celery, cached in Redis, persisted in PostgreSQL, and served behind nginx.

Stack: Python 3.12, Django 5.2, Django REST Framework, PostgreSQL 16, Redis 7, Celery 5 with Beat, nginx, Docker Compose.

- [Setup and run](#setup-and-run)
- [API usage guide](#api-usage-guide)
- [Assumptions and limitations](#assumptions-and-limitations)
- [Extras beyond the brief](#extras-beyond-the-brief)

---

## Setup and run

**Prerequisites:** Docker with Compose v2. For live Spotify data, a Spotify app (client id and secret) from <https://developer.spotify.com/dashboard> whose owner has a Spotify Premium subscription. Without one, set `SPOTIFY_MOCK=1` and the service runs on fixture data.

```bash
git clone https://github.com/atharvaingale01/EC-InfoSolutions-Code-Challenge.git
cd EC-InfoSolutions-Code-Challenge

make env     # copies .env.example to .env and generates a random DJANGO_SECRET_KEY
# edit .env: set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET, or set SPOTIFY_MOCK=1

make up      # builds images; starts db, redis, web, worker, beat, nginx
make seed    # 5 demo users, a staff user, sample activity; queues recommendations
```

The API is on <http://localhost/>. Swagger UI is at <http://localhost/api/docs/>. If port 80 is taken, use `NGINX_PORT=8080 make up`.

Without `make`:

```bash
cp .env.example .env
# set DJANGO_SECRET_KEY to any long random string (the placeholder is rejected by the
# production settings), then set the Spotify credentials or SPOTIFY_MOCK=1
docker compose up -d --build
docker compose exec web python manage.py seed_demo
```

**Services started**

| Service | Role |
|---------|------|
| nginx | Only published port. Reverse proxy to Django, serves static files, edge rate limit |
| web | Django under Gunicorn. Runs migrations on start |
| worker | Celery worker that builds recommendations |
| beat | Celery Beat. Refreshes all users every 6 hours, purges expired Spotify cache daily |
| db | PostgreSQL 16 |
| redis | Cache and Celery broker |

**Useful commands**

| Command | What it does |
|---------|--------------|
| `make env` | Create `.env` from the example with a generated secret key |
| `make up` / `make down` | Start / stop the stack |
| `make logs` | Tail all service logs |
| `make seed` | Create demo data (idempotent) |
| `make test` | Run the test suite inside the web container |
| `make lint` | Ruff lint, format check and OpenAPI schema validation |
| `make superuser` | Create an admin for `/admin/` |
| `make dev` / `make dev-down` | Development stack: runserver with autoreload, bind-mounted code, no nginx, Django on :8000. Other targets work against it with `DEV=1 make seed` etc. |
| `make clean` | Stop and delete volumes (destroys data) |

**Environment variables** are documented inline in `.env.example`. The ones you are most likely to change:

| Variable | Purpose |
|----------|---------|
| `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` | Spotify app credentials |
| `SPOTIFY_MOCK` | `1` to serve fixture tracks with no Spotify calls |
| `RECS_REFRESH_INTERVAL_MINUTES` | Beat interval for refreshing all users (default 360) |
| `RECS_CACHE_TTL_SECONDS` | Redis TTL for a user's recommendation list (default 3600) |
| `THROTTLE_*` | Per-user rate limits (DRF) |
| `NGINX_RATE_LIMIT`, `NGINX_RATE_BURST` | Per-IP edge rate limit (nginx) |
| `NGINX_PORT` | Host port for the API (default 80) |
| `DJANGO_SECRET_KEY` | Required for the production settings; the placeholder is rejected |
| `CORS_ALLOW_ALL_ORIGINS`, `CORS_ALLOWED_ORIGINS` | Browser origins allowed to call the API |

**Running tests locally** (outside Docker) needs a reachable Postgres:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5432 pytest
```

---

## API usage guide

Base URL: `http://localhost`. All bodies and responses are JSON. Errors return `{"detail": "..."}`, with an `errors` object keyed by field on validation failures.

### Authentication

Every route except registration, the token routes, health and the API docs requires credentials. Two schemes are accepted:

- **JWT** (recommended): obtain a token, send `Authorization: Bearer <access>`.
- **HTTP Basic**: `curl -u email:password ...`.

```bash
# 1. register
curl -X POST http://localhost/users/ -H 'Content-Type: application/json' -d '{
  "email": "me@example.com", "password": "Password123!", "name": "Me",
  "favorite_genres": ["rock", "indie"], "favorite_artists": ["Radiohead"], "moods": ["chill"]
}'

# 2. get tokens
curl -X POST http://localhost/auth/token/ -H 'Content-Type: application/json' \
  -d '{"email": "me@example.com", "password": "Password123!"}'
# {"access": "...", "refresh": "..."}

# 3. call the API
curl http://localhost/users/<user_id>/ -H 'Authorization: Bearer <access>'
```

Access tokens last 60 minutes. Refresh with `POST /auth/token/refresh/` and `{"refresh": "..."}`.

Demo accounts from `make seed`, all with password `Password123!`: `alice@example.com`, `bob@example.com`, `carol@example.com`, `dave@example.com`, `eve@example.com`, and `admin@example.com` (staff flag only, no admin model permissions). These credentials are public by design; run `seed_demo --flush` before exposing the stack beyond your machine.

**Who can call what**

| Route | Anonymous | Owner | Other user | Staff |
|-------|-----------|-------|------------|-------|
| `POST /users/` | register (201) | update self (200) | update self (200) | update self |
| `GET /users/{id}/` | 401 | 200 | 403 | 200 |
| `POST /recommendations/{id}/refresh/` | 401 | 202 | 403 | 202 |
| `GET /recommendations/{id}/` | 401 | 200 | 403 | 200 |
| `POST /activity/` | 401 | 201 | – | 201 |
| `GET /analytics/summary/`, `/trends/` | 401 | 200 | 200 | 200 |
| `GET /analytics/user/{id}/` | 401 | 200 | 403 | 200 |

### Endpoints

**`POST /users/`** — create or update a profile

Anonymous: registers, requires `email`, `password` and `name`. Authenticated: partial update of the caller's own profile; `email` and `password` are ignored. A recommendation rebuild is queued whenever genres, artists or moods change (at most one per minute per user; changes arriving during a build are applied by a follow-up build).

```json
{ "email": "me@example.com", "password": "Password123!", "name": "Me",
  "favorite_genres": ["rock", "indie"], "favorite_artists": ["Radiohead"], "moods": ["chill"] }
```

Genres are lowercased and de-duplicated. Each list holds at most 10 items. Moods must be one of `happy, sad, chill, energetic, focus, romantic, party, workout`.

**`GET /users/{user_id}/`** — profile and saved preferences

```json
{ "id": "…", "email": "me@example.com", "name": "Me",
  "favorite_genres": ["rock", "indie"], "favorite_artists": ["Radiohead"], "moods": ["chill"],
  "is_staff": false, "created_at": "…", "updated_at": "…" }
```

**`POST /recommendations/{user_id}/refresh/`** — trigger an async rebuild

Returns `202` immediately. Limited to 5 per minute per user. A pending build from the last 2 minutes is returned instead of queuing another.

```json
{ "recommendation_id": "…", "task_id": "…", "status": "pending" }
```

**`GET /recommendations/{user_id}/?limit=20`** — cached recommendations

```json
{
  "user_id": "…", "recommendation_id": "…", "generated_at": "2026-09-21T10:00:00Z",
  "source": "search_v1", "cached": true, "refresh_pending": false, "count": 20,
  "tracks": [
    { "spotify_id": "6b2oQwSGFkzsMtQruIWm2p", "name": "Creep", "artists": ["Radiohead"],
      "album": "Pablo Honey", "external_url": "https://open.spotify.com/track/6b2oQwSGFkzsMtQruIWm2p",
      "seed": "artist:Radiohead, genre:rock", "score": 28.0,
      "popularity": 0, "preview_url": null, "duration_ms": 238640 }
  ]
}
```

- `cached` is `true` when served from Redis, otherwise from the latest build in PostgreSQL.
- `refresh_pending` is `true` while a newer list is being built; the previous list is served meanwhile.
- `seed` explains why each track is there: `genre:`, `artist:`, `mood:`, `similar:` (discovered artist), or `fallback:pop`.
- `202 {"status": "pending", "recommendation_id": "…"}` when a build is running and no earlier list exists. `404` if nothing was ever generated, including a short reason if the last build failed.
- `limit` defaults to 20, maximum 50.

**`POST /activity/`** — record play, like or skip

The acting user is always the authenticated user.

```json
{ "track_id": "6b2oQwSGFkzsMtQruIWm2p", "track_name": "Creep", "artist_name": "Radiohead", "action": "like" }
```

Returns `201` with `id`, `user_id` and `created_at`. Limited to 60 per minute per user.

**`GET /analytics/summary/`** — overall usage and engagement

```json
{ "users": { "total": 6, "active_7d": 5 },
  "activity": { "total": 50, "by_action": { "play": 31, "like": 12, "skip": 7 }, "like_rate": 0.3871, "skip_rate": 0.2258 },
  "recommendations": { "total_generated": 5, "ready": 5, "failed": 0, "pending": 0, "avg_tracks": 20.0 },
  "cache": { "spotify_cache_entries": 42 }, "generated_at": "…" }
```

`like_rate` is likes ÷ plays, `active_7d` is distinct users with activity in the last 7 days.

**`GET /analytics/trends/?days=7&limit=10`** — trending genres, artists and tracks

```json
{ "window_days": 7,
  "top_genres": [ { "genre": "rock", "users": 2 } ],
  "top_artists": [ { "artist_name": "Radiohead", "interactions": 9, "likes": 3, "plays": 5 } ],
  "top_tracks": [ { "track_id": "…", "track_name": "Creep", "artist_name": "Radiohead",
                    "plays": 5, "likes": 3, "skips": 1, "interactions": 9 } ] }
```

Genres come from user preferences; artists and tracks from activity inside the window.

**`GET /analytics/user/{user_id}/`** — one user's engagement

```json
{ "user_id": "…",
  "activity": { "total": 10, "by_action": { "play": 6, "like": 3, "skip": 1 }, "like_rate": 0.5, "skip_rate": 0.1667 },
  "top_artists": [ { "artist_name": "Radiohead", "interactions": 6 } ],
  "recommendations": { "generated": 1, "last_generated_at": "…", "tracks_recommended": 20 },
  "engagement_rate": 0.15, "last_active_at": "…" }
```

`engagement_rate` is the share of recommended tracks the user has interacted with.

**Utility routes**

| Route | Auth | Purpose |
|-------|------|---------|
| `POST /auth/token/` | none | Obtain JWT access and refresh tokens |
| `POST /auth/token/refresh/` | none | New access token |
| `GET /health/` | none | Database and cache check |
| `GET /api/docs/` | none | Swagger UI |
| `GET /api/schema/` | none | OpenAPI 3 schema |

### Rate limits

Per user, backed by Redis: 5/min for refresh triggers, 60/min for activity writes, 120/min for every other authenticated call, 20/min for anonymous calls. Throttled responses return `429` with `Retry-After`. nginx adds a coarse 30 requests/second per IP with a burst of 50 in front, plus 1 request/second on the admin login form. Behind nginx the client address is taken from a header nginx sets itself, so it cannot be spoofed. All five limits are set in `.env` (`THROTTLE_*`, `NGINX_RATE_LIMIT`, `NGINX_RATE_BURST`).

### Postman

Import `postman/collection.json` and `postman/environment.json`, select the **Music Discovery — Local** environment, run **Auth → Login** once. Tokens and your user id are stored automatically; every other request inherits Bearer auth. A separate folder shows the same calls with HTTP Basic.

---

## Assumptions and limitations

**Spotify**

- **Spotify's recommendations endpoint is not available to new apps** (removed November 2024). Recommendations are therefore built by this service: track searches filtered by `genre:` and `artist:`, moods mapped to genre terms, results merged, scored by how many searches returned each track plus a bonus for favourite artists, capped per artist for variety. It is content-based on stated preferences, not collaborative filtering.
- **Artist top-tracks was removed in February 2026** and returns 403. Artist seeds use an artist-filtered track search instead.
- **Search results no longer include `popularity` or `preview_url`.** `popularity` is reported as 0 and ranking uses each track's position in Spotify's relevance order instead. Genre-only searches can therefore surface obscure tracks; listing at least one artist gives noticeably better results.
- **Search is capped at 10 results per call.** The engine pages with `offset` to widen the pool.
- **Live data requires a Premium-owned app.** Spotify requires this for all development-mode apps since February 2026. Free accounts see the app as blocked and every call returns 403. `SPOTIFY_MOCK=1` exists so the pipeline can be evaluated regardless.
- **Client Credentials flow only.** The service never sees a user's Spotify library or listening history.
- **Genres are free text**, since Spotify's genre-seed list is also gone. An unknown genre simply contributes nothing.
- **Moods are a fixed vocabulary** mapped to genre terms in `apps/recommendations/spotify/moods.py`.

**Service**

- `POST /users/` is dual-purpose to match the brief. An unauthenticated update by email would let anyone overwrite any profile, so updates require the caller's own credentials.
- Auth is deliberately minimal: register, token, refresh, ownership checks, Django's `is_staff`. No email verification, password reset or token blacklist.
- nginx serves plain HTTP, which is fine locally. Basic auth over HTTP sends credentials in the clear; TLS is required before real deployment.
- Analytics are computed on read with ORM aggregates. Fine at this scale; a rollup table would be needed under real load.
- After a profile change the previous list is served with `refresh_pending: true` until the rebuild finishes.
- Redis runs without persistence. A Redis restart drops the cache (rebuilt on demand) and any queued tasks (re-queued by the next scheduled refresh). If Redis is down, reads fall back to PostgreSQL instead of failing.
- A build is considered lost if it never started within one refresh interval or has been running for more than 15 minutes; the scheduled refresh marks such rows failed, and `refresh_pending` ignores them. The same job prunes failed rows after 7 days and keeps the last 5 ready builds per user.
- If two builds for one user overlap, the one requested last owns the result, even if the older one finishes later.
- Registration reveals whether an email is already taken. Standard trade-off for a small API; throttled per client.
- Production settings refuse to start with the placeholder `DJANGO_SECRET_KEY`. Generate one as described in `.env.example`, or set `DJANGO_ALLOW_INSECURE_SECRET=1` for a throwaway local run.
- Single Postgres and single Redis, no high availability.

---

## Extras beyond the brief

| Extra | Why |
|-------|-----|
| **JWT and Basic authentication** | Per-user throttling needs an identity; Basic lets Postman and curl skip the token step |
| **`seed_demo` command** (`make seed`) | 5 users with distinct tastes, a staff user and 50 activity rows, so every endpoint returns data immediately. Idempotent; `--flush` recreates, `--no-refresh` skips Spotify |
| **Mock Spotify mode** (`SPOTIFY_MOCK=1`) | Fixture of real track data served through the same client interface and cache. Labelled `source: mock_v1` so it cannot be mistaken for live output |
| **Development compose override** (`make dev`) | runserver with autoreload, code bind-mounted, DB and Redis published, no nginx |
| **Swagger UI and OpenAPI schema** | Generated from the views; `make lint` validates it with `spectacular --validate --fail-on-warn` |
| **Health endpoint** | Database and cache check, used by the compose healthcheck |
| **Function-based views throughout** | Every endpoint is an `@api_view` function; classes are used for models, serializers, permissions, throttles and clients |
| **Persistent Spotify cache table** | Every Spotify response stored in PostgreSQL with an expiry, on top of the Redis layer, so rebuilds for overlapping tastes cost few upstream calls |
| **Celery Beat cache purge** | Daily cleanup of expired Spotify cache rows |
| **109 tests** | Users, auth, ownership, throttling, Spotify client against mocked HTTP, ranking engine, mock client, Celery task outcomes, analytics, seeder |
| **Makefile and Postman collection** | One-command setup; collection with login script and both auth styles |
