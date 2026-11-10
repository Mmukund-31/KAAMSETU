from pathlib import Path

from app.tests.api.conftest import act, drive_to, submit_report

URL = "/api/v1/handovers"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "audio"


def test_summary_is_built_from_records_and_notes(client, world):
    w = world
    done = drive_to(client, w, "completion_review")                    # completed this shift
    blocked = drive_to(client, w, "in_progress")
    act(client, w.h(w.tech1), blocked["id"], "status", to="awaiting_parts", comment="Seal kit ordered")
    waiting = submit_report(client, w.h(w.tech2), "H-401 mein oil leak hai, production chal raha hai")["work_order"]

    notes = ("M-101 spindle was noisy at the end of the shift. Next shift should check the M-101 belt tension. "
             "Floor near the press was cleaned.")
    r = client.post(URL, json={"shift_identifier": "2026-11-10-A", "notes": notes, "language": "en"},
                    headers=w.h(w.tech1))
    assert r.status_code == 201, r.text
    h = r.json()
    s = h["generated_summary"]
    assert h["original_notes"] == notes and h["status"] == "submitted"
    assert [x["id"] for x in s["completed"]] == [done["id"]]
    assert [x["id"] for x in s["blocked"]] == [blocked["id"]]
    assert waiting["id"] in [x["id"] for x in s["awaiting_approval"]]
    assert done["id"] in [x["id"] for x in s["awaiting_approval"]]          # completion review needs sign-off
    assert s["next_shift_actions"] == ["Next shift should check the M-101 belt tension."]
    assert s["observations"] == ["M-101 spindle was noisy at the end of the shift.", "Floor near the press was cleaned."]
    attention = {a["code"]: a["reason"] for a in s["equipment_attention"]}
    assert attention["M-101"] == "mentioned in handover notes"
    assert "M-204" in attention and "H-401" in attention                   # open high-priority work
    sources = [(p["source"], p.get("work_order_id")) for p in h["pending_actions"]]
    assert ("notes", None) in sources and ("system", blocked["id"]) in sources
    assert h["history"][0]["action"] == "handover.create"


def test_unregistered_code_in_notes_is_not_listed(client, world):
    w = world
    r = client.post(URL, json={"shift_identifier": "B", "notes": "Q-555 looked odd."}, headers=w.h(w.tech1)).json()
    assert all(a["code"] != "Q-555" for a in r["generated_summary"]["equipment_attention"])


def test_hinglish_action_cue(client, world):
    w = world
    r = client.post(URL, json={"shift_identifier": "C", "notes": "M-204 ka bearing kal check karna hai.",
                               "language": "hinglish"}, headers=w.h(w.tech1)).json()
    assert r["generated_summary"]["next_shift_actions"] == ["M-204 ka bearing kal check karna hai."]


def test_review_rules(client, world):
    w = world
    h = client.post(URL, json={"shift_identifier": "D", "notes": "All quiet."}, headers=w.h(w.supervisor)).json()
    url = f"{URL}/{h['id']}/review"
    assert client.post(url, json={}, headers=w.h(w.supervisor)).json()["error"]["code"] == "self_review_not_allowed"
    assert client.post(url, json={}, headers=w.h(w.tech1)).status_code == 403
    r = client.post(url, json={"comment": "Noted", "pending_actions": [{"text": "Order spare V-belt"}]},
                    headers=w.h(w.supervisor2))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "reviewed" and body["reviewed_by"]["id"] == str(w.supervisor2.id)
    assert body["pending_actions"] == [{"text": "Order spare V-belt", "source": "supervisor", "work_order_id": None,
                                        "done": False}]
    assert client.post(url, json={}, headers=w.h(w.manager)).status_code == 409


def test_list_is_site_scoped(client, world):
    w = world
    client.post(URL, json={"shift_identifier": "E", "notes": "ok"}, headers=w.h(w.tech1))
    assert client.get(URL, headers=w.h(w.supervisor)).json()["total"] == 1
    assert client.get(URL, headers=w.h(w.other_supervisor)).json()["total"] == 0
    reviewed = client.get(URL, params={"status": "reviewed"}, headers=w.h(w.supervisor)).json()
    assert reviewed["total"] == 0


def test_voice_handover_keeps_transcript(client, world):
    w = world
    w.prisma.transcript = "M-101 ka belt dheela hai, agli shift mein check karna hai."
    r = client.post(f"{URL}/voice", data={"shift_identifier": "F", "language": "hinglish"},
                    files={"audio": ("h.mp3", (FIXTURES / "hinglish_m204.mp3").read_bytes(), "audio/mpeg")},
                    headers=w.h(w.tech1))
    assert r.status_code == 201, r.text
    h = r.json()
    assert h["original_notes"] == "M-101 ka belt dheela hai, agli shift mein check karna hai."
    assert h["generated_summary"]["transcript"]["gnani_request_id"] == "req-1"
    assert h["generated_summary"]["next_shift_actions"]
