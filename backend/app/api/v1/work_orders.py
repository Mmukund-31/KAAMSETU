import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import CurrentUser, DbSession
from app.core.errors import Forbidden
from app.domain.enums import Priority, UserRole, WorkOrderStatus
from app.gnani.timbre import TimbreClient
from app.intelligence.response import render
from app.schemas.common import ErrorResponse
from app.schemas.work_order import (
    ApproveRequest,
    AssignRequest,
    AttachChecklist,
    ChecklistItemUpdate,
    ChecklistOut,
    CommentRequired,
    CompleteRequest,
    StatusChange,
    WorkOrderActionResult,
    WorkOrderCreate,
    WorkOrderDetail,
    WorkOrderPage,
    WorkOrderUpdate,
)
from app.services import access, checklists, speech
from app.services import work_orders as queries
from app.workflows import assignment
from app.workflows import work_order as flows

router = APIRouter(tags=["work orders"])
_ERRORS = {r: {"model": ErrorResponse} for r in (401, 403, 404, 409, 422)}
Timbre = Annotated[TimbreClient, Depends(speech.get_timbre_client)]


def _locked(db, user, work_order_id):
    return access.get_work_order(db, user, work_order_id, for_update=True)


def _detail(db, user, wo) -> WorkOrderDetail:
    return queries.detail(db, user, wo)


@router.post("/work-orders", response_model=WorkOrderActionResult, status_code=status.HTTP_201_CREATED,
             responses=_ERRORS)
def create_work_order(body: WorkOrderCreate, user: CurrentUser, db: DbSession, timbre: Timbre):
    """Create a work order from a confirmed voice/text report preview.

    The signed evidence is verified and the draft is fully re-validated: equipment against the register,
    symptoms, category and priority. Replays return 409 duplicate_submission.
    """
    wo = flows.create_from_report(db, user, body.evidence_token, body.draft, body.submission_key, body.submit)
    lang = wo.evidence.selected_language.value if wo.evidence and wo.evidence.selected_language else \
        user.preferred_language.value
    text = render("submitted", lang, number=wo.display_number)
    return WorkOrderActionResult(work_order=_detail(db, user, wo),
                                 response=speech.spoken(timbre if body.speak else None, text, lang))


@router.get("/work-orders", response_model=WorkOrderPage, responses=_ERRORS)
def list_work_orders(
    user: CurrentUser,
    db: DbSession,
    status_: Annotated[list[WorkOrderStatus] | None, Query(alias="status")] = None,
    priority: Annotated[list[Priority] | None, Query()] = None,
    equipment_id: uuid.UUID | None = None,
    assigned_to: uuid.UUID | None = None,
    reported_by: uuid.UUID | None = None,
    mine: Annotated[bool, Query(description="Only work assigned to me")] = False,
    overdue: bool | None = None,
    safety_only: bool = False,
    q: Annotated[str | None, Query(max_length=100, description="Search description, equipment or WO number")] = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    sort: Literal["created_desc", "created_asc", "due_asc", "priority", "updated_desc"] = "created_desc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> WorkOrderPage:
    return queries.list_work_orders(
        db, user, statuses=status_, priorities=priority, equipment_id=equipment_id, assigned_to=assigned_to,
        reported_by=reported_by, mine=mine, overdue=overdue, safety_only=safety_only, q=q,
        created_from=created_from, created_to=created_to, sort=sort, page=page, page_size=page_size)


@router.get("/work-orders/{work_order_id}", response_model=WorkOrderDetail, responses=_ERRORS)
def get_work_order(work_order_id: uuid.UUID, user: CurrentUser, db: DbSession) -> WorkOrderDetail:
    return _detail(db, user, access.get_work_order(db, user, work_order_id))


@router.patch("/work-orders/{work_order_id}", response_model=WorkOrderDetail, responses=_ERRORS)
def update_work_order(work_order_id: uuid.UUID, body: WorkOrderUpdate, user: CurrentUser,
                      db: DbSession) -> WorkOrderDetail:
    """Edit description, location, category or production impact. Priority changes need a reason (supervisors)."""
    wo = _locked(db, user, work_order_id)
    flows.update_fields(db, user, wo, **body.model_dump())
    return _detail(db, user, wo)


@router.post("/work-orders/{work_order_id}/submit", response_model=WorkOrderDetail, responses=_ERRORS)
def submit(work_order_id: uuid.UUID, user: CurrentUser, db: DbSession) -> WorkOrderDetail:
    return _detail(db, user, flows.submit(db, user, _locked(db, user, work_order_id)))


@router.post("/work-orders/{work_order_id}/approve", response_model=WorkOrderDetail, responses=_ERRORS)
def approve(work_order_id: uuid.UUID, body: ApproveRequest, user: CurrentUser, db: DbSession) -> WorkOrderDetail:
    """Approve (supervisor/manager). Optionally override the rule-based priority with a recorded reason."""
    wo = flows.approve(db, user, _locked(db, user, work_order_id), body.comment, body.priority, body.priority_reason)
    return _detail(db, user, wo)


@router.post("/work-orders/{work_order_id}/reject", response_model=WorkOrderDetail, responses=_ERRORS)
def reject(work_order_id: uuid.UUID, body: CommentRequired, user: CurrentUser, db: DbSession) -> WorkOrderDetail:
    return _detail(db, user, flows.reject(db, user, _locked(db, user, work_order_id), body.comment))


@router.post("/work-orders/{work_order_id}/assign", response_model=WorkOrderDetail, responses=_ERRORS)
def assign(work_order_id: uuid.UUID, body: AssignRequest, user: CurrentUser, db: DbSession) -> WorkOrderDetail:
    """Assign or reassign a technician. The active SOP checklist for the equipment category is attached."""
    wo = assignment.assign(db, user, _locked(db, user, work_order_id), body.technician_id, body.comments)
    return _detail(db, user, wo)


@router.post("/work-orders/{work_order_id}/status", response_model=WorkOrderDetail, responses=_ERRORS)
def change_status(work_order_id: uuid.UUID, body: StatusChange, user: CurrentUser, db: DbSession) -> WorkOrderDetail:
    """Generic transition (start, block, awaiting parts, resume, close, reopen ...), validated by the state machine."""
    return _detail(db, user, flows.change_status(db, user, _locked(db, user, work_order_id), body.to, body.comment))


@router.post("/work-orders/{work_order_id}/complete", response_model=WorkOrderActionResult, responses=_ERRORS)
def complete(work_order_id: uuid.UUID, body: CompleteRequest, user: CurrentUser, db: DbSession, timbre: Timbre):
    """Assigned technician reports completion. Blocked while mandatory checklist steps are open."""
    wo = flows.complete(db, user, _locked(db, user, work_order_id), body.notes)
    lang = user.preferred_language.value
    return WorkOrderActionResult(
        work_order=_detail(db, user, wo),
        response=speech.spoken(timbre if body.speak else None,
                               render("completion_submitted", lang, number=wo.display_number), lang))


@router.post("/work-orders/{work_order_id}/escalate", response_model=WorkOrderDetail, responses=_ERRORS)
def escalate(work_order_id: uuid.UUID, body: CommentRequired, user: CurrentUser, db: DbSession) -> WorkOrderDetail:
    return _detail(db, user, flows.escalate(db, user, _locked(db, user, work_order_id), body.comment))


@router.post("/work-orders/{work_order_id}/checklists", response_model=ChecklistOut,
             status_code=status.HTTP_201_CREATED, responses=_ERRORS)
def attach_checklist(work_order_id: uuid.UUID, body: AttachChecklist, user: CurrentUser,
                     db: DbSession) -> ChecklistOut:
    """Attach an approved checklist (default: the active template for the equipment category). Idempotent."""
    wo = _locked(db, user, work_order_id)
    if user.role == UserRole.TECHNICIAN and user.id != wo.assigned_to:
        raise Forbidden("Only the assigned technician or a supervisor can attach a checklist", code="not_assignee")
    checklist = checklists.attach(db, user, wo, body.template_id)
    db.commit()
    return queries.checklist_out(db, checklist)


@router.get("/checklists/{checklist_id}", response_model=ChecklistOut, responses=_ERRORS)
def get_checklist(checklist_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ChecklistOut:
    checklist = checklists.get_checklist(db, checklist_id)
    access.get_work_order(db, user, checklist.work_order_id)  # access check (404 if not visible)
    return queries.checklist_out(db, checklist)


@router.patch("/checklists/{checklist_id}/items/{item_id}", response_model=ChecklistOut, responses=_ERRORS)
def record_checklist_item(checklist_id: uuid.UUID, item_id: uuid.UUID, body: ChecklistItemUpdate,
                          user: CurrentUser, db: DbSession) -> ChecklistOut:
    """Record one step: done, not_applicable or failed (the last two need a note). Assigned technician only."""
    checklist = checklists.get_checklist(db, checklist_id)
    wo = _locked(db, user, checklist.work_order_id)
    checklists.record_item(db, user, checklist, wo, item_id, body.response, body.notes)
    db.commit()
    return queries.checklist_out(db, checklist)
