"""REAL end-to-end report pipeline: audio -> Prisma -> extraction -> registry -> priority -> Timbre.

Spends a few credits. Skipped unless GNANI_API_KEY is set and RUN_GNANI_INTEGRATION=1.
Inputs are Timbre-generated synthetic speech, not human recordings.
"""

import base64
import os
from pathlib import Path

import pytest

from app.config import get_settings
from app.gnani.timbre import TimbreClient
from app.models import Equipment, EquipmentCategory, LanguageCode, UserRole
from app.services.audio import detect_format

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_GNANI_INTEGRATION") != "1" or not get_settings().gnani_configured,
        reason="Real Gnani tests need GNANI_API_KEY and RUN_GNANI_INTEGRATION=1",
    ),
]

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "audio"


@pytest.fixture
def m204(db, site):
    e = Equipment(equipment_code="M-204", name="Hydraulic Press Main Motor", category=EquipmentCategory.MECHANICAL,
                  site_id=site.id, is_critical=True)
    db.add(e)
    db.flush()
    return e


def technician(make_user, db, language):
    u = make_user(UserRole.TECHNICIAN)
    u.preferred_language = language
    db.flush()
    return u


def test_demo_scenario_real_prisma_and_timbre(client, db, m204, make_user, auth_headers):
    tech = technician(make_user, db, LanguageCode.HINGLISH)
    r = client.post("/api/v1/voice/process-report", headers=auth_headers(tech),
                    files={"audio": ("report.mp3", (FIXTURES / "hinglish_m204.mp3").read_bytes(), "audio/mpeg")})
    assert r.status_code == 200, r.text
    o = r.json()
    print("\nTranscript:", o["original_transcript"], "\nResponse:", o["response"]["text"])
    assert o["utterances"][0]["gnani_request_id"]
    assert o["equipment"]["equipment"]["id"] == str(m204.id)
    assert o["category"]["value"] == "mechanical"
    assert {"bearing_vibration", "abnormal_pressure"} <= {s["key"] for s in o["symptoms"]}
    assert o["draft"]["production_impact"] == "running"
    assert o["priority"]["level"] == "high"
    assert o["next_action"] == "confirm_preview"
    assert o["response"]["tts_available"] is True
    assert detect_format(base64.b64decode(o["response"]["audio_base64"])) == "mp3"


def test_telugu_spoken_number_code_real(client, db, m204, make_user, auth_headers):
    """Prisma keeps Telugu number words ("ఎం రెండు వందల నాలుగు"); the extractor must still find M-204."""
    spoken = TimbreClient().synthesize("మెషిన్ ఎం రెండు వందల నాలుగు లో వైబ్రేషన్ వస్తోంది.", language="te")
    tech = technician(make_user, db, LanguageCode.TE)
    o = client.post("/api/v1/voice/process-report", headers=auth_headers(tech),
                    files={"audio": ("te.mp3", spoken.audio, "audio/mpeg")}).json()
    print("\nTelugu transcript:", o["original_transcript"], "\nFollow-up:", o["response"]["text"])
    assert o["equipment"]["status"] == "matched"
    assert o["next_action"] == "ask_follow_up" and o["follow_up"]["field"] == "production_impact"

    answer = TimbreClient().synthesize("అవును, ప్రొడక్షన్ నడుస్తోంది.", language="te")
    import json

    r = client.post("/api/v1/voice/follow-up", headers=auth_headers(tech),
                    data={"evidence_token": o["evidence_token"], "draft": json.dumps(o["draft"]),
                          "field": "production_impact", "speak": "false"},
                    files={"audio": ("a.mp3", answer.audio, "audio/mpeg")})
    o2 = r.json()
    print("Answer transcript:", o2["transcript"])
    assert o2["draft"]["production_impact"] == "running"
    assert o2["next_action"] == "confirm_preview"
