# Database Design

PostgreSQL 16. All primary keys are UUID v4. All timestamps are `timestamptz`.
Enumerations are PostgreSQL enum types. Managed by Alembic migrations only
(`create_all` is used solely in the test fixture).

## Entity overview

```
sites 1--* users
sites 1--* equipment
equipment 1--* work_orders *--1 users (reported_by)
                        *--1 users (assigned_to, nullable)
work_orders 1--1 work_order_evidence   (immutable)
work_orders 1--* assignments
work_orders 1--* work_order_checklists *--1 checklist_templates 1--* checklist_items
work_order_checklists 1--* checklist_responses *--1 checklist_items
sites 1--* handovers *--1 users
audit_logs  (polymorphic: entity_type + entity_id)
```

## Enums

| Enum | Values |
|---|---|
| `user_role` | technician, supervisor, manager |
| `language_code` | en, hi, te, hinglish |
| `equipment_category` | mechanical, electrical, instrumentation, hydraulic, pneumatic, production, other |
| `operational_status` | running, stopped, degraded, maintenance, decommissioned |
| `priority` | low, medium, high, critical |
| `work_order_status` | reported, under_review, approved, assigned, in_progress, completion_review, closed, rejected, awaiting_parts, blocked, escalated, reopened |
| `production_impact` | running, degraded, stopped, unknown |
| `checklist_status` | pending, in_progress, completed |
| `checklist_response_value` | done, not_applicable, failed |
| `handover_status` | draft, submitted, reviewed |
| `report_channel` | voice, text, seed |

## Implementation notes (Phase 1)

- Migration `0001_initial_schema` creates all 12 tables and 11 enum types. Downgrade drops both. A test checks that models and migrations do not drift and that downgrade then upgrade succeeds.
- Constraint names follow a fixed convention (for example `fk_work_orders_equipment_id_equipment`, `uq_work_orders_submission_key`), so services can map violations to user-facing errors.
- The pg8000 driver reports foreign-key violations as `ProgrammingError`, not `IntegrityError`. Code must classify database errors by SQLSTATE using `app/database/errors.py`, never by exception class.
- `checklist_templates` has a partial unique index (`uq_checklist_templates_active`) that allows only one active version per category and work-order type.
- Handovers also store `review_comment`. Checklist instances store `template_version` as a snapshot.

## Tables

### sites
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| name | text not null | |
| location | text | |
| created_at | timestamptz | default now() |

### users
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| name | text not null | |
| email | text unique not null | stored lower-cased |
| password_hash | text not null | argon2id |
| role | user_role not null | |
| preferred_language | language_code | default 'en' |
| site_id | uuid fk sites | |
| is_active | bool | default true |
| created_at | timestamptz | |

### equipment
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| equipment_code | text unique not null | e.g. `M-204`; `code_normalized` (upper, no spaces/hyphens) indexed for tolerant lookup |
| name | text not null | |
| category | equipment_category not null | drives checklist template selection |
| site_id | uuid fk sites not null | |
| location | text | |
| operational_status | operational_status | default running |
| is_critical | bool | default false; feeds priority rules |
| created_at | timestamptz | |

### work_orders
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| number | int identity (start 1001) unique | human-friendly id, shown as `WO-1001` |
| equipment_id | uuid fk equipment not null | validated before insert |
| reported_by | uuid fk users not null | |
| assigned_to | uuid fk users | |
| issue_description | text not null | technician-reviewed text |
| issue_category | equipment_category not null | |
| symptoms | text[] | taxonomy keys |
| priority | priority not null | |
| priority_rule | text | id of the prioritisation rule that produced the priority |
| status | work_order_status not null | default reported |
| report_channel | report_channel not null | voice, text, or seed (synthetic demo data) |
| production_impact | production_impact not null | |
| safety_concern | bool | default false, only if explicitly reported |
| requires_approval | bool | default true |
| location_note | text | |
| submission_key | text unique | client idempotency key; replay -> 409 |
| due_at | timestamptz | computed from priority SLA |
| closed_at | timestamptz | |
| created_at / updated_at | timestamptz | |

Indexes: `(status, priority)`, `equipment_id`, `assigned_to`, `reported_by`, `created_at desc`, `due_at`.

### work_order_evidence  (immutable: never updated by application code)
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| work_order_id | uuid fk unique | one evidence row per order |
| original_transcript | text not null | verbatim Prisma output |
| detected_language | text | Prisma `detected_language_code` |
| selected_language | language_code | what the user chose |
| extracted_data | jsonb not null | ExtractedReport as first produced |
| prisma_request_id | text | for support/tracing |
| prisma_model | text | |
| audio_reference | text | null unless AUDIO_RETENTION != none |
| created_at | timestamptz | |

### assignments
| column | type |
|---|---|
| id | uuid pk |
| work_order_id | uuid fk |
| technician_id | uuid fk users |
| assigned_by | uuid fk users |
| assigned_at | timestamptz |
| comments | text |

### checklist_templates
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| name | text | |
| equipment_category | equipment_category | |
| work_order_type | text | default 'corrective' |
| version | int | |
| is_active | bool | one active per (category, type) |
| created_by | uuid fk users | supervisor |
| created_at | timestamptz | |

### checklist_items
| column | type |
|---|---|
| id | uuid pk |
| template_id | uuid fk |
| description | text  (company-approved SOP text only) |
| is_mandatory | bool |
| sequence | int |

### work_order_checklists
| column | type |
|---|---|
| id | uuid pk |
| work_order_id | uuid fk |
| template_id | uuid fk |
| template_version | int (snapshot) |
| status | checklist_status |
| created_at / completed_at | timestamptz |

### checklist_responses
| column | type |
|---|---|
| id | uuid pk |
| checklist_id | uuid fk |
| checklist_item_id | uuid fk |
| response | checklist_response |
| notes | text |
| completed_by | uuid fk users |
| completed_at | timestamptz |

Unique `(checklist_id, checklist_item_id)`.

### handovers
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| site_id | uuid fk | |
| created_by | uuid fk users | |
| shift_identifier | text | e.g. `2026-11-10-A` |
| original_notes | text | verbatim transcript or typed text |
| detected_language | text | |
| generated_summary | jsonb | completed / pending / blocked / equipment_attention / approvals / next_actions / observations |
| pending_actions | jsonb | editable list |
| status | handover_status | |
| reviewed_by | uuid fk users | |
| reviewed_at | timestamptz | |
| created_at | timestamptz | |

### audit_logs  (append-only)
| column | type |
|---|---|
| id | uuid pk |
| actor_id | uuid fk users (nullable for system) |
| action | text  e.g. `work_order.create`, `work_order.transition`, `work_order.priority_override`, `assignment.create`, `checklist.item_update`, `handover.review` |
| entity_type | text |
| entity_id | uuid |
| previous_value | jsonb |
| new_value | jsonb |
| comment | text |
| timestamp | timestamptz |

Index `(entity_type, entity_id, timestamp)`, `actor_id`.

## Work-order state machine (as implemented in `app/services/state_machine.py`)

"Supervisor" means supervisor or manager, at the order's site. "Assignee" means the technician the order is assigned to.
Action is the API call that performs the move. Generic transitions use `POST /work-orders/{id}/status`, which
refuses moves that have a dedicated action.

| From | To | Who | Reason required | Action / guard |
|---|---|---|---|---|
| reported | under_review | reporter, supervisor | no | `submit` (automatic on creation unless `submit=false`) |
| reported, under_review, approved | rejected | supervisor | yes | `reject` |
| under_review | approved | supervisor, not the reporter (unless `ALLOW_SELF_APPROVAL`) | no | `approve`, optional priority override with reason |
| under_review, approved, assigned, in_progress, blocked, awaiting_parts | escalated | supervisor | yes | `escalate` |
| escalated | approved / rejected / in_progress | manager only | yes | `approve` / `reject` / `status` |
| approved, reopened | assigned | supervisor | no | `assign` (escalated -> assigned: manager) |
| assigned, reopened | in_progress | assignee, supervisor | no | technician must be assigned |
| in_progress | blocked / awaiting_parts | assignee, supervisor | yes | |
| blocked, awaiting_parts | in_progress | assignee, supervisor | no | |
| in_progress | completion_review | assignee only | no | `complete`; every mandatory checklist step done or N/A |
| completion_review | closed | supervisor | no | sets `closed_at` |
| completion_review | reopened | supervisor | yes | keeps the assignee |

`closed` and `rejected` are terminal. A test walks the table to check that every status is
reachable and every open status can still reach an end. Reassignment while assigned,
in_progress, blocked or awaiting_parts keeps the status and writes `work_order.reassign`.

Priority override (on approve or PATCH): supervisor only, reason required, writes `work_order.priority_override`,
sets `priority_rule = supervisor_override`, recomputes `due_at`.

## SLA (configurable in `workflow_policy.yaml`)

critical 4 h, high 24 h, medium 72 h, low 7 d -> `due_at = created_at + hours`. Overdue = past `due_at` while
still owed (any open status except `completion_review`).

## Phase 4 schema changes (migration 0002)

- `work_order_evidence.report_id` (uuid, unique). One preview report becomes at most one work order, alongside the
  client `submission_key`.
- `audit_logs.seq` (bigint identity, unique). Strict insertion order. Several audit rows are often written in one
  transaction, and PostgreSQL `now()` is the transaction start time, so timestamps alone cannot order them.
- `audit_logs.timestamp` and `assignments.assigned_at` default to `clock_timestamp()`, the actual write time.
