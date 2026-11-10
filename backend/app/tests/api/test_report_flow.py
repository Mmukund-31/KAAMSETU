"""Report pipeline through the API with fake Gnani clients and a real database registry."""

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.gnani.errors import GnaniUnavailable
from app.main import app
from app.models import (
    AuditLog,
    Equipment,
    EquipmentCategory,
    LanguageCode,
    Site,
    UserRole,
    WorkOrder,
)
from app.services import speech
from app.tests.api.test_voice import FakePrisma, FakeTimbre

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "audio"
TEXT = "/api/v1/voice/process-text"
VOICE = "/api/v1/voice/process-report"
FOLLOW = "/api/v1/voice/follow-up"
EVAL = "/api/v1/voice/evaluate-draft"

DEMO = ("motor ka pressure abnormal hai, bearing mein vibration aa raha hai, machine number M204 hai, "
        "production abhi chal raha hai.")


@pytest.fixture
def registry(db, site):
    rows = [
        ("M-204", "Hydraulic Press Main Motor", EquipmentCategory.MECHANICAL, True),
        ("M-101", "CNC Lathe Spindle Motor", EquipmentCategory.MECHANICAL, False),
        ("H-401", "Hydraulic Power Unit", EquipmentCategory.HYDRAULIC, True),
        ("E-110", "Main Distribution Panel", EquipmentCategory.ELECTRICAL, True),
        ("E-220", "Air Compressor Motor Starter", EquipmentCategory.ELECTRICAL, False),
    ]
    items = {code: Equipment(equipment_code=code, name=name, category=cat, site_id=site.id, is_critical=crit,
                             location="Press Shop") for code, name, cat, crit in rows}
    db.add_all(items.values())
    other = Site(name="Other Plant")
    db.add(other)
    db.flush()
    db.add(Equipment(equipment_code="M-999", name="Elsewhere", category=EquipmentCategory.MECHANICAL,
                     site_id=other.id))
    db.flush()
    return items


@pytest.fixture
def tech(make_user, db):
    u = make_user(UserRole.TECHNICIAN)
    u.preferred_language = LanguageCode.HINGLISH
    db.flush()
    return u


@pytest.fixture
def fakes():
    prisma, timbre = FakePrisma(transcript=DEMO), FakeTimbre()
    app.dependency_overrides[speech.get_prisma_client] = lambda: prisma
    app.dependency_overrides[speech.get_timbre_client] = lambda: timbre
    yield prisma, timbre
    app.dependency_overrides.pop(speech.get_prisma_client, None)
    app.dependency_overrides.pop(speech.get_timbre_client, None)


def post_text(client, headers, text, **kw):
    r = client.post(TEXT, json={"text": text, **kw}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def answer(client, headers, outcome, text=None, field=None, audio=None, speak=True):
    data = {"evidence_token": outcome["evidence_token"], "draft": json.dumps(outcome["draft"]),
            "field": field or outcome["follow_up"]["field"], "speak": str(speak).lower()}
    if text is not None:
        data["answer_text"] = text
    files = {"audio": ("a.mp3", audio, "audio/mpeg")} if audio else None
    return client.post(FOLLOW, data=data, files=files, headers=headers)


# ── the demo scenario ────────────────────────────────────────────────────

def test_demo_report_by_voice(client, db, tech, registry, fakes, auth_headers):
    prisma, timbre = fakes
    r = client.post(VOICE, headers=auth_headers(tech),
                    files={"audio": ("r.mp3", (FIXTURES / "hinglish_m204.mp3").read_bytes(), "audio/mpeg")})
    assert r.status_code == 200, r.text
    o = r.json()

    assert o["next_action"] == "confirm_preview"
    assert o["equipment"]["status"] == "matched"
    assert o["equipment"]["equipment"]["code"] == "M-204"
    assert o["equipment"]["equipment"]["id"] == str(registry["M-204"].id)
    assert o["draft"]["equipment_code"] == "M-204"
    assert o["category"]["value"] == "mechanical"
    assert {s["key"] for s in o["symptoms"]} == {"bearing_vibration", "abnormal_pressure"}
    assert o["draft"]["production_impact"] == "running"
    assert (o["priority"]["level"], o["priority"]["rule_id"]) == ("high", "critical_equipment_fault")
    assert o["requires_approval"] is True
    assert o["missing_fields"] == [] and o["follow_up"] is None
    assert o["original_transcript"] == DEMO
    assert o["utterances"][0]["kind"] == "voice" and o["utterances"][0]["gnani_request_id"] == "req-1"
    assert o["response"]["text"] == "M-204 ke liye maintenance request taiyaar hai. Priority high hai. " \
                                    "Check karke submit kijiye."
    assert o["response"]["tts_available"] is True and o["response"]["audio_base64"]
    assert timbre.calls[0]["language"] == "hinglish"
    assert prisma.calls[0]["keyterms"] == ["E-110", "E-220", "H-401", "M-101", "M-204"]

    # Nothing is saved before the technician confirms (Phase 4).
    assert db.scalar(select(func.count()).select_from(WorkOrder)) == 0
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_spec_conversation_missing_production_then_haan(client, tech, registry, fakes, auth_headers):
    h = auth_headers(tech)
    o = post_text(client, h, "Machine M-204 mein vibration aa raha hai.")
    assert o["next_action"] == "ask_follow_up"
    assert o["follow_up"] == {"field": "production_impact", "question":
                              "M-204 ke liye maintenance request bana raha hoon. Kya production abhi bhi chal raha hai?"}
    assert o["priority"]["provisional"] is True

    r = answer(client, h, o, "Haan, production chal raha hai.")
    assert r.status_code == 200, r.text
    o2 = r.json()
    assert o2["next_action"] == "confirm_preview"
    assert o2["draft"]["production_impact"] == "running"
    assert [u["kind"] for u in o2["utterances"]] == ["text", "follow_up_text"]
    assert o2["utterances"][1]["field"] == "production_impact"
    assert o2["original_transcript"] == "Machine M-204 mein vibration aa raha hai."
    assert o2["report_id"] == o["report_id"]


def test_follow_up_by_voice(client, tech, registry, fakes, auth_headers):
    prisma, _ = fakes
    h = auth_headers(tech)
    o = post_text(client, h, "M-204 mein vibration hai")
    prisma.transcript = "nahi, production ruk gaya hai"
    o2 = answer(client, h, o, audio=(FIXTURES / "hinglish_m204.mp3").read_bytes()).json()
    assert o2["draft"]["production_impact"] == "stopped"
    assert o2["priority"]["level"] == "critical"   # stopped + critical equipment
    assert o2["utterances"][-1]["kind"] == "follow_up_voice"


# ── equipment validation ─────────────────────────────────────────────────

def test_unknown_equipment_is_never_accepted(client, tech, registry, fakes, auth_headers):
    h = auth_headers(tech)
    o = post_text(client, h, "M-209 mein vibration hai, production chal raha hai")
    assert o["next_action"] == "fix_equipment"
    assert o["equipment"]["status"] == "unknown" and o["equipment"]["heard"] == "M-209"
    assert o["equipment"]["equipment"] is None
    assert o["response"]["text"].startswith("Machine M-209 register mein nahi mili")
    suggested = [s["code"] for s in o["equipment"]["suggestions"]]
    assert suggested[0] == "M-204"
    assert set(suggested) <= set(registry)          # only real, same-site machines
    assert "M-999" not in suggested

    # Technician picks M-204 from the list.
    draft = {**o["draft"], "equipment_code": "M-204"}
    r = client.post(EVAL, json={"evidence_token": o["evidence_token"], "draft": draft}, headers=h)
    assert r.json()["next_action"] == "confirm_preview"
    assert r.json()["response"]["tts_available"] is None   # evaluate-draft does not speak by default


def test_spoken_correction_of_equipment(client, tech, registry, fakes, auth_headers):
    h = auth_headers(tech)
    o = post_text(client, h, "M-209 mein vibration hai, production chal raha hai")
    o2 = answer(client, h, o, "M-204", field="equipment_code").json()
    assert o2["equipment"]["status"] == "matched" and o2["next_action"] == "confirm_preview"


def test_missing_equipment_asks_for_it(client, tech, registry, fakes, auth_headers):
    o = post_text(client, auth_headers(tech), "Bearing mein vibration aa raha hai, production chal raha hai")
    assert o["next_action"] == "ask_follow_up"
    assert o["follow_up"]["field"] == "equipment_code"
    assert o["follow_up"]["question"] == "Kis machine mein problem hai? Machine number batayiye."


def test_equipment_at_another_site_is_not_matched(client, tech, registry, fakes, auth_headers):
    o = post_text(client, auth_headers(tech), "M-999 mein vibration hai, production chal raha hai")
    assert o["equipment"]["status"] == "unknown"


def test_digits_only_code_matches_when_unique(client, tech, registry, fakes, auth_headers):
    o = post_text(client, auth_headers(tech), "Machine number 204 mein vibration hai, production chal raha hai")
    assert o["equipment"]["equipment"]["code"] == "M-204"


def test_name_mentioned_suggests_machine(client, tech, registry, fakes, auth_headers):
    o = post_text(client, auth_headers(tech), "Compressor ke starter mein awaaz aa rahi hai")
    assert o["equipment"]["status"] == "missing"
    assert [s["code"] for s in o["equipment"]["suggestions"]] == ["E-220"]


# ── safety, corrections, languages ───────────────────────────────────────

def test_safety_report_is_critical_with_warning(client, tech, registry, fakes, auth_headers):
    o = post_text(client, auth_headers(tech), "E-110 panel mein sparking ho rahi hai, production band hai")
    assert o["draft"]["safety_concern"] is True
    assert (o["priority"]["level"], o["priority"]["rule_id"]) == ("critical", "safety_reported")
    assert o["response"]["text"].startswith("Aapne safety hazard report kiya hai.")


def test_transcript_correction_keeps_original(client, tech, registry, fakes, auth_headers):
    prisma, _ = fakes
    prisma.transcript = "M 209 mein vibration hai, production chal raha hai"
    h = auth_headers(tech)
    o = client.post(VOICE, headers=h, files={"audio": ("r.mp3", (FIXTURES / "hinglish_m204.mp3").read_bytes(),
                                                       "audio/mpeg")}).json()
    assert o["next_action"] == "fix_equipment"
    fixed = post_text(client, h, "M 204 mein vibration hai, production chal raha hai",
                      evidence_token=o["evidence_token"])
    assert fixed["next_action"] == "confirm_preview"
    assert fixed["original_transcript"] == "M 209 mein vibration hai, production chal raha hai"
    assert [u["kind"] for u in fixed["utterances"]] == ["voice", "correction"]
    assert fixed["report_id"] == o["report_id"]


@pytest.mark.parametrize("lang, text, expected_start", [
    ("hi", "मशीन M-204 में वाइब्रेशन आ रहा है।", "M-204 के लिए मेंटेनेंस रिक्वेस्ट तैयार कर रहा हूँ।"),
    ("te", "మెషిన్ ఎం రెండు వందల నాలుగు లో వైబ్రేషన్ వస్తోంది.", "M-204 కోసం మెయింటెనెన్స్ రిక్వెస్ట్"),
    ("en", "Machine M-204 is vibrating.", "I am preparing a maintenance request for M-204."),
])
def test_follow_up_question_in_each_language(client, tech, registry, fakes, auth_headers, lang, text,
                                             expected_start):
    o = post_text(client, auth_headers(tech), text, language=lang)
    assert o["language"] == lang
    assert o["follow_up"]["field"] == "production_impact"
    assert o["response"]["text"].startswith(expected_start)
    assert o["category"]["label"]


def test_telugu_yes_answer(client, tech, registry, fakes, auth_headers):
    h = auth_headers(tech)
    o = post_text(client, h, "మెషిన్ M-204 లో వైబ్రేషన్ వస్తోంది.", language="te")
    assert answer(client, h, o, "అవును").json()["draft"]["production_impact"] == "running"


def test_auto_language_follows_prisma_detection(client, tech, registry, fakes, auth_headers):
    prisma, _ = fakes
    prisma.transcript = "मशीन M-204 में वाइब्रेशन आ रहा है।"
    original = FakePrisma.transcribe

    def detect_hindi(self, *a, **kw):
        result = original(self, *a, **kw)
        return result.__class__(**{**result.__dict__, "detected_language": "hi-IN"})

    FakePrisma.transcribe = detect_hindi
    try:
        o = client.post(VOICE, data={"language": "auto"}, headers=auth_headers(tech),
                        files={"audio": ("r.mp3", (FIXTURES / "hinglish_m204.mp3").read_bytes(), "audio/mpeg")})
    finally:
        FakePrisma.transcribe = original
    assert o.json()["language"] == "hi"


# ── robustness ───────────────────────────────────────────────────────────

def test_tts_failure_falls_back_to_text(client, tech, registry, fakes, auth_headers):
    _, timbre = fakes
    timbre.error = GnaniUnavailable("down")
    o = post_text(client, auth_headers(tech), DEMO)
    assert o["next_action"] == "confirm_preview"
    assert o["response"]["tts_available"] is False
    assert o["response"]["tts_error"] == "speech_unavailable"
    assert o["response"]["audio_base64"] is None and o["response"]["text"]


def test_speak_false_skips_tts(client, tech, registry, fakes, auth_headers):
    _, timbre = fakes
    o = post_text(client, auth_headers(tech), DEMO, speak=False)
    assert timbre.calls == [] and o["response"]["tts_available"] is None


def test_prisma_failure_returns_error_not_a_fake_report(client, tech, registry, fakes, auth_headers):
    prisma, _ = fakes
    prisma.error = GnaniUnavailable("down")
    r = client.post(VOICE, headers=auth_headers(tech),
                    files={"audio": ("r.mp3", (FIXTURES / "hinglish_m204.mp3").read_bytes(), "audio/mpeg")})
    assert r.status_code == 503 and r.json()["error"]["code"] == "speech_unavailable"
    assert "draft" not in r.json()


def test_evidence_token_cannot_be_reused_by_another_user(client, tech, make_user, registry, fakes, auth_headers):
    o = post_text(client, auth_headers(tech), "M-204 mein vibration hai")
    other = make_user(UserRole.TECHNICIAN)
    r = answer(client, auth_headers(other), o, "haan")
    assert r.status_code == 403 and r.json()["error"]["code"] == "evidence_wrong_user"


def test_tampered_evidence_rejected(client, tech, registry, fakes, auth_headers):
    h = auth_headers(tech)
    o = post_text(client, h, "M-204 mein vibration hai")
    o["evidence_token"] = o["evidence_token"][:-3] + "abc"
    r = answer(client, h, o, "haan")
    assert r.status_code == 422 and r.json()["error"]["code"] == "evidence_invalid"


def test_client_cannot_inject_unknown_symptoms(client, tech, registry, fakes, auth_headers):
    h = auth_headers(tech)
    o = post_text(client, h, DEMO)
    draft = {**o["draft"], "symptoms": [*o["draft"]["symptoms"], "made_up_symptom"]}
    r = client.post(EVAL, json={"evidence_token": o["evidence_token"], "draft": draft}, headers=h).json()
    assert "made_up_symptom" not in r["draft"]["symptoms"]
    assert "unknown_symptoms_ignored" in r["warnings"]


def test_client_cannot_clear_safety_while_safety_symptom_present(client, tech, registry, fakes, auth_headers):
    h = auth_headers(tech)
    o = post_text(client, h, "E-110 mein sparking ho rahi hai, production chal raha hai")
    draft = {**o["draft"], "safety_concern": False}
    r = client.post(EVAL, json={"evidence_token": o["evidence_token"], "draft": draft}, headers=h).json()
    assert r["draft"]["safety_concern"] is True and r["priority"]["level"] == "critical"


@pytest.mark.parametrize("data, code", [
    ({"draft": "{not json", "field": "symptoms", "answer_text": "x"}, "invalid_draft"),
    ({"draft": "{}", "field": "symptoms"}, "empty_answer"),
])
def test_follow_up_validation(client, tech, registry, fakes, auth_headers, data, code):
    h = auth_headers(tech)
    o = post_text(client, h, "M-204 mein vibration hai")
    r = client.post(FOLLOW, data={"evidence_token": o["evidence_token"], **data}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == code


def test_report_endpoints_require_auth(client, fakes):
    assert client.post(TEXT, json={"text": "x"}).status_code == 401
    assert client.post(EVAL, json={"evidence_token": "x", "draft": {}}).status_code == 401
