"""Work-order lifecycle actions. Each one validates, changes state via the state machine, audits, and commits."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, Unprocessable
from app.database.errors import UNIQUE_VIOLATION, constraint_name, sqlstate
from app.domain.enums import (
    EquipmentCategory,
    Priority,
    ProductionImpact,
    ReportChannel,
    UserRole,
    WorkOrderStatus,
)
from app.intelligence.models import ReportDraft
from app.models import User, WorkOrder, WorkOrderEvidence
from app.services import audit, state_machine
from app.workflows import evidence as ev
from app.workflows import orchestrator
from app.workflows.escalation import due_at

logger = logging.getLogger("kaamsetu.work_orders")
S = WorkOrderStatus
TERMINAL = {S.CLOSED, S.REJECTED}


def _duplicate(db: Session, submission_key: str | None, report_id) -> WorkOrder | None:
    if submission_key:
        wo = db.scalar(select(WorkOrder).where(WorkOrder.submission_key == submission_key))
        if wo:
            return wo
    ev_row = db.scalar(select(WorkOrderEvidence).where(WorkOrderEvidence.report_id == report_id))
    return ev_row.work_order if ev_row else None


def create_from_report(db: Session, actor: User, evidence_token: str, draft: ReportDraft,
                       submission_key: str | None, submit: bool = True) -> WorkOrder:
    """Create a work order from a confirmed preview.

    Everything is re-validated server-side: the signed evidence, the equipment against the register,
    symptoms, category and priority. The client's draft is input, never trusted output.
    """
    evidence = ev.verify(evidence_token, actor.id)
    existing = _duplicate(db, submission_key, evidence.report_id)
    if existing:
        raise Conflict("This report was already submitted", code="duplicate_submission",
                       details={"work_order_id": str(existing.id), "number": existing.display_number})

    outcome = orchestrator.evaluate(db, actor, draft, evidence, evidence.language)
    if outcome.next_action != "confirm_preview":
        raise Unprocessable("The report is not complete yet", code="report_incomplete",
                            details={"next_action": outcome.next_action,
                                     "missing_fields": [m.field for m in outcome.missing_fields],
                                     "equipment_status": outcome.equipment.status})
    final = outcome.draft
    original = evidence.original
    now = datetime.now(UTC)
    wo = WorkOrder(
        equipment_id=outcome.equipment.equipment.id,  # type: ignore[union-attr]  # matched => present
        reported_by=actor.id,
        issue_description=final.issue_description.strip() or evidence.report_text,
        issue_category=outcome.category.value,
        symptoms=final.symptoms,
        priority=outcome.priority.level,
        priority_rule=outcome.priority.rule_id,
        production_impact=final.production_impact,
        safety_concern=final.safety_concern,
        requires_approval=outcome.requires_approval,
        report_channel=ReportChannel.VOICE if original.kind == "voice" else ReportChannel.TEXT,
        location_note=final.location_note,
        submission_key=submission_key,
        due_at=due_at(now, outcome.priority.level),
    )
    db.add(wo)
    try:
        db.flush()
        db.add(WorkOrderEvidence(
            work_order_id=wo.id,
            report_id=evidence.report_id,
            original_transcript=original.text,
            detected_language=original.detected_language,
            selected_language=evidence.language,
            prisma_request_id=original.gnani_request_id,
            prisma_model=original.model,
            audio_reference=None,  # AUDIO_RETENTION=none: audio is never stored
            extracted_data={
                "utterances": [u.model_dump(mode="json") for u in evidence.utterances],
                "submitted_draft": draft.model_dump(mode="json"),
                "validated": {
                    "equipment_code": final.equipment_code,
                    "symptoms": final.symptoms,
                    "category": outcome.category.value,
                    "category_basis": outcome.category.basis,
                    "priority": outcome.priority.model_dump(mode="json"),
                    "production_impact": final.production_impact.value,
                    "safety_concern": final.safety_concern,
                },
                "extraction": outcome.extraction.model_dump(mode="json") if outcome.extraction else None,
            },
        ))
        db.flush()
    except IntegrityError as exc:  # a concurrent duplicate won the race
        db.rollback()
        if sqlstate(exc) == UNIQUE_VIOLATION and constraint_name(exc) in (
                "uq_work_orders_submission_key", "uq_work_order_evidence_report_id"):
            raise Conflict("This report was already submitted", code="duplicate_submission") from exc
        raise

    audit.record(db, actor_id=actor.id, action="work_order.create", entity_type="work_order", entity_id=wo.id,
                 new_value={"number": wo.number, "equipment": final.equipment_code, "priority": wo.priority,
                            "priority_rule": wo.priority_rule, "category": wo.issue_category,
                            "channel": wo.report_channel, "safety_concern": wo.safety_concern})
    if submit:
        if wo.requires_approval:
            state_machine.transition(db, wo, S.UNDER_REVIEW, actor, via="submit")
        else:  # policy says no approval needed for this role
            _approve_by_policy(db, wo)
    db.commit()
    db.refresh(wo)
    logger.info("Work order created", extra={"ctx": {"work_order": wo.display_number, "priority": wo.priority.value}})
    return wo


def _approve_by_policy(db: Session, wo: WorkOrder) -> None:
    state_machine.transition(db, wo, S.UNDER_REVIEW, None, via="submit", details={"reason": "approval_not_required"})
    state_machine.transition(db, wo, S.APPROVED, None, via="approve", details={"reason": "approval_not_required"})


def submit(db: Session, actor: User, wo: WorkOrder) -> WorkOrder:
    state_machine.transition(db, wo, S.UNDER_REVIEW, actor, via="submit")
    db.commit()
    return wo


def _override_priority(db: Session, actor: User, wo: WorkOrder, priority: Priority, reason: str | None) -> None:
    if priority == wo.priority:
        return
    reason = (reason or "").strip()
    if len(reason) < state_machine.MIN_COMMENT:
        raise Unprocessable("A reason is required to change the priority", code="priority_reason_required")
    previous = {"priority": wo.priority.value, "priority_rule": wo.priority_rule,
                "due_at": wo.due_at.isoformat() if wo.due_at else None}
    wo.priority = priority
    wo.priority_rule = "supervisor_override"
    wo.due_at = due_at(wo.created_at, priority)
    audit.record(db, actor_id=actor.id, action="work_order.priority_override", entity_type="work_order",
                 entity_id=wo.id, previous_value=previous,
                 new_value={"priority": priority.value, "due_at": wo.due_at.isoformat()}, comment=reason)


def approve(db: Session, actor: User, wo: WorkOrder, comment: str | None, priority: Priority | None,
            priority_reason: str | None) -> WorkOrder:
    rule = state_machine.TRANSITIONS.get((wo.status, S.APPROVED))
    if rule is not None and actor.role in rule.roles and priority is not None:
        _override_priority(db, actor, wo, priority, priority_reason)
    state_machine.transition(db, wo, S.APPROVED, actor, comment, via="approve")
    db.commit()
    return wo


def reject(db: Session, actor: User, wo: WorkOrder, comment: str) -> WorkOrder:
    state_machine.transition(db, wo, S.REJECTED, actor, comment, via="reject")
    db.commit()
    return wo


def escalate(db: Session, actor: User, wo: WorkOrder, comment: str) -> WorkOrder:
    state_machine.transition(db, wo, S.ESCALATED, actor, comment, via="escalate")
    db.commit()
    return wo


def complete(db: Session, actor: User, wo: WorkOrder, notes: str | None) -> WorkOrder:
    state_machine.transition(db, wo, S.COMPLETION_REVIEW, actor, notes, via="complete")
    db.commit()
    return wo


def change_status(db: Session, actor: User, wo: WorkOrder, to: S, comment: str | None) -> WorkOrder:
    state_machine.transition(db, wo, to, actor, comment, via="status")
    db.commit()
    return wo


EDITABLE_BY_REPORTER = {S.REPORTED, S.UNDER_REVIEW}


def update_fields(db: Session, actor: User, wo: WorkOrder, *, issue_description: str | None,
                  location_note: str | None, issue_category: EquipmentCategory | None,
                  production_impact: ProductionImpact | None, priority: Priority | None,
                  priority_reason: str | None) -> WorkOrder:
    if wo.status in TERMINAL:
        raise Conflict(f"A {wo.status.value} work order cannot be edited", code="work_order_closed")
    supervisor = actor.role in (UserRole.SUPERVISOR, UserRole.MANAGER)
    if not supervisor:
        if actor.id != wo.reported_by or wo.status not in EDITABLE_BY_REPORTER:
            raise Forbidden("You can only edit your own report before it is approved", code="edit_not_permitted")
        if priority is not None and priority != wo.priority:
            raise Forbidden("Only supervisors can change the priority", code="edit_not_permitted")

    changes = {"issue_description": issue_description, "location_note": location_note,
               "issue_category": issue_category, "production_impact": production_impact}
    previous, new = {}, {}
    for field, value in changes.items():
        if value is not None and value != getattr(wo, field):
            previous[field], new[field] = getattr(wo, field), value
            setattr(wo, field, value)
    if new:
        audit.record(db, actor_id=actor.id, action="work_order.update", entity_type="work_order", entity_id=wo.id,
                     previous_value=previous, new_value=new)
    if priority is not None and supervisor:
        _override_priority(db, actor, wo, priority, priority_reason)
    db.commit()
    return wo
