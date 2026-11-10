"""Build and update a ReportDraft from extracted utterances. Pure functions."""

from app.domain.enums import ProductionImpact
from app.intelligence.models import ExtractedReport, ReportDraft


def draft_from_report(report: ExtractedReport) -> ReportDraft:
    """First draft from the main report. The technician's own words become the description."""
    return ReportDraft(
        equipment_code=report.equipment_candidates[0].display if report.equipment_candidates else None,
        issue_description=report.text.strip(),
        symptoms=[s.key for s in report.symptoms],
        production_impact=report.production_impact.value if report.production_impact else ProductionImpact.UNKNOWN,
        safety_concern=report.safety_concern,
        location_note=report.location_note,
    )


def merge_answer(draft: ReportDraft, answer: ExtractedReport, field: str) -> ReportDraft:
    """Merge a follow-up answer into the draft.

    The asked-about field may be overwritten; other fields are only filled when still empty,
    so an answer never silently erases something the technician already confirmed.
    """
    data = draft.model_copy(deep=True)

    if answer.equipment_candidates and (field == "equipment_code" or not data.equipment_code):
        data.equipment_code = answer.equipment_candidates[0].display

    new_symptoms = [s.key for s in answer.symptoms]
    data.symptoms = list(dict.fromkeys([*data.symptoms, *new_symptoms]))
    if field == "symptoms" and answer.text.strip():
        data.issue_description = f"{data.issue_description} {answer.text.strip()}".strip()[:2000]

    if answer.production_impact is not None and (
        field == "production_impact" or data.production_impact == ProductionImpact.UNKNOWN
    ):
        data.production_impact = answer.production_impact.value
    elif field == "production_impact" and answer.answer is not None:
        # The question is always "Is production still running?", so yes/no maps directly.
        data.production_impact = ProductionImpact.RUNNING if answer.answer == "yes" else ProductionImpact.STOPPED

    data.safety_concern = data.safety_concern or answer.safety_concern
    if answer.location_note and not data.location_note:
        data.location_note = answer.location_note
    return data
