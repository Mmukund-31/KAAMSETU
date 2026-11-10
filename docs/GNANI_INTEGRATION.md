# Gnani AI Integration

Source: https://docs.gnani.ai (read 2026-11-10). Everything below was taken from
the current docs, not from memory or earlier projects. Items marked **VERIFY**
are undocumented or inconsistent in the docs and are settled empirically in
Phase 2 with real requests; findings are recorded in the "Measured" section.

## Common

| Item | Value |
|---|---|
| API host | `https://api.vachana.ai` (the docs site is not the API host) |
| Auth header | `X-API-Key-ID: <api key>` on every request |
| Key source | https://app.gnani.ai/voice -> API keys. Programme registrations receive 5,000 credits. |
| Backend env | `GNANI_API_KEY`, `GNANI_API_BASE_URL`, model and voice settings (see `backend/.env.example`) |
| Python client | `httpx` (direct REST). The `gnani-vachana` SDK is not used (its TTS default model is withdrawn). |

### Error envelopes

- Auth / credit / rate limit (both products): `{"detail": {"error_code", "message", "status_code"}}`
  - 401 `MISSING_API_KEY`, 401 `INVALID_API_KEY`, 402 insufficient credit, 403 `SCOPE_NOT_ALLOWED`, 429 `RATE_LIMITED`
  - No `Retry-After` header. Documented example limit: "Only 1 active request is allowed at a time."
- STT errors: `{"success": false, "error": {"type", "message"}}` with types such as `INVALID_LANGUAGE_CODE`,
  `INVALID_MODEL`, `EMPTY_AUDIO`, `UNSUPPORTED_AUDIO_FORMAT`, `AUDIO_CONVERSION_ERROR`,
  `MAX_AUDIO_DURATION_EXCEEDED`, `TRANSCRIPTION_FAILED`, `INTERNAL_SERVER_ERROR`; 504 `UPSTREAM_TIMEOUT`.
- TTS errors: `{"success": false, "message", "status_code"}`; 400 bad params / wrong voice-model pair.
- Retry policy (from docs): retry 429, 500, 503, 504 with exponential backoff, max 3 attempts. Never retry other 4xx.

## Prisma (speech-to-text)

| Item | Value |
|---|---|
| Endpoint | `POST https://api.vachana.ai/stt/v3` (`multipart/form-data`) |
| Model used | `prisma-v3.0` (form field `model`). `prisma-v2.5` is the default when omitted. |
| Required fields | `audio_file` (file), `language_code` |
| Optional fields (v3.0) | `format` = `verbatim` (default) / `transcribe` / `codemix` / `transliterate`; `keyterms` (max 200, JSON array or CSV); `topic` (max 1600 chars); `previous_text`; `speaker_names`; `enable_substitution` + `substitution_map` |
| Audio formats | WAV, MP3, OGG, FLAC, AAC, M4A, detected by file extension; auto-converted to 16 kHz mono |
| Limits | max 30 s per request, min 0.1 s. Max upload bytes: **VERIFY** (undocumented) |
| Languages | `bn-IN en-IN gu-IN hi-IN kn-IN ml-IN mr-IN pa-IN ta-IN te-IN`; `indic-auto` for auto-detect (v3.0); 1-4 comma-separated hints e.g. `hi-IN,en-IN` |
| Hinglish | `en-IN` accepts Hindi-English mixed audio (Latin output); `format=codemix` keeps English words Latin |
| Response | `success, request_id, transcript, model, detected_language_code (v3.0), processing_time, end_to_end_latency, truncated` |
| Not provided | confidence scores, word-level timestamps |

KAAMSETU usage: UI language -> `language_code` map `en -> en-IN`, `hi -> hi-IN`, `te -> te-IN`,
`hinglish -> en-IN` (chosen from measurements below; configurable via `GNANI_PRISMA_HINGLISH_LANGUAGE`),
`auto -> indic-auto`. Registered equipment codes are passed as
`keyterms`; `topic="factory maintenance fault report"`. Streaming (`wss://api.vachana.ai/stt/v3/stream`)
and batch (`/stt/v3/batch/jobs`) exist but are not needed for reports of 30 s or less.

## Timbre (text-to-speech)

| Item | Value |
|---|---|
| Endpoint | `POST https://api.vachana.ai/api/v1/tts/inference` (JSON) |
| Model used | `timbre-v2.5` (recommended by docs; v2.0 withdrawn; `timbre-v3.0` also available) |
| Body | `text` (required), `model` (required), `voice`, `language`, `speed` (0.85-1.15 or slow/medium/fast), `audio_config` (required) |
| `audio_config` | `sample_rate` 8000/16000/22050/24000/44100/48000 (default 48000); `num_channels` 1; `sample_width` 2; `encoding` linear_pcm/pcm_s16le/pcm_mulaw/pcm_alaw/oggopus; `container` wav/raw/mp3/ogg/mulaw/alaw; `bitrate` (mp3) 32k-192k |
| Languages | `auto, hi-IN, en-IN, te-IN, ta-IN, kn-IN, ml-IN, mr-IN, pa-IN, bn-IN, gu-IN, hi-en` (Hinglish) |
| Voices v2.5 (bound to language) | en-IN: Kaveri, Trupti, Devika, Pranav, Shlok, Girish. hi-IN: Nalini, Bhavna, Yashvi, Urmila, Jwala, Chitra, Ambuja, Deepak, Roopesh, Vikrant, Hemraj, Jalaj, Omkar. te-IN: Suhana, Lehara, Lavanya, Yukti, Varuni. hi-en: Poorvi |
| Voices v3.0 (multilingual) | Avinash, Chetana, Devansh, Kalpana, Lakshmi, Prakash, Riyaa, Shivani, Shubham, Tarika, Vasudha, Yashraj, Harshad |
| Response | raw audio bytes; `Content-Type` `audio/wav`, `audio/mpeg` (mp3), `audio/ogg`, ... |
| Text limit | **VERIFY** (undocumented; over-long text returns 500) |
| Streaming | SSE `POST /api/v1/tts/sse`, WebSocket `wss://api.vachana.ai/api/v1/tts`; not needed for short acknowledgements |

KAAMSETU usage: `audio_config = {sample_rate: 24000, container: "mp3", bitrate: "64k"}` for small
mobile payloads; voice chosen per language from env (`GNANI_TIMBRE_VOICE_*`).

## Uncertainties to settle in Phase 2 (real requests)

| # | Question | Plan |
|---|---|---|
| a | Does Prisma accept Expo's `.m4a` (AAC) output directly? | Send a real Expo recording. If rejected, transcode server-side (ffmpeg) and document. |
| b | Hinglish TTS: `language=hi-en` + voice Poorvi (REST docs) vs `auto` (SDK docs)? | Try both, keep the one that returns 200 with natural output. |
| c | Are `language`/`speed` accepted on `timbre-v3.0`? | Only matters if v3.0 is adopted; test once. |
| d | Max STT upload size | Probe with a 30 s high-bitrate clip; set `MAX_AUDIO_UPLOAD_MB` accordingly. |
| e | Credit cost per STT/TTS call | Read dashboard balance before/after smoke test; budget the 5,000 credits. |
| f | `indic-auto` vs explicit `hi-IN,en-IN` on Hinglish accuracy | Measured on the Phase 8 dataset. |
| g | Streaming header name `model` vs `x-model` | Not needed (no streaming in MVP). |

## Security and privacy

- Keys only in `backend/.env`; never in client code, logs, or responses. Logging filter redacts `X-API-Key-ID`.
- Audio is validated (extension, magic bytes, size, duration) before upload to Gnani.
- Audio is **not retained** by default (`AUDIO_RETENTION=none`). Transcript and extracted JSON are retained as evidence.
- Logs record `request_id`, latency, status code; never transcript bodies at INFO level.

## Measured (Phase 2, 2026-11-10, real requests)

All inputs were Timbre-generated synthetic speech, not human recordings. Human speech,
background noise and real phone microphones are measured in Phase 7 and Phase 8.

### Contract confirmations

| Check | Result |
|---|---|
| Auth header `X-API-Key-ID` on `api.vachana.ai` | Works for both products |
| Prisma `POST /stt/v3` with `model=prisma-v3.0` | 200, body as documented; `request_id` is in the body only (no header) |
| Timbre `POST /api/v1/tts/inference`, `timbre-v2.5` | 200, raw audio; `x-api-request-id` and `x-audio-container` headers |
| Input formats accepted by Prisma | MP3, WAV, OGG (Opus) and **M4A (AAC-LC in MPEG-4)** verified. M4A verified in Phase 6 two ways: a file encoded by Windows Media Foundation (`ftyp mp42`, `mp4a`, now fixture `hinglish_m204.m4a` with a gated integration test), and recordings made by the app's own recorder in Edge (`audio/mp4;codecs=mp4a.40.2`, `ftyp isom`). Both transcribed correctly: Hinglish M-204 in 1.2 s and English H-401 in 0.5 s, end to end through `/voice/process-report` |
| Timbre containers | mp3 (`audio/mpeg`), wav (`audio/wav`), ogg (`audio/ogg`) all work |
| Timbre `speed` on v2.5 | Accepted (0.9 tested) |
| Hinglish TTS | `language=hi-en` and `language=auto` with voice Poorvi both return 200. KAAMSETU uses `hi-en` |
| Invalid key | 401 `{"detail":{"error_code":"INVALID_API_KEY","message":"Unauthorized"}}` |
| Unknown voice | 400 TTS envelope; the message lists supported voices, which include names not in the docs (e.g. Aarohi, Bhavini) |
| Missing `language_code` | 422 `{"detail":[{"type":"missing","loc":["body","language_code"],...}]}` |
| 0.05 s of silence | **200 with `transcript: ""` and no `model` field** (not an error). KAAMSETU returns `422 no_speech_detected` |
| 3 parallel STT requests | 1 succeeded, 2 got **429 "Only 1 active request is allowed at a time"**. KAAMSETU serialises all Gnani calls (`GNANI_MAX_CONCURRENCY=1`) |

### Timbre WAV header quirk

Timbre's WAV output writes `0xFFFFFFFF` as the RIFF and data chunk sizes (a streaming
placeholder). Python's `wave` module and `mutagen` both report about 134,217 seconds for a
2.56-second clip. `app/services/audio.py` parses RIFF chunks itself and uses the real byte
count. A fixture keeps this covered by tests.

### Hinglish recognition strategy

Same Timbre-generated Hinglish clip ("Motor ka pressure abnormal hai. Bearing mein vibration aa raha hai.
Machine number M-204 hai. Production abhi chal raha hai."), different `language_code` values:

| language_code | Transcript (abridged) | Equipment code |
|---|---|---|
| **`en-IN` (chosen)** | `motor ka pressure abnormal hai, bearing mein vibration aa raha hai, machine number M204 hai, production abhi chal raha hai.` | `M204` / `M-204` |
| `hi-IN,en-IN` | `मोटर का प्रेशर एबनॉर्मल है, बेयरिंग में वाइब्रेशन ...` (all Devanagari) | `M-204` |
| `hi-IN` | `मोटर का pressure abnormal है, bearing में vibration ...` (mixed script) | `M204` |
| `hi-IN,en-IN` + `format=codemix` | `मोटर का pressure abnormal है, bearing में vibration ...` | `M-204` |
| `indic-auto` | `... मशीन नंबर एम टू ज़ीरो फोर है ...` | spelled out in words |

`en-IN` is used for Hinglish because it reproduces what the technician said in Latin script,
the same form used for typed Hinglish. Explicit languages beat `indic-auto` for equipment codes:
auto-detect spelled them as words ("H four hundred one"). The app therefore always sends the
user's selected language and offers `auto` only as an explicit choice.

### Equipment code forms seen in transcripts (input for Phase 3 extraction)

| Language | Forms observed |
|---|---|
| English | `H-401`, `E-110` |
| Hinglish (`en-IN`) | `M204`, `M-204` |
| Hindi (`hi-IN`) | `M-204`, `M 204` (also from spoken "एम दो सौ चार") |
| Telugu (`te-IN`) | `ఎం రెండు వందల నాలుగు`: spoken number words are **not** converted to digits |
| `indic-auto` | `एम टू ज़ीरो फोर`, `H four hundred one` |

Passing site equipment codes as `keyterms` did not change these results in the tests run so far.
It is kept because it is documented to bias recognition, and Phase 8 will measure it on more clips.

### Latency (single requests, Hyderabad dev machine to api.vachana.ai)

| Operation | Observed |
|---|---|
| Prisma, clip of 2.5-7.5 s | 0.4-0.9 s end to end (server `processing_time` 0.13-0.51 s) |
| Timbre, one or two sentences | 0.5-2.0 s |

### Credit usage

Phase 2 made roughly 60 billable requests in total: the probe, experiments, integration tests,
smoke test and live check. The API returns no balance or cost information, so per-request cost
is still unmeasured. Check the remaining balance at https://app.gnani.ai/voice and record it here.

### Remaining uncertainties

| # | Status |
|---|---|
| a | M4A (AAC in MP4): **accepted**, measured in Phase 6 (see above). Not yet measured: an actual iPhone or Android recording over a real microphone. That is Phase 7 on a device, and the codec and container are the same. |
| b | Hinglish TTS language: **settled** (`hi-en`; `auto` also works). |
| c | `timbre-v3.0` parameters: not needed; v2.5 is used. |
| d | Max upload size: **open** but low-risk. The app caps uploads at 10 MB and 30 s; 30 s of 128 kbps AAC is about 0.5 MB. |
| e | Credit cost per call: **open**; needs the dashboard balance. |
| f | `indic-auto` vs explicit hints: **settled for equipment codes** (explicit wins); full accuracy comparison in Phase 8. |
| g | Streaming header names: not needed. |
