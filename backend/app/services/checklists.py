"""Approved SOP checklists: templates (versioned), attaching them to work orders, recording each step.

Checklist text comes only from templates that supervisors create. KAAMSETU never generates steps.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.domain.enums import (
    ChecklistResponseValue,
    ChecklistStatus,
    EquipmentCategory,
    WorkOrderStatus,
)
from app.models import (
    ChecklistItem,
    ChecklistResponse,
    ChecklistTemplate,
    User,
    WorkOrder,
    WorkOrderChecklist,
)
from app.services import audit

DONE = {ChecklistResponseValue.DONE, ChecklistResponseValue.NOT_APPLICABLE}
ATTACHABLE = {WorkOrderStatus.APPROVED, WorkOrderStatus.ASSIGNED, WorkOrderStatus.IN_PROGRESS,
              WorkOrderStatus.BLOCKED, WorkOrderStatus.AWAITING_PARTS, WorkOrderStatus.REOPENED}


# ── templates ────────────────────────────────────────────────────────────

def list_templates(db: Session, category: EquipmentCategory | None, active_only: bool) -> list[ChecklistTemplate]:
    q = select(ChecklistTemplate).order_by(ChecklistTemplate.equipment_category, ChecklistTemplate.version.desc())
    if category:
        q = q.where(ChecklistTemplate.equipment_category == category)
    if active_only:
        q = q.where(ChecklistTemplate.is_active.is_(True))
    return list(db.scalars(q))


def get_template(db: Session, template_id: uuid.UUID) -> ChecklistTemplate:
    tpl = db.get(ChecklistTemplate, template_id)
    if tpl is None:
        raise NotFound("Checklist template not found", code="template_not_found")
    return tpl


def active_template(db: Session, category: EquipmentCategory, work_order_type: str = "corrective"):
    return db.scalar(select(ChecklistTemplate).where(
        ChecklistTemplate.equipment_category == category, ChecklistTemplate.work_order_type == work_order_type,
        ChecklistTemplate.is_active.is_(True)))


def publish_template(db: Session, actor: User, name: str, category: EquipmentCategory, work_order_type: str,
                     items: list[tuple[str, bool]]) -> ChecklistTemplate:
    """Create the next version for (category, type) and make it the only active one."""
    current_max = db.scalar(select(func.max(ChecklistTemplate.version)).where(
        ChecklistTemplate.equipment_category == category, ChecklistTemplate.work_order_type == work_order_type)) or 0
    previous = active_template(db, category, work_order_type)
    if previous is not None:
        previous.is_active = False
        db.flush()  # the partial unique index allows only one active version
    tpl = ChecklistTemplate(name=name.strip(), equipment_category=category, work_order_type=work_order_type,
                            version=current_max + 1, created_by=actor.id)
    tpl.items = [ChecklistItem(description=d.strip(), is_mandatory=m, sequence=i) for i, (d, m) in enumerate(items, 1)]
    db.add(tpl)
    db.flush()
    audit.record(db, actor_id=actor.id, action="checklist_template.publish", entity_type="checklist_template",
                 entity_id=tpl.id, previous_value={"active_version": previous.version} if previous else None,
                 new_value={"name": tpl.name, "category": category, "version": tpl.version, "items": len(items)})
    return tpl


def deactivate_template(db: Session, actor: User, tpl: ChecklistTemplate) -> ChecklistTemplate:
    if tpl.is_active:
        tpl.is_active = False
        audit.record(db, actor_id=actor.id, action="checklist_template.deactivate", entity_type="checklist_template",
                     entity_id=tpl.id, previous_value={"is_active": True}, new_value={"is_active": False})
    return tpl


# ── work-order checklists ────────────────────────────────────────────────

def for_work_order(db: Session, work_order_id: uuid.UUID) -> list[WorkOrderChecklist]:
    return list(db.scalars(select(WorkOrderChecklist).where(WorkOrderChecklist.work_order_id == work_order_id)
                           .order_by(WorkOrderChecklist.created_at)))


def attach(db: Session, actor: User | None, wo: WorkOrder, template_id: uuid.UUID | None = None):
    """Attach a template (default: the active one for the equipment category). Idempotent per template."""
    if wo.status not in ATTACHABLE:
        raise Conflict(f"A checklist cannot be attached while the order is {wo.status.value}",
                       code="checklist_not_allowed")
    tpl = get_template(db, template_id) if template_id else active_template(db, wo.equipment.category)
    if tpl is None:
        raise NotFound(f"No active checklist template for {wo.equipment.category.value} equipment",
                       code="no_active_template")
    if not tpl.is_active:
        raise Conflict("Only active template versions can be attached", code="template_inactive")
    existing = next((c for c in for_work_order(db, wo.id) if c.template_id == tpl.id), None)
    if existing:
        return existing
    checklist = WorkOrderChecklist(work_order_id=wo.id, template_id=tpl.id, template_version=tpl.version)
    db.add(checklist)
    db.flush()
    audit.record(db, actor_id=actor.id if actor else None, action="checklist.attach", entity_type="work_order",
                 entity_id=wo.id, new_value={"checklist_id": checklist.id, "template": tpl.name,
                                             "version": tpl.version})
    return checklist


def progress(checklist: WorkOrderChecklist) -> dict:
    by_item = {r.checklist_item_id: r for r in checklist.responses}
    mandatory = [i for i in checklist.template.items if i.is_mandatory]
    mandatory_done = sum(1 for i in mandatory if by_item.get(i.id) and by_item[i.id].response in DONE)
    return {"items_total": len(checklist.template.items), "items_answered": len(by_item),
            "mandatory_total": len(mandatory), "mandatory_done": mandatory_done,
            "is_complete": mandatory_done == len(mandatory)}


def incomplete_checklists(db: Session, wo: WorkOrder) -> list[WorkOrderChecklist]:
    return [c for c in for_work_order(db, wo.id) if not progress(c)["is_complete"]]


def get_checklist(db: Session, checklist_id: uuid.UUID) -> WorkOrderChecklist:
    c = db.get(WorkOrderChecklist, checklist_id)
    if c is None:
        raise NotFound("Checklist not found", code="checklist_not_found")
    return c


def record_item(db: Session, actor: User, checklist: WorkOrderChecklist, wo: WorkOrder, item_id: uuid.UUID,
                response: ChecklistResponseValue, notes: str | None) -> ChecklistResponse:
    if actor.id != wo.assigned_to:
        raise Forbidden("Only the assigned technician can record checklist steps", code="not_assignee")
    if wo.status != WorkOrderStatus.IN_PROGRESS:
        raise Conflict("Start the work before recording checklist steps", code="work_not_in_progress")
    item = next((i for i in checklist.template.items if i.id == item_id), None)
    if item is None:
        raise NotFound("Checklist item not found", code="checklist_item_not_found")
    notes = (notes or "").strip() or None
    if response != ChecklistResponseValue.DONE and (not notes or len(notes) < 3):
        raise Unprocessable("A note is required when a step is not applicable or failed", code="notes_required")

    existing = next((r for r in checklist.responses if r.checklist_item_id == item_id), None)
    previous = {"response": existing.response, "notes": existing.notes} if existing else None
    now = datetime.now(UTC)
    if existing:
        existing.response, existing.notes, existing.completed_by, existing.completed_at = response, notes, actor.id, now
        row = existing
    else:
        row = ChecklistResponse(checklist_id=checklist.id, checklist_item_id=item_id, response=response, notes=notes,
                                completed_by=actor.id, completed_at=now)
        checklist.responses.append(row)
    db.flush()

    state = progress(checklist)
    all_answered = state["items_answered"] == state["items_total"]
    checklist.status = ChecklistStatus.COMPLETED if state["is_complete"] and all_answered else ChecklistStatus.IN_PROGRESS
    checklist.completed_at = now if checklist.status == ChecklistStatus.COMPLETED else None
    audit.record(db, actor_id=actor.id, action="checklist.item_update", entity_type="work_order", entity_id=wo.id,
                 previous_value=previous, new_value={"checklist_id": checklist.id, "item": item.sequence,
                                                     "response": response, "notes": notes},
                 comment=None)
    return row
