# Audio fixtures

Synthetic speech generated with **Gnani Timbre v2.5** on 2026-11-10. These are not human
recordings. They are used by unit tests (format and duration checks) and real-API
integration tests (Prisma transcription).

| File | Voice / language | Content |
|---|---|---|
| `hinglish_m204.mp3` | Poorvi, hi-en | "Motor ka pressure abnormal hai. Bearing mein vibration aa raha hai. Machine number M-204 hai. Production abhi chal raha hai." |
| `hinglish_m204.ogg` | Poorvi, hi-en | same sentence, Ogg Opus |
| `hindi_m204_streaming_header.wav` | Nalini, hi-IN | "Machine M-204 mein vibration aa raha hai." 16 kHz PCM. RIFF sizes are the 0xFFFFFFFF streaming placeholder. |
| `english_h401.mp3` | Kaveri, en-IN | "Machine H-401 has an oil leak near the pump. Production is still running." |
| `hinglish_m204.m4a` | Poorvi, hi-en | same sentence as `hinglish_m204.mp3`, re-encoded to AAC-LC mono in an MPEG-4 container (`ftyp mp42`, `mp4a`) with Windows Media Foundation, i.e. the format phones record. Added in Phase 6. |
| `browser_fragmented_3s.m4a` | Poorvi, hi-en (via fake microphone) | first 3 s of the same sentence, recorded by Edge's MediaRecorder (`audio/mp4;codecs=mp4a.40.2`) through the technician app's web recorder settings: a **fragmented** MP4 (`moov` + `moof`/`mdat`). Added in Phase 7 for the duration fix. |
