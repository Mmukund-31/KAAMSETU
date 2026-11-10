"""Work-order queries and serialisation (read side)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import String, case, cast, func, or_, select
from sqlalchemy.orm import Session

from app.domain.enums import Priority, UserRole, WorkOrderStatus
from app.intelligence.response import priority_label, render
from app.models import (
    Assignment,
    AuditLog,
    Equipment,
    User,
    WorkOrder,
    WorkOrderChecklist,
)
from app.schemas.work_order import (
    AllowedActionOut,
    AssignmentOut,
    ChecklistItemOut,
    ChecklistOut,
    EquipmentRef,
    EvidenceOut,
    HistoryEntry,
    PersonRef,
    WorkOrderDetail,
    WorkOrderPage,
    WorkOrderSummary,
)
from app.services import access, checklists, state_machine
from app.workflows.assignment import ASSIGN_TRANSITIONS, REASSIGNABLE
from app.workflows.escalation import is_overdue, overdue_clause

_PRIORITY_ORDER = {Priority.CRITICAL: 0, Priority.HIGH: 1, Priority.MEDIUM: 2, Priority.LOW: 3}
SORTS = {"created_desc", "created_asc", "due_asc", "priority", "updated_desc"}


def person(user: User | None) -> PersonRef | None:
    return PersonRef(id=user.id, name=user.name) if user else None


def summary(wo: WorkOrder, now: datetime | None = None) -> WorkOrderSummary:
    e = wo.equipment
    return WorkOrderSummary(
        id=wo.id, number=wo.number, display_number=wo.display_number, status=wo.status, priority=wo.priority,
        issue_category=wo.issue_category, symptoms=wo.symptoms or [], issue_description=wo.issue_description,
        production_impact=wo.production_impact, safety_concern=wo.safety_concern, report_channel=wo.report_channel,
        equipment=EquipmentRef(id=e.id, code=e.equipment_code, name=e.name, category=e.category, location=e.location,
                               is_critical=e.is_critical),
        reporter=person(wo.reporter), assignee=person(wo.assignee), created_at=wo.created_at,
        updated_at=wo.updated_at, due_at=wo.due_at, closed_at=wo.closed_at, is_overdue=is_overdue(wo, now),
    )


def list_work_orders(
    db: Session,
    user: User,
    *,
    statuses: list[WorkOrderStatus] | None = None,
    priorities: list[Priority] | None = None,
    equipment_id: uuid.UUID | None = None,
    assigned_to: uuid.UUID | None = None,
    reported_by: uuid.UUID | None = None,
    mine: bool = False,
    overdue: bool | None = None,
    safety_only: bool = False,
    q: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    sort: str = "created_desc",
    page: int = 1,
    page_size: int = 20,
) -> WorkOrderPage:
    query = access.scope_work_orders(select(WorkOrder), user)
    if statuses:
        query = query.where(WorkOrder.status.in_(statuses))
    if priorities:
        query = query.where(WorkOrder.priority.in_(priorities))
    if equipment_id:
        query = query.where(WorkOrder.equipment_id == equipment_id)
    if assigned_to:
        query = query.where(WorkOrder.assigned_to == assigned_to)
    if reported_by:
        query = query.where(WorkOrder.reported_by == reported_by)
    if mine:
        query = query.where(WorkOrder.assigned_to == user.id)
    if overdue is True:
        query = query.where(overdue_clause())
    elif overdue is False:
        query = query.where(~overdue_clause())
    if safety_only:
        query = query.where(WorkOrder.safety_concern.is_(True))
    if created_from:
        query = query.where(WorkOrder.created_at >= created_from)
    if created_to:
        query = query.where(WorkOrder.created_at <= created_to)
    if q and q.strip():
        term = q.strip()
        number = term.upper().removeprefix("WO-").removeprefix("WO")
        like = f"%{term}%"
        conditions = [WorkOrder.issue_description.ilike(like),
                      WorkOrder.equipment_id.in_(select(Equipment.id).where(
                          or_(Equipment.equipment_code.ilike(like), Equipment.name.ilike(like))))]
        if number.isdigit():
            conditions.append(cast(WorkOrder.number, String) == number)
        query = query.where(or_(*conditions))

    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    order = {
        "created_desc": [WorkOrder.created_at.desc()],
        "created_asc": [WorkOrder.created_at.asc()],
        "due_asc": [WorkOrder.due_at.asc().nulls_last()],
        "updated_desc": [WorkOrder.updated_at.desc()],
        "priority": [case(_PRIORITY_ORDER, value=WorkOrder.priority), WorkOrder.created_at.desc()],
    }[sort]
    rows = db.scalars(query.order_by(*order, WorkOrder.number.desc()).offset((page - 1) * page_size)
                      .limit(page_size)).unique().all()
    now = datetime.now(UTC)
    return WorkOrderPage(items=[summary(w, now) for w in rows], total=total or 0, page=page, page_size=page_size)


def checklist_out(db: Session, c: WorkOrderChecklist) -> ChecklistOut:
    by_item = {r.checklist_item_id: r for r in c.responses}
    people = {u.id: u for u in db.scalars(select(User).where(User.id.in_({r.completed_by for r in c.responses})))} \
        if c.responses else {}
    items = []
    for item in c.template.items:
        r = by_item.get(item.id)
        items.append(ChecklistItemOut(
            id=item.id, sequence=item.sequence, description=item.description, is_mandatory=item.is_mandatory,
            response=r.response if r else None, notes=r.notes if r else None,
            completed_by=person(people.get(r.completed_by)) if r else None, completed_at=r.completed_at if r else None,
        ))
    return ChecklistOut(id=c.id, work_order_id=c.work_order_id, template_id=c.template_id,
                        template_name=c.template.name, template_version=c.template_version, status=c.status,
                        created_at=c.created_at, completed_at=c.completed_at, items=items, **checklists.progress(c))


def history(db: Session, entity_type: str, entity_id: uuid.UUID) -> list[HistoryEntry]:
    rows = db.execute(
        select(AuditLog, User).outerjoin(User, User.id == AuditLog.actor_id)
        .where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
        .order_by(AuditLog.seq)
    ).all()
    return [HistoryEntry(id=a.id, action=a.action, actor=person(u), previous_value=a.previous_value,
                         new_value=a.new_value, comment=a.comment, timestamp=a.timestamp) for a, u in rows]


def detail(db: Session, user: User, wo: WorkOrder) -> WorkOrderDetail:
    db.refresh(wo)
    ev = wo.evidence
    evidence = None
    if ev is not None:
        data = ev.extracted_data or {}
        evidence = EvidenceOut(
            original_transcript=ev.original_transcript, detected_language=ev.detected_language,
            selected_language=ev.selected_language.value if ev.selected_language else None,
            prisma_request_id=ev.prisma_request_id, prisma_model=ev.prisma_model,
            utterances=data.get("utterances", []), validated=data.get("validated", {}),
            audio_retained=ev.audio_reference is not None, created_at=ev.created_at,
        )
    assignment_rows = db.execute(
        select(Assignment, User).join(User, User.id == Assignment.technician_id)
        .where(Assignment.work_order_id == wo.id).order_by(Assignment.assigned_at, Assignment.id)
    ).all()
    assigners = {u.id: u for u in db.scalars(select(User).where(User.id.in_({a.assigned_by for a, _ in assignment_rows})))}
    assignments = [AssignmentOut(technician=person(t), assigned_by=person(assigners.get(a.assigned_by)),
                                 assigned_at=a.assigned_at, comments=a.comments) for a, t in assignment_rows]

    is_supervisor = user.role in (UserRole.SUPERVISOR, UserRole.MANAGER)
    can_assign = is_supervisor and (wo.status in REASSIGNABLE or (
        wo.status in ASSIGN_TRANSITIONS and (wo.status != WorkOrderStatus.ESCALATED or user.role == UserRole.MANAGER)))
    announcement = None
    if wo.assigned_to == user.id and wo.status in (WorkOrderStatus.ASSIGNED, WorkOrderStatus.REOPENED):
        lang = user.preferred_language.value
        announcement = render("task_assigned", lang, number=wo.display_number, code=wo.equipment.equipment_code,
                              priority=priority_label(wo.priority, lang))

    return WorkOrderDetail(
        **summary(wo).model_dump(),
        priority_rule=wo.priority_rule, requires_approval=wo.requires_approval, location_note=wo.location_note,
        evidence=evidence, assignments=assignments,
        checklists=[checklist_out(db, c) for c in checklists.for_work_order(db, wo.id)],
        history=history(db, "work_order", wo.id),
        allowed_actions=[AllowedActionOut(action=a.via, to=a.to, comment_required=a.comment_required,
                                          blocked_reason=a.blocked_reason)
                         for a in state_machine.allowed_actions(db, wo, user) if a.via != "assign"],
        can_assign=can_assign,
        task_announcement=announcement,
    )
