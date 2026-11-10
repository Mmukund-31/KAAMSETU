# KAAMSETU Architecture

## Philosophy

Voice is the interface. AI is the intelligence layer. The backend is the source of
truth. Workflows produce the business outcome.

## Style: modular monolith

One FastAPI process, one PostgreSQL database, two thin clients. No microservices,
no message queue, no Redis. Real-time needs are met by polling (15 s) on the
dashboard; WebSockets are deferred unless the demo shows a need.

```
+-----------------------+          +----------------------------------------------------------+
| Technician app (Expo) |--audio-->| FastAPI  /api/v1                                         |
| record > review >     |<--tts----|                                                          |
| confirm > tasks       |          |  api/       thin routers, auth deps, request/response     |
+-----------------------+          |     |                                                    |
+-----------------------+          |  services/ + workflows/   business rules, state machine  |
| Supervisor web (Vite) |--json--->|     |                                                    |
| dashboard > approvals |          |  models/ (SQLAlchemy 2)  -->  PostgreSQL 16 (Alembic)    |
+-----------------------+          |                                                          |
                                   |  intelligence/  pure functions: extract > classify >     |
                                   |                 prioritise > missing fields > respond    |
                                   |  gnani/         prisma.py (STT), timbre.py (TTS)         |--> api.vachana.ai
                                   +----------------------------------------------------------+
```

## Layering rules (enforced in code review)

1. `api/` routes contain no business logic; they validate input, call a service, shape output.
2. `intelligence/` never imports SQLAlchemy or touches the DB. It is pure and table-tested.
3. `gnani/` is the only package that knows the Gnani host, headers and payloads.
4. Every work-order state change goes through `services/state_machine.py`, which validates the
   transition, checks the actor's role, and writes an `audit_logs` row in the same transaction.
5. The AI layer never executes DB operations; it returns a proposal that the orchestrator validates.
6. Secrets live in `backend/.env` only. Clients talk to the backend, never to Gnani.

## Voice-to-work-order pipeline

```
audio (m4a <= 30 s)
  -> services/audio.validate()          type, size, duration
     -> gnani/prisma.transcribe()       Prisma v3.0, language hint or indic-auto, equipment codes as keyterms
        -> intelligence/extraction      equipment code, symptoms, production impact, safety, location
           -> workflows/orchestrator
                - resolve equipment against DB (exact > normalised > suggestions)
                - intelligence/classification  -> category
                - intelligence/prioritization  -> priority + rule id
                - intelligence/missing_fields  -> follow-up question(s)
                - next_action in {fix_equipment, ask_follow_up, confirm_preview}
                  -> intelligence/response -> text -> gnani/timbre.synthesize() (optional, falls back to text)
  technician confirms preview
  -> workflows/work_order.create()  re-validates, writes work_orders + work_order_evidence (immutable) + audit_logs
```

The original transcript is stored verbatim in `work_order_evidence` and is never
overwritten by edits; technician corrections are stored as the work order's
`issue_description` and the extracted JSON, and the diff is auditable.

## Work-order lifecycle

```
REPORTED -> UNDER_REVIEW -> APPROVED -> ASSIGNED -> IN_PROGRESS -> COMPLETION_REVIEW -> CLOSED
               |                                      |   ^                                |
               v                                      v   |                                v
            REJECTED                 BLOCKED / AWAITING_PARTS / ESCALATED             REOPENED -> ASSIGNED
```

The full transition table with roles lives in `docs/DATABASE_DESIGN.md` and is
the single source of truth for `services/state_machine.py`.

## Decision log

| # | Decision | Why |
|---|---|---|
| 1 | Rule-based extraction, no LLM | Gnani offers no text-generation API; rules are deterministic, offline-testable, and cannot hallucinate equipment IDs. |
| 2 | `httpx` against the REST contract, not the `gnani-vachana` SDK | Full control of timeouts, retries, logging; SDK defaults to a withdrawn TTS model. |
| 3 | Sync SQLAlchemy sessions | Simpler; request volume is small; no async DB driver complexity. |
| 4 | Single `GNANI_API_BASE_URL` | Prisma and Timbre share `https://api.vachana.ai`; paths are constants. |
| 5 | No Redis / queue / WebSockets | No real async need in the MVP; polling suffices for the demo. |
| 6 | Audio not retained by default | Privacy and storage; `AUDIO_RETENTION` policy switch exists for pilots. |
| 7 | Audit log doubles as status history | One immutable table, action `work_order.transition`, avoids duplication. |
| 8 | Argon2 for passwords, PyJWT HS256 for tokens | Modern, maintained, no legacy bcrypt pitfalls. |
| 9 | `pg8000` Postgres driver, SQLAlchemy without C extensions on Windows | Smart App Control on the dev machine blocks psycopg-binary's libpq DLL and SQLAlchemy's Cython modules. Both replacements are pure Python and officially supported by SQLAlchemy. |
| 10 | No self-registration | Open sign-up would let anyone choose the manager role. Managers create any role; supervisors create technicians at their own site. |
| 11 | Role re-read from DB on every request | A role change or deactivation takes effect immediately, even for tokens already issued. |
| 12 | DB errors classified by SQLSTATE | pg8000 reports foreign-key violations as `ProgrammingError`; `app/database/errors.py` gives one driver-independent check. |
| 13 | Dev ports 5433 (DB) and 8001 (API) | A native PostgreSQL 17 service and another project already use 5432 and 8000 on the dev machine. |
