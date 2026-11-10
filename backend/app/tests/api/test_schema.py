"""Checks that the migrated schema enforces the constraints the domain relies on."""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.database.base import Base
from app.database.errors import FOREIGN_KEY_VIOLATION, UNIQUE_VIOLATION, constraint_name, sqlstate
from app.models import (
    ChecklistTemplate,
    Equipment,
    EquipmentCategory,
    Priority,
    ProductionImpact,
    ReportChannel,
    WorkOrder,
)
from app.tests.conftest import alembic_config

EXPECTED_TABLES = {
    "sites", "users", "equipment", "work_orders", "work_order_evidence", "assignments",
    "checklist_templates", "checklist_items", "work_order_checklists", "checklist_responses",
    "handovers", "audit_logs",
}


def test_all_tables_exist(engine):
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())


def test_models_match_migrations(engine):
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], f"Models and migrations have drifted: {diff}"


def test_downgrade_and_upgrade_roundtrip(engine, test_database_url):
    cfg = alembic_config(test_database_url)
    command.downgrade(cfg, "base")
    assert not (EXPECTED_TABLES & set(inspect(engine).get_table_names()))
    command.upgrade(cfg, "head")
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())


def test_equipment_code_unique_after_normalisation(db, site):
    db.add(Equipment(equipment_code="M-204", name="A", category=EquipmentCategory.MECHANICAL, site_id=site.id))
    db.flush()
    db.add(Equipment(equipment_code="m 204", name="B", category=EquipmentCategory.MECHANICAL, site_id=site.id))
    with pytest.raises(IntegrityError):
        db.flush()


def test_work_order_number_is_sequential_and_requires_known_equipment(db, site, make_user):
    tech = make_user()
    eq = Equipment(equipment_code="X-1", name="X", category=EquipmentCategory.OTHER, site_id=site.id)
    db.add(eq)
    db.flush()

    def wo(**kw):
        return WorkOrder(reported_by=tech.id, issue_description="d", issue_category=EquipmentCategory.OTHER,
                         priority=Priority.LOW, production_impact=ProductionImpact.UNKNOWN,
                         report_channel=ReportChannel.TEXT, **kw)

    a, b = wo(equipment_id=eq.id), wo(equipment_id=eq.id)
    db.add_all([a, b])
    db.flush()
    assert b.number == a.number + 1
    assert a.display_number == f"WO-{a.number}"

    import uuid

    db.add(wo(equipment_id=uuid.uuid4()))
    with pytest.raises(DBAPIError) as excinfo:
        db.flush()
    assert sqlstate(excinfo.value) == FOREIGN_KEY_VIOLATION
    assert constraint_name(excinfo.value) == "fk_work_orders_equipment_id_equipment"


def test_duplicate_submission_key_rejected(db, site, make_user):
    tech = make_user()
    eq = Equipment(equipment_code="X-2", name="X", category=EquipmentCategory.OTHER, site_id=site.id)
    db.add(eq)
    db.flush()
    for _ in range(2):
        db.add(WorkOrder(equipment_id=eq.id, reported_by=tech.id, issue_description="d",
                         issue_category=EquipmentCategory.OTHER, priority=Priority.LOW,
                         production_impact=ProductionImpact.UNKNOWN, report_channel=ReportChannel.TEXT,
                         submission_key="same-key"))
    with pytest.raises(IntegrityError) as excinfo:
        db.flush()
    assert sqlstate(excinfo.value) == UNIQUE_VIOLATION
    assert constraint_name(excinfo.value) == "uq_work_orders_submission_key"


def test_only_one_active_checklist_template_per_category(db):
    db.add(ChecklistTemplate(name="v1", equipment_category=EquipmentCategory.MECHANICAL, version=1))
    db.flush()
    db.add(ChecklistTemplate(name="v2", equipment_category=EquipmentCategory.MECHANICAL, version=2))
    with pytest.raises(IntegrityError):
        db.flush()


def test_inactive_old_template_version_allowed(db):
    db.add(ChecklistTemplate(name="v1", equipment_category=EquipmentCategory.HYDRAULIC, version=1, is_active=False))
    db.add(ChecklistTemplate(name="v2", equipment_category=EquipmentCategory.HYDRAULIC, version=2))
    db.flush()
