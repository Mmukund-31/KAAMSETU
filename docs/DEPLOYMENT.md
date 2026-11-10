# Deployment

KAAMSETU has three deployable parts: the API with PostgreSQL, the supervisor console (static files) and the
technician app (Expo). This page covers the demo deployment that was verified, and what changes for a hosted pilot.

## 1. One command: database, API and console (verified 2026-11-10)

```powershell
Copy-Item backend\.env.example backend\.env   # set GNANI_API_KEY and a random JWT_SECRET_KEY (32+ characters)
docker compose up -d --build
docker compose exec backend python scripts/seed.py   # synthetic demo data (idempotent)
```

| Service | URL | What it is |
|---|---|---|
| `web` | http://localhost:8080 | supervisor console (nginx); `/api` is forwarded to the backend on the compose network |
| `backend` | http://localhost:8001 | FastAPI; runs `alembic upgrade head` on start; health check on `/health` |
| `db` | localhost:5433 | PostgreSQL 16 with a named volume `kaamsetu_pgdata` |

Host ports are overridable: `KAAMSETU_WEB_HOST_PORT`, `KAAMSETU_API_HOST_PORT`, `KAAMSETU_DB_HOST_PORT`.

Verified on this machine:
- all three containers healthy, with migrations at 0002;
- through nginx, the console signs in, lists the 7 seed work orders, opens a detail page, renders the analytics
  and serves deep links after a reload, with no console errors;
- the backend image runs as a non-root user; its 489 tests pass inside the container (Python 3.12);
- real Prisma transcribed the `.m4a` fixture through the container;
- the container logs hold no secrets.

## 2. Technician app

**On a phone with Expo Go** (development; see `docs/DEVICE_TEST.md`):

```powershell
cd technician-app
# .env: EXPO_PUBLIC_API_URL=http://<laptop-LAN-IP>:8001   (the backend must listen on 0.0.0.0, see above)
npx expo start
```

**Installable Android build** (an APK for demo phones; needs a free Expo account and `npm i -g eas-cli`):

```powershell
cd technician-app
# eas.json "preview": set EXPO_PUBLIC_API_URL to the laptop's LAN address first
eas build -p android --profile preview
```

The `preview` profile sets `KAAMSETU_ALLOW_HTTP=1`, and `app.config.js` then allows plain HTTP on Android so the
APK can reach `http://<LAN-IP>:8001`. Builds without it, including `production`, keep Android's HTTPS-only
default. This was checked with `expo config`: the exception is present only for preview. The EAS build itself was
not run here, because it needs an Expo account.

## 3. Hosted pilot: what must change

| Item | Demo setting | Pilot |
|---|---|---|
| `APP_ENV` | `development` | `production`: refuses weak `JWT_SECRET_KEY` and `CORS_ORIGINS=*`, hides `/docs` |
| TLS | none | a reverse proxy with HTTPS for the console and API; the app's production profile points at `https://…` |
| Request size | app checks `Content-Length` | also `client_max_body_size` at the proxy (the bundled nginx sets 11 MB) |
| `CORS_ORIGINS` | localhost dev origins | only the console's HTTPS origin (not needed when console and API share the nginx origin) |
| Demo accounts | seeded, shared password | do not run `seed.py`; create real accounts as a manager |
| Database | compose volume | managed PostgreSQL with backups; `alembic upgrade head` on deploy |
| Processes | one API process | the Gnani one-request-at-a-time guard and the rate limits are per process; add a shared limiter before scaling out |
| Audio | `AUDIO_RETENTION=none` | keep it unless there is a consent and retention policy |
| Gnani credits | developer key | a production key with monitored credit; failures already degrade to text |

## 4. Checks after a deployment

```powershell
curl http://<host>/api/v1/health/db          # {"status":"ok","database":"ok","migration_revision":"0002"}
cd e2e ; node run.mjs demo                   # full demo across both apps, against a local stack only
```

`e2e/` starts its own stack on fixed local ports, so it checks a machine's setup, not a remote deployment.
