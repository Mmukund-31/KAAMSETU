# evaluation

Measured accuracy of the voice-to-work-order pipeline. **Read [RESULTS.md](RESULTS.md) first.**

| File | What it is |
|---|---|
| `dataset.json` | v1: 40 synthetic reports, 10 each in English, Hinglish, Hindi, Telugu, written as a held-out set |
| `dataset_v2_holdout.json` | v2: 20 further reports written after the v1 rule fixes and run once |
| `run_eval.py` | the runner (real FastAPI app in-process, real Prisma and Timbre) |
| `results/*.json`, `results/*.md` | generated per-run detail: field accuracy, outcome classes, WER/CER, latency, every miss with its transcript |
| `RESULTS.md` | written summary of the runs and what they mean |
| `audio/generated/` | Timbre-synthesised clips and their manifest (git-ignored; regenerated on the first run) |

Labelling rules: what a maintenance engineer would record from the sentence. `equipment` is `null` when the
code is missing or not in the register. `production_impact` is `unknown` when it is not stated. `safety_concern` is
true only for an explicit, non-negated hazard. `category` lists every acceptable answer when the category is
genuinely ambiguous. Priority is not hand-labelled: the configured policy is applied to the labelled fields.

Conditions per report: `text` (the reference text, no speech recognition), `clean` (Timbre audio through Prisma),
`noisy` (the same with synthetic factory noise at 10 dB SNR), and `auto` (Prisma language auto-detection).

All audio is synthetic speech. These are not human-speech or pilot results.
