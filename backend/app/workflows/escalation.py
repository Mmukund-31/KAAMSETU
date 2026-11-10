"""SLA due dates and overdue rules (hours per priority in config/workflow_policy.yaml)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_
from sqlalchemy.sql.elements import ColumnElement

from app.domain.enums import Priority, WorkOrderStatus
from app.intelligence.config_loader import workflow_policy
from app.models import WorkOrder

S = WorkOrderStatus
# Work is still owed. completion_review is excluded: the technician has finished and it awaits sign-off.
OVERDUE_STATUSES = frozenset({S.REPORTED, S.UNDER_REVIEW, S.APPROVED, S.ASSIGNED, S.IN_PROGRESS, S.BLOCKED,
                              S.AWAITING_PARTS, S.ESCALATED, S.REOPENED})
OPEN_STATUSES = frozenset(set(S) - {S.CLOSED, S.REJECTED})


def due_at(created_at: datetime, priority: Priority) -> datetime:
    return created_at + timedelta(hours=workflow_policy().sla_hours[priority])


def is_overdue(wo: WorkOrder, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    return wo.due_at is not None and wo.status in OVERDUE_STATUSES and wo.due_at < now


def overdue_clause(now: datetime | None = None) -> ColumnElement[bool]:
    now = now or datetime.now(UTC)
    return and_(WorkOrder.status.in_(OVERDUE_STATUSES), WorkOrder.due_at.is_not(None), WorkOrder.due_at < now)
