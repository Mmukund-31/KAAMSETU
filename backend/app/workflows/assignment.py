"""Assign and reassign technicians. Attaches the approved checklist for the equipment category."""

from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.domain.enums import UserRole, WorkOrderStatus
from app.models import Assignment, User, WorkOrder
from app.services import audit, checklists, state_machine

S = WorkOrderStatus
# Statuses from which "assign" moves the order to ASSIGNED.
ASSIGN_TRANSITIONS = {S.APPROVED, S.REOPENED, S.ESCALATED}
# Statuses where a supervisor may hand the work to someone else without changing its status.
REASSIGNABLE = {S.ASSIGNED, S.IN_PROGRESS, S.BLOCKED, S.AWAITING_PARTS}


def assign(db: Session, actor: User, wo: WorkOrder, technician_id, comments: str | None) -> WorkOrder:
    if actor.role not in (UserRole.SUPERVISOR, UserRole.MANAGER):
        raise Forbidden("Only supervisors can assign work", code="insufficient_role")
    technician = db.get(User, technician_id)
    if technician is None:
        raise NotFound("Technician not found", code="technician_not_found")
    if technician.role != UserRole.TECHNICIAN or not technician.is_active:
        raise Unprocessable("Work can only be assigned to an active technician", code="not_a_technician")
    if technician.site_id != wo.equipment.site_id:
        raise Unprocessable("The technician works at a different site", code="technician_wrong_site")

    if wo.status not in ASSIGN_TRANSITIONS | REASSIGNABLE:
        raise Conflict(f"A {wo.status.value} work order cannot be assigned", code="invalid_transition",
                       details={"from": wo.status.value, "to": S.ASSIGNED.value})
    if wo.status in REASSIGNABLE and wo.assigned_to == technician.id:
        raise Conflict("The work order is already assigned to this technician", code="already_assigned")

    previous = wo.assigned_to
    wo.assigned_to = technician.id
    db.add(Assignment(work_order_id=wo.id, technician_id=technician.id, assigned_by=actor.id,
                      comments=(comments or "").strip() or None))
    db.flush()
    if wo.status in ASSIGN_TRANSITIONS:
        state_machine.transition(db, wo, S.ASSIGNED, actor, comments, via="assign",
                                 details={"technician_id": str(technician.id)})
    else:
        audit.record(db, actor_id=actor.id, action="work_order.reassign", entity_type="work_order", entity_id=wo.id,
                     previous_value={"assigned_to": str(previous) if previous else None},
                     new_value={"assigned_to": str(technician.id), "status": wo.status.value}, comment=comments)

    # Attach the approved SOP checklist for this equipment category, if one exists and none is attached yet.
    if not checklists.for_work_order(db, wo.id):
        template = checklists.active_template(db, wo.equipment.category)
        if template is not None:
            checklists.attach(db, actor, wo, template.id)
    db.commit()
    return wo
