# Evaluation results

Measured on 2026-11-10 with the real backend, real Gnani Prisma (`prisma-v3.0`) and real Gnani Timbre
(`timbre-v2.5`). The generated detail for every run, including every miss and every transcript, is in `results/`.

> **What these numbers are, and are not.** All speech is synthesised by Gnani Timbre from the dataset text; none
> of it is a person speaking. The "noisy" condition mixes synthetic factory noise (rumble plus 100/200 Hz hum) at
> 10 dB SNR. The numbers measure the pipeline on clear and noisy machine speech. They are **not** accuracy on real
> technicians, accents, phone microphones or a real shop floor, and they are not pilot results.
> `docs/DEVICE_TEST.md` is the first step towards that.

## The three runs

| Run | Set | Why it exists | Whole report correct (text / clean / noisy) |
|---|---|---|---|
| **v1 held-out** | `dataset.json`, 40 reports | written for Phase 8 without looking at the rules, measured before any change | **72% / 68% / 68%** |
| v1 after fixes | same 40 | the rule gaps v1 exposed were fixed, so this is **no longer held out** | 100% / 98% / 95% |
| **v2 held-out** | `dataset_v2_holdout.json`, 20 new reports | written after the fixes, run once, never tuned on | **45% / 45% / 45%** |

**The honest generalisation figure is v2: 45% of new reports came out completely right on the first pass.** v1
after fixes mostly shows the rules can be extended quickly once a phrasing has been seen. That is how a rule-based
engine improves, but it is not evidence of accuracy on unseen speech.

## What happens when a report is not right

The pipeline is built to ask rather than guess, so a miss usually costs the technician one more answer, not a wrong
work order.

| Run (clean speech) | Correct | Asked a follow-up or the machine (recoverable) | Wrong preview without asking | …of which a safety concern was missed |
|---|---|---|---|---|
| v1 held-out (40) | 27 | 12 | 1 | 0 |
| v2 held-out (20) | 9 | 9 | 2 | 1 |

"Wrong without asking" means a preview the technician would have to correct by reading it. A supervisor still
approves every report. The one missed safety concern (v2-hl-03, Hinglish "chingari nikli", sparks) came from a
missing Latin spelling of "sparks". That spelling was added after the measurement (see below), and the 45% above
was measured before it.

## Field accuracy, v2 held-out (20 reports)

| Field | text | clean | noisy |
|---|---|---|---|
| Equipment (matched in the register) | 100% | 95% | 100% |
| Category | 100% | 100% | 100% |
| Safety concern | 95% | 95% | 90% |
| Symptoms (exact set) | 70% | 70% | 70% |
| Production impact | 70% | 65% | 70% |
| Next action | 60% | 60% | 60% |
| Priority (configured policy applied to the true fields) | 75% | 75% | 70% |

Symptom precision is 0.95 and recall 0.79 (clean). When the engine names a symptom it is almost always right, but
it misses some.

v1 held-out on clean speech: equipment 92%, symptoms 80%, production impact 90%, safety 100%, category 100%, next
action 75%, priority 98%.

## Speech recognition (Prisma), both held-out sets

| Language | Median WER clean / noisy | Auto language detection | Median request latency |
|---|---|---|---|
| English | 0.00 / 0.00–0.02 | 100% | 0.30 s |
| Hinglish | 0.00–0.10 / 0.00–0.05 | 0% (detected as hi-IN) | 0.30 s |
| Hindi | 0.27–0.31 / 0.30–0.33 | 100% | 0.25 s |
| Telugu | 0.00 / 0.00 | 100% | 0.30 s |

- On this synthetic speech Prisma is close to word-perfect in English, Hinglish and Telugu, and the 10 dB noise
  barely changed it.
- The Hindi WER is mostly script, not meaning. Prisma writes English loanwords in Latin ("pressure meter",
  "belt", "boiler") and numbers as digits ("101"), while the reference text is all Devanagari. The extraction handles
  both, which is why Hindi field accuracy does not drop from text to speech.
- Prisma auto-detection labels Hinglish as `hi-IN` every time. That confirms the design choice to send Hinglish
  as an explicit `en-IN` request, which returns the Latin-script transcript the rules expect, instead of relying on
  auto-detection.
- Two of the speech-only errors are recognition errors that the app handles safely. Prisma heard "I-602" as
  "E-602", which is not in the register, so the app asked which machine was meant. In noise, Prisma once inserted a
  comma inside the Telugu word for sparks; burning smell still raised the safety concern.
- Latency covers the whole `/voice/process-report` request in-process: upload, Prisma, extraction and database. With
  Timbre speaking the reply, the app measured 2.4–2.9 s from stop to preview (`docs/DEMO_SCRIPT.md`).

## Where the rules fall short (v2 held-out misses)

- **Production status said in a new way** (5 of 11 misses): "the line is down", "we are still producing", "the
  furnace is working", "भट्टी चल रही है", "ప్రొడక్షన్ కి ఇబ్బంది లేదు" ("no trouble for production"). The app
  asks "is production running?", which is one tap.
- **Symptoms said in a new way:**
  - "finish kharab" (quality);
  - "belt side mein chala jaata hai" (belt tracking off);
  - "kabhi 5 bar kabhi 12 bar" (an erratic reading described by its numbers);
  - "तापमान की रीडिंग नहीं आ रही" (sensor gives nothing);
  - "chingari" (sparks), the safety miss.
- **One extra symptom:** "बिजली काट दी गई" ("power was switched off", an action) was read as a power failure.

These are vocabulary and phrasing gaps, the known limit of a keyword engine with no language model. After one
follow-up answer, the technician's own words are accepted as the description.

## What was changed after v1 (and is therefore not held out)

All of the following have regression tests in `backend/app/tests/unit/test_phase8_rule_fixes.py`:

- **New phrasings:** "no power", "jamming", "start hi nahi", "chal hi nahi", Hindi "रिसाव" (leak) for air leaks,
  "ढीली" (feminine of loose), and Telugu "నిప్పు రవ్వలు" (sparks, two words).
- **Machine types as subjects for production status:** boiler, compressor, pump, conveyor and press, in all scripts.
  Also Hinglish "ruka hua".
- **Spoken numbers after "number"** (नंबर, నంబర్), and digit groups such as "1-01" (Prisma's formatting of 101).
  Mixed forms like "2 sau" are deliberately not read.
- **After v2, one safety fix:** "chingari" and "chingaari", the Hindi plural "चिंगारियाँ", and Hinglish "ghayal"
  (injured). Re-running v2 on typed text afterwards gives 10 correct, 9 asked, 1 wrong and 0 safety misses
  (`results/v2-after-safety-fix.md`, text condition only). That is no longer a held-out number.

## Targets from the plan

| Target | Result |
|---|---|
| At least 90% required-field extraction on the labelled set | Equipment 92–100% (held out); production impact 65–90% held out, so **not met on unseen phrasings**. Met on v1 after fixes (production 100% text). |
| 100% on permission and state-transition tests | Met (backend suite and the `e2e/` E8–E10 checks). |
| No work orders for invalid equipment | Met: unregistered codes produce `fix_equipment` (en-09, hl-06), and the server refuses creation (`e2e/` E1). |
| Real Prisma and Timbre end to end | Met (this evaluation and `e2e/`). |

## Reproduce

```powershell
cd backend
.\.venv\Scripts\python.exe ..\evaluation\run_eval.py --name v1                                      # dataset.json
.\.venv\Scripts\python.exe ..\evaluation\run_eval.py --dataset dataset_v2_holdout.json --name v2
.\.venv\Scripts\python.exe ..\evaluation\run_eval.py --text-only --name quick                       # no Gnani calls
```

The first full run synthesises the clips with Timbre (60 calls), cached in `audio/generated/` with a manifest.
Every run then makes 3 Prisma calls per report. Re-synthesised audio can differ slightly from these runs.
