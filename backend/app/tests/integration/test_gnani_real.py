"""REAL Gnani API tests. These spend programme credits.

Skipped unless both are set:
    GNANI_API_KEY (backend/.env)  and  RUN_GNANI_INTEGRATION=1
Run:  $env:RUN_GNANI_INTEGRATION="1"; .venv\\Scripts\\python.exe -m pytest -m integration -v
The audio inputs are Timbre-generated synthetic speech (fixtures/audio), not human recordings.
"""

import os
import re
from pathlib import Path

import pytest

from app.config import get_settings
from app.gnani.base import GnaniHttp
from app.gnani.errors import GnaniAuthError, GnaniBadRequest
from app.gnani.prisma import PrismaClient
from app.gnani.timbre import TimbreClient
from app.main import app
from app.models import Equipment, EquipmentCategory, LanguageCode, UserRole
from app.services import speech
from app.services.audio import detect_format

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_GNANI_INTEGRATION") != "1" or not get_settings().gnani_configured,
        reason="Real Gnani tests need GNANI_API_KEY and RUN_GNANI_INTEGRATION=1",
    ),
]

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "audio"


@pytest.fixture(scope="module")
def http():
    h = GnaniHttp()
    yield h
    h.close()


@pytest.fixture(scope="module")
def prisma(http):
    return PrismaClient(http)


@pytest.fixture(scope="module")
def timbre(http):
    return TimbreClient(http)


def compact(text: str) -> str:
    return re.sub(r"[\s\-]", "", text).upper()


def test_prisma_transcribes_hinglish_demo_sentence(prisma):
    result = prisma.transcribe((FIXTURES / "hinglish_m204.mp3").read_bytes(), "a.mp3", language="hinglish",
                               keyterms=["M-204"])
    print("\nPrisma hinglish:", result.transcript, "| request_id:", result.request_id)
    assert result.request_id
    assert "M204" in compact(result.transcript)
    assert re.search(r"vibration|वाइब्रेशन", result.transcript, re.I)
    assert re.search(r"bearing|बेयरिंग", result.transcript, re.I)


def test_prisma_accepts_wav_with_streaming_header_and_ogg(prisma):
    wav = prisma.transcribe((FIXTURES / "hindi_m204_streaming_header.wav").read_bytes(), "a.wav", language="hi")
    ogg = prisma.transcribe((FIXTURES / "hinglish_m204.ogg").read_bytes(), "a.ogg", language="hinglish")
    assert wav.detected_language == "hi-IN" and "204" in wav.transcript
    assert ogg.transcript


def test_prisma_english(prisma):
    result = prisma.transcribe((FIXTURES / "english_h401.mp3").read_bytes(), "a.mp3", language="en")
    assert "H401" in compact(result.transcript)
    assert "oil" in result.transcript.lower()


@pytest.mark.parametrize("language, magic", [("en", "mp3"), ("hi", "mp3"), ("te", "mp3"), ("hinglish", "mp3")])
def test_timbre_speaks_every_language(timbre, language, magic):
    text = {"en": "Your request has been submitted for supervisor review.",
            "hi": "आपकी रिक्वेस्ट सुपरवाइज़र रिव्यू के लिए भेज दी गई है।",
            "te": "మీ అభ్యర్థన సూపర్వైజర్ సమీక్షకు పంపబడింది.",
            "hinglish": "Request supervisor review ke liye submit ho gayi hai."}[language]
    result = timbre.synthesize(text, language=language)
    assert result.content_type == "audio/mpeg"
    assert detect_format(result.audio) == magic
    assert len(result.audio) > 2000
    assert result.request_id


def test_round_trip_timbre_to_prisma(timbre, prisma):
    spoken = timbre.synthesize("Machine E-110 is tripping. Production has stopped.", language="en")
    heard = prisma.transcribe(spoken.audio, "a.mp3", language="en")
    print("\nRound trip:", heard.transcript)
    assert "E110" in compact(heard.transcript)
    assert "stop" in heard.transcript.lower()


def test_real_bad_voice_is_a_bad_request(http):
    settings = get_settings().model_copy(update={"gnani_timbre_voice_en": "NoSuchVoice"})
    with pytest.raises(GnaniBadRequest, match="not supported"):
        TimbreClient(http, settings).synthesize("hello", language="en")


def test_real_invalid_key_is_an_auth_error():
    from pydantic import SecretStr

    bad = GnaniHttp(get_settings().model_copy(update={"gnani_api_key": SecretStr("invalid-key-for-test")}))
    with pytest.raises(GnaniAuthError) as e:
        TimbreClient(bad).synthesize("hello", language="en")
    assert e.value.gnani_code == "INVALID_API_KEY"
    bad.close()


def test_transcribe_endpoint_end_to_end(client, db, site, make_user, auth_headers):
    """Full stack: HTTP upload -> validation -> real Prisma -> JSON, with site equipment as keyterms."""
    app.dependency_overrides.pop(speech.get_prisma_client, None)
    db.add(Equipment(equipment_code="M-204", name="Press motor", category=EquipmentCategory.MECHANICAL,
                     site_id=site.id))
    tech = make_user(UserRole.TECHNICIAN)
    tech.preferred_language = LanguageCode.HINGLISH
    db.flush()
    r = client.post("/api/v1/voice/transcribe", headers=auth_headers(tech),
                    files={"audio": ("r.mp3", (FIXTURES / "hinglish_m204.mp3").read_bytes(), "audio/mpeg")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["language_requested"] == "en-IN"
    assert body["gnani_request_id"]
    assert "M204" in compact(body["transcript"])


def test_synthesize_endpoint_end_to_end(client, make_user, auth_headers):
    tech = make_user(UserRole.TECHNICIAN)
    r = client.post("/api/v1/voice/synthesize", headers=auth_headers(tech),
                    json={"text": "M-204 ke liye request taiyaar hai.", "language": "hinglish"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg"
    assert r.headers["X-Voice"] == "Poorvi"
    assert detect_format(r.content) == "mp3"
