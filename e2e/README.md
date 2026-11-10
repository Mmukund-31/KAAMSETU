# e2e: end-to-end harness

Both KAAMSETU apps, driven in headless Microsoft Edge against the real backend, real PostgreSQL and **real Gnani
Prisma and Timbre**. One command starts its own stack, runs the scenarios, cites the database rows, deletes what it
created, checks the server logs for secrets and writes a report.

```powershell
# prerequisites: Docker DB up and seeded, backend\.env with GNANI_API_KEY, npm install done in
# supervisor-web and technician-app, Microsoft Edge installed (Windows)
cd e2e
npm install
node run.mjs            # demo + error paths (about 4 min incl. two app builds; spends a few Gnani credits)
node run.mjs demo       # only the demo scenario
node run.mjs errors --no-build   # reuse the last app builds
node run.mjs all --docs # also copy the key screenshots to docs/screenshots
node run.mjs demo --keep         # leave the created records in the DB (ids in .run/created.txt)
```

Output in `e2e/.run/` (git-ignored): `report.md` (every check), `results.json` (timings and evidence), `shots/`,
`logs/` (server logs).

## What it starts (and only that)

| Port | Process | Notes |
|---|---|---|
| 8001 | backend (uvicorn) | real Gnani API |
| 8002 | second backend | its `GNANI_API_BASE_URL` points at the fault proxy |
| 8099 | Gnani fault proxy (in-process) | forwards to `https://api.vachana.ai` unchanged, or answers 429 / 500 when a fault is switched on |
| 5173 | supervisor-web (Vite dev) | proxies `/api` to 8001 |
| 8081 / 8082 | technician-app web builds (in-process static server) | built with `EXPO_PUBLIC_API_URL` = 8001 / 8002 |

The run refuses to start if any of these ports is in use; it never stops anything it did not start. Login and voice
rate limits are raised for the harness backends only (`RATE_LIMIT_*_PER_MINUTE=200`), because it signs in many
times a minute from one address.

## The microphone

Chromium's fake capture device plays a WAV in place of a microphone. The harness decodes the Timbre-generated
fixture `backend/app/tests/fixtures/audio/hinglish_m204.mp3` with Windows Media Foundation (`tools/make-wav.ps1`)
and appends 6 s of silence, so a recording longer than the sentence does not pick up a repeat. A second browser gets
a silent file. The technician app's own recorder then produces AAC in MP4 (`audio/mp4;codecs=mp4a.40.2`), the same
as on phones, and the harness checks it. This is synthetic speech, not a human voice or a phone microphone; that is
`docs/DEVICE_TEST.md`.

## Scenarios

- **demo** (`scenarios/demo.mjs`, 32 checks): the `docs/DEMO_SCRIPT.md` story across three browser contexts (tech1,
  tech2 and the supervisor). It checks the received API payloads, the Timbre playback (spied on
  `HTMLMediaElement.play`), the recording format, timings, and the PostgreSQL rows through `tools/db.py evidence`:
  status, assignee, Prisma request id, verbatim transcript, no audio stored, 7 checklist responses, and the audit
  transitions in order.
- **errors** (`scenarios/errors.mjs`, 34 checks):
  - E1 unknown machine (registered suggestions only, server refuses to create).
  - E2 production follow-up.
  - E3 silence (real Prisma empty transcript).
  - E4 the 30 s recorder limit.
  - E5 Prisma 429 on every retry, then recovery.
  - E6 Prisma 500, then typing.
  - E7 Timbre 500, text-only replies and the order still created.
  - E8 duplicate taps and concurrency: one request on a double tap; 5 parallel identical submissions give
    201 + 4×409; 5 parallel with different keys give 201 + 4×409; two supervisors approving at once give 200 + 409,
    and only one approval is audited.
  - E9 roles and scope (403 / 404, each app refuses the other role).
  - E10 checklist gate.
  - E11 real short-lived tokens expiring mid-session in both apps.
  - E12 backend unreachable.

## Tools

- `tools/db.py`: `evidence WO-n`, `counts`, `token <email> <seconds>` (a real token with a short life),
  `cleanup <file>` (deletes only the listed ids and refuses seed records).
- `tools/make-wav.ps1`: Media Foundation decoder for the fake microphone file.
