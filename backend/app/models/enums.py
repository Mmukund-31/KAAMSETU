"""Domain enumerations. Stored as PostgreSQL enum types using the lowercase values."""

from enum import StrEnum

from sqlalchemy import Enum as SAEnum


class UserRole(StrEnum):
    TECHNICIAN = "technician"
    SUPERVISOR = "supervisor"
    MANAGER = "manager"


class LanguageCode(StrEnum):
    EN = "en"
    HI = "hi"
    TE = "te"
    HINGLISH = "hinglish"


class EquipmentCategory(StrEnum):
    MECHANICAL = "mechanical"
    ELECTRICAL = "electrical"
    INSTRUMENTATION = "instrumentation"
    HYDRAULIC = "hydraulic"
    PNEUMATIC = "pneumatic"
    PRODUCTION = "production"
    OTHER = "other"


class OperationalStatus(StrEnum):
    RUNNING = "running"
    STOPPED = "stopped"
    DEGRADED = "degraded"
    MAINTENANCE = "maintenance"
    DECOMMISSIONED = "decommissioned"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class WorkOrderStatus(StrEnum):
    REPORTED = "reported"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETION_REVIEW = "completion_review"
    CLOSED = "closed"
    REJECTED = "rejected"
    AWAITING_PARTS = "awaiting_parts"
    BLOCKED = "blocked"
    ESCALATED = "escalated"
    REOPENED = "reopened"


class ProductionImpact(StrEnum):
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


class ReportChannel(StrEnum):
    VOICE = "voice"
    TEXT = "text"
    SEED = "seed"  # synthetic demo record created by scripts/seed.py


class ChecklistStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class ChecklistResponseValue(StrEnum):
    DONE = "done"
    NOT_APPLICABLE = "not_applicable"
    FAILED = "failed"


class HandoverStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    REVIEWED = "reviewed"


def pg_enum(enum_cls: type[StrEnum], name: str) -> SAEnum:
    """Enum column type that stores the lowercase `.value`, not the member name."""
    return SAEnum(
        enum_cls,
        name=name,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )
