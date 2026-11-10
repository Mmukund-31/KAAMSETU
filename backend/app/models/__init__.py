"""Import every model so `Base.metadata` is complete for Alembic and tests."""

from app.models.audit_log import AuditLog
from app.models.checklist import (
    ChecklistItem,
    ChecklistResponse,
    ChecklistTemplate,
    WorkOrderChecklist,
)
from app.models.enums import (
    ChecklistResponseValue,
    ChecklistStatus,
    EquipmentCategory,
    HandoverStatus,
    LanguageCode,
    OperationalStatus,
    Priority,
    ProductionImpact,
    ReportChannel,
    UserRole,
    WorkOrderStatus,
)
from app.models.equipment import Equipment, normalize_equipment_code
from app.models.handover import Handover
from app.models.site import Site
from app.models.user import User
from app.models.work_order import Assignment, WorkOrder, WorkOrderEvidence

__all__ = [
    "Assignment",
    "AuditLog",
    "ChecklistItem",
    "ChecklistResponse",
    "ChecklistResponseValue",
    "ChecklistStatus",
    "ChecklistTemplate",
    "Equipment",
    "EquipmentCategory",
    "Handover",
    "HandoverStatus",
    "LanguageCode",
    "OperationalStatus",
    "Priority",
    "ProductionImpact",
    "ReportChannel",
    "Site",
    "User",
    "UserRole",
    "WorkOrder",
    "WorkOrderChecklist",
    "WorkOrderEvidence",
    "WorkOrderStatus",
    "normalize_equipment_code",
]
