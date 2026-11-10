"""Voice API tests with fake Gnani clients (no network). Real-API tests live in tests/integration."""

import base64
from pathlib import Path

import pytest

from app.gnani.errors import (
    GnaniAuthError,
    GnaniBadRequest,
    GnaniCreditError,
    GnaniNotConfigured,
    GnaniRateLimited,
    GnaniUnavailable,
)
from app.gnani.prisma import TranscriptionResult
from app.gnani.timbre import SynthesisResult
from app.main import app
from app.models import Equipment, EquipmentCategory, LanguageCode, Site, UserRole
from app.services import speech

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "audio"
TRANSCRIBE = "/api/v1/voice/transcribe"
SYNTH = "/api/v1/voice/synthesize"


class FakePrisma:
    def __init__(self, transcript="machine number M204 hai", error=None):
        self.transcript, self.error, self.calls = transcript, error, []

    def transcribe(self, audio, filename, *, language=None, keyterms=None, **_):
        self.calls.append({"filename": filename, "language": language, "keyterms": keyterms, "size": len(audio)})
        if self.error:
            raise self.error
        return TranscriptionResult(self.transcript, "prisma-v3.0", "en-IN", "en-IN", "req-1", 0.4, 0.5, False)


class FakeTimbre:
    def __init__(self, error=None):
        self.error, self.calls = error, []

    def synthesize(self, text, *, language, speed=None, **_):
        self.calls.append({"text": text, "language": language, "speed": speed})
        if self.error:
            raise self.error
        return SynthesisResult(b"ID3fake", "audio/mpeg", "mp3", "Poorvi", "hi-en", "timbre-v2.5", "tts-1")


@pytest.fixture
def fake_prisma():
    fake = FakePrisma()
    app.dependency_overrides[speech.get_prisma_client] = lambda: fake
    yield fake
    app.dependency_overrides.pop(speech.get_prisma_client, None)


@pytest.fixture
def fake_timbre():
    fake = FakeTimbre()
    app.dependency_overrides[speech.get_timbre_client] = lambda: fake
    yield fake
    app.dependency_overrides.pop(speech.get_timbre_client, None)


@pytest.fixture
def tech(make_user, db):
    user = make_user(UserRole.TECHNICIAN)
    user.preferred_language = LanguageCode.HINGLISH
    db.flush()
    return user


def upload(name="hinglish_m204.mp3", content=None):
    data = content if content is not None else (FIXTURES / name).read_bytes()
    return {"audio": (name, data, "application/octet-stream")}


# ── transcribe ───────────────────────────────────────────────────────────

def test_transcribe_happy_path(client, tech, auth_headers, fake_prisma, db, site):
    db.add_all([Equipment(equipment_code=c, name=c, category=EquipmentCategory.MECHANICAL, site_id=site.id)
                for c in ("M-204", "H-401")])
    other = Site(name="Elsewhere")
    db.add(other)
    db.flush()
    db.add(Equipment(equipment_code="Z-999", name="z", category=EquipmentCategory.OTHER, site_id=other.id))
    db.flush()

    r = client.post(TRANSCRIBE, files=upload(), headers=auth_headers(tech))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["transcript"] == "machine number M204 hai"
    assert body["gnani_request_id"] == "req-1"
    assert body["audio_format"] == "mp3"
    assert 1 < body["audio_duration_s"] < 15

    call = fake_prisma.calls[0]
    assert call["language"] == "hinglish"  # defaults to the user's preferred language
    assert call["keyterms"] == ["H-401", "M-204"]  # only this site's equipment
    assert call["filename"] == "audio.mp3"


def test_transcribe_explicit_and_auto_language(client, tech, auth_headers, fake_prisma):
    client.post(TRANSCRIBE, files=upload(), data={"language": "te"}, headers=auth_headers(tech))
    client.post(TRANSCRIBE, files=upload(), data={"language": "auto"}, headers=auth_headers(tech))
    assert [c["language"] for c in fake_prisma.calls] == ["te", None]


def test_transcribe_rejects_unknown_language(client, tech, auth_headers, fake_prisma):
    r = client.post(TRANSCRIBE, files=upload(), data={"language": "fr"}, headers=auth_headers(tech))
    assert r.status_code == 422
    assert fake_prisma.calls == []


def test_transcribe_requires_auth(client, fake_prisma):
    assert client.post(TRANSCRIBE, files=upload()).status_code == 401
    assert fake_prisma.calls == []


def test_transcribe_trusts_content_not_filename(client, tech, auth_headers, fake_prisma):
    r = client.post(TRANSCRIBE, files=upload(name="looks-like.wav",
                                             content=(FIXTURES / "hinglish_m204.ogg").read_bytes()),
                    headers=auth_headers(tech))
    assert r.status_code == 200
    assert fake_prisma.calls[0]["filename"] == "audio.ogg"


@pytest.mark.parametrize("content, status, code", [
    (b"", 422, "empty_audio"),
    (b"MZ\x90\x00 this is not audio", 415, "unsupported_audio_format"),
])
def test_transcribe_rejects_bad_uploads_without_calling_gnani(client, tech, auth_headers, fake_prisma,
                                                              content, status, code):
    r = client.post(TRANSCRIBE, files=upload(name="x.mp3", content=content), headers=auth_headers(tech))
    assert r.status_code == status
    assert r.json()["error"]["code"] == code
    assert fake_prisma.calls == []


def test_transcribe_rejects_oversize_upload(client, tech, auth_headers, fake_prisma, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "max_audio_upload_mb", 1)
    r = client.post(TRANSCRIBE, files=upload(content=b"ID3" + b"\x00" * (1024 * 1024 + 10)),
                    headers=auth_headers(tech))
    assert r.status_code == 413
    assert fake_prisma.calls == []


def test_empty_transcript_reported_as_no_speech(client, tech, auth_headers, fake_prisma):
    fake_prisma.transcript = ""
    r = client.post(TRANSCRIBE, files=upload(), headers=auth_headers(tech))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "no_speech_detected"
    assert r.json()["error"]["details"]["gnani_request_id"] == "req-1"


@pytest.mark.parametrize("error, status, code", [
    (GnaniRateLimited("busy", status_code=429), 503, "speech_rate_limited"),
    (GnaniAuthError("bad key", status_code=401, gnani_code="INVALID_API_KEY"), 502, "speech_auth_failed"),
    (GnaniCreditError("no credit", status_code=402), 502, "speech_credit_exhausted"),
    (GnaniBadRequest("bad audio", status_code=400, gnani_code="AUDIO_CONVERSION_ERROR"), 422,
     "speech_request_rejected"),
    (GnaniUnavailable("down", status_code=503), 503, "speech_unavailable"),
    (GnaniNotConfigured("no key"), 503, "speech_not_configured"),
])
def test_gnani_errors_are_mapped_honestly(client, tech, auth_headers, fake_prisma, error, status, code):
    fake_prisma.error = error
    r = client.post(TRANSCRIBE, files=upload(), headers=auth_headers(tech))
    assert r.status_code == status
    assert r.json()["error"]["code"] == code
    assert "transcript" not in r.json()
    assert "bad key" not in r.text  # upstream auth detail is not shown to end users


def test_rate_limited_response_has_retry_after(client, tech, auth_headers, fake_prisma):
    fake_prisma.error = GnaniRateLimited("busy")
    r = client.post(TRANSCRIBE, files=upload(), headers=auth_headers(tech))
    assert r.headers["Retry-After"] == "2"


# ── synthesize ───────────────────────────────────────────────────────────

def test_synthesize_returns_audio(client, tech, auth_headers, fake_timbre):
    r = client.post(SYNTH, json={"text": "Request submit ho gayi hai.", "language": "hinglish"},
                    headers=auth_headers(tech))
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg"
    assert r.content == b"ID3fake"
    assert r.headers["X-Voice"] == "Poorvi"
    assert r.headers["X-Gnani-Request-ID"] == "tts-1"


def test_synthesize_base64_for_mobile(client, tech, auth_headers, fake_timbre):
    r = client.post(SYNTH + "?as_base64=true", json={"text": "Hello", "language": "en", "speed": 0.9},
                    headers=auth_headers(tech))
    body = r.json()
    assert base64.b64decode(body["audio_base64"]) == b"ID3fake"
    assert body["content_type"] == "audio/mpeg"
    assert fake_timbre.calls[0] == {"text": "Hello", "language": "en", "speed": 0.9}


@pytest.mark.parametrize("payload", [
    {"text": "", "language": "en"},
    {"text": "x" * 501, "language": "en"},
    {"text": "ok", "language": "fr"},
    {"text": "ok", "language": "en", "speed": 3},
])
def test_synthesize_validation(client, tech, auth_headers, fake_timbre, payload):
    assert client.post(SYNTH, json=payload, headers=auth_headers(tech)).status_code == 422
    assert fake_timbre.calls == []


def test_synthesize_failure_is_reported_not_faked(client, tech, auth_headers, fake_timbre):
    fake_timbre.error = GnaniUnavailable("down")
    r = client.post(SYNTH, json={"text": "Hello", "language": "en"}, headers=auth_headers(tech))
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "speech_unavailable"
    assert r.headers["content-type"].startswith("application/json")


def test_synthesize_requires_auth(client, fake_timbre):
    assert client.post(SYNTH, json={"text": "Hello", "language": "en"}).status_code == 401


def test_voice_endpoints_rate_limited(client, tech, auth_headers, fake_timbre, monkeypatch):
    from app.config import get_settings
    from app.core.rate_limit import limiter

    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    monkeypatch.setattr(get_settings(), "rate_limit_voice_per_minute", 2)
    limiter.reset()
    codes = [client.post(SYNTH, json={"text": "Hi", "language": "en"}, headers=auth_headers(tech)).status_code
             for _ in range(3)]
    assert codes == [200, 200, 429]
