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
| POST | `/voice/transcribe` | T/S/M | multipart `audio`, `language` -> `{transcript, detected_language, request_id, processing_time}` |
| POST | `/voice/synthesize` | any | `{text, language, speed?}` -> audio/mpeg (or `?base64=true` -> `{audio_base64, mime}`) |
| POST | `/voice/process-report` | T | multipart `audio`, `language` -> `ReportOutcome` (transcript, extracted, equipment_status, suggestions, missing_fields, follow_up_question, priority, next_action, response_text, response_audio_base64?, tts_available) |
| POST | `/voice/process-text` | T | `{text, language}` -> same `ReportOutcome` (text fallback / after transcript edit) |
| POST | `/voice/follow-up` | T | `{draft, answer_text?}` or multipart with `answer_audio` -> updated `ReportOutcome` |

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
