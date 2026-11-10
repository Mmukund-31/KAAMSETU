import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domain.enums import (
    ChecklistResponseValue,
    ChecklistStatus,
    EquipmentCategory,
    Priority,
    ProductionImpact,
    ReportChannel,
    WorkOrderStatus,
)
from app.intelligence.models import ReportDraft
from app.schemas.report import SpokenResponse

# ── requests ─────────────────────────────────────────────────────────────


class WorkOrderCreate(BaseModel):
    evidence_token: str
    draft: ReportDraft
    submission_key: str | None = Field(default=None, min_length=8, max_length=64,
                                       description="Client-generated idempotency key")
    submit: bool = Field(default=True, description="Send for supervisor review immediately")
    speak: bool = True


class WorkOrderUpdate(BaseModel):
    issue_description: str | None = Field(default=None, min_length=1, max_length=2000)
    location_note: str | None = Field(default=None, max_length=255)
    issue_category: EquipmentCategory | None = None
    production_impact: ProductionImpact | None = None
    priority: Priority | None = None
    priority_reason: str | None = Field(default=None, max_length=500)


class ApproveRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=1000)
    priority: Priority | None = Field(default=None, description="Override the rule-based priority")
    priority_reason: str | None = Field(default=None, max_length=500)


class CommentRequired(BaseModel):
    comment: str = Field(min_length=3, max_length=1000)


class AssignRequest(BaseModel):
    technician_id: uuid.UUID
    comments: str | None = Field(default=None, max_length=1000)


class StatusChange(BaseModel):
    to: WorkOrderStatus
    comment: str | None = Field(default=None, max_length=1000)


class CompleteRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=1000)
    speak: bool = False


class ChecklistItemUpdate(BaseModel):
    response: ChecklistResponseValue
    notes: str | None = Field(default=None, max_length=1000)


class AttachChecklist(BaseModel):
    template_id: uuid.UUID | None = None


# ── responses ────────────────────────────────────────────────────────────

class PersonRef(BaseModel):
    id: uuid.UUID
    name: str


class EquipmentRef(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    category: EquipmentCategory
    location: str | None
    is_critical: bool


class WorkOrderSummary(BaseModel):
    id: uuid.UUID
    number: int
    display_number: str
    status: WorkOrderStatus
    priority: Priority
    issue_category: EquipmentCategory
    symptoms: list[str]
    issue_description: str
    production_impact: ProductionImpact
    safety_concern: bool
    report_channel: ReportChannel
    equipment: EquipmentRef
    reporter: PersonRef
    assignee: PersonRef | None
    created_at: datetime
    updated_at: datetime
    due_at: datetime | None
    closed_at: datetime | None
    is_overdue: bool


class EvidenceOut(BaseModel):
    original_transcript: str
    detected_language: str | None
    selected_language: str | None
    prisma_request_id: str | None
    prisma_model: str | None
    utterances: list[dict[str, Any]]
    validated: dict[str, Any]
    audio_retained: bool
    created_at: datetime


class AssignmentOut(BaseModel):
    technician: PersonRef
    assigned_by: PersonRef
    assigned_at: datetime
    comments: str | None


class ChecklistItemOut(BaseModel):
    id: uuid.UUID
    sequence: int
    description: str
    is_mandatory: bool
    response: ChecklistResponseValue | None
    notes: str | None
    completed_by: PersonRef | None
    completed_at: datetime | None


class ChecklistOut(BaseModel):
    id: uuid.UUID
    work_order_id: uuid.UUID
    template_id: uuid.UUID
    template_name: str
    template_version: int
    status: ChecklistStatus
    created_at: datetime
    completed_at: datetime | None
    items: list[ChecklistItemOut]
    items_total: int
    items_answered: int
    mandatory_total: int
    mandatory_done: int
    is_complete: bool


class HistoryEntry(BaseModel):
    id: uuid.UUID
    action: str
    actor: PersonRef | None
    previous_value: dict[str, Any] | None
    new_value: dict[str, Any] | None
    comment: str | None
    timestamp: datetime


class AllowedActionOut(BaseModel):
    action: Literal["submit", "approve", "reject", "assign", "complete", "escalate", "status"]
    to: WorkOrderStatus
    comment_required: bool
    blocked_reason: str | None


class WorkOrderDetail(WorkOrderSummary):
    priority_rule: str | None
    requires_approval: bool
    location_note: str | None
    evidence: EvidenceOut | None
    assignments: list[AssignmentOut]
    checklists: list[ChecklistOut]
    history: list[HistoryEntry]
    allowed_actions: list[AllowedActionOut]
    can_assign: bool
    task_announcement: str | None = Field(default=None, description="Spoken-style task text for the assignee")


class WorkOrderActionResult(BaseModel):
    work_order: WorkOrderDetail
    response: SpokenResponse | None = None


class WorkOrderPage(BaseModel):
    items: list[WorkOrderSummary]
    total: int
    page: int
    page_size: int
