from app.tests.api.conftest import drive_to, submit_report


def test_equipment_list_is_site_scoped_and_searchable(client, world):
    w = world
    codes = [e["code"] for e in client.get("/api/v1/equipment", headers=w.h(w.tech1)).json()["items"]]
    assert codes == ["E-110", "H-401", "M-101", "M-204"]
    found = client.get("/api/v1/equipment", params={"q": "m204"}, headers=w.h(w.tech1)).json()["items"]
    assert [e["code"] for e in found] == ["M-204"]
    hyd = client.get("/api/v1/equipment", params={"category": "hydraulic"}, headers=w.h(w.tech1)).json()["items"]
    assert [e["code"] for e in hyd] == ["H-401"]
    assert client.get(f"/api/v1/equipment/{w.equipment['X-900'].id}", headers=w.h(w.tech1)).status_code == 404


def test_create_equipment(client, world):
    w = world
    body = {"equipment_code": "p 777", "name": "Vacuum Pump", "category": "pneumatic", "is_critical": True}
    r = client.post("/api/v1/equipment", json=body, headers=w.h(w.supervisor))
    assert r.status_code == 201 and r.json()["code"] == "P-777"
    assert client.post("/api/v1/equipment", json={**body, "equipment_code": "P777"},
                       headers=w.h(w.supervisor)).json()["error"]["code"] == "equipment_code_taken"
    assert client.post("/api/v1/equipment", json={**body, "equipment_code": "Q-1"},
                       headers=w.h(w.supervisor)).status_code == 422
    assert client.post("/api/v1/equipment", json=body, headers=w.h(w.tech1)).status_code == 403
    # The new machine is immediately usable in a voice report
    o = client.post("/api/v1/voice/process-text", json={"text": "P-777 mein air leak hai, production chal raha hai",
                                                          "speak": False}, headers=w.h(w.tech1)).json()
    assert o["equipment"]["status"] == "matched"


def test_users_list_for_assignment(client, world):
    w = world
    techs = client.get("/api/v1/users", params={"role": "technician"}, headers=w.h(w.supervisor)).json()
    assert {t["id"] for t in techs} == {str(w.tech1.id), str(w.tech2.id)}
    assert client.get("/api/v1/users", headers=w.h(w.tech1)).status_code == 403


def test_audit_log_endpoint(client, world):
    w = world
    wo = drive_to(client, w, "approved")
    r = client.get("/api/v1/audit-logs", params={"entity_id": wo["id"]}, headers=w.h(w.manager)).json()
    assert [e["action"] for e in r["items"]] == ["work_order.transition", "work_order.transition",
                                                 "work_order.create"]                # newest first
    assert r["items"][0]["actor"]["id"] == str(w.supervisor.id)
    assert client.get("/api/v1/audit-logs", headers=w.h(w.tech1)).status_code == 403
    other = client.get("/api/v1/audit-logs", headers=w.h(w.other_supervisor)).json()
    assert other["total"] == 0


def test_every_state_change_is_audited(client, db, world):
    """No transition without an audit row: compare the transitions recorded to the final status path."""
    from sqlalchemy import select

    from app.models import AuditLog

    w = world
    wo = drive_to(client, w, "closed")
    rows = db.scalars(select(AuditLog).where(AuditLog.entity_id == wo["id"],
                                             AuditLog.action == "work_order.transition").order_by(AuditLog.seq))
    path = [r.new_value["status"] for r in rows]
    assert path == ["under_review", "approved", "assigned", "in_progress", "completion_review", "closed"]
    prev = [r.previous_value["status"] for r in db.scalars(
        select(AuditLog).where(AuditLog.entity_id == wo["id"], AuditLog.action == "work_order.transition")
        .order_by(AuditLog.seq))]
    assert prev == ["reported", *path[:-1]]


def test_seed_history_appears_in_equipment_detail(client, db, world):
    w = world
    submit_report(client, w.h(w.tech1))
    detail = client.get(f"/api/v1/equipment/{w.equipment['M-204'].id}", headers=w.h(w.tech1)).json()
    assert detail["work_orders_total"] == 1
