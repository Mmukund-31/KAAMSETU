# Roadmap

Phases are executed sequentially. Each ends with verification and a report; the
next starts only on confirmation. "Done" means implemented **and** verified.

| Phase | Est. | Deliverable | Status |
|---|---|---|---|
| 0 | 1 d | Repository scaffold, env template, docs skeleton, Gnani API research | done 2026-11-10 |
| 1 | 3 d | FastAPI + settings + Postgres + models + Alembic + JWT auth + RBAC + health + seed + tests | done 2026-11-10 (63 tests passing) |
| 2 | 2 d | Prisma + Timbre httpx adapters, real smoke test, mocked unit tests, gated integration tests | done 2026-11-10 (156 tests + 12 real-API tests passing) |
| 3 | 3 d | Rule-based extraction / classification / prioritisation / missing fields, orchestrator, `/voice/*` | done 2026-11-10 (334 tests + 14 real-API tests passing) |
| 4 | 3 d | Work-order CRUD, state machine, approvals, assignment, checklists, handovers, audit, dashboard APIs | done 2026-11-10 (406 tests passing; live demo scenario verified) |
| 5 | 4 d | Supervisor web (Vite + React + Tailwind + Recharts) | done 2026-11-10 (37 web tests; 31-check live UI run against the real backend) |
| 6 | 4 d | Technician Expo app (record, upload, preview, confirm, tasks, checklist, handover) | done 2026-11-10 (29 app tests; 27-check live run with real Prisma + Timbre; M4A verified) |
| 7 | 2 d | End-to-end verification of the demo scenario + error paths | done 2026-11-10 (`e2e/` 74/74 against real APIs; phone checklist pending, run by the user) |
| 8 | 3 d | Evaluation dataset + measured results, coverage, security review, Docker check, polish | done 2026-11-10 (held-out 45% whole-report; coverage 96% / 92% / 92%; 0 vulns in shipped web deps; Docker verified) |
| 9 | 2 d | README, screenshots, demo script, limitations, submission write-up | done 2026-11-10 (submission docs; console in Docker Compose; Android preview profile; final verification) |

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

## Phase 3 output

- `app/intelligence/`: `text` (normalisation, clauses, negation, yes/no), `numbers` (spoken letters and numbers in
  4 languages), `extraction`, `classification`, `prioritization`, `missing_fields`, `drafting`, `response`, plus a typed
  `config_loader` that rejects invalid YAML at load time.
- `app/intelligence/config/`: `taxonomy.yaml` (26 symptoms, production-impact patterns), `priority_rules.yaml`
  (8 ordered rules), `workflow_policy.yaml`, `responses.yaml` (6 messages x 4 languages).
- `app/workflows/evidence.py` (signed evidence token) and `app/workflows/orchestrator.py`.
- Routes: `process-report`, `process-text` (typed report or transcript correction), `follow-up`, `evaluate-draft`.
- `app/domain/enums.py`: pure enums; `app.models.enums` re-exports them.
- Fixed a Phase 2 bug: `/openapi.json` and `/docs` returned 500 because of an invalid `responses=` declaration on
  `/voice/synthesize`. A test now covers the schema.
- Tests: 44 labelled extraction cases (en / hinglish / hi / te, 14 of them real Prisma transcripts); number parsing;
  every priority rule; classification; drafting; templates; config integrity; evidence tokens; 34 API flow tests;
  a layering guard; 2 real end-to-end pipeline tests.

## Phase 4 inputs from Phase 3

- `POST /work-orders` must take `{evidence_token, draft, submission_key}`. It verifies the token, re-runs
  `orchestrator.evaluate`, requires `next_action == confirm_preview`, then writes `work_orders`,
  `work_order_evidence` (from the token's utterances) and `audit_logs`.
- `priority_rule` is already a column on `work_orders`.

## Phase 4 output

- `app/services/state_machine.py`: one transition table with role, assignee or reporter, reason and dedicated-action
  rules, plus guards (assigned technician, self-approval, checklist complete). `allowed_actions` drives UI buttons.
- `app/workflows/work_order.py`: create from confirmed evidence (re-validated, duplicate-proof), approve with priority
  override, reject, escalate, complete, generic status, edits. `assignment.py`: assign or reassign, which auto-attaches
  the SOP checklist. `escalation.py`: SLA due dates and the overdue rule.
- `app/services/`: `access` (site and ownership scope, row lock for actions), `checklists` (versioned templates, steps),
  `work_orders` (list, filters, detail), `equipment` (register and history), `handovers` (fact-based summary),
  `dashboard` (SQL aggregates).
- 27 new routes: 38 in total.
- Migration `0002`: evidence `report_id`, audit `seq`, `clock_timestamp()` defaults.
- Tests: the demo scenario end to end with an exact audit trail, every lifecycle rule, the transition-table
  structure, creation and duplicate protection, scope, filters, checklists, handovers, exact dashboard numbers
  including a cross-site regression guard, and equipment, users and audit.
- Live check on the dev server with real Prisma and Timbre: report, create (WO-1008), duplicate 409, approve, assign,
  start, checklist gate, 7 steps, complete, close, and dashboard +1. The test order was then removed from the dev DB.

## Phase 5 inputs from Phase 4

- The web app can build its action buttons from `allowed_actions` and `can_assign`. Disabled buttons show
  `blocked_reason`.
- The approval queue is `GET /work-orders?status=under_review&status=escalated&sort=priority`.
- Every dashboard tile maps to one field of `GET /dashboard/overview`.

## Phase 5 output

- `supervisor-web/`: React 18 + TypeScript (strict) + Vite 6 + Tailwind 3 + TanStack Query 5 + Recharts 3.
  It uses a fetch wrapper rather than axios, since one wrapper with the error envelope and 401 handling was all
  that was needed.
- Pages: Login, Overview (15 s polling), Approvals (new reports, completion review), Work orders (URL filters),
  Work-order detail, Equipment and detail, Technicians (add account), Handovers and detail (review), Analytics,
  Audit log, Settings (SOP template versions).
- The work-order detail page shows the verbatim transcript next to the structured order. Action buttons come from
  `allowed_actions`, with disabled reasons. It covers approve with a priority override and reason, reject or
  escalate with a reason, assign or reassign, edit with audit, the checklist with progress, and history.
- Tests: 37 Vitest + Testing Library tests: API client, formatting, login and role gate, session expiry, list
  filters, approval queue, detail actions, assign, handover review, template publish, and empty states.
- Live check (headless Edge, real backend on 8001, real PostgreSQL), 31 checks, all passed. A technician reported
  through `/voice/process-text`. The supervisor then approved with a priority override, assigned, watched the
  technician finish through the API, and closed the order. The checks covered the audit trail, dashboard and
  equipment updates, every page, no horizontal scroll at 390 px, the mobile menu, sign-out and zero console
  errors. The test orders (WO-1009 to WO-1014) were removed afterwards; the dev DB is back to the seed.
- Found and fixed during the live run:
  - The Close dialog had two controls labelled "Close". They are now "Close work order" and "Dismiss dialog".
  - At phone width the overview scrolled sideways, because grid columns grew to fit a wide table. Cards are now
    `min-w-0`.
  - The trend chart smoothed daily counts. It now draws straight segments with daily dots.
  - The supervisor view had a block for the task announcement, but the API sends that text only to the assigned
    technician, so the block could never show. It was removed.

## Phase 6 output

- `technician-app/`: Expo SDK 58 (React Native 0.88, React 19.3, TypeScript 6), expo-audio, expo-secure-store,
  React Navigation 7 (tabs plus a task stack), TanStack Query 5, Ionicons.
- Flow: sign in (technicians only) → language (once) → Report (mic with a 30 s cap, or type) → Review (spoken reply,
  transcript correction, registered-machine picker, follow-up by one tap, voice or text) → Preview (editable,
  priority with explanation) → Send (one idempotency key per report; 409 duplicate shown as already sent) →
  spoken acknowledgement.
- My work: assigned tasks and my reports. Task: announcement shown and spoken, start, blocked or parts (reason), SOP
  checklist (N/A or failed needs a note), complete blocked until the mandatory steps are done, spoken confirmation.
- Handover: voice (Prisma transcript) or text, with the record-based summary.
- Interface text in English, Hinglish, Hindi and Telugu, with key-parity and placeholder tests. Hindi and Telugu still
  need native-speaker review.
- Tests: 29 Jest + RNTL 14 tests covering strings, the API client, sign-in and roles, session restore and expiry,
  recording and upload, mic denied, the 30 s auto-stop, busy speech service, follow-up by tap and by voice, unknown
  machine, typed report and submit, duplicate, report incomplete, task list, start, checklist rules, blocked reason,
  complete with voice, and handover.
- Builds: web export and Android + iOS Hermes bundles compile.
- **M4A settled:** Prisma accepts AAC in MP4. A Windows Media Foundation fixture `hinglish_m204.m4a` was added with a
  format unit test and a gated real-Prisma test, which passed.
- Live run (Edge, 390 px, fake microphone playing a Timbre clip, real backend, Prisma and Timbre): 27 of 27 checks
  passed. The app's own recorder produced `audio/mp4;codecs=mp4a.40.2`. A recording cut off at
  "production abhi." correctly triggered the production follow-up, which was answered by voice. The run covered two
  work orders, the unknown-machine picker, an assigned task announced in voice and text, start, 7 checklist steps,
  complete, a spoken handover, switching to Telugu, sign-out and zero console errors. Test records removed afterwards;
  the dev DB is back to the seed.
- Fixed during the run: emoji icons looked inconsistent on Windows (now Ionicons); the Telugu title was clipped (title
  line height); the task screen showed the announcement only as audio (now also text).
- No Gnani key, host or auth header in any client bundle (scanned).

## Phase 7 output

- `e2e/`: one-command harness (`node run.mjs`). It starts two backends, a Gnani fault proxy, the supervisor console
  and two technician web builds; drives three browser contexts with a fake microphone; cites PostgreSQL rows; cleans
  up to the starting counts; and scans the logs for secrets.
- Demo scenario, 32 checks: Hinglish voice report → preview (2.4–3.0 s) → work order with spoken acknowledgement
  (1.1–1.5 s) → visible in the supervisor queue (0.8–1.3 s) → approve and assign → Telugu announcement → 7 steps →
  complete → close. The audit trail is in exact order and the Prisma request id and verbatim transcript are in
  `work_order_evidence`.
- Error paths, 34 checks: unknown machine, follow-up, silence, 30 s limit, Prisma 429 and recovery, Prisma 500 with
  typing, Timbre 500 with text-only, double tap and parallel submissions, simultaneous approvals (the race test
  carried over from Phase 4), roles and scope, checklist gate, token expiry in both apps, server unreachable.
- Bugs found and fixed:
  1. **Fragmented MP4 measured as 0.06 s.** Browser MediaRecorder output was rejected as "too short". The backend
     now reads fragment durations (`fragmented_mp4_duration`), with fixture `browser_fragmented_3s.m4a` and tests.
  2. **The 30 s auto-stop overshot to over 30 s.** It now stops at 29.5 s and measured 29.68 s, which was accepted.
  3. **"Session ended" notice lost.** A restored, expired session lost the notice in both apps, because the restore
     code signed out a second time.
  4. **Typed report lost after a failed send.** The text now survives errors.
- `docs/DEMO_SCRIPT.md` rewritten with measured timings, the DB evidence of one run, and "if something goes wrong on
  stage" lines that were each triggered for real. `docs/DEVICE_TEST.md` is a 13-step phone checklist.
  `docs/screenshots/` holds 10 screenshots from the run.

## Phase 8 output

- **Evaluation** (`evaluation/`):
  - v1, 40 held-out reports, measured as-is: whole report correct 72% for text, 68% clean, 68% noisy. The gaps
    were then fixed, with regression tests.
  - v2, 20 new held-out reports, run once: 45% / 45% / 45%. Equipment 95%, category 100%, safety 95%, symptom
    precision 0.95 and recall 0.79, production impact 65–70%.
  - 9 of 20 v2 misses became a follow-up question, and 2 a wrong preview, one of them a missed safety concern
    (fixed afterwards).
  - Prisma: WER about 0 in en, Hinglish and te, and 0.3 in Hindi (script, not meaning). Auto-detection labels
    Hinglish as hi-IN, which confirms the explicit en-IN choice.
- **Coverage:** backend 95.9% of app lines (every layer ≥ 84%; services 94%, workflows 96%, intelligence 96%);
  supervisor-web 91.6% lines (49 tests); technician-app 91.7% lines (39 tests).
- **Security** (`docs/SECURITY.md`):
  - route-by-route auth and role tests generated from the app's route list;
  - security headers; API docs hidden in production; production refuses `CORS_ORIGINS=*`;
  - React Router 7.18.5 and Vitest 5.1.0 upgrades (0 npm vulnerabilities in supervisor-web);
  - pip-audit clean; bandit clean apart from 2 false positives; git history free of secrets.
- **Docker:** non-root image with a health check. 489 backend tests pass inside the container on Python 3.12, and
  `docker compose up` was healthy, with migrations at 0002, real Prisma working and clean logs.
- **Polish:** `PATCH /auth/me` (own language). The technician app saves a language switch on the account, so task
  announcements follow it. This closes a Phase 6 limitation.
- **Regression:** `e2e/` 74 of 74 after all changes.

## Phase 9 output

- **Build completed:**
  - The supervisor console is now in Docker Compose (`supervisor-web/Dockerfile`, nginx forwarding `/api`), so
    `docker compose up -d --build` runs the database, API and console.
  - Verified in a browser through nginx: sign-in, the 7 seed orders, detail, analytics, deep-link reload, no console
    errors.
- **Technician app:**
  - `eas.json` with an Android `preview` APK profile.
  - `app.config.js` allows plain HTTP only for that profile (checked with `expo config`). The EAS build itself
    needs an Expo account and was not run.
- **Docs:**
  - `docs/SUBMISSION.md` (challenge write-up; the individual-contribution section is left for the submitter);
  - `docs/DEPLOYMENT.md`, `docs/DEMO_VIDEO.md` (shot list);
  - a rewritten `README.md` with screenshots (13 in `docs/screenshots/`).
- **Final verification:** see `docs/TESTING.md` (2026-11-10, Phase 9 rows).

## Phase 9 inputs from Phase 8

- Submission write-up should quote the held-out numbers (v2 45%, v1 68%) alongside the after-fix ones, and the
  outcome breakdown (most misses become a follow-up).
- The phone run (`docs/DEVICE_TEST.md`) is still the one unverified link.

## Phase 8 inputs from Phase 7

- Run `docs/DEVICE_TEST.md` on a phone (the user), and feed real recordings into the evaluation set.
- The harness is the regression gate: run `node e2e/run.mjs` after every change in Phase 8.

## Phase 7 inputs from Phase 6

- Run in Expo Go on a real phone (`EXPO_PUBLIC_API_URL` = LAN IP, backend `--host 0.0.0.0`) and record with a real
  microphone in a noisy room, in all four languages.
- Walk the demo script across both apps: phone report → web approve and assign → phone checklist and complete → web
  close.

## Phase 6 inputs from Phase 5

- Technician flows the web app does not cover: recording, transcript review, follow-up questions, preview and
  confirm, my tasks, starting work, checklist steps, completion, handovers by voice.
- `task_announcement` is returned only to the assignee, so the mobile app should play it with Timbre.
