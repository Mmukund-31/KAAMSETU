"""Shift handovers.

The summary is assembled from facts in the database (work completed this shift, open, blocked and
awaiting approval at the site, equipment needing attention) plus the author's own sentences,
sorted into next-shift actions or observations by configured cue words. Nothing is invented,
and the original notes or transcript are stored unchanged next to the summary.
"""

import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.domain.enums import HandoverStatus, Priority, UserRole, WorkOrderStatus
from app.intelligence.config_loader import workflow_policy
from app.intelligence.extraction import extract
from app.intelligence.text import tokens
from app.models import AuditLog, Equipment, Handover, User, WorkOrder, normalize_equipment_code
from app.schemas.management import HandoverDetail, HandoverOut, HandoverPage, PendingAction
from app.services import access, audit
from app.services.work_orders import history, person

S = WorkOrderStatus
_SENTENCES = re.compile(r"(?<=[.!?।॥])\s+|\n+")


def _brief(wo: WorkOrder) -> dict:
    return {"id": str(wo.id), "number": wo.display_number, "equipment_code": wo.equipment.equipment_code,
            "status": wo.status.value, "priority": wo.priority.value,
            "assignee": wo.assignee.name if wo.assignee else None}


def _split_notes(notes: str) -> tuple[list[str], list[str]]:
    cues = workflow_policy().handover.cue_keywords
    actions, observations = [], []
    for sentence in (s.strip() for s in _SENTENCES.split(notes)):
        if not sentence:
            continue
        toks = tokens(sentence)
        (actions if any(c.find(toks) for c in cues) else observations).append(sentence)
    return actions, observations


def build_summary(db: Session, site_id: uuid.UUID, notes: str, language: str) -> tuple[dict, list[dict]]:
    now = datetime.now(UTC)
    window_start = now - timedelta(hours=workflow_policy().handover.shift_hours)
    site_orders = select(WorkOrder).join(Equipment, Equipment.id == WorkOrder.equipment_id).where(
        Equipment.site_id == site_id)

    completed_ids = set(db.scalars(select(AuditLog.entity_id).where(
        AuditLog.entity_type == "work_order", AuditLog.action == "work_order.transition",
        AuditLog.timestamp >= window_start,
        AuditLog.new_value["status"].astext.in_([S.COMPLETION_REVIEW.value, S.CLOSED.value]))))
    completed = list(db.scalars(site_orders.where(WorkOrder.id.in_(completed_ids)))) if completed_ids else []
    open_rows = list(db.scalars(site_orders.where(WorkOrder.status.in_([
        S.APPROVED, S.ASSIGNED, S.IN_PROGRESS, S.REOPENED, S.BLOCKED, S.AWAITING_PARTS, S.UNDER_REVIEW,
        S.ESCALATED, S.REPORTED, S.COMPLETION_REVIEW])).order_by(WorkOrder.number)))
    blocked = [w for w in open_rows if w.status in (S.BLOCKED, S.AWAITING_PARTS)]
    awaiting = [w for w in open_rows if w.status in (S.REPORTED, S.UNDER_REVIEW, S.ESCALATED, S.COMPLETION_REVIEW)]
    pending = [w for w in open_rows if w.status in (S.APPROVED, S.ASSIGNED, S.IN_PROGRESS, S.REOPENED)]

    attention: dict[str, dict] = {}
    for w in open_rows:
        if w.priority in (Priority.CRITICAL, Priority.HIGH) or w.safety_concern:
            attention.setdefault(w.equipment.equipment_code, {
                "code": w.equipment.equipment_code, "name": w.equipment.name,
                "reason": "safety concern" if w.safety_concern else f"open {w.priority.value} priority work"})
    # Machines the author mentions are checked against the register; unknown codes are not listed.
    mentioned = {c.code for c in extract(notes, language).equipment_candidates}
    if mentioned:
        for e in db.scalars(select(Equipment).where(Equipment.site_id == site_id,
                                                    Equipment.code_normalized.in_(
                                                        {normalize_equipment_code(c) for c in mentioned}))):
            attention.setdefault(e.equipment_code, {"code": e.equipment_code, "name": e.name,
                                                    "reason": "mentioned in handover notes"})

    actions, observations = _split_notes(notes)
    summary = {
        "generated_at": now.isoformat(),
        "window_hours": workflow_policy().handover.shift_hours,
        "counts": {"completed": len(completed), "pending": len(pending), "blocked": len(blocked),
                   "awaiting_approval": len(awaiting)},
        "completed": [_brief(w) for w in completed],
        "pending": [_brief(w) for w in pending],
        "blocked": [_brief(w) for w in blocked],
        "awaiting_approval": [_brief(w) for w in awaiting],
        "equipment_attention": list(attention.values()),
        "next_shift_actions": actions,
        "observations": observations,
    }
    pending_actions = [PendingAction(text=a, source="notes").model_dump(mode="json") for a in actions]
    pending_actions += [PendingAction(text=f"{w.display_number} {w.equipment.equipment_code}: {w.status.value}",
                                      source="system", work_order_id=w.id).model_dump(mode="json") for w in blocked]
    return summary, pending_actions


def create(db: Session, actor: User, shift_identifier: str, notes: str, language: str | None,
           detected_language: str | None = None, transcript_meta: dict | None = None) -> Handover:
    if actor.site_id is None:
        raise Unprocessable("Your account is not linked to a site", code="no_site")
    notes = notes.strip()
    if not notes:
        raise Unprocessable("Handover notes are empty", code="empty_notes")
    lang = language or actor.preferred_language.value
    summary, pending = build_summary(db, actor.site_id, notes, lang)
    if transcript_meta:
        summary["transcript"] = transcript_meta
    h = Handover(site_id=actor.site_id, created_by=actor.id, shift_identifier=shift_identifier.strip(),
                 original_notes=notes, detected_language=detected_language, generated_summary=summary,
                 pending_actions=pending, status=HandoverStatus.SUBMITTED)
    db.add(h)
    db.flush()
    audit.record(db, actor_id=actor.id, action="handover.create", entity_type="handover", entity_id=h.id,
                 new_value={"shift": h.shift_identifier, "counts": summary["counts"],
                            "actions": len(pending)})
    db.commit()
    db.refresh(h)
    return h


def get(db: Session, user: User, handover_id: uuid.UUID) -> Handover:
    h = db.get(Handover, handover_id)
    if h is None or not access.can_view_site(user, h.site_id):
        raise NotFound("Handover not found", code="handover_not_found")
    return h


def review(db: Session, actor: User, h: Handover, comment: str | None,
           pending_actions: list[PendingAction] | None) -> Handover:
    if actor.role not in (UserRole.SUPERVISOR, UserRole.MANAGER):
        raise Forbidden("Only supervisors can review handovers", code="insufficient_role")
    if actor.id == h.created_by:
        raise Forbidden("You cannot review your own handover", code="self_review_not_allowed")
    if h.status != HandoverStatus.SUBMITTED:
        raise Conflict(f"This handover is already {h.status.value}", code="handover_not_submitted")
    previous = {"status": h.status.value, "pending_actions": len(h.pending_actions)}
    if pending_actions is not None:
        h.pending_actions = [a.model_dump(mode="json") for a in pending_actions]
    h.status = HandoverStatus.REVIEWED
    h.reviewed_by = actor.id
    h.reviewed_at = datetime.now(UTC)
    h.review_comment = (comment or "").strip() or None
    audit.record(db, actor_id=actor.id, action="handover.review", entity_type="handover", entity_id=h.id,
                 previous_value=previous, new_value={"status": h.status.value,
                                                     "pending_actions": len(h.pending_actions)},
                 comment=h.review_comment)
    db.commit()
    db.refresh(h)
    return h


def out(db: Session, h: Handover) -> HandoverOut:
    people = {u.id: u for u in db.scalars(select(User).where(User.id.in_({h.created_by, h.reviewed_by} - {None})))}
    return HandoverOut(id=h.id, site_id=h.site_id, shift_identifier=h.shift_identifier, status=h.status,
                       created_by=person(people[h.created_by]), created_at=h.created_at, original_notes=h.original_notes,
                       detected_language=h.detected_language, generated_summary=h.generated_summary,
                       pending_actions=h.pending_actions, reviewed_by=person(people.get(h.reviewed_by)),
                       reviewed_at=h.reviewed_at, review_comment=h.review_comment)


def detail(db: Session, h: Handover) -> HandoverDetail:
    return HandoverDetail(**out(db, h).model_dump(), history=history(db, "handover", h.id))


def list_handovers(db: Session, user: User, status: HandoverStatus | None, page: int, page_size: int) -> HandoverPage:
    query = select(Handover)
    scope = access.site_scope(user)
    if scope is not None:
        query = query.where(Handover.site_id == scope)
    if status:
        query = query.where(Handover.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(Handover.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return HandoverPage(items=[out(db, h) for h in rows], total=total, page=page, page_size=page_size)
