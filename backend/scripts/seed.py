"""Idempotent synthetic demo data for KAAMSETU.

Everything created here is SYNTHETIC demo data:
  * the site name carries "(Demo)",
  * historical work orders have report_channel = 'seed' and a transcript stating no audio exists,
  * checklist templates are prefixed "[DEMO SOP]". A real deployment must replace them with
    company-approved procedures; KAAMSETU never generates SOP content.

Run:  .venv\\Scripts\\python.exe scripts\\seed.py
Safe to run repeatedly; existing rows (matched by natural key) are left untouched.
"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.database.session import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    ChecklistItem,
    ChecklistTemplate,
    Equipment,
    EquipmentCategory,
    LanguageCode,
    Priority,
    ProductionImpact,
    ReportChannel,
    Site,
    User,
    UserRole,
    WorkOrder,
    WorkOrderEvidence,
    WorkOrderStatus,
)
from app.services import audit  # noqa: E402

DEMO_PASSWORD = "Kaamsetu@2026"
SITE_NAME = "Hyderabad Plant 1 (Demo)"

USERS = [
    ("Ravi Kumar", "tech1@kaamsetu.demo", UserRole.TECHNICIAN, LanguageCode.HINGLISH),
    ("Lakshmi Reddy", "tech2@kaamsetu.demo", UserRole.TECHNICIAN, LanguageCode.TE),
    ("Arjun Yadav", "tech3@kaamsetu.demo", UserRole.TECHNICIAN, LanguageCode.HI),
    ("Priya Sharma", "supervisor@kaamsetu.demo", UserRole.SUPERVISOR, LanguageCode.EN),
    ("Sanjay Rao", "manager@kaamsetu.demo", UserRole.MANAGER, LanguageCode.EN),
]

# (code, name, category, location, is_critical)
EQUIPMENT = [
    ("M-204", "Hydraulic Press Main Motor", EquipmentCategory.MECHANICAL, "Press Shop, Bay 2", True),
    ("M-101", "CNC Lathe Spindle Motor", EquipmentCategory.MECHANICAL, "Machining Hall, Line A", False),
    ("M-305", "Conveyor Drive Motor", EquipmentCategory.MECHANICAL, "Assembly, Conveyor 3", False),
    ("E-110", "Main Distribution Panel", EquipmentCategory.ELECTRICAL, "Electrical Room 1", True),
    ("E-220", "Air Compressor Motor Starter", EquipmentCategory.ELECTRICAL, "Utility Block", False),
    ("H-401", "Hydraulic Power Unit", EquipmentCategory.HYDRAULIC, "Press Shop, Bay 1", True),
    ("H-402", "Injection Moulding Hydraulics", EquipmentCategory.HYDRAULIC, "Moulding Hall", False),
    ("P-501", "Pneumatic Clamp Line", EquipmentCategory.PNEUMATIC, "Welding Cell 2", False),
    ("P-502", "Compressed Air Dryer", EquipmentCategory.PNEUMATIC, "Utility Block", False),
    ("I-601", "Boiler Pressure Transmitter", EquipmentCategory.INSTRUMENTATION, "Boiler House", True),
    ("I-602", "Furnace Thermocouple Loop", EquipmentCategory.INSTRUMENTATION, "Heat Treatment", False),
    ("L-701", "Packaging Line 1", EquipmentCategory.PRODUCTION, "Dispatch, Packing Area", False),
]

# Demo SOP templates. Items reference site procedures rather than inventing technical instructions.
TEMPLATES = {
    EquipmentCategory.MECHANICAL: (
        "[DEMO SOP] Mechanical fault inspection",
        [
            ("Inform the area supervisor and production lead before starting work.", True),
            ("Apply lockout/tagout according to the site LOTO procedure and verify zero energy.", True),
            ("Inspect the reported component visually and record observations.", True),
            ("Record vibration or temperature readings using the site-approved instrument, if applicable.", False),
            ("Carry out the corrective action approved by the supervisor.", True),
            ("Remove locks and tags per the LOTO procedure and confirm the area is clear.", True),
            ("Run a functional test with the operator and record the result.", True),
        ],
    ),
    EquipmentCategory.ELECTRICAL: (
        "[DEMO SOP] Electrical fault inspection",
        [
            ("Confirm you hold the site electrical work permit for this equipment.", True),
            ("Isolate and lock out the supply according to the site LOTO procedure.", True),
            ("Verify absence of voltage with an approved tester (test-before-touch).", True),
            ("Inspect the reported component and record observations.", True),
            ("Carry out the corrective action approved by the supervisor.", True),
            ("Restore supply per procedure and record the functional test result.", True),
        ],
    ),
    EquipmentCategory.HYDRAULIC: (
        "[DEMO SOP] Hydraulic system inspection",
        [
            ("Inform the area supervisor and production lead before starting work.", True),
            ("Isolate the unit and release stored hydraulic pressure per the site procedure.", True),
            ("Inspect hoses, fittings and reservoir level; record observations.", True),
            ("Record system pressure reading after restart, if applicable.", False),
            ("Carry out the corrective action approved by the supervisor.", True),
            ("Run a functional test with the operator and record the result.", True),
        ],
    ),
}

# Closed historical orders so equipment history and analytics have something real to aggregate.
# (equipment_code, days_ago, symptoms, category, priority, impact, description)
HISTORY = [
    ("M-204", 26, ["bearing_vibration"], EquipmentCategory.MECHANICAL, Priority.HIGH, ProductionImpact.RUNNING,
     "Bearing vibration on main motor; bearing replaced."),
    ("M-204", 12, ["bearing_vibration", "abnormal_noise"], EquipmentCategory.MECHANICAL, Priority.HIGH,
     ProductionImpact.DEGRADED, "Repeat vibration with grinding noise; alignment corrected."),
    ("H-401", 20, ["oil_leak"], EquipmentCategory.HYDRAULIC, Priority.MEDIUM, ProductionImpact.RUNNING,
     "Minor oil leak at pump outlet fitting; fitting re-sealed."),
    ("E-110", 17, ["tripping"], EquipmentCategory.ELECTRICAL, Priority.HIGH, ProductionImpact.STOPPED,
     "Incomer breaker tripping under load; loose terminal tightened."),
    ("P-501", 9, ["air_leak"], EquipmentCategory.PNEUMATIC, Priority.LOW, ProductionImpact.RUNNING,
     "Air leak at clamp cylinder hose; hose replaced."),
    ("M-305", 6, ["overheating"], EquipmentCategory.MECHANICAL, Priority.MEDIUM, ProductionImpact.RUNNING,
     "Conveyor motor running hot; cooling fan cover cleaned."),
    ("I-601", 4, ["erratic_reading"], EquipmentCategory.INSTRUMENTATION, Priority.HIGH, ProductionImpact.RUNNING,
     "Pressure transmitter reading erratic; recalibrated."),
]


def _get_or_create_site(db: Session) -> Site:
    site = db.scalar(select(Site).where(Site.name == SITE_NAME))
    if site is None:
        site = Site(name=SITE_NAME, location="Hyderabad, Telangana (synthetic)")
        db.add(site)
        db.flush()
    return site


def seed(db: Session) -> dict[str, int]:
    created = {"users": 0, "equipment": 0, "templates": 0, "work_orders": 0}
    site = _get_or_create_site(db)

    users: dict[str, User] = {}
    for name, email, role, lang in USERS:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(name=name, email=email, password_hash=hash_password(DEMO_PASSWORD), role=role,
                        preferred_language=lang, site_id=site.id)
            db.add(user)
            created["users"] += 1
        users[email] = user
    db.flush()
    manager = users["manager@kaamsetu.demo"]
    supervisor = users["supervisor@kaamsetu.demo"]

    equipment: dict[str, Equipment] = {}
    for code, name, category, location, critical in EQUIPMENT:
        eq = db.scalar(select(Equipment).where(Equipment.equipment_code == code))
        if eq is None:
            eq = Equipment(equipment_code=code, name=name, category=category, site_id=site.id,
                           location=location, is_critical=critical)
            db.add(eq)
            created["equipment"] += 1
        equipment[code] = eq
    db.flush()

    for category, (name, items) in TEMPLATES.items():
        exists = db.scalar(select(ChecklistTemplate).where(ChecklistTemplate.equipment_category == category,
                                                           ChecklistTemplate.is_active.is_(True)))
        if exists is None:
            tpl = ChecklistTemplate(name=name, equipment_category=category, version=1, created_by=supervisor.id)
            tpl.items = [ChecklistItem(description=d, is_mandatory=m, sequence=i) for i, (d, m) in enumerate(items, 1)]
            db.add(tpl)
            created["templates"] += 1
    db.flush()

    has_history = db.scalar(select(WorkOrder.id).where(WorkOrder.report_channel == ReportChannel.SEED).limit(1))
    if has_history is None:
        now = datetime.now(UTC)
        technicians = [users["tech1@kaamsetu.demo"], users["tech2@kaamsetu.demo"], users["tech3@kaamsetu.demo"]]
        for i, (code, days_ago, symptoms, category, priority, impact, description) in enumerate(HISTORY):
            reported_at = now - timedelta(days=days_ago)
            wo = WorkOrder(
                equipment_id=equipment[code].id,
                reported_by=technicians[i % 3].id,
                assigned_to=technicians[(i + 1) % 3].id,
                issue_description=description,
                issue_category=category,
                symptoms=symptoms,
                priority=priority,
                status=WorkOrderStatus.CLOSED,
                production_impact=impact,
                report_channel=ReportChannel.SEED,
                requires_approval=True,
                created_at=reported_at,
                updated_at=reported_at + timedelta(hours=20),
                due_at=reported_at + timedelta(hours=24),
                closed_at=reported_at + timedelta(hours=20),
            )
            db.add(wo)
            db.flush()
            db.add(WorkOrderEvidence(
                work_order_id=wo.id,
                original_transcript="[SEED] Synthetic historical record. No voice recording exists.",
                extracted_data={"source": "seed", "symptoms": symptoms},
            ))
            audit.record(db, actor_id=manager.id, action="seed.create", entity_type="work_order", entity_id=wo.id,
                         new_value={"status": wo.status, "source": "seed"}, comment="Synthetic demo history")
            created["work_orders"] += 1

    db.commit()
    return created


def main() -> None:
    with SessionLocal() as db:
        created = seed(db)
    print("Seed complete (synthetic demo data):", ", ".join(f"{k}+{v}" for k, v in created.items()))
    print(f"\nDemo accounts - password for all: {DEMO_PASSWORD}")
    for name, email, role, lang in USERS:
        print(f"  {role.value:<11} {email:<28} {name} ({lang.value})")


if __name__ == "__main__":
    main()
