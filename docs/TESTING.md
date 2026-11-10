# Testing Strategy

## Tiers

| Tier | Location | Runs | Uses |
|---|---|---|---|
| Unit | `backend/app/tests/unit/` | always | pure intelligence functions, state-machine table, Gnani adapters with mocked `httpx` |
| API | `backend/app/tests/api/` | always | FastAPI TestClient against a throwaway Postgres DB (`DATABASE_URL_TEST`), Gnani mocked |
| Integration | `backend/app/tests/integration/` | only with `RUN_GNANI_INTEGRATION=1` and `GNANI_API_KEY` | **real** Prisma and Timbre requests |
| Evaluation | `evaluation/run_eval.py` | on demand | real Prisma + extraction over the labelled dataset |
| Frontend | `supervisor-web` (vitest), `technician-app` (jest) | always | component + flow tests with mocked API |
| E2E | manual scripted walkthrough (Phase 7), optional Playwright | before demo | real backend, real Gnani |

A mocked test passing never counts as proof that the real integration works.
Integration test results are reported separately with request IDs and latencies.

## Backend test matrix (what must be covered)

- Auth: register, login, wrong password, expired/invalid token, `me`
- RBAC: every protected route x role
- Work orders: create from valid draft, reject unknown equipment, duplicate `submission_key` -> 409, filters, pagination
- Extraction: table-driven across ~40 transcripts (en/hi/hinglish/te): equipment code forms, symptoms, impact, safety, missing fields
- Priority rules: each rule and ordering
- State machine: every allowed transition; forbidden transitions; role checks; self-approval block; comment-required
- Approval / rejection / priority override -> audit rows
- Assignment, checklist gating (mandatory incomplete -> 409), handover creation + review
- Gnani adapters: success, 401, 402, 429 then success, 500, timeout, malformed body; TTS failure -> text fallback in `/voice/process-report`
- Audio validation: oversize, wrong type, too long

## Results so far

| Date | Suite | Result |
|---|---|---|
| 2026-11-10 | Phase 1: unit + API (auth, RBAC, schema, migrations, seed) | 63 passed |
| 2026-11-10 | Phase 2: unit + API, Gnani mocked | 156 passed |
| 2026-11-10 | Phase 2: real Gnani integration (`-m integration`) | 12 passed |
| 2026-11-10 | `scripts/gnani_smoke.py`, real round trip in en / hi / te / hinglish | passed |
| 2026-11-10 | Phase 3: unit + API (extraction, rules, evidence, report flow), Gnani mocked | 334 passed |
| 2026-11-10 | Phase 3: real Gnani integration incl. end-to-end report pipeline (Hinglish demo, Telugu with voice follow-up) | 14 passed |

### Extraction test set (Phase 3)

`app/tests/unit/extraction_cases.py` holds 44 labelled cases: 14 English, 12 Hinglish, 10 Hindi, 8 Telugu.
14 of them are real Prisma transcripts captured in Phase 2. All 44 pass. That is a regression
test the rules were written against, not an independent accuracy measurement. The independent
measurement on held-out recordings, including human speech, is Phase 8.

The integration tests and smoke script use Timbre-generated speech as input, so they prove
the integration works. They do not measure accuracy on human speech.

## Evaluation dataset (Phase 8)

~40 synthetic reports, 10 per language, labelled with expected
`equipment_id, category, symptoms, production_impact, missing_fields`.
Metrics: per-field accuracy, transcript similarity to reference text, language
agreement, end-to-end work-order creation success. Results are reported as
measured on synthetic data; they are not pilot results.

Targets (aspirational, not guaranteed): at least 90 % required-field extraction accuracy on the
labelled set; 100 % pass on permission and state-transition tests; zero work orders for
invalid equipment IDs; real Prisma + Timbre demonstrated end to end.

## Commands

```powershell
cd backend
# Use "python -m" - pip's .exe launchers are blocked by Smart App Control on the dev machine.
.\.venv\Scripts\python.exe -m pytest                       # unit + api (integration auto-skipped)
$env:RUN_GNANI_INTEGRATION="1"; .\.venv\Scripts\python.exe -m pytest -m integration
.\.venv\Scripts\python.exe -m ruff check app
```
