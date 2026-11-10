"""Domain enumerations. Pure Python (no SQLAlchemy) so the intelligence layer can use them.

Stored as PostgreSQL enum types via app.models.types.pg_enum; re-exported by app.models.enums.
"""

from enum import StrEnum


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


__all__ = [
    "UserRole",
    "LanguageCode",
    "EquipmentCategory",
    "OperationalStatus",
    "Priority",
    "WorkOrderStatus",
    "ProductionImpact",
    "ReportChannel",
    "ChecklistStatus",
    "ChecklistResponseValue",
    "HandoverStatus",
]
