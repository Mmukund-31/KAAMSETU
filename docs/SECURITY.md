# Security review (Phase 8)

Reviewed on 2026-11-10. This is a prototype review, not a penetration test. Everything marked "test" is enforced
by an automated test that fails if it regresses.

## Summary

| Area | Status | Evidence |
|---|---|---|
| Every API route requires a token, except health and login | OK | test: `test_security.py` reads the route list from the app; all 41 non-public operations return 401 without a token |
| Supervisor and manager routes refuse technicians | OK | test: 11 routes give 403 to a technician |
| Role always re-read from the database; deactivated users locked out at once | OK | Phase 1 tests |
| Scope: other sites' and other technicians' records are invisible (404, not 403) | OK | Phase 4 tests; `e2e/` E9 |
| Forged, `alg: none` and expired tokens refused | OK | tests; `e2e/` E11 with real short-lived tokens |
| Passwords | OK | argon2id; uniform timing for unknown email or wrong password; login rate limit 10/min per IP |
| Gnani key never reaches a client | OK | the key is only in `backend/.env`; client bundles scanned: no key, no Gnani host, no auth header |
| No secrets, tokens or transcripts in logs | OK | redaction filter; log scans in every `e2e/` run and in the Docker check |
| Secrets never committed | OK | read-only scan of all 7 commits: no key, no JWT secret, `.env` never committed |
| Production refuses weak configuration | OK | test: the app will not start with a placeholder or short `JWT_SECRET_KEY`, or with `CORS_ORIGINS=*` |
| API map hidden in production | **Added** | test: `/docs`, `/redoc`, `/openapi.json` return 404 when `APP_ENV=production` |
| Security headers | **Added** | test: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cross-Origin-Resource-Policy: same-site`, and `Cache-Control: no-store` on `/api` |
| Upload limits | OK | size limit before reading (413); type from magic bytes (415); duration under 30 s; audio never written to disk |
| SQL injection | OK | ORM only; the only raw SQL is the constant `SELECT 1` health check |
| Evidence integrity | OK | transcripts travel in an HS256 evidence token bound to the user, valid 2 h; tampering gives `422 evidence_invalid` |
| Audit trail | OK | append-only, no update or delete endpoint; ordered by an identity sequence |
| Concurrency | OK | row lock per action; `e2e/` E8 races two approvals and five parallel submissions |
| Container | **Hardened** | non-root user (uid 10001), health check, `.dockerignore` excludes `.env`, venv, caches and logs |
| Self-service profile | **Added** | `PATCH /auth/me` accepts only `preferred_language`; extra fields such as `role` are ignored (test) |

## Dependency audit

| Package set | Tool | Result | Action |
|---|---|---|---|
| backend `requirements.txt` | pip-audit 2.9.0 | no known vulnerabilities | none |
| backend code | bandit 1.9.4 | 2 low, both false positives: the token-type constants `"access"` and `"report_evidence"` are read as passwords | none. Note: bandit 1.8.6 could not parse Python 3.14 and skipped every file, which looks like "0 issues". 1.9.4 scans all files. |
| supervisor-web | npm audit | **was 9** (2 critical, 7 moderate): React Router open-redirect advisories in shipped code; Vitest, tinypool and mocker in test tooling | upgraded `react-router-dom` 6.30.6 → **7.18.5** and `vitest` 3.2.7 → **5.1.0**; now **0 vulnerabilities**. All 49 web tests, the build and the `e2e/` run pass after the upgrade |
| technician-app | npm audit | 24 moderate or low, all in `glob` and `minimatch` used by Expo CLI and Jest | **accepted**: build and test tooling only. Neither library is in the web or Android bundle (checked). The patterns are ours, not user input. npm's only "fix" is downgrading the Expo SDK. Revisit with the next Expo SDK |
| e2e | npm audit | 0 | none |

Run them again:

```powershell
cd backend ; .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip_audit -r requirements.txt
.\.venv\Scripts\python.exe -m bandit -r app -x app/tests
cd ..\supervisor-web ; npm audit
cd ..\technician-app ; npm audit --omit=dev
```

## Known gaps (accepted for the prototype)

- Rate limits and the Gnani one-request-at-a-time guard are in memory, per process.
- The request-size check uses `Content-Length`. Audio uploads are also capped while reading, but a chunked JSON body
  without a length is not capped by the app. Put the API behind a reverse proxy with a body limit
  (`client_max_body_size`) in any real deployment.
- Tokens: 60-minute access tokens with no refresh or revocation list. Deactivating a user takes effect immediately
  because the role is re-read on every request.
- The supervisor console keeps its token in `localStorage`. The technician app uses the OS keychain or keystore;
  its web preview uses `localStorage`. httpOnly cookies would be safer for a hosted console.
- No HTTPS in the dev setup. A real deployment needs TLS at the proxy, and Android release builds need HTTPS or a
  cleartext exception.
- The demo accounts share one known password (`Kaamsetu@2026`). Change or remove them before any shared
  deployment.
