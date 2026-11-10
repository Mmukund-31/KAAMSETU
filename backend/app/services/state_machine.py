"""Work-order lifecycle: the ONLY place a work order's status changes.

Every transition is validated against TRANSITIONS (from, to) -> Rule, checked for role and
assignment, checked against its guards, applied, and written to audit_logs in the caller's
transaction. API routes and workflows never set `status` directly.

    REPORTED -> UNDER_REVIEW -> APPROVED -> ASSIGNED -> IN_PROGRESS -> COMPLETION_REVIEW -> CLOSED
    side states: REJECTED, BLOCKED, AWAITING_PARTS, ESCALATED, REOPENED
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import Conflict, Forbidden, Unprocessable
from app.domain.enums import UserRole, WorkOrderStatus
from app.models import User, WorkOrder
from app.services import audit, checklists

S = WorkOrderStatus
SUP = frozenset({UserRole.SUPERVISOR, UserRole.MANAGER})
MGR = frozenset({UserRole.MANAGER})
NONE: frozenset[UserRole] = frozenset()

Via = Literal["submit", "approve", "reject", "assign", "complete", "escalate", "status"]


@dataclass(frozen=True)
class Rule:
    roles: frozenset[UserRole]                                  # may act on any order in their scope
    technician: Literal["assignee", "reporter"] | None = None    # a technician may act if they are this
    comment_required: bool = False
    via: Via = "status"                                          # the API action that performs it


TRANSITIONS: dict[tuple[S, S], Rule] = {
    (S.REPORTED, S.UNDER_REVIEW): Rule(SUP, technician="reporter", via="submit"),
    (S.REPORTED, S.REJECTED): Rule(SUP, comment_required=True, via="reject"),
    (S.UNDER_REVIEW, S.APPROVED): Rule(SUP, via="approve"),
    (S.UNDER_REVIEW, S.REJECTED): Rule(SUP, comment_required=True, via="reject"),
    (S.APPROVED, S.REJECTED): Rule(SUP, comment_required=True, via="reject"),
    (S.APPROVED, S.ASSIGNED): Rule(SUP, via="assign"),
    (S.REOPENED, S.ASSIGNED): Rule(SUP, via="assign"),
    (S.ESCALATED, S.ASSIGNED): Rule(MGR, via="assign"),
    (S.ASSIGNED, S.IN_PROGRESS): Rule(SUP, technician="assignee"),
    (S.REOPENED, S.IN_PROGRESS): Rule(SUP, technician="assignee"),
    (S.IN_PROGRESS, S.BLOCKED): Rule(SUP, technician="assignee", comment_required=True),
    (S.IN_PROGRESS, S.AWAITING_PARTS): Rule(SUP, technician="assignee", comment_required=True),
    (S.BLOCKED, S.IN_PROGRESS): Rule(SUP, technician="assignee"),
    (S.AWAITING_PARTS, S.IN_PROGRESS): Rule(SUP, technician="assignee"),
    (S.IN_PROGRESS, S.COMPLETION_REVIEW): Rule(NONE, technician="assignee", via="complete"),
    (S.COMPLETION_REVIEW, S.CLOSED): Rule(SUP),
    (S.COMPLETION_REVIEW, S.REOPENED): Rule(SUP, comment_required=True),
    (S.ESCALATED, S.APPROVED): Rule(MGR, comment_required=True, via="approve"),
    (S.ESCALATED, S.REJECTED): Rule(MGR, comment_required=True, via="reject"),
    (S.ESCALATED, S.IN_PROGRESS): Rule(MGR, comment_required=True),
    **{(src, S.ESCALATED): Rule(SUP, comment_required=True, via="escalate")
       for src in (S.UNDER_REVIEW, S.APPROVED, S.ASSIGNED, S.IN_PROGRESS, S.BLOCKED, S.AWAITING_PARTS)},
}
MIN_COMMENT = 3


@dataclass(frozen=True)
class AllowedAction:
    to: S
    via: Via
    comment_required: bool
    blocked_reason: str | None = None


def _permitted(rule: Rule, actor: User, wo: WorkOrder) -> bool:
    if actor.role in rule.roles:
        return True
    if actor.role == UserRole.TECHNICIAN:
        if rule.technician == "assignee":
            return wo.assigned_to == actor.id
        if rule.technician == "reporter":
            return wo.reported_by == actor.id
    return False


def _guard(db: Session, wo: WorkOrder, to: S, actor: User) -> str | None:
    """Return why the transition cannot happen now, or None."""
    if to in (S.ASSIGNED, S.IN_PROGRESS) and wo.assigned_to is None:
        return "no_technician_assigned"
    if to == S.APPROVED and actor.id == wo.reported_by and not get_settings().allow_self_approval:
        return "self_approval_not_allowed"
    if to == S.COMPLETION_REVIEW and checklists.incomplete_checklists(db, wo):
        return "checklist_incomplete"
    return None


_GUARD_ERRORS = {
    "no_technician_assigned": (Conflict, "Assign a technician first"),
    "self_approval_not_allowed": (Forbidden, "You cannot approve a work order you reported"),
    "checklist_incomplete": (Conflict, "Complete all mandatory checklist steps first"),
}


def transition(
    db: Session,
    wo: WorkOrder,
    to: S,
    actor: User | None,
    comment: str | None = None,
    *,
    via: Via = "status",
    details: dict[str, Any] | None = None,
) -> WorkOrder:
    """Validate and apply one transition. `actor=None` means an automatic transition by system policy."""
    current = wo.status
    rule = TRANSITIONS.get((current, to))
    if rule is None:
        allowed = sorted(t.value for (f, t) in TRANSITIONS if f == current)
        raise Conflict(f"Cannot move a work order from {current.value} to {to.value}", code="invalid_transition",
                       details={"from": current.value, "to": to.value, "allowed": allowed})
    if rule.via != via:
        raise Conflict(f"Use the '{rule.via}' action for this change", code="use_dedicated_action",
                       details={"action": rule.via})
    if actor is not None:
        if not _permitted(rule, actor, wo):
            raise Forbidden("You are not allowed to make this change", code="transition_not_permitted",
                            details={"from": current.value, "to": to.value})
        reason = _guard(db, wo, to, actor)
        if reason:
            error_cls, message = _GUARD_ERRORS[reason]
            raise error_cls(message, code=reason)
    comment = (comment or "").strip() or None
    if rule.comment_required and (comment is None or len(comment) < MIN_COMMENT):
        raise Unprocessable("A reason is required for this change", code="comment_required")

    wo.status = to
    if to == S.CLOSED:
        wo.closed_at = datetime.now(UTC)
    audit.record(db, actor_id=actor.id if actor else None, action="work_order.transition", entity_type="work_order",
                 entity_id=wo.id, previous_value={"status": current.value},
                 new_value={"status": to.value, "via": via, **(details or {})}, comment=comment)
    return wo


def allowed_actions(db: Session, wo: WorkOrder, actor: User) -> list[AllowedAction]:
    """What the actor can do next, for building UI buttons. Guarded actions carry a blocked_reason."""
    actions = []
    for (src, to), rule in TRANSITIONS.items():
        if src != wo.status or not _permitted(rule, actor, wo):
            continue
        reason = None if rule.via == "assign" else _guard(db, wo, to, actor)
        actions.append(AllowedAction(to=to, via=rule.via, comment_required=rule.comment_required,
                                     blocked_reason=reason))
    return actions
