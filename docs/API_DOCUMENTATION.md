# API Documentation (planned contract)

Base path `/api/v1`. JSON unless noted. Bearer JWT in `Authorization` header.
Errors use one envelope: `{"error": {"code": "...", "message": "...", "details": {...}}}`.
Lists are paginated: `?page=1&page_size=20` -> `{"items": [...], "total": n, "page": 1, "page_size": 20}`.
Interactive OpenAPI docs are served at `/docs` once Phase 1 lands.

Roles: **T** technician, **S** supervisor, **M** manager (M includes S).

## Health
| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/health` (also unversioned `/health`) | none | liveness; reports `gnani_configured` (true/false only) |
| GET | `/health/db` | none | runs `SELECT 1`, returns current `migration_revision`; 503 if unreachable |

## Auth
| Method | Path | Auth | Body -> Response |
|---|---|---|---|
| POST | `/auth/register` | S/M | `{name,email,password,role,preferred_language,site_id?}` -> 201 user |
| POST | `/auth/login` | none, rate limited | `{email,password}` -> `{access_token, token_type, expires_at, user}` |
| GET | `/auth/me` | any | -> user (with site) |

**Implemented in Phase 1.** Notes:

- There is no self-registration in any environment, because open registration would let anyone pick the manager role. Managers may create any role; supervisors may create technicians at their own site only (`403 role_not_permitted` / `site_not_permitted`).
- Passwords: 8-128 characters with at least one letter and one digit; hashed with argon2id. Validation errors never echo submitted values.
- Login failures return the same `401 invalid_credentials` for an unknown email and a wrong password, and spend the same hashing time on both. Disabled accounts get `403 account_disabled`. Login is limited to `RATE_LIMIT_LOGIN_PER_MINUTE` (default 10) per client IP, with `429 rate_limited` and a `Retry-After` header.
- Tokens: HS256, `sub`, `role`, `type=access`, `iat`, `exp`, `jti`. Expired tokens give `401 token_expired`; others give `401 invalid_token`. The user's role is always re-read from the database, never trusted from the token, and a deactivated user's existing tokens stop working immediately.
- Every response carries `X-Request-ID` (echoed from the request or generated). Bodies over `MAX_AUDIO_UPLOAD_MB + 1` MB get `413 payload_too_large`.

## Voice (Phase 2-3)
| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/voice/transcribe` | any role | multipart `audio` (file), `language` (`en`, `hi`, `te`, `hinglish`, `auto`; default: user's preferred language) -> `{transcript, language_requested, detected_language, model, gnani_request_id, processing_time_s, truncated, audio_format, audio_duration_s}` |
| POST | `/voice/synthesize` | any role | JSON `{text (1-500 chars), language, speed? (0.85-1.15)}` -> `audio/mpeg` bytes with `X-Voice` and `X-Gnani-Request-ID` headers; `?as_base64=true` -> `{audio_base64, content_type, voice, language_code, model, gnani_request_id}` |

**Implemented in Phase 2.** Both routes share a per-IP limit (`RATE_LIMIT_VOICE_PER_MINUTE`, default 30).

Audio checks before anything is sent to Gnani:
- `422 empty_audio`, `413 audio_too_large` (over `MAX_AUDIO_UPLOAD_MB`), `415 unsupported_audio_format`.
- The format comes from the file's magic bytes; the filename and declared type are ignored.
- `422 audio_too_short` (under 0.1 s) and `422 audio_too_long` (over 30 s), when the duration can be read.

Equipment codes registered at the user's site are sent to Prisma as `keyterms`.

Gnani failures are reported, never hidden:

| Upstream | KAAMSETU response |
|---|---|
| Silence (empty transcript) | `422 no_speech_detected` |
| 429 busy | `503 speech_rate_limited` with `Retry-After: 2` |
| 401/403 key or scope | `502 speech_auth_failed` |
| 402 credit | `502 speech_credit_exhausted` |
| 400/422 rejected input | `422 speech_request_rejected` with `gnani_code` |
| 5xx, timeout, network | `503 speech_unavailable` |
| Key not set | `503 speech_not_configured` |

Error details carry `gnani_request_id` when Gnani returned one. User-facing messages suggest text input as the fallback.
| POST | `/voice/process-report` | any role | multipart `audio`, `language?`, `speak?` (default true) -> `ReportOutcome` |
| POST | `/voice/process-text` | any role | JSON `{text, language?, evidence_token?, speak?}` -> `ReportOutcome`. Without a token this is a typed report (voice fallback). With a token it is a **transcript correction**: the original Prisma transcript is kept and the corrected text is re-extracted |
| POST | `/voice/follow-up` | any role | multipart `evidence_token`, `draft` (JSON), `field`, then `answer_text` or `audio`, `speak?` -> updated `ReportOutcome` |
| POST | `/voice/evaluate-draft` | any role | JSON `{evidence_token, draft, speak?}` -> `ReportOutcome`; re-validates a draft after manual edits, such as a machine picked from the suggestions |

**Implemented in Phase 3.** None of these endpoints writes to the database. The work order is created only when the technician confirms (Phase 4, `POST /work-orders`), and that step re-validates everything.

`ReportOutcome` fields:

| Field | Meaning |
|---|---|
| `next_action` | `fix_equipment` (code not in register), `ask_follow_up` (a mandatory field is missing), `confirm_preview` (ready to submit) |
| `draft` | Editable fields: `equipment_code`, `issue_description` (technician's own words), `symptoms` (taxonomy keys), `production_impact`, `safety_concern`, `location_note`, `category_override` |
| `equipment` | `status` matched / unknown / missing, `heard`, the matched register row, `suggestions` (same-site register rows only) |
| `symptoms`, `category` | Recognised symptoms with labels in the report language; category with `basis` (symptoms / equipment / override / none) |
| `priority` | `level`, `rule_id`, `explanation`, `provisional` (true while production impact or equipment is unknown) |
| `missing_fields`, `follow_up` | All missing mandatory fields with questions; `follow_up` is the next single question |
| `response` | `text` always; `audio_base64`, `content_type`, `voice`, `gnani_request_id` when Timbre succeeded; `tts_available` false plus `tts_error` when it failed (the flow continues) |
| `original_transcript`, `utterances` | The first utterance exactly as received, plus every correction and answer, each with its kind and Gnani request id |
| `evidence_token` | Signed record of the utterances; send it back with every follow-up, correction and the final submission |
| `requires_approval`, `warnings` | Policy result; warnings such as `unknown_symptoms_ignored`, `equipment_decommissioned` |

Errors specific to the report flow: `422 evidence_invalid` (token modified or not an evidence token), `422 evidence_expired` (older than 2 hours), `403 evidence_wrong_user`, `422 invalid_draft`, `422 empty_answer`, `422 too_many_utterances`.

## Work orders (Phase 4)
| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/work-orders` | T | confirmed draft + `submission_key` -> work order (status `reported`); 422 unknown equipment; 409 duplicate |
| GET | `/work-orders` | any (T sees own/assigned) | filters: `status, priority, equipment_id, assigned_to, site_id, q, from, to, overdue` |
| GET | `/work-orders/{id}` | any with access | includes evidence, assignments, checklist summary, audit trail |
| PATCH | `/work-orders/{id}` | T (own, while reported) / S | editable fields only |
| POST | `/work-orders/{id}/submit` | T | reported -> under_review (if not auto) |
| POST | `/work-orders/{id}/approve` | S/M | `{comment?, priority_override?, override_reason?}` |
| POST | `/work-orders/{id}/reject` | S/M | `{comment}` required |
| POST | `/work-orders/{id}/assign` | S/M | `{technician_id, comments?}` |
| POST | `/work-orders/{id}/status` | per state table | `{to, comment?}` generic transition |
| POST | `/work-orders/{id}/complete` | assigned T | -> completion_review; 409 if mandatory checklist items open |
| POST | `/work-orders/{id}/escalate` | S/M | `{comment}` |

## Equipment
| Method | Path | Auth |
|---|---|---|
| GET | `/equipment` | any; filters `site_id, category, q` |
| GET | `/equipment/{id}` | any; includes recent work orders + recurring faults |
| POST | `/equipment` | S/M |

## Users
| Method | Path | Auth |
|---|---|---|
| GET | `/users?role=technician&site_id=` | S/M |

## Checklists
| Method | Path | Auth |
|---|---|---|
| GET | `/checklists/templates` | any |
| POST / PATCH | `/checklists/templates[/{id}]` | S/M; new version, deactivate old |
| POST | `/work-orders/{id}/checklists` | S or assigned T; auto-picks active template by equipment category |
| PATCH | `/checklists/{id}/items/{item_id}` | assigned T; `{response, notes}` |

## Handovers
| Method | Path | Auth |
|---|---|---|
| POST | `/handovers` | T/S; `{shift_identifier, notes}` or multipart audio |
| GET | `/handovers` | any (site-scoped) |
| GET | `/handovers/{id}` | any |
| POST | `/handovers/{id}/review` | S/M; `{comment?, pending_actions?}` |

## Dashboard (S/M)
| Method | Path | Returns |
|---|---|---|
| GET | `/dashboard/overview` | total, open, pending_approval, in_progress, critical_high, overdue, completed_7d |
| GET | `/dashboard/work-order-trends?days=30` | daily created / closed |
| GET | `/dashboard/equipment-issues` | top equipment by count, by category |
| GET | `/dashboard/technician-workload` | per technician: assigned, in_progress, blocked, overdue |

## Audit (S/M)
| Method | Path |
|---|---|
| GET | `/audit-logs?entity_type=&entity_id=&actor_id=&page=` |

## Status codes
200/201 success; 400 malformed; 401 unauthenticated; 403 role/ownership; 404; 409 invalid transition / duplicate / checklist incomplete; 413 audio too large; 415 unsupported audio; 422 validation (incl. unknown equipment); 429 rate limited; 502 Gnani upstream error; 503 Gnani unavailable.
