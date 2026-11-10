"""Dashboard numbers must equal what is in the database, scoped to the viewer's site."""

from datetime import UTC, datetime, timedelta

from app.models import WorkOrder
from app.tests.api.conftest import act, drive_to, submit_report


def test_overview_counts_are_exact(client, db, world):
    w = world
    drive_to(client, w, "closed")                                   # 1 closed
    drive_to(client, w, "in_progress")                              # 1 in progress
    submit_report(client, w.h(w.tech1), "E-110 mein sparking hai, production band hai")  # under review, critical
    blocked = drive_to(client, w, "in_progress")
    act(client, w.h(w.tech1), blocked["id"], "status", to="blocked", comment="Waiting for crane")

    ov = client.get("/api/v1/dashboard/overview", headers=w.h(w.supervisor)).json()
    assert ov["total"] == 4 and ov["open"] == 3
    assert ov["pending_approval"] == 1 and ov["in_progress"] == 1 and ov["blocked"] == 1
    assert ov["completed_7d"] == 1 and ov["safety_open"] == 1
    assert ov["critical_high_open"] == 3
    assert ov["by_status"]["closed"] == 1 and ov["by_status"]["under_review"] == 1
    assert ov["by_priority_open"] == {"low": 0, "medium": 0, "high": 2, "critical": 1}
    assert ov["overdue"] == 0


def test_other_sites_orders_are_not_counted(client, db, world):
    """Regression guard: a lost join in the aggregate query would multiply or leak counts."""
    w = world
    submit_report(client, w.h(w.tech1))
    ov = client.get("/api/v1/dashboard/overview", headers=w.h(w.other_supervisor)).json()
    assert ov["total"] == 0
    assert client.get("/api/v1/dashboard/overview", headers=w.h(w.supervisor)).json()["total"] == 1


def test_overdue_count(client, db, world):
    w = world
    wo = submit_report(client, w.h(w.tech1))["work_order"]
    row = db.get(WorkOrder, wo["id"])
    row.due_at = datetime.now(UTC) - timedelta(minutes=5)
    db.flush()
    assert client.get("/api/v1/dashboard/overview", headers=w.h(w.supervisor)).json()["overdue"] == 1


def test_trends(client, world):
    w = world
    drive_to(client, w, "closed")
    submit_report(client, w.h(w.tech1))
    points = client.get("/api/v1/dashboard/work-order-trends", params={"days": 7}, headers=w.h(w.manager)).json()
    assert len(points) == 7
    assert points[-1]["day"] == datetime.now(UTC).date().isoformat()
    assert points[-1]["created"] == 2 and points[-1]["closed"] == 1
    assert sum(p["created"] for p in points[:-1]) == 0


def test_equipment_issues_and_recurring_faults(client, world):
    w = world
    submit_report(client, w.h(w.tech1))
    submit_report(client, w.h(w.tech1), "M-204 mein bearing vibration hai, production ruk gaya hai")
    submit_report(client, w.h(w.tech1), "H-401 mein oil leak hai, production chal raha hai")
    r = client.get("/api/v1/dashboard/equipment-issues", headers=w.h(w.supervisor)).json()
    top = r["equipment"][0]
    assert (top["code"], top["work_orders"], top["recurring"]) == ("M-204", 2, True)
    assert top["top_symptoms"][0] == {"symptom": "bearing_vibration", "label": "Bearing vibration", "count": 2}
    assert r["by_category"] == {"mechanical": 2, "hydraulic": 1}
    detail = client.get(f"/api/v1/equipment/{top['equipment_id']}", headers=w.h(w.supervisor)).json()
    assert detail["recurring_faults"][0]["symptom"] == "bearing_vibration"
    assert detail["open_work_orders"] == 2 and len(detail["recent_work_orders"]) == 2


def test_technician_workload(client, world):
    w = world
    drive_to(client, w, "in_progress")          # tech1 in progress
    drive_to(client, w, "closed")               # tech1 closed
    rows = {r["technician"]["id"]: r for r in
            client.get("/api/v1/dashboard/technician-workload", headers=w.h(w.supervisor)).json()}
    t1 = rows[str(w.tech1.id)]
    assert (t1["in_progress"], t1["closed_30d"], t1["open_total"]) == (1, 1, 1)
    assert rows[str(w.tech2.id)]["open_total"] == 0
    assert str(w.other_tech.id) not in rows


def test_dashboard_is_for_supervisors(client, world):
    w = world
    for path in ("overview", "work-order-trends", "equipment-issues", "technician-workload"):
        assert client.get(f"/api/v1/dashboard/{path}", headers=w.h(w.tech1)).status_code == 403
