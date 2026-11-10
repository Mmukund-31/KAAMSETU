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
`hinglish -> hi-IN,en-IN` (fallback `indic-auto`). Registered equipment codes are passed as
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

## Measured (filled in Phase 2)

_Pending real smoke test._
