# Music Discovery Backend

A Django REST backend that recommends songs to users based on their stated genres, artists and moods, using the Spotify Web API. Recommendations are built asynchronously with Celery, cached in Redis, persisted in PostgreSQL, and served behind nginx.

| Layer | Choice |
|-------|--------|
| API | Django 5.2, Django REST Framework, drf-spectacular (Swagger) |
| Auth | JWT (SimpleJWT) **and** HTTP Basic, per-user rate limiting |
| Data | PostgreSQL 16 |
| Cache / broker | Redis 7 |
| Background jobs | Celery worker + Celery Beat |
| Edge | nginx reverse proxy |
| Packaging | Docker Compose, Makefile |

---

## Contents

- [Quick start](#quick-start)
- [Architecture](#architecture)
- [Authentication](#authentication)
- [API reference](#api-reference)
- [Background processing](#background-processing)
- [Caching](#caching)
- [Rate limiting](#rate-limiting)
- [Analytics definitions](#analytics-definitions)
- [Testing](#testing)
- [Project layout](#project-layout)
- [Assumptions and limitations](#assumptions-and-limitations)

---

## Quick start

Prerequisites: Docker with Compose v2, and a Spotify app (client id + secret) from <https://developer.spotify.com/dashboard>.

```bash
git clone https://github.com/atharvaingale01/EC-InfoSolutions-Code-Challenge.git
cd EC-InfoSolutions-Code-Challenge

cp .env.example .env
# edit .env → set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET

make up        # builds images, starts db, redis, web, worker, beat, nginx
make seed      # 5 demo users + staff user + sample activity, queues recommendations
```

The API is now on <http://localhost/> (nginx). Interactive docs: <http://localhost/api/docs/>.

Without `make`:

```bash
docker compose up -d --build
docker compose exec web python manage.py seed_demo
```

Useful targets:

| Command | What it does |
|---------|--------------|
| `make up` / `make down` | Start / stop the production-style stack (nginx on :80) |
| `make dev` / `make dev-down` | Start / stop the dev stack (autoreload, no nginx) |
| `make logs` | Tail all service logs |
| `make seed` | Create demo data (idempotent) |
| `make test` | Run the pytest suite inside the web container |
| `make lint` | Ruff lint and format check |
| `make superuser` | Create an admin user for `/admin/` |
| `make clean` | Stop and delete volumes (destroys data) |

Change the published port with `NGINX_PORT=8080 make up` if 80 is taken.

### Development stack

`docker-compose.dev.yml` is an override layered on the base file. It swaps gunicorn for Django's autoreloading `runserver`, bind-mounts the source tree so edits apply instantly, turns on `DEBUG` and the browsable API, publishes Postgres and Redis on the host, and skips nginx.

```bash
make dev          # docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
make dev-logs
make dev-down
```

Dev API: <http://localhost:8000/>. Host ports are configurable with `DEV_WEB_PORT`, `DEV_DB_PORT`, `DEV_REDIS_PORT`. The dev stack uses its own project name and volumes, so it can run alongside the production-style stack.

| | `docker-compose.yml` | `+ docker-compose.dev.yml` |
|-|----------------------|----------------------------|
| App server | gunicorn, 3 workers | runserver with autoreload |
| Code | baked into the image | bind-mounted from the host |
| Settings | `config.settings.prod` | `config.settings.dev`, `DEBUG=1` |
| Entry point | nginx on :80 | Django on :8000, no nginx |
| DB / Redis ports | internal only | published to the host |
| Celery worker | concurrency 2, info logs | concurrency 1, debug logs |

### Demo accounts

`make seed` creates these users, all with password `Password123!`:

| Email | Genres | Artists | Moods |
|-------|--------|---------|-------|
| alice@example.com | rock, indie | Radiohead, Arctic Monkeys | chill |
| bob@example.com | hip-hop, r-n-b | Kendrick Lamar, Drake | energetic, party |
| carol@example.com | pop, dance | Dua Lipa, The Weeknd | happy |
| dave@example.com | classical, jazz | Miles Davis | focus |
| eve@example.com | edm, electronic | Daft Punk, Fred again.. | workout |
| admin@example.com | staff / superuser | | |

### Postman

Import `postman/collection.json` and `postman/environment.json`. Run **Auth → Login** first; it stores the tokens and your user id in the environment. Every other request inherits Bearer auth. The **Basic Auth** folder demonstrates the same endpoints with HTTP Basic.

---

## Architecture

```
 client ──► nginx :80 ──► gunicorn/django :8000 ──► PostgreSQL
                │                 │
                │ /static/        ├──► Redis (cache db1, broker db0, results db2)
                ▼                 │            ▲            ▲
          static volume           │            │            │
                                  │      celery worker   celery beat
                                  │            │
                                  └────────────┴──► Spotify Web API
```

**Recommendation flow**

1. `POST /recommendations/{user_id}/refresh/` creates a `Recommendation` row with status `pending` and enqueues a Celery task. Responds `202` immediately.
2. The worker resolves the user's preferences into Spotify queries, routes every call through a persistent `SpotifyCache` table, merges and ranks the results, marks the row `ready`, and writes the track list to Redis.
3. `GET /recommendations/{user_id}/` reads Redis first, falls back to the newest `ready` row in PostgreSQL (re-warming Redis), returns `202` if only a `pending` row exists, or `404` if nothing was ever generated.

Registering or updating a profile also queues a refresh, so new users get recommendations without an explicit trigger.

**Data model**

| Table | Purpose |
|-------|---------|
| `users_user` | Custom user: UUID id, email login, `favorite_genres`, `favorite_artists`, `moods` (JSON lists) |
| `recommendations_recommendation` | One row per generation: status, normalised `tracks` JSON, `seed_params` snapshot, task id, error |
| `recommendations_spotifycache` | Raw Spotify responses keyed by sha256(endpoint + params) with an expiry |
| `activity_useractivity` | play / like / skip events with denormalised track and artist names |

---

## Authentication

Two schemes are accepted on every protected route. DRF tries them in order.

**JWT (recommended)**

```bash
# register (anonymous)
curl -X POST http://localhost/users/ -H 'Content-Type: application/json' -d '{
  "email": "me@example.com", "password": "Password123!", "name": "Me",
  "favorite_genres": ["rock"], "favorite_artists": ["Radiohead"], "moods": ["chill"]
}'

# obtain tokens
curl -X POST http://localhost/auth/token/ -H 'Content-Type: application/json' \
  -d '{"email": "me@example.com", "password": "Password123!"}'
# → {"access": "...", "refresh": "..."}

# use
curl http://localhost/users/<user_id>/ -H 'Authorization: Bearer <access>'

# refresh
curl -X POST http://localhost/auth/token/refresh/ -H 'Content-Type: application/json' \
  -d '{"refresh": "<refresh>"}'
```

Access tokens last 60 minutes, refresh tokens 7 days (configurable via `JWT_ACCESS_MINUTES`, `JWT_REFRESH_DAYS`).

**HTTP Basic**

```bash
curl -u me@example.com:Password123! http://localhost/users/<user_id>/
```

**Access rules**

| Route | Anonymous | Owner | Other user | Staff |
|-------|-----------|-------|------------|-------|
| `POST /users/` | register (201) | update self (200) | update self (200) | update self |
| `GET /users/{id}/` | 401 | 200 | 403 | 200 |
| `POST /recommendations/{id}/refresh/` | 401 | 202 | 403 | 202 |
| `GET /recommendations/{id}/` | 401 | 200 | 403 | 200 |
| `POST /activity/` | 401 | 201 | – | 201 |
| `GET /analytics/summary/`, `/trends/` | 401 | 200 | 200 | 200 |
| `GET /analytics/user/{id}/` | 401 | 200 | 403 | 200 |

The acting user for `POST /activity/` is always taken from the credentials, never from the request body.

---

## API reference

Full OpenAPI schema at `/api/schema/`, Swagger UI at `/api/docs/`. Errors use `{"detail": "..."}`; validation errors add an `errors` object keyed by field.

### `POST /users/` — register or update

Anonymous request registers. Authenticated request performs a partial update of the caller's own profile (email and password are ignored on update).

```json
{
  "email": "me@example.com",
  "password": "Password123!",
  "name": "Me",
  "favorite_genres": ["rock", "indie"],
  "favorite_artists": ["Radiohead"],
  "moods": ["chill"]
}
```

- Genres are trimmed, lowercased and de-duplicated. Each list holds at most 10 items.
- Moods must be from: `happy, sad, chill, energetic, focus, romantic, party, workout`.
- Response `201` (created) or `200` (updated) with the profile.

### `GET /users/{user_id}/`

```json
{
  "id": "6f1c…", "email": "me@example.com", "name": "Me",
  "favorite_genres": ["rock", "indie"], "favorite_artists": ["Radiohead"], "moods": ["chill"],
  "is_staff": false, "created_at": "…", "updated_at": "…"
}
```

### `POST /recommendations/{user_id}/refresh/`

Queues a background rebuild. Throttled to 5 per minute per user. If a `pending` build from the last 2 minutes exists, it is returned instead of queuing a duplicate.

```json
{ "recommendation_id": "…", "task_id": "…", "status": "pending" }
```

### `GET /recommendations/{user_id}/?limit=20`

```json
{
  "user_id": "…",
  "recommendation_id": "…",
  "generated_at": "2026-09-21T10:00:00Z",
  "source": "search_v1",
  "cached": true,
  "count": 20,
  "tracks": [
    {
      "spotify_id": "6b2oQwSGFkzsMtQruIWm2p",
      "name": "Creep",
      "artists": ["Radiohead"],
      "album": "Pablo Honey",
      "preview_url": null,
      "external_url": "https://open.spotify.com/track/6b2oQwSGFkzsMtQruIWm2p",
      "popularity": 88,
      "duration_ms": 238640,
      "seed": "artist:Radiohead, genre:rock",
      "score": 33.8
    }
  ]
}
```

`cached` is `true` when served from Redis. `202 {"status": "pending"}` while a build is running; `404` if none was ever generated. `limit` is capped at 50.

### `POST /activity/`

```json
{ "track_id": "6b2oQwSGFkzsMtQruIWm2p", "track_name": "Creep", "artist_name": "Radiohead", "action": "play" }
```

`action` is one of `play`, `like`, `skip`. Response `201` echoes the row with `user_id` and `created_at`. Throttled to 60 per minute per user.

### `GET /analytics/summary/`

```json
{
  "users": { "total": 6, "active_7d": 5 },
  "activity": { "total": 50, "by_action": { "play": 31, "like": 12, "skip": 7 }, "like_rate": 0.3871, "skip_rate": 0.2258 },
  "recommendations": { "total_generated": 5, "ready": 5, "failed": 0, "pending": 0, "avg_tracks": 20.0 },
  "cache": { "spotify_cache_entries": 42 },
  "generated_at": "…"
}
```

### `GET /analytics/trends/?days=7&limit=10`

```json
{
  "window_days": 7,
  "top_genres": [ { "genre": "rock", "users": 2 } ],
  "top_artists": [ { "artist_name": "Radiohead", "interactions": 9, "likes": 3, "plays": 5 } ],
  "top_tracks": [ { "track_id": "…", "track_name": "Creep", "artist_name": "Radiohead", "plays": 5, "likes": 3, "skips": 1, "interactions": 9 } ]
}
```

### `GET /analytics/user/{user_id}/`

```json
{
  "user_id": "…",
  "activity": { "total": 10, "by_action": { "play": 6, "like": 3, "skip": 1 }, "like_rate": 0.5, "skip_rate": 0.1667 },
  "top_artists": [ { "artist_name": "Radiohead", "interactions": 6 } ],
  "recommendations": { "generated": 1, "last_generated_at": "…", "tracks_recommended": 20 },
  "engagement_rate": 0.15,
  "last_active_at": "…"
}
```

### Utility

| Route | Auth | Purpose |
|-------|------|---------|
| `POST /auth/token/` | none | Obtain access + refresh JWT |
| `POST /auth/token/refresh/` | none | New access token |
| `GET /health/` | none | DB + cache check, used by the compose healthcheck |
| `GET /api/docs/` | none | Swagger UI |
| `/admin/` | staff | Django admin (`make superuser`) |

---

## Background processing

Celery with Redis as broker. Three tasks live in `apps/recommendations/tasks.py`:

| Task | Trigger | Behaviour |
|------|---------|-----------|
| `refresh_user_recommendations` | refresh endpoint, profile create/update, Beat fan-out | Builds and stores recommendations. Retries up to 3× with backoff on Spotify 5xx/429. Always leaves the row `ready` or `failed`. |
| `refresh_all_recommendations` | Beat, every `RECS_REFRESH_INTERVAL_MINUTES` (default 360) | Queues one refresh per active user |
| `purge_expired_spotify_cache` | Beat, daily | Deletes expired `SpotifyCache` rows |

Watch it work: `docker compose logs -f worker beat`.

### How recommendations are built

Spotify retired `GET /v1/recommendations` for applications created after November 2024, together with the genre-seed, related-artist and audio-feature endpoints. This service therefore synthesises recommendations from endpoints that remain available under the Client Credentials flow:

| Preference | Spotify call |
|-----------|--------------|
| each genre | `GET /search?type=track&q=genre:"<genre>"` |
| each artist | `GET /search?type=artist` to resolve the id, then `GET /artists/{id}/top-tracks` |
| each mood | mapped to genre terms (e.g. `chill → chill, ambient, lo-fi`) and searched as above |

Candidates are de-duplicated by track id and scored as `seed_hits × 10 + popularity ÷ 10`, with a bonus for tracks from a favourite artist. Results are capped at 3 tracks per artist for variety and truncated to `RECS_DEFAULT_LIMIT` (20). A user with no preferences receives a `pop` fallback so the endpoint is never empty.

The client is behind a small interface. If your Spotify app still has access to the legacy recommendations endpoint, it can be swapped in without touching the tasks or views.

---

## Caching

| Layer | Key | TTL | Invalidated by |
|-------|-----|-----|----------------|
| Redis: per-user track list | `recs:{user_id}` | `RECS_CACHE_TTL_SECONDS` (1 h) | Overwritten when a build completes, deleted on profile update |
| Redis: Spotify access token | `spotify:token` | `expires_in − 60 s` | Refetched on a 401 |
| PostgreSQL: `SpotifyCache` | sha256(endpoint + params) | `SPOTIFY_CACHE_TTL_SECONDS` (6 h) | Expiry; purged daily by Beat |
| Redis: throttle counters | DRF-managed | per rate window | – |

Repeat requests for the same user cost zero Spotify calls until the Redis entry expires. Rebuilds for users with overlapping tastes reuse the persistent cache, so the fan-out refresh makes far fewer upstream calls than users × seeds.

---

## Rate limiting

Two layers:

- **nginx** caps each client IP at 30 requests/second with a burst of 50 before traffic reaches Django.
- **DRF throttles** are keyed on the authenticated user (IP for anonymous callers):

| Scope | Default | Applies to |
|-------|---------|-----------|
| `anon` | 20/min | register, token endpoints |
| `user` | 120/min | all other authenticated endpoints |
| `refresh` | 5/min | `POST /recommendations/{id}/refresh/` |
| `activity` | 60/min | `POST /activity/` |

Throttled responses return `429` with a `Retry-After` header. Rates are configurable in `.env`.

---

## Analytics definitions

| Metric | Definition |
|--------|-----------|
| `like_rate` | likes ÷ plays (0 when there are no plays) |
| `skip_rate` | skips ÷ plays |
| `active_7d` | distinct users with any activity in the last 7 days |
| `avg_tracks` | mean track count across `ready` recommendation rows |
| `top_genres` | count of users listing each genre in their preferences |
| `top_artists` / `top_tracks` | interactions within the `days` window, ordered by interactions then likes |
| `tracks_recommended` | distinct track ids across all of the user's `ready` recommendations |
| `engagement_rate` | distinct recommended tracks the user interacted with ÷ `tracks_recommended` |

---

## Testing

```bash
make test            # inside the web container (uses the compose Postgres)
```

Or locally:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5432 pytest
```

The suite (64 tests) covers registration and profile updates, JWT and Basic auth, ownership rules, the Spotify client (token caching, persistent cache, 429/5xx/401 handling via mocked HTTP), the ranking engine, refresh and retrieve flows, Celery task failure paths, all three analytics endpoints, per-user throttling and the seed command. Celery runs eagerly and Spotify is replaced by a deterministic fake, so no network access is needed.

---

## Project layout

```
config/            settings (base / dev / prod / test), celery app, root urls
apps/core/         permissions, throttles, health endpoint, seed_demo command
apps/users/        custom User, register / update / detail views, JWT routes
apps/recommendations/
  spotify/         client, persistent cache, mood map, exceptions
  engine.py        candidate collection + ranking
  tasks.py         Celery tasks
  views.py         refresh + retrieve endpoints
apps/activity/     UserActivity model + endpoint
apps/analytics/    aggregation queries + endpoints
tests/             pytest suite
docker/            nginx config, entrypoint
docker-compose.yml       production-style stack
docker-compose.dev.yml   dev override (runserver, bind mounts)
postman/           collection + environment
```

---

## Assumptions and limitations

- **Spotify recommendations endpoint is deprecated** for new apps, so results come from search and artist top-tracks. Quality depends on Spotify search relevance for `genre:` queries; it is a reasonable proxy, not a collaborative-filtering engine.
- **Client Credentials only.** The service never sees a user's Spotify library or listening history; recommendations reflect the preferences they type in.
- **Genres are free text.** Spotify's genre-seed list endpoint is also deprecated, so genres are not validated. An unknown genre simply contributes no tracks.
- **Moods are a fixed vocabulary** mapped to genre terms in `apps/recommendations/spotify/moods.py`.
- **Auth is deliberately minimal**: register, token, refresh, ownership checks. No email verification, password reset, token blacklisting or roles beyond Django's `is_staff`.
- **Plain HTTP.** nginx terminates HTTP only, which is fine locally. Basic auth over HTTP sends credentials in the clear, so TLS must be added before any real deployment.
- **Analytics are computed on read** with ORM aggregates. That is fine at this scale; under real load they would move to a rollup table or materialised views.
- **Single Redis, single Postgres**, no high-availability considerations.
- `market` defaults to `US` for top-tracks and search (`SPOTIFY_MARKET`).
- `POST /users/` is intentionally dual-purpose to match the brief's "create or update" on one route. An unauthenticated upsert by email would let anyone overwrite any profile, so updates require credentials.
