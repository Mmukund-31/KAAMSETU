"""Dashboard aggregates. Every number is a SQL aggregate over real rows; nothing is hard-coded."""

import uuid
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Date, cast, func, literal_column, select
from sqlalchemy.orm import Session

from app.domain.enums import Priority, UserRole, WorkOrderStatus
from app.models import Equipment, User, WorkOrder
from app.schemas.management import (
    EquipmentIssue,
    EquipmentIssues,
    Overview,
    TechnicianWorkload,
    TrendPoint,
)
from app.services import access
from app.services.equipment import fault_counts
from app.services.work_orders import person
from app.workflows.escalation import OPEN_STATUSES, overdue_clause

S = WorkOrderStatus


def _scoped(user: User):
    """Base query of work orders the dashboard user may see (their site, or all for a site-less manager)."""
    query = select(WorkOrder).join(Equipment, Equipment.id == WorkOrder.equipment_id)
    site = access.site_scope(user)
    return query.where(Equipment.site_id == site) if site is not None else query


def _count(db: Session, query) -> int:
    return db.scalar(select(func.count()).select_from(query.subquery())) or 0


def overview(db: Session, user: User) -> Overview:
    base = _scoped(user)
    now = datetime.now(UTC)
    # Aggregate over a subquery of the scoped query so the equipment join (site scope) is preserved.
    sub = base.subquery()
    rows = db.execute(select(sub.c.status, func.count()).group_by(sub.c.status)).all()
    by_status = {s: 0 for s in S} | {S(status): n for status, n in rows}
    open_sub = base.where(WorkOrder.status.in_(OPEN_STATUSES)).subquery()
    prio_rows = db.execute(select(open_sub.c.priority, func.count()).group_by(open_sub.c.priority)).all()
    by_priority = {p: 0 for p in Priority} | {Priority(p): n for p, n in prio_rows}
    open_total = sum(n for s, n in by_status.items() if s in OPEN_STATUSES)
    return Overview(
        total=sum(by_status.values()),
        open=open_total,
        pending_approval=by_status[S.REPORTED] + by_status[S.UNDER_REVIEW] + by_status[S.ESCALATED],
        in_progress=by_status[S.IN_PROGRESS],
        blocked=by_status[S.BLOCKED] + by_status[S.AWAITING_PARTS],
        completion_review=by_status[S.COMPLETION_REVIEW],
        critical_high_open=by_priority[Priority.CRITICAL] + by_priority[Priority.HIGH],
        overdue=_count(db, base.where(overdue_clause(now))),
        safety_open=_count(db, base.where(WorkOrder.status.in_(OPEN_STATUSES), WorkOrder.safety_concern.is_(True))),
        completed_7d=_count(db, base.where(WorkOrder.status == S.CLOSED,
                                           WorkOrder.closed_at >= now - timedelta(days=7))),
        by_status=by_status,
        by_priority_open=by_priority,
        generated_at=now,
    )


def trends(db: Session, user: User, days: int) -> list[TrendPoint]:
    today = datetime.now(UTC).date()
    start = today - timedelta(days=days - 1)
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
    base = _scoped(user)
    c_sub = base.where(WorkOrder.created_at >= start_dt).subquery()
    k_sub = base.where(WorkOrder.closed_at >= start_dt).subquery()
    # Literal 'UTC' (not a bind parameter) so SELECT and GROUP BY are the same expression for PostgreSQL.
    utc = literal_column("'UTC'")
    day_created = cast(func.timezone(utc, c_sub.c.created_at), Date)
    day_closed = cast(func.timezone(utc, k_sub.c.closed_at), Date)
    created = dict(db.execute(select(day_created, func.count()).group_by(day_created)).all())
    closed = dict(db.execute(select(day_closed, func.count()).group_by(day_closed)).all())
    points = []
    for i in range(days):
        d: date = start + timedelta(days=i)
        points.append(TrendPoint(day=d, created=created.get(d, 0), closed=closed.get(d, 0)))
    return points


def equipment_issues(db: Session, user: User, days: int, limit: int) -> EquipmentIssues:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = list(db.scalars(_scoped(user).where(WorkOrder.created_at >= since)))
    by_equipment: dict[uuid.UUID, list[WorkOrder]] = defaultdict(list)
    for w in rows:
        by_equipment[w.equipment_id].append(w)
    lang = user.preferred_language.value
    issues = []
    for orders in by_equipment.values():
        e = orders[0].equipment
        issues.append(EquipmentIssue(
            equipment_id=e.id, code=e.equipment_code, name=e.name, category=e.category, is_critical=e.is_critical,
            work_orders=len(orders), open=sum(1 for w in orders if w.status in OPEN_STATUSES),
            top_symptoms=fault_counts([w.symptoms for w in orders], lang, limit=3), recurring=len(orders) >= 2))
    issues.sort(key=lambda i: (-i.work_orders, -i.open, i.code))
    categories = Counter(w.issue_category for w in rows)
    return EquipmentIssues(days=days, equipment=issues[:limit], by_category=dict(categories),
                           by_symptom=fault_counts([w.symptoms for w in rows], lang, limit=10))


def technician_workload(db: Session, user: User) -> list[TechnicianWorkload]:
    tech_query = select(User).where(User.role == UserRole.TECHNICIAN, User.is_active.is_(True)).order_by(User.name)
    site = access.site_scope(user)
    if site is not None:
        tech_query = tech_query.where(User.site_id == site)
    techs = list(db.scalars(tech_query))
    if not techs:
        return []
    ids = [t.id for t in techs]
    now = datetime.now(UTC)
    counts: dict[uuid.UUID, Counter] = defaultdict(Counter)
    for assignee, status, n in db.execute(select(WorkOrder.assigned_to, WorkOrder.status, func.count())
                                          .where(WorkOrder.assigned_to.in_(ids))
                                          .group_by(WorkOrder.assigned_to, WorkOrder.status)).all():
        counts[assignee][status] = n
    overdue = dict(db.execute(select(WorkOrder.assigned_to, func.count()).where(
        WorkOrder.assigned_to.in_(ids), overdue_clause(now)).group_by(WorkOrder.assigned_to)).all())
    closed_30 = dict(db.execute(select(WorkOrder.assigned_to, func.count()).where(
        WorkOrder.assigned_to.in_(ids), WorkOrder.status == S.CLOSED,
        WorkOrder.closed_at >= now - timedelta(days=30)).group_by(WorkOrder.assigned_to)).all())
    result = []
    for t in techs:
        c = counts[t.id]
        result.append(TechnicianWorkload(
            technician=person(t), preferred_language=t.preferred_language,
            assigned=c[S.ASSIGNED] + c[S.REOPENED], in_progress=c[S.IN_PROGRESS],
            blocked=c[S.BLOCKED] + c[S.AWAITING_PARTS], completion_review=c[S.COMPLETION_REVIEW],
            overdue=overdue.get(t.id, 0), closed_30d=closed_30.get(t.id, 0),
            open_total=sum(n for s, n in c.items() if s in OPEN_STATUSES)))
    return result
