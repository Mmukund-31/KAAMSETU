# Roadmap

Phases are executed sequentially. Each ends with verification and a report; the
next starts only on confirmation. "Done" means implemented **and** verified.

| Phase | Est. | Deliverable | Status |
|---|---|---|---|
| 0 | 1 d | Repository scaffold, env template, docs skeleton, Gnani API research | done 2026-11-10 |
| 1 | 3 d | FastAPI + settings + Postgres + models + Alembic + JWT auth + RBAC + health + seed + tests | done 2026-11-10 (63 tests passing) |
| 2 | 2 d | Prisma + Timbre httpx adapters, real smoke test, mocked unit tests, gated integration tests | done 2026-11-10 (156 tests + 12 real-API tests passing) |
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

## Phase 2 output

- `app/gnani/`: typed errors; shared httpx client with retry on 429/5xx/timeouts, one-in-flight guard, error-envelope mapping; Prisma and Timbre adapters.
- `app/services/audio.py`: magic-byte format detection, duration (custom RIFF parser plus mutagen), size and length limits.
- `app/services/speech.py`: language resolution, site equipment codes as keyterms, Gnani error to API error mapping.
- Routes `POST /api/v1/voice/transcribe` and `POST /api/v1/voice/synthesize`.
- `scripts/gnani_smoke.py`: real round trip in all four languages.
- Tests: 93 new mocked tests (adapters, retries, error mapping, audio validation, voice API), 12 real-API integration tests.
- Real measurements recorded in `docs/GNANI_INTEGRATION.md` "Measured"; Hinglish set to Prisma `en-IN`.

## Phase 3 inputs from Phase 2

- Equipment codes arrive as `M-204`, `M204`, `M 204`, and in Telugu as number words (`ఎం రెండు వందల నాలుగు`). The extractor must normalise all of them and validate against the registry.
- Hinglish transcripts are Latin script; Hindi transcripts are Devanagari with some English words in Latin; Telugu transcripts are Telugu script with English loanwords transliterated (`వైబ్రేషన్`, `ప్రొడక్షన్`).

## Phase 3 file list (next)

`app/intelligence/{extraction,classification,prioritization,missing_fields,response,numbers}.py`,
`app/intelligence/config/{taxonomy,priority_rules,required_fields,responses}.yaml`, `app/workflows/orchestrator.py`,
`app/schemas/report.py`, additions to `app/api/v1/voice.py` (`process-report`, `process-text`, `follow-up`),
and table-driven tests in `app/tests/unit/test_extraction.py` and siblings.
