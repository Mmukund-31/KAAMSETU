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
| 2026-11-10 | Phase 4: unit + API incl. lifecycle, permissions, checklists, handovers, dashboard, audit | 406 passed |
| 2026-11-10 | Phase 4: live HTTP walk-through of the demo scenario on the dev server (real Prisma + Timbre, real PostgreSQL) | passed (13 checks) |
| 2026-11-10 | Phase 5: supervisor-web Vitest + Testing Library, API mocked with backend-shaped fixtures | 37 passed |
| 2026-11-10 | Phase 5: live UI run in headless Edge against the real backend and PostgreSQL (report, approve with override, assign, technician completes, close; every page; 390 px layout; console errors) | 31 of 31 checks passed |
| 2026-11-10 | Phase 5: backend regression after the web work | 406 passed, 14 skipped (integration) |
| 2026-11-10 | Phase 6: technician-app Jest (jest-expo) + React Native Testing Library 14, native modules faked | 29 passed |
| 2026-11-10 | Phase 6: Expo web export and Android + iOS Hermes bundles | compiled |
| 2026-11-10 | Phase 6: M4A (AAC/MP4) through real Prisma: Media Foundation files via `/voice/process-report`, plus new gated test `test_prisma_accepts_aac_m4a_like_phone_recordings` | passed |
| 2026-11-10 | Phase 6: live run of the technician web build in headless Edge with a fake microphone, real backend, Prisma and Timbre | 27 of 27 checks passed |
| 2026-11-10 | Phase 6: backend after adding the m4a fixture | 407 passed, 15 skipped (integration) |
| 2026-11-10 | Phase 7: `e2e/` demo scenario across both apps (real backend, Prisma, Timbre, PostgreSQL evidence) | 32 of 32 checks passed |
| 2026-11-10 | Phase 7: `e2e/` error paths E1–E12 (fault proxy for Gnani 429/500, real short-lived tokens, races, roles, offline) | 34 of 34 checks passed |
| 2026-11-10 | Phase 7: full `node run.mjs all` from fresh builds, incl. preflight, cleanup back to seed counts, log secret scan | 74 of 74 checks passed |
| 2026-11-10 | Phase 7: backend after the fragmented-MP4 duration fix | 410 passed, 15 skipped (integration) |
| 2026-11-10 | Phase 7: supervisor-web after the session-expiry fix | 39 passed |
| 2026-11-10 | Phase 7: technician-app after the 29.5 s stop, session notice and kept-text fixes | 30 passed |
| 2026-11-10 | Phase 8: evaluation v1 held-out (40 reports, real Prisma), before any change | whole report 72% text / 68% clean / 68% noisy |
| 2026-11-10 | Phase 8: evaluation v2 held-out (20 new reports), run once | whole report 45% / 45% / 45% |
| 2026-11-10 | Phase 8: backend incl. security, profile and rule-fix tests | 489 passed, 15 skipped; coverage 95.9% of app lines |
| 2026-11-10 | Phase 8: backend inside the Docker image (Python 3.12, non-root) | 489 passed, 15 skipped |
| 2026-11-10 | Phase 8: supervisor-web after the React Router 7 / Vitest 5 upgrade | 49 passed; coverage 91.6% lines |
| 2026-11-10 | Phase 8: technician-app | 39 passed; coverage 91.7% lines |
| 2026-11-10 | Phase 8: `e2e/` full regression after all Phase 8 changes | 74 of 74 checks passed |
| 2026-11-10 | Phase 9: `docker compose up -d --build` (db, backend, nginx console) as written in the README, seed, browser check through nginx | healthy; sign-in, 7 orders, detail, analytics, deep-link reload, no console errors |
| 2026-11-10 | Phase 9 final: backend / supervisor-web / technician-app | 494 passed (15 skipped) / 49 passed / 39 passed; web build and web+Android+iOS bundles compiled |
| 2026-11-10 | Phase 9 final: `e2e/` all scenarios from fresh builds | 74 of 74 checks passed; DB back to seed counts; logs clean |

Concurrency is covered by the end-to-end harness (Phase 7, E8):
- two supervisors approving one order at the same moment give 200 + 409, with exactly one approval audited;
- five parallel submissions of one report give one 201 and four 409, both with the same idempotency key and with
  different keys.

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

### Evaluation and coverage (Phase 8)

- Accuracy: `evaluation/run_eval.py` (see `evaluation/RESULTS.md`). The v1 and v2 held-out numbers were measured
  before any tuning on them, and later runs are labelled as not held out.
- Coverage: backend `python -m pytest --cov=app --cov-report=json:coverage.json` then
  `python scripts/coverage_by_layer.py coverage.json`; web and app `npm run coverage`. These are line coverage
  figures. The 15 real-API integration tests are not included in the backend number.
- Security checks: `app/tests/api/test_security.py` (route inventory, 401 / 403, forged tokens, headers,
  production settings) and `docs/SECURITY.md` for the audit commands.

### End-to-end harness (Phase 7)

`e2e/run.mjs` starts its own stack, drives both apps in headless Edge with a fake microphone, and checks the API
payloads, Timbre playback, the recording format, timings and the PostgreSQL rows (`e2e/tools/db.py`). Gnani failures
are injected by a pass-through proxy in front of a second backend, so the real API is used before and after each
fault. Details and the list of scenarios: `e2e/README.md`. The phone run is the manual checklist in
`docs/DEVICE_TEST.md`.

### Technician app (Phase 6)

`technician-app/src/test/`: `setup.ts` replaces the native modules with fakes. The fake expo-audio recorder
publishes its status like the real hook, so the 30 s auto-stop is testable; the player records what it played. The
secure store, crypto and file system are faked too. `harness.tsx` swaps `fetch` for a route table with
backend-shaped fixtures, and multipart bodies stay inspectable (`form.get("language")`).

The live run used Chromium's fake capture device (`--use-file-for-fake-audio-capture`) playing a Timbre-generated
WAV. It exercises the app's real recorder, upload, Prisma, extraction and Timbre playback. It does not measure
accuracy on human speech or phone microphones; that is Phases 7 and 8.

### Supervisor web (Phase 5)

`supervisor-web/src/test/`: `harness.tsx` replaces `fetch` with a route table and fixtures shaped exactly like
the backend schemas. Unmatched requests fail loudly. The tests cover:

- the API client: error envelope, a 401 clears the session, network errors;
- labels and audit rendering;
- login, including refusing technicians, and session restore and expiry;
- work-order list filters and the approval-queue query;
- detail actions built from `allowed_actions`: blocked reasons, the priority override needing a reason, reject
  needing a reason, server errors shown in the dialog, assignment;
- handover review, template publishing, and empty states.

The live UI run used Playwright (`playwright-core` driving the installed Microsoft Edge). It ran from the session
scratchpad and is not a project dependency yet. A committed Playwright smoke test is a Phase 8 option.

## Commands

```powershell
cd backend
# Use "python -m" - pip's .exe launchers are blocked by Smart App Control on the dev machine.
.\.venv\Scripts\python.exe -m pytest                       # unit + api (integration auto-skipped)
$env:RUN_GNANI_INTEGRATION="1"; .\.venv\Scripts\python.exe -m pytest -m integration
.\.venv\Scripts\python.exe -m ruff check app

cd ..\supervisor-web
npm test ; npm run typecheck ; npm run build

cd ..\technician-app
npm test ; npm run typecheck ; npm run export:native

cd ..\e2e
npm install ; node run.mjs            # all scenarios; real Gnani calls
```
