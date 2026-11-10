# KAAMSETU

**Speak the work. Structure the action. Keep operations moving.**

KAAMSETU is a multilingual, voice-first field-workforce intelligence platform for
factory maintenance. A technician reports a machine fault by speaking in Hindi,
Telugu, English or Hinglish. Gnani **Prisma** transcribes the speech, a
deterministic extraction engine turns the transcript into a validated work-order
request, a supervisor approves and assigns it on a web dashboard, and Gnani
**Timbre** speaks acknowledgements and follow-up questions back to the technician.

Built for the Gnani AI Great Indian AI Internship Challenge.

> **Project status: Phase 6 complete (backend, supervisor console and technician app).** Spoken or typed
> reports in English, Hindi, Telugu or Hinglish become validated work orders. Each order
> moves through a role-checked lifecycle (approval, assignment, SOP checklist, completion,
> close) with a full audit trail. Supervisors run that lifecycle in the web console, which has
> a live dashboard, approvals, work-order detail with the original transcript, equipment,
> technicians, handovers, analytics, the audit log and SOP templates. Technicians report by voice
> in the Expo app, answer follow-up questions, confirm the preview, work their assigned tasks through
> the SOP checklist and hand over the shift, hearing Timbre replies in their language. End-to-end
> verification on real devices is next (Phase 7). See [docs/ROADMAP.md](docs/ROADMAP.md) and
> [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

## Why

Maintenance teams run on phone calls, WhatsApp and paper logs. Reports are
incomplete, language-mixed and invisible to supervisors until too late. KAAMSETU
keeps voice as the interface but makes the backend the source of truth: every
report becomes a structured, traceable, approval-gated work order.

## Architecture at a glance

```
Technician app (Expo) --audio/JSON-->  FastAPI /api/v1  --> PostgreSQL 16
Supervisor web (Vite) --JSON-------->       |
                                            +- gnani/prisma.py  --> api.vachana.ai  (Prisma v3.0 STT)
                                            +- gnani/timbre.py  --> api.vachana.ai  (Timbre v2.5 TTS)
                                            +- intelligence/    rule-based extraction, classification, priority
                                            +- workflows/       orchestrator, lifecycle state machine, audit
```

- **Voice is the interface.** Prisma and Timbre are called only from the backend; API keys never reach a client.
- **AI is the language layer.** Extraction is deterministic and configurable (no LLM); Gnani provides speech in and speech out.
- **The backend is the source of truth.** Every state change is validated by a state machine and written to an audit log.

Full details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL 16, PyJWT, argon2 |
| Speech | Gnani Prisma v3.0 (STT), Gnani Timbre v2.5 (TTS) via REST (`httpx`) |
| Supervisor web | React 18, TypeScript 5, Vite 6, Tailwind CSS 3, TanStack Query 5, React Router 6, Recharts 3, Vitest |
| Technician app | React Native 0.88, Expo SDK 58, TypeScript 6, expo-audio, expo-secure-store, React Navigation 7, TanStack Query 5, Jest + RNTL 14 |
| Infra | Docker Compose (Postgres + backend) |

## Repository layout

```
backend/          FastAPI application, Alembic migrations, tests
supervisor-web/   Supervisor console (Vite + React), see supervisor-web/README.md
technician-app/   Technician mobile app (Expo), see technician-app/README.md
evaluation/       Labelled multilingual test set + runner  - created in Phase 8
docs/             Architecture, DB design, API, Gnani integration, testing, demo script, roadmap
docker-compose.yml
```

## Quick start

Prerequisites: Docker Desktop (running), Python 3.12+ (`py -3.14` on this machine), Node 20+.

Ports: Postgres is published on host port **5433** and the API runs on **8001**,
because a native PostgreSQL service and another project already use 5432 and 8000
on the development machine. Override with `KAAMSETU_DB_HOST_PORT` / `KAAMSETU_API_HOST_PORT`.

```powershell
# 1. Environment
Copy-Item backend\.env.example backend\.env
# edit backend\.env: paste GNANI_API_KEY (https://app.gnani.ai/voice) and set a random JWT_SECRET_KEY

# 2. Database
docker compose up -d db

# 3. Backend
cd backend
py -3.14 -m venv .venv
$env:DISABLE_SQLALCHEMY_CEXT="1"   # see Windows note below
.\.venv\Scripts\python.exe -m pip install --no-binary sqlalchemy -r requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe scripts\seed.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8001
# API docs: http://localhost:8001/docs

# Tests (uses a separate kaamsetu_test database, created automatically; Gnani is mocked)
.\.venv\Scripts\python.exe -m pytest

# Real Gnani checks (spend a few credits)
.\.venv\Scripts\python.exe scripts\gnani_smoke.py
$env:RUN_GNANI_INTEGRATION="1"; .\.venv\Scripts\python.exe -m pytest -m integration

# 4. Supervisor console (proxies /api to the backend on 8001)
cd ..\supervisor-web ; npm install ; npm run dev     # http://localhost:5173
npm test ; npm run build

# 5. Technician app (Expo Go on a phone: set EXPO_PUBLIC_API_URL to your LAN IP and run the
#    backend with --host 0.0.0.0, see technician-app/README.md)
cd ..\technician-app ; npm install ; npx expo start
npm test ; npm run typecheck
```

Or run DB + backend together: `docker compose up --build`.

### Windows note (Smart App Control)

On a Windows machine with Smart App Control on, unsigned native binaries inside a
virtualenv are blocked. Three workarounds are built in:

- **SQLAlchemy** is installed without its Cython extensions (`--no-binary sqlalchemy`
  with `DISABLE_SQLALCHEMY_CEXT=1`). It then runs in its pure-Python mode.
- **The Postgres driver is `pg8000`**, which is pure Python, instead of `psycopg[binary]`,
  whose bundled libpq DLL is blocked.
- **Tools run as `python -m <tool>`** (`pytest`, `alembic`, `uvicorn`), because the
  pip-generated `.exe` launchers are blocked. `python.exe` itself is signed.

Inside Docker (Linux) none of this applies, but the same requirements file is used.

## Demo accounts (seeded, synthetic)

Created by `backend/scripts/seed.py` from Phase 1. All data is synthetic
industrial demo data, clearly separate from any live operational records.

| Role | Email | Language |
|---|---|---|
| Technician | tech1@kaamsetu.demo | Hinglish |
| Technician | tech2@kaamsetu.demo | Telugu |
| Technician | tech3@kaamsetu.demo | Hindi |
| Supervisor | supervisor@kaamsetu.demo | English |
| Manager | manager@kaamsetu.demo | English |

Password for every demo account: `Kaamsetu@2026`. These are synthetic demo
credentials only; change them before any shared deployment.

The seed also creates 12 machines (including `M-204`, the demo motor), three
`[DEMO SOP]` checklist templates and seven closed historical work orders marked
`report_channel = seed`. There is no self-registration: managers create accounts of
any role, and supervisors create technicians for their own site.

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/DATABASE_DESIGN.md](docs/DATABASE_DESIGN.md)
- [docs/API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md)
- [docs/GNANI_INTEGRATION.md](docs/GNANI_INTEGRATION.md)
- [docs/TESTING.md](docs/TESTING.md)
- [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md)
- [docs/ROADMAP.md](docs/ROADMAP.md)
- [docs/LIMITATIONS.md](docs/LIMITATIONS.md)

## Honesty notes

- KAAMSETU is a prototype. It is not an industrial safety certification system
  and does not diagnose machines autonomously. Checklists show only
  company-approved SOP content.
- Speech recognition and synthesis are real Gnani API calls. If the API is
  unavailable the app falls back to text and says so; it never fakes a result.
- Measured results in `evaluation/RESULTS.md` (Phase 8) are on a synthetic
  labelled set, not a real-world pilot.
