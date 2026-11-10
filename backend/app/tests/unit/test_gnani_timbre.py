import json

import httpx
import pytest

from app.gnani.errors import GnaniBadRequest, GnaniResponseError
from app.gnani.timbre import MAX_TEXT_CHARS, TimbreClient, voice_for
from app.tests.unit.gnani_fakes import Recorder, fake_settings, make_http

MP3 = httpx.Response(200, content=b"ID3\x04fake-mp3", headers={"content-type": "audio/mpeg",
                                                                "x-api-request-id": "tts-req-1"})


def client(rec: Recorder, **settings) -> TimbreClient:
    return TimbreClient(make_http(rec, **settings), fake_settings(**settings))


def test_synthesize_builds_documented_body_and_returns_audio():
    rec = Recorder(MP3)
    result = client(rec).synthesize("  M-204 ke liye   request taiyaar hai. ", language="hinglish")

    req = rec.requests[0]
    assert req.url.path == "/api/v1/tts/inference"
    body = json.loads(req.content)
    assert body["text"] == "M-204 ke liye request taiyaar hai."  # whitespace normalised
    assert body["model"] == "timbre-v2.5"
    assert body["voice"] == "Poorvi" and body["language"] == "hi-en"
    assert body["audio_config"] == {"sample_rate": 24000, "num_channels": 1, "sample_width": 2,
                                    "container": "mp3", "bitrate": "64k"}
    assert "speed" not in body

    assert result.audio.startswith(b"ID3")
    assert result.content_type == "audio/mpeg"
    assert result.request_id == "tts-req-1"


@pytest.mark.parametrize("ui, lang, voice", [("en", "en-IN", "Kaveri"), ("hi", "hi-IN", "Nalini"),
                                             ("te", "te-IN", "Suhana"), ("hinglish", "hi-en", "Poorvi")])
def test_voice_per_language(ui, lang, voice):
    assert voice_for(ui, fake_settings()) == (lang, voice)


@pytest.mark.parametrize("requested, sent", [(0.5, 0.85), (2.0, 1.15), (0.9, 0.9)])
def test_speed_is_clamped_to_documented_range(requested, sent):
    rec = Recorder(MP3)
    client(rec).synthesize("hello", language="en", speed=requested)
    assert json.loads(rec.requests[0].content)["speed"] == sent


def test_wav_container_uses_linear_pcm():
    rec = Recorder(httpx.Response(200, content=b"RIFF....WAVE", headers={"content-type": "audio/wav"}))
    client(rec).synthesize("hello", language="en", container="wav")
    assert json.loads(rec.requests[0].content)["audio_config"]["encoding"] == "linear_pcm"


def test_json_instead_of_audio_is_a_contract_violation():
    rec = Recorder(httpx.Response(200, json={"success": True}))
    with pytest.raises(GnaniResponseError):
        client(rec).synthesize("hello", language="en")


def test_empty_body_is_a_contract_violation():
    rec = Recorder(httpx.Response(200, content=b"", headers={"content-type": "audio/mpeg"}))
    with pytest.raises(GnaniResponseError):
        client(rec).synthesize("hello", language="en")


def test_invalid_text_rejected_before_network():
    rec = Recorder(MP3)
    c = client(rec)
    with pytest.raises(GnaniBadRequest):
        c.synthesize("   ", language="en")
    with pytest.raises(GnaniBadRequest):
        c.synthesize("x" * (MAX_TEXT_CHARS + 1), language="en")
    with pytest.raises(GnaniBadRequest):
        c.synthesize("hi", language="en", container="flac")
    assert rec.requests == []


def test_unsupported_language():
    with pytest.raises(ValueError):
        voice_for("fr", fake_settings())
