"""Structural checks on the transition table (no database needed)."""

from collections import deque

from app.domain.enums import UserRole
from app.domain.enums import WorkOrderStatus as S
from app.services.state_machine import TRANSITIONS


def reachable_from(start: S) -> set[S]:
    seen, queue = {start}, deque([start])
    while queue:
        current = queue.popleft()
        for (src, dst) in TRANSITIONS:
            if src == current and dst not in seen:
                seen.add(dst)
                queue.append(dst)
    return seen


def test_every_status_is_reachable_from_reported():
    assert reachable_from(S.REPORTED) == set(S)


def test_only_closed_and_rejected_are_terminal():
    with_exits = {src for src, _ in TRANSITIONS}
    assert set(S) - with_exits == {S.CLOSED, S.REJECTED}


def test_every_open_status_can_still_reach_an_end():
    for status in set(S) - {S.CLOSED, S.REJECTED}:
        assert reachable_from(status) & {S.CLOSED, S.REJECTED}, status


def test_negative_moves_always_need_a_reason():
    for (src, dst), rule in TRANSITIONS.items():
        if dst in (S.REJECTED, S.BLOCKED, S.AWAITING_PARTS, S.ESCALATED, S.REOPENED):
            assert rule.comment_required, (src, dst)


def test_technicians_never_approve_reject_close_or_assign():
    for (_, dst), rule in TRANSITIONS.items():
        if dst in (S.APPROVED, S.REJECTED, S.CLOSED, S.ASSIGNED, S.REOPENED, S.ESCALATED):
            assert UserRole.TECHNICIAN not in rule.roles and rule.technician is None, dst


def test_only_the_assignee_reports_completion():
    rule = TRANSITIONS[(S.IN_PROGRESS, S.COMPLETION_REVIEW)]
    assert rule.roles == frozenset() and rule.technician == "assignee" and rule.via == "complete"


def test_escalations_resolved_only_by_managers():
    for (src, _), rule in TRANSITIONS.items():
        if src == S.ESCALATED:
            assert rule.roles == {UserRole.MANAGER}
