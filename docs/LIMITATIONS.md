# Known Limitations

Kept current as phases land. KAAMSETU is a prototype built for a challenge demonstration.

## Product scope

- Not an industrial safety system and not an autonomous diagnosis tool. Priority comes from configurable organisation rules; it is not a judgement about the machine.
- Checklist templates in the seed data are labelled `[DEMO SOP]`. A real deployment must load company-approved procedures. KAAMSETU never generates SOP content.
- The safety-warning message ("keep clear and follow the site emergency procedure") is a fixed, configurable string. It does not replace site emergency procedures.

## Speech (Gnani)

- All speech measurements so far use Timbre-generated speech, not human recordings. Real voices, accents, factory noise and phone microphones are untested until Phase 7 and Phase 8.
- Prisma's handling of Expo `.m4a` recordings is not yet verified (Phase 6).
- Gnani allows one in-flight request per key. KAAMSETU serialises calls in one process. Several server processes or many simultaneous technicians would queue or get `503 speech_rate_limited`.
- Per-request credit cost is unknown; the API does not report it.

## Language understanding (rule-based, no LLM)

- Extraction recognises the 26 symptoms in `config/taxonomy.yaml`. Faults outside it are not classified. After one follow-up question the technician's own description is accepted, and the category falls back to the equipment's category.
- Negation handling is window-based. Unusual sentence structures can defeat it, for example double negatives or negation far from the word.
- The 44-case extraction test set was written alongside the rules. Passing it is a regression check, not evidence of accuracy on new speech.
- Hindi and Telugu response templates and labels were written for this prototype and need review by native speakers before any pilot.
- Spoken-number parsing covers common forms (digit by digit, "two hundred four", Hindi and Telugu number words). Unusual forms are not converted, and the technician is asked to confirm the machine.

## Platform

- The rate limiter is in memory and per process.
- The equipment register is scanned per report, which is fine for hundreds of machines per site, not tens of thousands.
- Dev machine specifics: Smart App Control requires pure-Python SQLAlchemy and the `pg8000` driver. Ports 5433 and 8001 avoid local conflicts.
