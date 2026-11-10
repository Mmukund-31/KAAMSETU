# Known Limitations

Kept current as phases land. KAAMSETU is a prototype built for a challenge demonstration.

## Product scope

- Not an industrial safety system and not an autonomous diagnosis tool. Priority comes from configurable organisation rules; it is not a judgement about the machine.
- Checklist templates in the seed data are labelled `[DEMO SOP]`. A real deployment must load company-approved procedures. KAAMSETU never generates SOP content.
- The safety-warning message ("keep clear and follow the site emergency procedure") is a fixed, configurable string. It does not replace site emergency procedures.

## Speech (Gnani)

- All speech measurements so far use Timbre-generated speech, not human recordings. Real voices, accents, factory noise and phone microphones are untested until Phase 7 and Phase 8.
- Prisma accepts AAC `.m4a` (verified in Phase 6 with a Media Foundation file and with recordings from the app's own
  recorder in a browser). A recording from a physical phone microphone is still to be tried, in Phase 7.
- Gnani allows one in-flight request per key. KAAMSETU serialises calls in one process. Several server processes or many simultaneous technicians would queue or get `503 speech_rate_limited`.
- Per-request credit cost is unknown; the API does not report it.

## Language understanding (rule-based, no LLM)

- **Measured:** on 20 unseen synthetic reports (v2 held-out), 45% came out fully right on the first pass. 9 of 20
  needed one follow-up answer, usually production status phrased in a new way, and 2 produced a wrong preview, one
  with a missed safety concern (since fixed). See `evaluation/RESULTS.md`. That is synthetic speech; human speech
  is unmeasured.
- Extraction recognises the 26 symptoms in `config/taxonomy.yaml`. Faults outside it are not classified. After one follow-up question the technician's own description is accepted, and the category falls back to the equipment's category.
- Negation handling is window-based. Unusual sentence structures can defeat it, for example double negatives or negation far from the word.
- The 44-case extraction test set was written alongside the rules. Passing it is a regression check, not evidence of accuracy on new speech.
- Hindi and Telugu response templates and labels were written for this prototype and need review by native speakers before any pilot.
- Spoken-number parsing covers common forms (digit by digit, "two hundred four", Hindi and Telugu number words). Unusual forms are not converted, and the technician is asked to confirm the machine.

## Workflow (Phase 4)

- Overdue orders are flagged and counted, but nothing escalates them automatically. Escalation is a manual supervisor
  action; no scheduler runs in the MVP.
- Notifications are pull-based: technicians see new tasks when their app refreshes. There are no push messages.
- Handover summaries sort the author's sentences by cue words only. A sentence with no cue word is listed as an
  observation even if it implies an action.
- Concurrent actions on one work order are serialised by a row lock. The end-to-end harness proves it for
  simultaneous approvals and for parallel submissions of one report. Other action pairs rely on the same lock but are
  not each raced.

## Supervisor web (Phase 5)

- The access token is stored in `localStorage` (60-minute expiry). A cross-site-scripting bug could read it. The app
  renders no raw HTML, but httpOnly cookies would be safer for a pilot.
- Updates arrive by 15-second polling. Two supervisors acting on one order at once get a clear `409` from the
  server, but the second screen refreshes only on the next poll or action.
- Light theme only. The layout works at phone width, but the console is designed for desktop use.
- Supervisors cannot record checklist steps; by design only the assigned technician can (mobile app).
- The UI is English only. Technician-facing language support lives in the mobile app and the spoken responses.

## Technician app (Phase 6)

- Not yet run on a physical phone or an emulator: this machine has no Android system image or connected device. The
  app is verified by its Jest suite, by compiling the Android and iOS Hermes bundles, and end to end (Phase 7) by
  driving its web build with the real recorder against the real backend, Prisma and Timbre, using a fake microphone
  that plays a Timbre-generated clip. The phone run is the manual checklist in `docs/DEVICE_TEST.md`.
- A language switch in the app is saved to the account (`PATCH /auth/me`, Phase 8), so announcements follow it. If
  that call fails (offline), the app still works in the new language, and the account keeps the old one until the
  next successful switch.
- Plain `http://` to a LAN IP works in Expo Go. A standalone release build needs HTTPS, or an Android cleartext
  exception.
- No offline mode: reports need a connection at the moment of sending. Pull-based updates only, with no push
  notifications.
- The Android preview build profile (`eas.json`) has not been built here, because EAS needs an Expo account.
- The web build is a development preview. Its token is stored in `localStorage`, not a secure store.

## Security (Phase 8, see `docs/SECURITY.md`)

- Build-time advisories in the technician app's tooling (`glob`, `minimatch` via Expo CLI and Jest) are accepted:
  they are not in the app bundle.
- Chunked JSON bodies without `Content-Length` are not size-capped by the app; use a reverse proxy limit.
- No token refresh or revocation list; TLS is left to the deployment's proxy.

## Platform

- The rate limiter is in memory and per process.
- The equipment register is scanned per report, which is fine for hundreds of machines per site, not tens of thousands.
- Dev machine specifics: Smart App Control requires pure-Python SQLAlchemy and the `pg8000` driver. Ports 5433 and 8001 avoid local conflicts.
