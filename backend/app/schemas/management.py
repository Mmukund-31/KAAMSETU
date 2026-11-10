"""Schemas for equipment, users, checklist templates, handovers, dashboard and audit."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain.enums import (
    EquipmentCategory,
    HandoverStatus,
    LanguageCode,
    OperationalStatus,
    Priority,
    UserRole,
    WorkOrderStatus,
)
from app.schemas.work_order import HistoryEntry, PersonRef, WorkOrderSummary

# ── equipment ────────────────────────────────────────────────────────────


class EquipmentOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    category: EquipmentCategory
    site_id: uuid.UUID
    site_name: str
    location: str | None
    operational_status: OperationalStatus
    is_critical: bool
    open_work_orders: int
    created_at: datetime


class EquipmentCreate(BaseModel):
    equipment_code: str = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z]{1,3}[- ]?\d{2,4}$")
    name: str = Field(min_length=2, max_length=160)
    category: EquipmentCategory
    location: str | None = Field(default=None, max_length=160)
    is_critical: bool = False
    site_id: uuid.UUID | None = None


class FaultCount(BaseModel):
    symptom: str
    label: str
    count: int


class EquipmentDetail(EquipmentOut):
    work_orders_total: int
    work_orders_90d: int
    recurring_faults: list[FaultCount]
    recent_work_orders: list[WorkOrderSummary]


class EquipmentPage(BaseModel):
    items: list[EquipmentOut]
    total: int
    page: int
    page_size: int


# ── users ────────────────────────────────────────────────────────────────

class UserListItem(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    role: UserRole
    preferred_language: LanguageCode
    site_id: uuid.UUID | None
    is_active: bool
    open_assigned: int


# ── checklist templates ──────────────────────────────────────────────────

class TemplateItemIn(BaseModel):
    description: str = Field(min_length=3, max_length=500)
    is_mandatory: bool = True


class TemplateCreate(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    equipment_category: EquipmentCategory
    work_order_type: str = Field(default="corrective", min_length=3, max_length=32)
    items: list[TemplateItemIn] = Field(min_length=1, max_length=50)


class TemplateItemOut(BaseModel):
    id: uuid.UUID
    sequence: int
    description: str
    is_mandatory: bool


class TemplateOut(BaseModel):
    id: uuid.UUID
    name: str
    equipment_category: EquipmentCategory
    work_order_type: str
    version: int
    is_active: bool
    created_at: datetime
    items: list[TemplateItemOut]


# ── handovers ────────────────────────────────────────────────────────────

class HandoverCreate(BaseModel):
    shift_identifier: str = Field(min_length=1, max_length=64)
    notes: str = Field(min_length=1, max_length=4000)
    language: LanguageCode | None = None


class PendingAction(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    source: str = Field(default="supervisor", max_length=16)
    work_order_id: uuid.UUID | None = None
    done: bool = False


class HandoverReview(BaseModel):
    comment: str | None = Field(default=None, max_length=1000)
    pending_actions: list[PendingAction] | None = None


class HandoverOut(BaseModel):
    id: uuid.UUID
    site_id: uuid.UUID
    shift_identifier: str
    status: HandoverStatus
    created_by: PersonRef
    created_at: datetime
    original_notes: str
    detected_language: str | None
    generated_summary: dict[str, Any]
    pending_actions: list[dict[str, Any]]
    reviewed_by: PersonRef | None
    reviewed_at: datetime | None
    review_comment: str | None


class HandoverDetail(HandoverOut):
    history: list[HistoryEntry]


class HandoverPage(BaseModel):
    items: list[HandoverOut]
    total: int
    page: int
    page_size: int


# ── dashboard ────────────────────────────────────────────────────────────

class Overview(BaseModel):
    total: int
    open: int
    pending_approval: int
    in_progress: int
    blocked: int
    completion_review: int
    critical_high_open: int
    overdue: int
    safety_open: int
    completed_7d: int
    by_status: dict[WorkOrderStatus, int]
    by_priority_open: dict[Priority, int]
    generated_at: datetime


class TrendPoint(BaseModel):
    day: date
    created: int
    closed: int


class EquipmentIssue(BaseModel):
    equipment_id: uuid.UUID
    code: str
    name: str
    category: EquipmentCategory
    is_critical: bool
    work_orders: int
    open: int
    top_symptoms: list[FaultCount]
    recurring: bool


class EquipmentIssues(BaseModel):
    days: int
    equipment: list[EquipmentIssue]
    by_category: dict[EquipmentCategory, int]
    by_symptom: list[FaultCount]


class TechnicianWorkload(BaseModel):
    technician: PersonRef
    preferred_language: LanguageCode
    assigned: int
    in_progress: int
    blocked: int
    completion_review: int
    overdue: int
    closed_30d: int
    open_total: int


# ── audit ────────────────────────────────────────────────────────────────

class AuditEntry(HistoryEntry):
    entity_type: str
    entity_id: uuid.UUID


class AuditPage(BaseModel):
    items: list[AuditEntry]
    total: int
    page: int
    page_size: int
