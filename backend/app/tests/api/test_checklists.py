from app.tests.api.conftest import act, drive_to

TEMPLATES = "/api/v1/checklists/templates"


def item_url(c, item):
    return f"/api/v1/checklists/{c['id']}/items/{item['id']}"


def test_publish_new_version_deactivates_previous(client, world):
    w = world
    body = {"name": "[TEST SOP] Mechanical v2", "equipment_category": "mechanical",
            "items": [{"description": "Apply lockout/tagout"}, {"description": "Replace bearing", "is_mandatory": True},
                      {"description": "Photograph the part", "is_mandatory": False}]}
    r = client.post(TEMPLATES, json=body, headers=w.h(w.supervisor))
    assert r.status_code == 201, r.text
    new = r.json()
    assert new["version"] == 2 and new["is_active"] and [i["sequence"] for i in new["items"]] == [1, 2, 3]
    active = client.get(TEMPLATES, params={"category": "mechanical"}, headers=w.h(w.tech1)).json()
    assert [t["id"] for t in active] == [new["id"]]
    every = client.get(TEMPLATES, params={"category": "mechanical", "active_only": "false"},
                       headers=w.h(w.tech1)).json()
    assert [t["version"] for t in every] == [2, 1]


def test_only_supervisors_publish_templates(client, world):
    w = world
    r = client.post(TEMPLATES, json={"name": "x step", "equipment_category": "mechanical",
                                     "items": [{"description": "abc"}]}, headers=w.h(w.tech1))
    assert r.status_code == 403


def test_existing_checklists_keep_their_version(client, world):
    w = world
    wo = drive_to(client, w, "assigned")
    client.post(TEMPLATES, json={"name": "v2", "equipment_category": "mechanical",
                                 "items": [{"description": "New step"}]}, headers=w.h(w.supervisor))
    detail = client.get(f"/api/v1/work-orders/{wo['id']}", headers=w.h(w.tech1)).json()
    assert detail["checklists"][0]["template_version"] == 1 and len(detail["checklists"][0]["items"]) == 3


def test_attach_is_idempotent_and_requires_template(client, world):
    w = world
    wo = drive_to(client, w, "assigned")
    url = f"/api/v1/work-orders/{wo['id']}/checklists"
    first = client.post(url, json={}, headers=w.h(w.supervisor))
    assert first.status_code == 201 and first.json()["id"] == wo["checklists"][0]["id"]
    # hydraulic equipment has no active template
    other = drive_to(client, w, "approved")
    from app.models import WorkOrder  # noqa: F401

    r = client.post(f"/api/v1/work-orders/{other['id']}/checklists",
                    json={"template_id": "00000000-0000-0000-0000-000000000000"}, headers=w.h(w.supervisor))
    assert r.status_code == 404


def test_step_rules(client, world):
    w = world
    wo = drive_to(client, w, "assigned")
    c = wo["checklists"][0]
    first = c["items"][0]
    # not started yet
    assert client.patch(item_url(c, first), json={"response": "done"}, headers=w.h(w.tech1)).status_code == 409
    act(client, w.h(w.tech1), wo["id"], "status", to="in_progress")
    # only the assignee records steps
    r = client.patch(item_url(c, first), json={"response": "done"}, headers=w.h(w.supervisor))
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_assignee"
    # failed / not applicable need a note
    r = client.patch(item_url(c, first), json={"response": "failed"}, headers=w.h(w.tech1))
    assert r.status_code == 422 and r.json()["error"]["code"] == "notes_required"
    r = client.patch(item_url(c, first), json={"response": "failed", "notes": "Lock missing"}, headers=w.h(w.tech1))
    assert r.json()["status"] == "in_progress" and r.json()["mandatory_done"] == 0
    # a failed mandatory step blocks completion
    for item in c["items"][1:]:
        client.patch(item_url(c, item), json={"response": "done"}, headers=w.h(w.tech1))
    assert act(client, w.h(w.tech1), wo["id"], "complete", expect=409)["error"]["code"] == "checklist_incomplete"
    # correcting the step (re-answer) updates it in place
    r = client.patch(item_url(c, first), json={"response": "done"}, headers=w.h(w.tech1)).json()
    assert r["is_complete"] and r["status"] == "completed" and r["items"][0]["completed_by"]["id"] == str(w.tech1.id)
    assert act(client, w.h(w.tech1), wo["id"], "complete")["work_order"]["status"] == "completion_review"


def test_unknown_item_404(client, world):
    w = world
    wo = drive_to(client, w, "in_progress")
    c = wo["checklists"][0]
    r = client.patch(f"/api/v1/checklists/{c['id']}/items/00000000-0000-0000-0000-000000000000",
                     json={"response": "done"}, headers=w.h(w.tech1))
    assert r.status_code == 404


def test_checklist_not_visible_to_other_site(client, world):
    w = world
    wo = drive_to(client, w, "assigned")
    c = wo["checklists"][0]
    assert client.get(f"/api/v1/checklists/{c['id']}", headers=w.h(w.other_supervisor)).status_code == 404
    assert client.get(f"/api/v1/checklists/{c['id']}", headers=w.h(w.tech1)).status_code == 200
