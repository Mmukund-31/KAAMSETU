"""Equipment register: list, detail with maintenance history, create."""

import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.database.errors import UNIQUE_VIOLATION, sqlstate
from app.domain.enums import EquipmentCategory, UserRole
from app.intelligence.config_loader import taxonomy
from app.models import Equipment, Site, User, WorkOrder, normalize_equipment_code
from app.schemas.management import (
    EquipmentCreate,
    EquipmentDetail,
    EquipmentOut,
    EquipmentPage,
    FaultCount,
)
from app.services import access, audit
from app.services.work_orders import summary
from app.workflows.escalation import OPEN_STATUSES

RECURRING_DAYS = 90


def _open_counts(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not ids:
        return {}
    rows = db.execute(select(WorkOrder.equipment_id, func.count()).where(
        WorkOrder.equipment_id.in_(ids), WorkOrder.status.in_(OPEN_STATUSES)).group_by(WorkOrder.equipment_id))
    return dict(rows.all())


def out(e: Equipment, open_count: int) -> EquipmentOut:
    return EquipmentOut(id=e.id, code=e.equipment_code, name=e.name, category=e.category, site_id=e.site_id,
                        site_name=e.site.name, location=e.location, operational_status=e.operational_status,
                        is_critical=e.is_critical, open_work_orders=open_count, created_at=e.created_at)


def list_equipment(db: Session, user: User, *, category: EquipmentCategory | None, q: str | None,
                   site_id: uuid.UUID | None, page: int, page_size: int) -> EquipmentPage:
    query = select(Equipment)
    scope = access.site_scope(user)
    if scope is not None:
        query = query.where(Equipment.site_id == scope)
    elif site_id:
        query = query.where(Equipment.site_id == site_id)
    if category:
        query = query.where(Equipment.category == category)
    if q and q.strip():
        like = f"%{q.strip()}%"
        query = query.where(or_(Equipment.equipment_code.ilike(like), Equipment.name.ilike(like),
                                Equipment.location.ilike(like),
                                Equipment.code_normalized == normalize_equipment_code(q)))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = list(db.scalars(query.order_by(Equipment.equipment_code).offset((page - 1) * page_size).limit(page_size)))
    counts = _open_counts(db, [e.id for e in rows])
    return EquipmentPage(items=[out(e, counts.get(e.id, 0)) for e in rows], total=total, page=page,
                         page_size=page_size)


def fault_counts(symptom_lists: list[list[str]], language: str = "en", limit: int = 5) -> list[FaultCount]:
    tax = taxonomy()
    counter = Counter(s for symptoms in symptom_lists for s in (symptoms or []))
    return [FaultCount(symptom=s, label=tax.symptoms[s].label_for(language) if s in tax.symptoms else s, count=n)
            for s, n in counter.most_common(limit)]


def get_detail(db: Session, user: User, equipment_id: uuid.UUID) -> EquipmentDetail:
    e = db.get(Equipment, equipment_id)
    if e is None or not access.can_view_site(user, e.site_id):
        raise NotFound("Equipment not found", code="equipment_not_found")
    since = datetime.now(UTC) - timedelta(days=RECURRING_DAYS)
    orders = list(db.scalars(select(WorkOrder).where(WorkOrder.equipment_id == e.id)
                             .order_by(WorkOrder.created_at.desc())))
    recent_90 = [w for w in orders if w.created_at >= since]
    visible = [w for w in orders if access.can_view(user, w)]
    lang = user.preferred_language.value
    return EquipmentDetail(
        **out(e, sum(1 for w in orders if w.status in OPEN_STATUSES)).model_dump(),
        work_orders_total=len(orders), work_orders_90d=len(recent_90),
        recurring_faults=[f for f in fault_counts([w.symptoms for w in recent_90], lang) if f.count >= 2],
        recent_work_orders=[summary(w) for w in visible[:20]],
    )


def create(db: Session, actor: User, data: EquipmentCreate) -> EquipmentOut:
    if actor.role not in (UserRole.SUPERVISOR, UserRole.MANAGER):
        raise Forbidden("Only supervisors can register equipment", code="insufficient_role")
    site_id = data.site_id or actor.site_id
    if site_id is None or db.get(Site, site_id) is None:
        raise Unprocessable("A valid site is required", code="unknown_site")
    if not access.can_view_site(actor, site_id):
        raise Forbidden("You can only register equipment at your own site", code="site_not_permitted")
    code = data.equipment_code.strip().upper().replace(" ", "-")
    if "-" not in code:
        letters = code.rstrip("0123456789")
        code = f"{letters}-{code[len(letters):]}"
    if db.scalar(select(Equipment).where(Equipment.code_normalized == normalize_equipment_code(code))):
        raise Conflict(f"Equipment {code} is already registered", code="equipment_code_taken")
    e = Equipment(equipment_code=code, name=data.name.strip(), category=data.category, site_id=site_id,
                  location=data.location, is_critical=data.is_critical)
    db.add(e)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        if sqlstate(exc) == UNIQUE_VIOLATION:
            raise Conflict(f"Equipment {code} is already registered", code="equipment_code_taken") from exc
        raise
    audit.record(db, actor_id=actor.id, action="equipment.create", entity_type="equipment", entity_id=e.id,
                 new_value={"code": code, "name": e.name, "category": e.category, "is_critical": e.is_critical})
    db.commit()
    db.refresh(e)
    return out(e, 0)
