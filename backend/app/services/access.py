"""Who may see what.

Technicians see work orders they reported or are assigned to. Supervisors see their site.
Managers see their site, or every site when they have no site. A record outside a user's
scope is reported as 404, so its existence is not revealed.
"""

import uuid

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.models import Equipment, User, UserRole, WorkOrder


def site_scope(user: User) -> uuid.UUID | None:
    """Site the user is limited to, or None for unrestricted (a manager without a site)."""
    if user.role == UserRole.MANAGER and user.site_id is None:
        return None
    return user.site_id


def scope_work_orders(query: Select, user: User) -> Select:
    if user.role == UserRole.TECHNICIAN:
        return query.where(or_(WorkOrder.reported_by == user.id, WorkOrder.assigned_to == user.id))
    site = site_scope(user)
    if site is None:
        return query
    return query.where(WorkOrder.equipment_id.in_(select(Equipment.id).where(Equipment.site_id == site)))


def can_view(user: User, wo: WorkOrder) -> bool:
    if user.role == UserRole.TECHNICIAN:
        return user.id in (wo.reported_by, wo.assigned_to)
    site = site_scope(user)
    return site is None or wo.equipment.site_id == site


def get_work_order(db: Session, user: User, work_order_id: uuid.UUID, *, for_update: bool = False) -> WorkOrder:
    query = db.query(WorkOrder).filter(WorkOrder.id == work_order_id)
    if for_update:
        # Serialise concurrent actions on the same order (e.g. two supervisors approving at once).
        query = query.with_for_update(of=WorkOrder)
    wo = query.one_or_none()
    if wo is None or not can_view(user, wo):
        raise NotFound("Work order not found", code="work_order_not_found")
    return wo


def can_view_site(user: User, site_id: uuid.UUID) -> bool:
    scope = site_scope(user)
    return scope is None or scope == site_id
