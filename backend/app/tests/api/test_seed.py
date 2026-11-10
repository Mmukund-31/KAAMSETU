"""The seed script must be idempotent and clearly mark its data as synthetic."""

import importlib.util
from pathlib import Path

from sqlalchemy import func, select

from app.config import BACKEND_DIR
from app.models import ChecklistTemplate, Equipment, ReportChannel, User, WorkOrder


def _load_seed_module():
    spec = importlib.util.spec_from_file_location("seed", Path(BACKEND_DIR) / "scripts" / "seed.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seed_is_idempotent_and_marked_synthetic(db):
    seed = _load_seed_module()
    first = seed.seed(db)
    second = seed.seed(db)

    assert first["users"] == 5 and first["equipment"] == 12 and first["templates"] == 3
    assert all(v == 0 for v in second.values()), second

    assert db.scalar(select(Equipment).where(Equipment.equipment_code == "M-204")).is_critical
    assert db.scalar(select(func.count()).select_from(User).where(User.email.like("%@kaamsetu.demo"))) == 5
    templates = db.scalars(select(ChecklistTemplate)).all()
    assert all(t.name.startswith("[DEMO SOP]") for t in templates)
    seeded = db.scalars(select(WorkOrder).where(WorkOrder.report_channel == ReportChannel.SEED)).all()
    assert seeded and all(w.evidence.original_transcript.startswith("[SEED]") for w in seeded)
