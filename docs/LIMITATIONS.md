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
- Concurrent actions on one work order are serialised by a row lock, but no automated multi-connection race test
  exists yet.

## Supervisor web (Phase 5)

- The access token is stored in `localStorage` (60-minute expiry). A cross-site-scripting bug could read it. The app
  renders no raw HTML, but httpOnly cookies would be safer for a pilot.
- Updates arrive by 15-second polling. Two supervisors acting on one order at once get a clear `409` from the
  server, but the second screen refreshes only on the next poll or action.
- Light theme only. The layout works at phone width, but the console is designed for desktop use.
- Supervisors cannot record checklist steps; by design only the assigned technician can (mobile app).
- The UI is English only. Technician-facing language support lives in the mobile app and the spoken responses.

## Technician app (Phase 6)

- Not yet run on a physical phone or an emulator. This machine has no Android system image or connected device. The
  app was verified through its Jest suite, by compiling the Android and iOS Hermes bundles, and by driving its web
  build against the real backend, Prisma and Timbre (with a fake microphone playing a Timbre-generated clip). Phase 7
  runs it in Expo Go on a phone.
- The language choice is stored on the device. Task announcements use the account's `preferred_language` on the
  server, so a technician who switches language in the app still hears announcements in the account language until
  an admin changes it.
- Plain `http://` to a LAN IP works in Expo Go. A standalone release build needs HTTPS, or an Android cleartext
  exception.
- No offline mode: reports need a connection at the moment of sending. Pull-based updates only, with no push
  notifications.
- The web build is a development preview. Its token is stored in `localStorage`, not a secure store.

## Platform

- The rate limiter is in memory and per process.
- The equipment register is scanned per report, which is fine for hundreds of machines per site, not tens of thousands.
- Dev machine specifics: Smart App Control requires pure-Python SQLAlchemy and the `pg8000` driver. Ports 5433 and 8001 avoid local conflicts.
