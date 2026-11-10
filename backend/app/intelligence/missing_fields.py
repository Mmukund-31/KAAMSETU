"""Which mandatory fields are still missing, in the order the follow-up questions should be asked."""

from typing import Literal

from app.domain.enums import ProductionImpact
from app.intelligence.config_loader import workflow_policy
from app.intelligence.models import MissingField, ReportDraft

EquipmentStatus = Literal["matched", "unknown", "missing"]


def find_missing(
    draft: ReportDraft,
    equipment_status: EquipmentStatus,
    answered_fields: set[str] | frozenset[str] = frozenset(),
) -> list[MissingField]:
    missing: list[MissingField] = []
    for field in workflow_policy().required_fields:
        if field == "equipment_code" and equipment_status != "matched":
            reason = "not_registered" if equipment_status == "unknown" else "not_stated"
            missing.append(MissingField(field=field, reason=reason))
        elif field == "symptoms" and not draft.symptoms:
            # After one answer to the symptom question, the technician's own words are accepted.
            if "symptoms" not in answered_fields or not draft.issue_description.strip():
                missing.append(MissingField(field=field, reason="no_recognised_symptom"))
        elif field == "production_impact" and draft.production_impact == ProductionImpact.UNKNOWN:
            missing.append(MissingField(field=field, reason="not_stated"))
    return missing
