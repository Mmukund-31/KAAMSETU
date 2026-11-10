"""Work-order creation (validation, duplicates) and the read side (scope, filters, search, sort, detail)."""

import uuid

import pytest
from sqlalchemy import func, select

from app.models import WorkOrder, WorkOrderEvidence
from app.tests.api.conftest import act, drive_to, preview, submit_report

URL = "/api/v1/work-orders"


def count(db) -> int:
    return db.scalar(select(func.count()).select_from(WorkOrder))


# ── creation ─────────────────────────────────────────────────────────────

def test_duplicate_submission_key_returns_409_and_creates_nothing(client, db, world):
    w = world
    o = preview(client, w.h(w.tech1))
    body = {"evidence_token": o["evidence_token"], "draft": o["draft"], "submission_key": "tap-once-123",
            "speak": False}
    first = client.post(URL, json=body, headers=w.h(w.tech1))
    second = client.post(URL, json=body, headers=w.h(w.tech1))
    assert first.status_code == 201 and second.status_code == 409
    assert second.json()["error"]["code"] == "duplicate_submission"
    assert second.json()["error"]["details"]["work_order_id"] == first.json()["work_order"]["id"]
    assert count(db) == 1


def test_same_report_cannot_be_submitted_twice_with_new_key(client, db, world):
    w = world
    o = preview(client, w.h(w.tech1))
    for key, expected in (("key-aaaaaaaa", 201), ("key-bbbbbbbb", 409)):
        r = client.post(URL, json={"evidence_token": o["evidence_token"], "draft": o["draft"],
                                   "submission_key": key, "speak": False}, headers=w.h(w.tech1))
        assert r.status_code == expected
    assert count(db) == 1


def test_incomplete_report_is_rejected(client, db, world):
    w = world
    o = preview(client, w.h(w.tech1), "Machine M-204 mein vibration aa raha hai.")  # production unknown
    r = client.post(URL, json={"evidence_token": o["evidence_token"], "draft": o["draft"], "speak": False},
                    headers=w.h(w.tech1))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "report_incomplete"
    assert r.json()["error"]["details"]["missing_fields"] == ["production_impact"]
    assert count(db) == 0


def test_unregistered_equipment_never_creates_work_order(client, db, world):
    w = world
    o = preview(client, w.h(w.tech1))
    draft = {**o["draft"], "equipment_code": "Z-999"}
    r = client.post(URL, json={"evidence_token": o["evidence_token"], "draft": draft, "speak": False},
                    headers=w.h(w.tech1))
    assert r.status_code == 422 and r.json()["error"]["details"]["equipment_status"] == "unknown"
    assert count(db) == 0


def test_other_sites_equipment_cannot_be_used(client, db, world):
    w = world
    o = preview(client, w.h(w.tech1))
    r = client.post(URL, json={"evidence_token": o["evidence_token"], "draft": {**o["draft"], "equipment_code":
                                                                                "X-900"}, "speak": False},
                    headers=w.h(w.tech1))
    assert r.status_code == 422 and count(db) == 0


def test_priority_and_category_are_recomputed_server_side(client, world):
    """The client cannot choose its own priority: there is no priority field, and edits are re-evaluated."""
    w = world
    o = preview(client, w.h(w.tech1))
    draft = {**o["draft"], "production_impact": "stopped"}  # technician corrects production impact
    wo = client.post(URL, json={"evidence_token": o["evidence_token"], "draft": draft, "speak": False},
                     headers=w.h(w.tech1)).json()["work_order"]
    assert (wo["priority"], wo["priority_rule"]) == ("critical", "critical_equipment_stopped")


def test_forged_or_foreign_evidence_rejected(client, world):
    w = world
    o = preview(client, w.h(w.tech1))
    r = client.post(URL, json={"evidence_token": o["evidence_token"], "draft": o["draft"]}, headers=w.h(w.tech2))
    assert r.status_code == 403 and r.json()["error"]["code"] == "evidence_wrong_user"
    r = client.post(URL, json={"evidence_token": o["evidence_token"] + "x", "draft": o["draft"]},
                    headers=w.h(w.tech1))
    assert r.status_code == 422 and r.json()["error"]["code"] == "evidence_invalid"


def test_voice_report_records_prisma_evidence(client, db, world):
    w = world
    files = {"audio": ("r.mp3", b"ID3" + b"\x00" * 2000, "audio/mpeg")}
    o = client.post("/api/v1/voice/process-report", data={"speak": "false"}, files=files, headers=w.h(w.tech1)).json()
    wo = client.post(URL, json={"evidence_token": o["evidence_token"], "draft": o["draft"], "speak": False},
                     headers=w.h(w.tech1)).json()["work_order"]
    assert wo["report_channel"] == "voice"
    ev = db.scalar(select(WorkOrderEvidence).where(WorkOrderEvidence.work_order_id == wo["id"]))
    assert ev.prisma_request_id == "req-1" and ev.prisma_model == "prisma-v3.0"
    assert ev.report_id is not None and ev.audio_reference is None


def test_submit_false_keeps_reported_then_submit(client, world):
    w = world
    wo = submit_report(client, w.h(w.tech1), submit=False)["work_order"]
    assert wo["status"] == "reported"
    assert [a["action"] for a in wo["allowed_actions"]] == ["submit"]
    assert act(client, w.h(w.tech1), wo["id"], "submit")["status"] == "under_review"


def test_tts_failure_does_not_fail_submission(client, world):
    from app.gnani.errors import GnaniUnavailable

    w = world
    w.timbre.error = GnaniUnavailable("down")
    r = submit_report(client, w.h(w.tech1), speak=True)
    assert r["work_order"]["status"] == "under_review"
    assert r["response"]["tts_available"] is False and r["response"]["text"]


# ── reading ──────────────────────────────────────────────────────────────

@pytest.fixture
def three_orders(client, world):
    w = world
    a = submit_report(client, w.h(w.tech1))["work_order"]                                    # M-204 high
    b = submit_report(client, w.h(w.tech1), "H-401 mein oil leak hai, production chal raha hai")["work_order"]
    c = submit_report(client, w.h(w.tech2), "E-110 mein sparking hai, production band hai")["work_order"]
    return a, b, c


def test_technician_sees_only_own_or_assigned(client, world, three_orders):
    w = world
    a, b, c = three_orders
    ids = {i["id"] for i in client.get(URL, headers=w.h(w.tech1)).json()["items"]}
    assert ids == {a["id"], b["id"]}
    assert client.get(f"{URL}/{c['id']}", headers=w.h(w.tech1)).status_code == 404


def test_supervisor_filters(client, world, three_orders):
    w = world
    a, b, c = three_orders
    h = w.h(w.supervisor)

    def ids(**params):
        return [i["id"] for i in client.get(URL, params=params, headers=h).json()["items"]]

    assert set(ids()) == {a["id"], b["id"], c["id"]}
    assert ids(priority="critical") == [c["id"]]                    # safety reported
    assert set(ids(priority="high")) == {a["id"], b["id"]}          # M-204 and H-401 are critical equipment
    assert set(ids(priority=["critical", "high"])) == {a["id"], b["id"], c["id"]}
    assert ids(equipment_id=b["equipment"]["id"]) == [b["id"]]
    assert ids(safety_only="true") == [c["id"]]
    assert ids(reported_by=str(w.tech2.id)) == [c["id"]]
    assert ids(q="oil") == [b["id"]]
    assert ids(q="M-204") == [a["id"]]
    assert ids(q=a["display_number"]) == [a["id"]]
    assert ids(q="Distribution") == [c["id"]]
    assert ids(sort="priority")[0] == c["id"]
    assert ids(overdue="true") == []


def test_pagination(client, world, three_orders):
    w = world
    r = client.get(URL, params={"page_size": 2, "page": 2}, headers=w.h(w.supervisor)).json()
    assert r["total"] == 3 and len(r["items"]) == 1 and r["page"] == 2
    assert client.get(URL, params={"page_size": 500}, headers=w.h(w.supervisor)).status_code == 422


def test_overdue_filter_and_flag(client, db, world, three_orders):
    from datetime import UTC, datetime, timedelta

    w = world
    a, _, _ = three_orders
    wo = db.get(WorkOrder, uuid.UUID(a["id"]))
    wo.due_at = datetime.now(UTC) - timedelta(hours=1)
    db.flush()
    r = client.get(URL, params={"overdue": "true"}, headers=w.h(w.supervisor)).json()
    assert [i["id"] for i in r["items"]] == [a["id"]] and r["items"][0]["is_overdue"] is True


def test_detail_shows_allowed_actions_per_role(client, world):
    w = world
    wo = drive_to(client, w, "in_progress")
    tech_view = client.get(f"{URL}/{wo['id']}", headers=w.h(w.tech1)).json()
    actions = {(a["action"], a["to"]): a for a in tech_view["allowed_actions"]}
    assert ("complete", "completion_review") in actions
    assert actions[("complete", "completion_review")]["blocked_reason"] == "checklist_incomplete"
    assert actions[("status", "blocked")]["comment_required"] is True
    assert tech_view["can_assign"] is False
    sup_view = client.get(f"{URL}/{wo['id']}", headers=w.h(w.supervisor)).json()
    assert sup_view["can_assign"] is True
    assert ("complete", "completion_review") not in {(a["action"], a["to"]) for a in sup_view["allowed_actions"]}
