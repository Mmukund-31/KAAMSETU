"""The full demo scenario (spec section 16) and the lifecycle rules around it."""

import pytest
from sqlalchemy import select

from app.models import AuditLog, WorkOrder, WorkOrderEvidence
from app.tests.api.conftest import DEMO, act, drive_to, submit_report


def test_demo_scenario_end_to_end(client, db, world):
    w = world
    # 1-10: technician reports by voice/text, previews, submits
    created = submit_report(client, w.h(w.tech1), speak=True)
    wo = created["work_order"]
    assert wo["status"] == "under_review"
    assert wo["display_number"].startswith("WO-")
    assert (wo["equipment"]["code"], wo["issue_category"], wo["priority"]) == ("M-204", "mechanical", "high")
    assert wo["priority_rule"] == "critical_equipment_fault"
    assert set(wo["symptoms"]) == {"bearing_vibration", "abnormal_pressure"}
    assert wo["production_impact"] == "running"
    assert wo["report_channel"] == "text"
    assert wo["due_at"] is not None and wo["is_overdue"] is False
    assert wo["evidence"]["original_transcript"] == DEMO
    assert wo["evidence"]["audio_retained"] is False
    assert created["response"]["text"] == \
        f"Request supervisor review ke liye submit kar di gayi hai. Work order number {wo['display_number']}."
    assert created["response"]["tts_available"] is True

    # 11-12: supervisor sees it in the approval queue and approves
    queue = client.get("/api/v1/work-orders", params={"status": "under_review"}, headers=w.h(w.supervisor)).json()
    assert [i["id"] for i in queue["items"]] == [wo["id"]]
    detail = client.get(f"/api/v1/work-orders/{wo['id']}", headers=w.h(w.supervisor)).json()
    assert {a["action"] for a in detail["allowed_actions"]} >= {"approve", "reject", "escalate"}
    wo = act(client, w.h(w.supervisor), wo["id"], "approve", comment="Inspect today")
    assert wo["status"] == "approved"

    # 13: assign; the mechanical SOP checklist is attached automatically
    wo = act(client, w.h(w.supervisor), wo["id"], "assign", technician_id=str(w.tech2.id), comments="Bay 2")
    assert wo["status"] == "assigned" and wo["assignee"]["id"] == str(w.tech2.id)
    assert len(wo["checklists"]) == 1 and wo["checklists"][0]["template_name"] == "[TEST SOP] Mechanical"

    # 14: technician sees the task, with a spoken-style announcement in their language
    mine = client.get("/api/v1/work-orders", params={"mine": "true"}, headers=w.h(w.tech2)).json()
    assert [i["id"] for i in mine["items"]] == [wo["id"]]
    task = client.get(f"/api/v1/work-orders/{wo['id']}", headers=w.h(w.tech2)).json()
    assert task["task_announcement"].startswith(f"New task {wo['display_number']} on M-204")

    # 15: start work, complete the approved checklist
    wo = act(client, w.h(w.tech2), wo["id"], "status", to="in_progress")
    checklist = wo["checklists"][0]
    blocked = act(client, w.h(w.tech2), wo["id"], "complete", expect=409)
    assert blocked["error"]["code"] == "checklist_incomplete"
    for item in checklist["items"]:
        r = client.patch(f"/api/v1/checklists/{checklist['id']}/items/{item['id']}",
                         json={"response": "done"} if item["is_mandatory"] else
                         {"response": "not_applicable", "notes": "No vibration meter on shift"},
                         headers=w.h(w.tech2))
        assert r.status_code == 200, r.text
    assert r.json()["is_complete"] and r.json()["status"] == "completed"

    # 16: report completion (spoken acknowledgement)
    done = act(client, w.h(w.tech2), wo["id"], "complete", notes="Bearing replaced", speak=True)
    assert done["work_order"]["status"] == "completion_review"
    assert done["response"]["tts_available"] is True

    # 17: supervisor closes
    wo = act(client, w.h(w.supervisor), wo["id"], "status", to="closed")
    assert wo["status"] == "closed" and wo["closed_at"] and wo["allowed_actions"] == []

    # 19: dashboard reflects the real records
    ov = client.get("/api/v1/dashboard/overview", headers=w.h(w.manager)).json()
    assert ov["completed_7d"] == 1 and ov["open"] == 0 and ov["total"] == 1

    # Every step is in the audit trail, in order, with the right actor.
    actions = [(h["action"], (h["new_value"] or {}).get("status")) for h in wo["history"]]
    assert actions == [
        ("work_order.create", None),
        ("work_order.transition", "under_review"),
        ("work_order.transition", "approved"),
        ("work_order.transition", "assigned"),
        ("checklist.attach", None),
        ("work_order.transition", "in_progress"),
        ("checklist.item_update", None), ("checklist.item_update", None), ("checklist.item_update", None),
        ("work_order.transition", "completion_review"),
        ("work_order.transition", "closed"),
    ]
    by = {(h["new_value"] or {}).get("status"): h["actor"]["id"] for h in wo["history"] if h["actor"]}
    assert by["approved"] == str(w.supervisor.id) and by["completion_review"] == str(w.tech2.id)


def test_evidence_is_immutable_record_of_what_was_said(client, db, world):
    w = world
    wo = submit_report(client, w.h(w.tech1))["work_order"]
    ev = db.scalar(select(WorkOrderEvidence).where(WorkOrderEvidence.work_order_id == wo["id"]))
    assert ev.original_transcript == DEMO
    assert ev.extracted_data["validated"]["equipment_code"] == "M-204"
    assert ev.extracted_data["utterances"][0]["kind"] == "text"
    # Editing the work order never touches the evidence
    act(client, w.h(w.supervisor), wo["id"], "patch", issue_description="Bearing noise on press motor")
    db.refresh(ev)
    assert ev.original_transcript == DEMO


# ── permission and transition rules ──────────────────────────────────────

def test_technician_cannot_approve(client, world):
    w = world
    wo = submit_report(client, w.h(w.tech1))["work_order"]
    r = act(client, w.h(w.tech2), wo["id"], "approve", expect=404)  # not visible to an unrelated technician
    assert r["error"]["code"] == "work_order_not_found"
    r = act(client, w.h(w.tech1), wo["id"], "approve", expect=403)  # the reporter can see it but not approve
    assert r["error"]["code"] == "transition_not_permitted"


def test_supervisor_cannot_approve_own_report(client, world):
    w = world
    wo = submit_report(client, w.h(w.supervisor))["work_order"]
    r = act(client, w.h(w.supervisor), wo["id"], "approve", expect=403)
    assert r["error"]["code"] == "self_approval_not_allowed"
    assert act(client, w.h(w.supervisor2), wo["id"], "approve")["status"] == "approved"


def test_self_approval_allowed_only_by_policy(client, world, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "allow_self_approval", True)
    w = world
    wo = submit_report(client, w.h(w.supervisor))["work_order"]
    assert act(client, w.h(w.supervisor), wo["id"], "approve")["status"] == "approved"


def test_reject_requires_reason_and_is_terminal(client, world):
    w = world
    wo = submit_report(client, w.h(w.tech1))["work_order"]
    assert act(client, w.h(w.supervisor), wo["id"], "reject", expect=422, comment="")["error"]["code"] == \
        "validation_error"
    wo = act(client, w.h(w.supervisor), wo["id"], "reject", comment="Duplicate of an open order")
    assert wo["status"] == "rejected" and wo["allowed_actions"] == []
    r = act(client, w.h(w.supervisor), wo["id"], "approve", expect=409)
    assert r["error"]["code"] == "invalid_transition" and r["error"]["details"]["allowed"] == []


def test_supervisor_of_other_site_cannot_see_or_act(client, world):
    w = world
    wo = submit_report(client, w.h(w.tech1))["work_order"]
    assert client.get(f"/api/v1/work-orders/{wo['id']}", headers=w.h(w.other_supervisor)).status_code == 404
    assert act(client, w.h(w.other_supervisor), wo["id"], "approve", expect=404)
    listing = client.get("/api/v1/work-orders", headers=w.h(w.other_supervisor)).json()
    assert listing["total"] == 0


def test_only_assignee_can_start_and_complete(client, world):
    w = world
    wo = drive_to(client, w, "assigned")  # assigned to tech1
    # tech2 is unrelated: cannot even see it
    assert act(client, w.h(w.tech2), wo["id"], "status", expect=404, to="in_progress")
    wo = act(client, w.h(w.tech1), wo["id"], "status", to="in_progress")
    # supervisors cannot complete on the technician's behalf
    assert act(client, w.h(w.supervisor), wo["id"], "complete", expect=403)["error"]["code"] == \
        "transition_not_permitted"


def test_block_needs_reason_and_resume(client, world):
    w = world
    wo = drive_to(client, w, "in_progress")
    assert act(client, w.h(w.tech1), wo["id"], "status", expect=422, to="awaiting_parts")["error"]["code"] == \
        "comment_required"
    wo = act(client, w.h(w.tech1), wo["id"], "status", to="awaiting_parts", comment="Bearing 6205 out of stock")
    assert wo["status"] == "awaiting_parts"
    assert act(client, w.h(w.tech1), wo["id"], "complete", expect=409)["error"]["code"] == "invalid_transition"
    assert act(client, w.h(w.tech1), wo["id"], "status", to="in_progress")["status"] == "in_progress"


def test_dedicated_actions_cannot_be_bypassed_via_generic_status(client, world):
    w = world
    wo = submit_report(client, w.h(w.tech1))["work_order"]
    r = act(client, w.h(w.supervisor), wo["id"], "status", expect=409, to="approved")
    assert r["error"]["code"] == "use_dedicated_action" and r["error"]["details"]["action"] == "approve"
    wo = drive_to(client, w, "in_progress")
    r = act(client, w.h(w.tech1), wo["id"], "status", expect=409, to="completion_review")
    assert r["error"]["details"]["action"] == "complete"


def test_cannot_skip_states(client, world):
    w = world
    wo = submit_report(client, w.h(w.tech1))["work_order"]
    r = act(client, w.h(w.supervisor), wo["id"], "status", expect=409, to="closed")
    assert r["error"]["code"] == "invalid_transition"
    assert set(r["error"]["details"]["allowed"]) == {"approved", "rejected", "escalated"}


def test_reopen_and_rework(client, world):
    w = world
    wo = drive_to(client, w, "completion_review")
    assert act(client, w.h(w.supervisor), wo["id"], "status", expect=422, to="reopened")
    wo = act(client, w.h(w.supervisor), wo["id"], "status", to="reopened", comment="Noise still present")
    assert wo["status"] == "reopened" and wo["assignee"]["id"] == str(w.tech1.id)
    wo = act(client, w.h(w.tech1), wo["id"], "status", to="in_progress")
    assert wo["status"] == "in_progress"


def test_escalation_resolved_by_manager_only(client, world):
    w = world
    wo = submit_report(client, w.h(w.tech1))["work_order"]
    wo = act(client, w.h(w.supervisor), wo["id"], "escalate", comment="Needs capex approval")
    assert wo["status"] == "escalated"
    assert act(client, w.h(w.supervisor2), wo["id"], "approve", expect=403, comment="ok")
    assert act(client, w.h(w.manager), wo["id"], "approve", expect=422)["error"]["code"] == "comment_required"
    wo = act(client, w.h(w.manager), wo["id"], "approve", comment="Approved by plant manager")
    assert wo["status"] == "approved"


def test_priority_override_on_approve_is_audited(client, db, world):
    w = world
    wo = submit_report(client, w.h(w.tech1))["work_order"]
    r = act(client, w.h(w.supervisor), wo["id"], "approve", expect=422, priority="critical")
    assert r["error"]["code"] == "priority_reason_required"
    wo2 = act(client, w.h(w.supervisor), wo["id"], "approve", priority="critical",
              priority_reason="Press is the line bottleneck this week")
    assert (wo2["priority"], wo2["priority_rule"]) == ("critical", "supervisor_override")
    assert wo2["due_at"] < wo["due_at"]  # critical SLA is shorter
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "work_order.priority_override"))
    assert entry.previous_value["priority"] == "high" and entry.new_value["priority"] == "critical"
    assert entry.comment == "Press is the line bottleneck this week"


@pytest.mark.parametrize("field, value", [("priority", "low")])
def test_technician_cannot_change_priority(client, world, field, value):
    w = world
    wo = submit_report(client, w.h(w.tech1))["work_order"]
    r = act(client, w.h(w.tech1), wo["id"], "patch", expect=403, **{field: value})
    assert r["error"]["code"] == "edit_not_permitted"


def test_reporter_can_edit_only_before_approval(client, world):
    w = world
    wo = submit_report(client, w.h(w.tech1))["work_order"]
    assert act(client, w.h(w.tech1), wo["id"], "patch", location_note="Bay 2, east side")["location_note"] == \
        "Bay 2, east side"
    act(client, w.h(w.supervisor), wo["id"], "approve")
    assert act(client, w.h(w.tech1), wo["id"], "patch", expect=403, location_note="x")


def test_reassign_keeps_status_and_is_audited(client, world):
    w = world
    wo = drive_to(client, w, "in_progress")
    wo = act(client, w.h(w.supervisor), wo["id"], "assign", technician_id=str(w.tech2.id), comments="Shift change")
    assert wo["status"] == "in_progress" and wo["assignee"]["id"] == str(w.tech2.id)
    assert [a["technician"]["id"] for a in wo["assignments"]] == [str(w.tech1.id), str(w.tech2.id)]
    assert wo["history"][-1]["action"] == "work_order.reassign"
    assert len(wo["checklists"]) == 1  # not attached twice


@pytest.mark.parametrize("who, code", [("other_tech", "technician_wrong_site"), ("supervisor", "not_a_technician")])
def test_assign_validation(client, world, who, code):
    w = world
    wo = drive_to(client, w, "approved")
    r = act(client, w.h(w.supervisor), wo["id"], "assign", expect=422, technician_id=str(getattr(w, who).id))
    assert r["error"]["code"] == code


def test_cannot_assign_before_approval(client, world):
    w = world
    wo = submit_report(client, w.h(w.tech1))["work_order"]
    r = act(client, w.h(w.supervisor), wo["id"], "assign", expect=409, technician_id=str(w.tech1.id))
    assert r["error"]["code"] == "invalid_transition"


def test_closed_work_order_is_frozen(client, db, world):
    w = world
    wo = drive_to(client, w, "closed")
    assert act(client, w.h(w.supervisor), wo["id"], "patch", expect=409, issue_description="x")
    assert act(client, w.h(w.supervisor), wo["id"], "assign", expect=409, technician_id=str(w.tech2.id))
    assert db.get(WorkOrder, wo["id"]).status.value == "closed"
