# KAAMSETU: Gnani AI Great Indian AI Internship Challenge submission

**Speak the work. Structure the action. Keep operations moving.**

KAAMSETU turns a factory technician's spoken fault report, in Hindi, Telugu, English or Hinglish, into a validated,
approval-gated maintenance work order. It then carries that order through assignment, an SOP checklist, completion
and close, with every step audited. Gnani **Prisma** is the ears and Gnani **Timbre** is the voice; a deterministic
backend is the source of truth.

## 1. Problem

Maintenance on Indian shop floors runs on phone calls, WhatsApp voice notes and paper logs. Reports are:

- **incomplete**: no machine number, no word on whether production stopped;
- **mixed-language**: Hinglish, or Telugu with English machine terms;
- **invisible** to supervisors until a line is already down.

Typing a ticket on a phone with gloves on is not realistic, so technicians do not do it. The result is lost
reports, unclear priorities and no record of who did what.

## 2. Solution

Keep voice as the interface, and make the backend the source of truth.

1. **Technician speaks** (Expo app). The app records `.m4a` for up to 30 s and uploads it to the backend.
2. **Prisma transcribes** it in the technician's language. The site's registered equipment codes are sent as
   key terms.
3. **Rules structure it** with no LLM: machine code (written, spoken in four languages, or "number 101"), symptoms
   from a 26-symptom taxonomy, production impact, explicit safety hazards and negation.
4. **The register validates it.** A code that is not registered never becomes a work order; the app offers
   registered machines instead.
5. **Missing information becomes one question.** For example "Production chal raha hai ya band hai?", spoken by
   Timbre and answered by tap, voice or text.
6. **The technician confirms** an editable preview. Priority comes from configurable site rules, with the reason
   shown.
7. **The supervisor decides** in the web console. The verbatim transcript and the Prisma request id sit next to the
   structured order. The supervisor approves (with a priority override and a reason, if needed) or rejects, then
   assigns.
8. **The assignee hears the task** in their own language. They work the company SOP checklist (Complete stays
   locked until the mandatory steps are done) and complete it. Timbre confirms, and the supervisor closes it.
9. **Everything is audited**, and shift handovers are summarised from the records plus the technician's own spoken
   notes.

## 3. How Gnani is used

| | Prisma (speech to text) | Timbre (text to speech) |
|---|---|---|
| Model | `prisma-v3.0`, `POST /stt/v3` | `timbre-v2.5`, `POST /api/v1/tts/inference` |
| Languages | `en-IN`, `hi-IN`, `te-IN`; Hinglish sent as `en-IN` for Latin-script output (measured: auto-detection labels Hinglish `hi-IN`) | Kaveri (en), Nalini (hi), Suhana (te), Poorvi (Hinglish, `hi-en`) |
| Used for | fault reports, follow-up answers, spoken handovers | report preview, follow-up questions, submission acknowledgement, task announcement to the assignee, completion confirmation |
| Inputs | `.m4a` (AAC/MP4) from phones and the browser, WAV, MP3, OGG; site equipment codes as key terms | template text only (no generated text reaches a technician) |
| Reliability | retries on 429 and 5xx with backoff; one request in flight per key; busy → "try again"; down → "type instead" | failure never blocks work: the text is always on screen, and the order is still created |
| Security | the key exists only on the backend; no client bundle contains it, the Gnani host or the auth header (scanned) | same |

Measured in this project:
- Prisma accepts AAC `.m4a`, both from Windows Media Foundation and from the browser's recorder.
- Median request latency is about 0.3 s.
- The app measured 2.4–3.0 s from "stop recording" to a spoken preview.

## 4. Features

- **Technician app** (React Native / Expo SDK 58):
  - Voice, or typed text as a fallback.
  - Transcript correction, registered-machine picker, one-tap follow-ups, and an editable preview with one
    idempotency key per report, so a double tap never makes two orders.
  - My work, the spoken task, start / blocked / parts, the SOP checklist, completion, and a spoken handover.
  - Interface in English, Hinglish, Hindi and Telugu. The token is kept in the OS keychain or keystore.
- **Supervisor console** (React / Vite):
  - Live dashboard and approval queues.
  - Work-order detail with evidence, history and action buttons generated from the server's state machine.
  - Equipment history, technician workload, handover review, analytics (each chart with a table view), the audit
    log, and SOP template versions.
- **Backend** (FastAPI / PostgreSQL):
  - One state-machine table with role rules, guards (no self-approval, checklist gate, assignee only) and row locks.
  - Immutable evidence: a signed evidence token carries the original transcript from recording to submission.
  - Append-only audit log, site scoping, rate limits and secret redaction.

## 5. Results (measured, and what they mean)

All accuracy figures use **Gnani Timbre-generated speech**, not people. They are synthetic results, not a pilot
(`evaluation/RESULTS.md`).

| | Result |
|---|---|
| Held-out set v1 (40 reports, measured before any tuning) | whole report correct: 72% (text) / 68% (clean speech) / 68% (10 dB factory noise) |
| Held-out set v2 (20 new reports, run once) | **45%** whole report correct on the first pass; equipment 95%, category 100%, safety 95%, symptom precision 0.95 and recall 0.79 |
| When v2 was not fully right | 9 of 20 asked one follow-up question (recoverable); 2 of 20 showed a wrong preview, 1 of them with a missed safety concern (fixed afterwards) |
| Prisma word error rate | about 0 for English, Hinglish and Telugu; 0.3 for Hindi, mostly English loanwords written in Latin script |
| Tests | backend 494 (95.9% line coverage) plus 15 real-API tests; supervisor web 49 (91.6%); technician app 39 (91.7%) |
| End to end | `e2e/`: 74 of 74 checks with both apps, real Prisma, Timbre and PostgreSQL, including 12 failure cases (Gnani 429 and 500 injected, silence, the 30 s limit, races, expired tokens, offline) |

The honest reading:
- The pipeline is reliable about **which machine** a report is for, and **safe in how it fails**: it asks rather
  than guesses.
- Recognising **new phrasings of production status and symptoms** is the weak point of a keyword engine with no
  language model.
- Nothing has been measured on human speech yet.

## 6. Architecture

A modular monolith: one FastAPI process, one PostgreSQL database, two thin clients. Layers are enforced by tests:
- `intelligence/` has no database access;
- `gnani/` is the only code that knows Gnani;
- every state change goes through `state_machine.py` and writes an audit row in the same transaction.

The design decisions with reasons are in `docs/ARCHITECTURE.md`.

## 7. Limitations

These are stated in full in `docs/LIMITATIONS.md` and `docs/SECURITY.md`:
- a prototype on synthetic data;
- not run on a physical phone in this repository (a 13-step checklist is in `docs/DEVICE_TEST.md`);
- no offline mode or push notifications;
- per-process rate limits;
- Hindi and Telugu interface text needs native-speaker review;
- the SOP checklists in the seed are labelled `[DEMO SOP]`; KAAMSETU never writes SOP content.

## 8. Run it

`docker compose up -d --build` starts the database, API and console (http://localhost:8080). For the phone app,
see `README.md`. `cd e2e ; node run.mjs` re-proves everything in about 4 minutes.

## 9. Individual contribution

I independently conceptualised and developed KAAMSETU, from defining the problem and designing the system architecture to implementing the application, integrating Gnani AI APIs and verifying the end-to-end workflows.
I made the key product and engineering decisions, including choosing a voice-first approach for factory technicians, building separate technician and supervisor interfaces, using Gnani Prisma for speech recognition and Timbre for speech generation, and keeping operational decisions within a deterministic backend rather than allowing an LLM to directly control work orders. I also designed the work-order lifecycle, equipment validation, approval and assignment rules, checklist gates, audit trail and database structure.
I worked across the FastAPI backend, PostgreSQL data layer, React Native technician application and React supervisor console. I implemented and tested the voice-processing workflows, structured fault extraction, multilingual interactions, work-order management and supervisor approval flow. I also investigated API behaviour, handled failure scenarios and verified the application through automated tests and end-to-end checks using real Gnani API integrations.
I used Claude code and ChatGPT as development assistants for exploring implementation approaches, reviewing architecture, generating and refining code, identifying edge cases, debugging and improving test coverage. I directed the development, made the final technical decisions, reviewed the generated changes, ran the tests and verified the resulting behaviour. AI tools assisted the engineering process; responsibility for the product direction, integration decisions, validation and final submission remained mine.
I also documented the architecture, engineering trade-offs, evaluation results, security considerations and known limitations so that the implementation and its results can be independently understood and reviewed. 
