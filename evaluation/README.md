# evaluation

Labelled synthetic maintenance-report dataset and evaluation runner.
Created in **Phase 8**.

- `dataset.json` - ~40 reports (10 each: English, Hindi, Hinglish, Telugu) with
  expected equipment_id, category, symptoms, production_impact, missing_fields.
- `audio/samples/` - a few self-recorded clips; `audio/generated/` - Timbre-synthesised
  clips (clearly labelled as synthetic TTS speech, not human recordings).
- `run_eval.py` - runs Prisma then extraction, reports per-field accuracy.
- `RESULTS.md` - measured numbers. Synthetic test results, not a pilot.
