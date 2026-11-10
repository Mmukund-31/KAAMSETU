import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domain.enums import EquipmentCategory, OperationalStatus
from app.intelligence.models import (
    ExtractedReport,
    FollowUpField,
    PriorityDecision,
    ReportDraft,
    Severity,
)

NextAction = Literal["fix_equipment", "ask_follow_up", "confirm_preview"]
ReportLanguage = Literal["en", "hi", "te", "hinglish"]


class EquipmentBrief(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    category: EquipmentCategory
    location: str | None
    is_critical: bool
    operational_status: OperationalStatus


class EquipmentResolution(BaseModel):
    status: Literal["matched", "unknown", "missing"]
    heard: str | None = Field(default=None, description="Code as heard or typed, before registry lookup")
    equipment: EquipmentBrief | None = None
    suggestions: list[EquipmentBrief] = Field(default=[], description="Registered machines only, never invented")


class SymptomOut(BaseModel):
    key: str
    label: str
    category: EquipmentCategory
    severity: Severity
    safety: bool


class CategoryOut(BaseModel):
    value: EquipmentCategory
    label: str
    basis: Literal["symptoms", "equipment", "override", "none"]


class MissingFieldOut(BaseModel):
    field: FollowUpField
    reason: str
    question: str


class FollowUpQuestion(BaseModel):
    field: FollowUpField
    question: str


class SpokenResponse(BaseModel):
    text: str
    tts_available: bool | None = Field(default=None, description="None when speech was not requested")
    tts_error: str | None = None
    audio_base64: str | None = None
    content_type: str | None = None
    voice: str | None = None
    gnani_request_id: str | None = None


class ReportOutcome(BaseModel):
    report_id: uuid.UUID
    language: ReportLanguage
    next_action: NextAction
    transcript: str = Field(description="The latest utterance")
    original_transcript: str = Field(description="The first utterance exactly as received (Prisma or typed)")
    utterances: list[dict[str, Any]]
    draft: ReportDraft
    equipment: EquipmentResolution
    symptoms: list[SymptomOut]
    category: CategoryOut
    priority: PriorityDecision
    missing_fields: list[MissingFieldOut]
    follow_up: FollowUpQuestion | None
    requires_approval: bool
    warnings: list[str]
    extraction: ExtractedReport | None = Field(default=None, description="Raw extraction of the latest utterance")
    response: SpokenResponse
    evidence_token: str = Field(description="Signed; send back with follow-ups, corrections and submission")


class ProcessTextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    language: ReportLanguage | None = None
    evidence_token: str | None = Field(default=None, description="Set when correcting a voice transcript")
    speak: bool = True


class EvaluateDraftRequest(BaseModel):
    evidence_token: str
    draft: ReportDraft
    speak: bool = False
