# gnani/

The only package allowed to know about `api.vachana.ai`.

- `base.py`   shared httpx client, auth header, retry/backoff, error mapping
- `prisma.py` speech-to-text adapter (Prisma v3.0, `POST /stt/v3`)
- `timbre.py` text-to-speech adapter (Timbre v2.5, `POST /api/v1/tts/inference`)
- `errors.py` typed exceptions (auth, credit, rate-limit, bad request, unavailable)

Implemented in Phase 2. Contract: docs/GNANI_INTEGRATION.md.
