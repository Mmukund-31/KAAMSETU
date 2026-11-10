"""A small synthetic plant used by the Phase 4 work-order tests, plus helpers to drive the API."""

import uuid
from dataclasses import dataclass, field

import pytest

from app.main import app
from app.models import (
    ChecklistItem,
    ChecklistTemplate,
    Equipment,
    EquipmentCategory,
    LanguageCode,
    Site,
    User,
    UserRole,
)
from app.services import speech
from app.tests.api.test_voice import FakePrisma, FakeTimbre

DEMO = ("motor ka pressure abnormal hai, bearing mein vibration aa raha hai, machine number M-204 hai, "
        "production abhi chal raha hai.")


@dataclass
class World:
    site: Site
    other_site: Site
    equipment: dict[str, Equipment]
    tech1: User
    tech2: User
    other_tech: User          # technician at the other site
    supervisor: User
    supervisor2: User
    manager: User
    other_supervisor: User    # supervisor at the other site
    template: ChecklistTemplate
    headers: dict[str, dict] = field(default_factory=dict)
    prisma: FakePrisma | None = None
    timbre: FakeTimbre | None = None

    def h(self, user: User) -> dict:
        return self.headers[user.email]


@pytest.fixture
def world(db, make_user, auth_headers) -> World:
    site = make_user.site
    other = Site(name="Second Plant")
    db.add(other)
    db.flush()
    rows = [("M-204", "Hydraulic Press Main Motor", EquipmentCategory.MECHANICAL, True, site),
            ("M-101", "CNC Lathe Spindle Motor", EquipmentCategory.MECHANICAL, False, site),
            ("H-401", "Hydraulic Power Unit", EquipmentCategory.HYDRAULIC, True, site),
            ("E-110", "Main Distribution Panel", EquipmentCategory.ELECTRICAL, True, site),
            ("X-900", "Other Plant Compressor", EquipmentCategory.PNEUMATIC, False, other)]
    equipment = {}
    for code, name, cat, crit, s in rows:
        equipment[code] = Equipment(equipment_code=code, name=name, category=cat, is_critical=crit, site_id=s.id,
                                    location="Bay 1")
    db.add_all(equipment.values())

    tpl = ChecklistTemplate(name="[TEST SOP] Mechanical", equipment_category=EquipmentCategory.MECHANICAL, version=1)
    tpl.items = [ChecklistItem(description="Apply lockout/tagout", is_mandatory=True, sequence=1),
                 ChecklistItem(description="Inspect component", is_mandatory=True, sequence=2),
                 ChecklistItem(description="Record vibration reading", is_mandatory=False, sequence=3)]
    db.add(tpl)
    db.flush()

    tech1 = make_user(UserRole.TECHNICIAN)
    tech1.preferred_language = LanguageCode.HINGLISH
    w = World(
        site=site, other_site=other, equipment=equipment, tech1=tech1, tech2=make_user(UserRole.TECHNICIAN),
        other_tech=make_user(UserRole.TECHNICIAN, site=other), supervisor=make_user(UserRole.SUPERVISOR),
        supervisor2=make_user(UserRole.SUPERVISOR), manager=make_user(UserRole.MANAGER),
        other_supervisor=make_user(UserRole.SUPERVISOR, site=other), template=tpl,
    )
    db.flush()
    for u in (w.tech1, w.tech2, w.other_tech, w.supervisor, w.supervisor2, w.manager, w.other_supervisor):
        w.headers[u.email] = auth_headers(u)

    w.prisma, w.timbre = FakePrisma(transcript=DEMO), FakeTimbre()
    app.dependency_overrides[speech.get_prisma_client] = lambda: w.prisma
    app.dependency_overrides[speech.get_timbre_client] = lambda: w.timbre
    yield w
    app.dependency_overrides.pop(speech.get_prisma_client, None)
    app.dependency_overrides.pop(speech.get_timbre_client, None)


def preview(client, headers, text=DEMO, language=None) -> dict:
    body = {"text": text, "speak": False}
    if language:
        body["language"] = language
    r = client.post("/api/v1/voice/process-text", json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def submit_report(client, headers, text=DEMO, *, key: str | None = "auto", expect=201, **extra) -> dict:
    o = preview(client, headers, text)
    body = {"evidence_token": o["evidence_token"], "draft": o["draft"], "speak": False, **extra}
    if key:
        body["submission_key"] = uuid.uuid4().hex if key == "auto" else key
    r = client.post("/api/v1/work-orders", json=body, headers=headers)
    assert r.status_code == expect, r.text
    return r.json()


def act(client, headers, wo_id, action, expect=200, **body) -> dict:
    method = client.patch if action == "patch" else client.post
    path = f"/api/v1/work-orders/{wo_id}" + ("" if action == "patch" else f"/{action}")
    r = method(path, json=body, headers=headers)
    assert r.status_code == expect, f"{action}: {r.status_code} {r.text}"
    return r.json()


def drive_to(client, w: World, target: str) -> dict:
    """Create a report and move it along the happy path up to `target`. Returns the latest detail."""
    wo = submit_report(client, w.h(w.tech1))["work_order"]
    order = ["under_review", "approved", "assigned", "in_progress", "completion_review", "closed"]
    steps = order[: order.index(target) + 1]
    for step in steps[1:]:
        if step == "approved":
            wo = act(client, w.h(w.supervisor), wo["id"], "approve")
        elif step == "assigned":
            wo = act(client, w.h(w.supervisor), wo["id"], "assign", technician_id=str(w.tech1.id))
        elif step == "in_progress":
            wo = act(client, w.h(w.tech1), wo["id"], "status", to="in_progress")
        elif step == "completion_review":
            for c in wo["checklists"]:
                for item in c["items"]:
                    r = client.patch(f"/api/v1/checklists/{c['id']}/items/{item['id']}",
                                     json={"response": "done"}, headers=w.h(w.tech1))
                    assert r.status_code == 200, r.text
            wo = act(client, w.h(w.tech1), wo["id"], "complete")["work_order"]
        elif step == "closed":
            wo = act(client, w.h(w.supervisor), wo["id"], "status", to="closed")
    assert wo["status"] == target
    return wo
