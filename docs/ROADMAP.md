# Roadmap

Phases are executed sequentially. Each ends with verification and a report; the
next starts only on confirmation. "Done" means implemented **and** verified.

| Phase | Est. | Deliverable | Status |
|---|---|---|---|
| 0 | 1 d | Repository scaffold, env template, docs skeleton, Gnani API research | done 2026-11-10 |
| 1 | 3 d | FastAPI + settings + Postgres + models + Alembic + JWT auth + RBAC + health + seed + tests | done 2026-11-10 (63 tests passing) |
| 2 | 2 d | Prisma + Timbre httpx adapters, real smoke test, mocked unit tests, gated integration tests | pending |
| 3 | 3 d | Rule-based extraction / classification / prioritisation / missing fields, orchestrator, `/voice/*` | pending |
| 4 | 3 d | Work-order CRUD, state machine, approvals, assignment, checklists, handovers, audit, dashboard APIs | pending |
| 5 | 4 d | Supervisor web (Vite + React + Tailwind + Recharts) | pending |
| 6 | 4 d | Technician Expo app (record, upload, preview, confirm, tasks, checklist, handover) | pending |
| 7 | 2 d | End-to-end verification of the demo scenario + error paths | pending |
| 8 | 3 d | Evaluation dataset + measured results, coverage, security review, Docker check, polish | pending |
| 9 | 2 d | README, screenshots, demo script, limitations, submission write-up | pending |

## Phase 0 output

- Root: `README.md`, `.gitignore`, `.editorconfig`, `docker-compose.yml`
- `backend/`: `requirements.txt` (pinned, verified on Python 3.14), `pyproject.toml`, `Dockerfile`, `.env.example`, `app/` package skeleton
- `docs/`: this file plus ARCHITECTURE, DATABASE_DESIGN, API_DOCUMENTATION, GNANI_INTEGRATION, TESTING, DEMO_SCRIPT
- Placeholders: `supervisor-web/`, `technician-app/`, `evaluation/`
- Environment finding: Windows Smart App Control blocks unsigned native binaries in the venv.
  Resolved by using `pg8000`, installing SQLAlchemy without C extensions, and running tools via `python -m`.
- Open item before Phase 1 database work: start Docker Desktop (the daemon was not running).

## Phase 1 output

- Settings (`app/config.py`), JSON logging with secret redaction, uniform error envelope, in-memory rate limiter.
- 12 SQLAlchemy models with 11 PostgreSQL enums; migration `0001_initial_schema` (upgrade, downgrade and drift-checked).
- argon2id passwords, HS256 JWT, `get_current_user` and `require_roles` dependencies.
- Routes: `/health`, `/api/v1/health`, `/api/v1/health/db`, `/api/v1/auth/{login,register,me}`.
- `scripts/seed.py`: idempotent synthetic site, 5 users, 12 machines, 3 `[DEMO SOP]` templates, 7 closed historical orders.
- Tests: 63 passing (auth, RBAC, token handling, rate limit, validation, schema constraints, migrations, seed, redaction).
- Live check: server started against the dev DB; login, `me`, register RBAC, 401/403, docs and CORS behaved as expected; a scan found no secret, password or token in the server log.
- Environment findings: a native PostgreSQL 17 service holds port 5432, so the container uses 5433; another project serves on 8000, so KAAMSETU uses 8001.

## Phase 2 file list (next)

`app/gnani/{base,errors,prisma,timbre}.py`, `app/services/audio.py`, `app/schemas/voice.py`, `app/api/v1/voice.py`,
`scripts/gnani_smoke.py`, `app/tests/unit/test_gnani_prisma.py`, `app/tests/unit/test_gnani_timbre.py`,
`app/tests/unit/test_audio_validation.py`, `app/tests/integration/test_gnani_real.py`, and the "Measured" section of
`docs/GNANI_INTEGRATION.md`.
