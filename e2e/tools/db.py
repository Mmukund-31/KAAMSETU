"""Database helpers for the end-to-end harness. Run with the backend virtualenv from the backend folder:

    python ../e2e/tools/db.py evidence WO-1021      -> JSON: the work order, its evidence, assignments,
                                                       checklist responses and audit trail, straight from PostgreSQL
    python ../e2e/tools/db.py counts                -> JSON: row counts (work orders, handovers, audit)
    python ../e2e/tools/db.py token <email> <secs>  -> a real access token for that user expiring in <secs> seconds
    python ../e2e/tools/db.py cleanup <file>        -> delete the work orders / handovers listed in <file>

The harness uses these to cite real rows as evidence and to put the dev DB back to the seed afterwards.
Only ids recorded by the harness are ever deleted, and seed records are refused.
"""

import json
import sys
import uuid
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from sqlalchemy import delete, func, select  # noqa: E402

from app.core.security import create_access_token  # noqa: E402
from app.database.session import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Assignment,
    AuditLog,
    ChecklistResponse,
    Equipment,
    Handover,
    User,
    WorkOrder,
    WorkOrderChecklist,
    WorkOrderEvidence,
)


def _iso(value):
    return value.isoformat() if value else None


def evidence(display_number: str) -> dict:
    number = int(display_number.upper().removeprefix("WO-"))
    with SessionLocal() as db:
        wo = db.scalar(select(WorkOrder).where(WorkOrder.number == number))
        if wo is None:
            return {"error": f"{display_number} not found"}
        names = {u.id: u.name for u in db.scalars(select(User))}
        ev = db.scalar(select(WorkOrderEvidence).where(WorkOrderEvidence.work_order_id == wo.id))
        eq = db.get(Equipment, wo.equipment_id)
        checklist_ids = list(db.scalars(select(WorkOrderChecklist.id).where(WorkOrderChecklist.work_order_id == wo.id)))
        responses = list(db.scalars(select(ChecklistResponse).where(ChecklistResponse.checklist_id.in_(checklist_ids))))
        audit = list(db.scalars(select(AuditLog).where(AuditLog.entity_id == wo.id).order_by(AuditLog.seq)))
        assignments = list(db.scalars(select(Assignment).where(Assignment.work_order_id == wo.id)))
        return {
            "work_order": {
                "id": str(wo.id), "number": wo.display_number, "status": wo.status.value, "priority": wo.priority.value,
                "priority_rule": wo.priority_rule, "category": wo.issue_category.value,
                "production_impact": wo.production_impact.value, "safety_concern": wo.safety_concern,
                "symptoms": wo.symptoms, "equipment": eq.equipment_code, "channel": wo.report_channel.value,
                "reported_by": names.get(wo.reported_by), "assigned_to": names.get(wo.assigned_to),
                "created_at": _iso(wo.created_at), "closed_at": _iso(wo.closed_at),
            },
            "evidence": None if ev is None else {
                "prisma_request_id": ev.prisma_request_id, "prisma_model": ev.prisma_model,
                "original_transcript": ev.original_transcript, "selected_language": ev.selected_language,
                "detected_language": ev.detected_language, "audio_retained": ev.audio_reference is not None,
                "utterances": len((ev.extracted_data or {}).get("utterances", [])),
            },
            "assignments": [{"technician": names.get(a.technician_id), "by": names.get(a.assigned_by)} for a in assignments],
            "checklist_responses": [{"response": r.response.value, "by": names.get(r.completed_by)} for r in responses],
            "audit": [{
                "seq": a.seq, "action": a.action, "actor": names.get(a.actor_id),
                "from": (a.previous_value or {}).get("status"), "to": (a.new_value or {}).get("status"),
                "comment": a.comment,
            } for a in audit],
        }


def counts() -> dict:
    with SessionLocal() as db:
        return {
            "work_orders": db.scalar(select(func.count()).select_from(WorkOrder)),
            "handovers": db.scalar(select(func.count()).select_from(Handover)),
            "audit_logs": db.scalar(select(func.count()).select_from(AuditLog)),
        }


def token(email: str, seconds: int) -> str:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email.lower()))
        if user is None:
            raise SystemExit(f"no user {email}")
        value, _ = create_access_token(user.id, user.role.value, timedelta(seconds=seconds))
        return value


def cleanup(path: str) -> dict:
    rows = [line.split() for line in Path(path).read_text().splitlines() if line.strip()]
    wo_ids = list({uuid.UUID(i) for kind, i in rows if kind == "wo"})
    ho_ids = list({uuid.UUID(i) for kind, i in rows if kind == "handover"})
    with SessionLocal() as db:
        found = db.execute(select(WorkOrder.number, WorkOrder.report_channel).where(WorkOrder.id.in_(wo_ids))).all()
        if any(r.report_channel.value == "seed" for r in found):
            raise SystemExit("refusing: a seed record is in the cleanup list")
        audit = db.execute(delete(AuditLog).where(AuditLog.entity_id.in_(wo_ids + ho_ids))).rowcount
        orders = db.execute(delete(WorkOrder).where(WorkOrder.id.in_(wo_ids))).rowcount
        handovers = db.execute(delete(Handover).where(Handover.id.in_(ho_ids))).rowcount
        db.commit()
    return {"deleted_work_orders": sorted(f"WO-{r.number}" for r in found), "work_orders": orders,
            "handovers": handovers, "audit_rows": audit, "now": counts()}


if __name__ == "__main__":
    command, *args = sys.argv[1:]
    if command == "evidence":
        print(json.dumps(evidence(args[0]), ensure_ascii=False))
    elif command == "counts":
        print(json.dumps(counts()))
    elif command == "token":
        print(token(args[0], int(args[1])))
    elif command == "cleanup":
        print(json.dumps(cleanup(args[0])))
    else:
        raise SystemExit(f"unknown command {command}")
