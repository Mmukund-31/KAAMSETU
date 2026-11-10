"""Data models of the intelligence layer. Pure Pydantic, no database access."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.domain.enums import EquipmentCategory, Priority, ProductionImpact

Confidence = Literal["high", "medium", "low"]
Severity = Literal["low", "medium", "high"]
UILanguage = Literal["en", "hi", "te", "hinglish"]
FollowUpField = Literal["equipment_code", "symptoms", "production_impact"]


class EquipmentCandidate(BaseModel):
    """A possible equipment code heard in the transcript. Only the registry decides whether it is real."""

    code: str = Field(description="Normalised: letters+digits ('M204') or digits only ('204')")
    display: str = Field(description="Readable form, e.g. 'M-204'")
    heard: str = Field(description="Text as it appeared in the transcript")
    method: Literal["direct", "spoken", "digits_only"]
    confidence: Confidence


class SymptomMatch(BaseModel):
    key: str
    category: EquipmentCategory
    severity: Severity
    safety: bool
    terms: list[str]


class ImpactMatch(BaseModel):
    value: ProductionImpact
    confidence: Confidence
    evidence: str


class ExtractedReport(BaseModel):
    """What one utterance explicitly says. Unknown stays None or empty; nothing is inferred."""

    language: UILanguage
    text: str
    equipment_candidates: list[EquipmentCandidate] = []
    symptoms: list[SymptomMatch] = []
    negated_symptoms: list[str] = []
    production_impact: ImpactMatch | None = None
    safety_concern: bool = False
    safety_terms: list[str] = []
    location_note: str | None = None
    answer: Literal["yes", "no"] | None = None


class ReportDraft(BaseModel):
    """The editable work-order request shown to the technician before submission."""

    equipment_code: str | None = Field(default=None, max_length=32)
    issue_description: str = Field(default="", max_length=2000)
    symptoms: list[str] = Field(default_factory=list, max_length=20)
    production_impact: ProductionImpact = ProductionImpact.UNKNOWN
    safety_concern: bool = False
    location_note: str | None = Field(default=None, max_length=255)
    category_override: EquipmentCategory | None = None

    @field_validator("symptoms")
    @classmethod
    def _dedupe(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(v.strip() for v in value if v and v.strip()))


class Classification(BaseModel):
    category: EquipmentCategory
    basis: Literal["symptoms", "equipment", "override", "none"]
    scores: dict[str, float] = {}


class PriorityContext(BaseModel):
    safety_concern: bool
    production_impact: ProductionImpact
    equipment_critical: bool | None
    symptom_severities: list[Severity]
    category: EquipmentCategory


class PriorityDecision(BaseModel):
    level: Priority
    rule_id: str
    explanation: str
    provisional: bool = Field(description="True while production impact or equipment is still unknown")


class MissingField(BaseModel):
    field: FollowUpField
    reason: str
