import json
import re

import httpx
import pytest

from app.gnani.errors import GnaniBadRequest, GnaniResponseError
from app.gnani.prisma import DEFAULT_TOPIC, PrismaClient, language_code_for
from app.tests.unit.gnani_fakes import (
    REAL_PRISMA_BODY,
    Recorder,
    fake_settings,
    json_response,
    make_http,
)


def form_fields(request: httpx.Request) -> dict[str, str]:
    """Parse simple text fields out of a multipart body."""
    body = request.content.decode("utf-8", errors="replace")
    return dict(re.findall(r'name="([^"]+)"\r\n\r\n(.*?)\r\n--', body, flags=re.S))


def client(rec: Recorder, **settings) -> PrismaClient:
    return PrismaClient(make_http(rec, **settings), fake_settings(**settings))


def test_transcribe_builds_documented_request_and_parses_real_response():
    rec = Recorder(json_response(200, REAL_PRISMA_BODY))
    result = client(rec).transcribe(b"ID3fakeaudio", "report.mp3", language="hinglish", keyterms=["M-204", "H-401"])

    req = rec.requests[0]
    assert req.method == "POST" and req.url.path == "/stt/v3"
    assert req.headers["content-type"].startswith("multipart/form-data")
    fields = form_fields(req)
    assert fields["model"] == "prisma-v3.0"
    assert fields["language_code"] == "en-IN"  # verified best Hinglish setting
    assert json.loads(fields["keyterms"]) == ["M-204", "H-401"]
    assert fields["topic"] == DEFAULT_TOPIC
    assert 'name="audio_file"; filename="audio.mp3"' in req.content.decode("latin-1")

    assert result.transcript.startswith("motor ka pressure abnormal hai")
    assert result.detected_language == "en-IN"
    assert result.request_id == REAL_PRISMA_BODY["request_id"]
    assert result.language_code_requested == "en-IN"
    assert result.truncated is False


@pytest.mark.parametrize("ui, expected", [("en", "en-IN"), ("hi", "hi-IN"), ("te", "te-IN"),
                                          ("hinglish", "en-IN"), (None, "indic-auto")])
def test_language_mapping(ui, expected):
    assert language_code_for(ui, fake_settings()) == expected


def test_unknown_language_rejected():
    with pytest.raises(ValueError):
        language_code_for("fr", fake_settings())


def test_keyterms_are_deduplicated_and_capped():
    rec = Recorder(json_response(200, REAL_PRISMA_BODY))
    terms = ["M-204", "M-204", " "] + [f"X-{i}" for i in range(300)]
    client(rec).transcribe(b"ID3x", "a.mp3", language="en", keyterms=terms)
    sent = json.loads(form_fields(rec.requests[0])["keyterms"])
    assert sent[0] == "M-204" and sent.count("M-204") == 1
    assert len(sent) == 200


def test_hinglish_format_setting_is_sent_only_when_configured():
    rec = Recorder(json_response(200, REAL_PRISMA_BODY))
    client(rec, gnani_prisma_hinglish_format="codemix").transcribe(b"ID3x", "a.mp3", language="hinglish")
    client(rec).transcribe(b"ID3x", "a.mp3", language="hinglish")
    assert form_fields(rec.requests[0])["format"] == "codemix"
    assert "format" not in form_fields(rec.requests[1])


def test_empty_transcript_is_returned_not_invented():
    # Real API behaviour for silence: success with an empty transcript and no model field.
    rec = Recorder(json_response(200, {"success": True, "request_id": "r1", "transcript": ""}))
    result = client(rec).transcribe(b"RIFFxxxxWAVE", "a.wav", language="hi")
    assert result.transcript == ""
    assert result.model == "prisma-v3.0"


@pytest.mark.parametrize("body", [{"success": False, "transcript": "x"}, {"success": True}, ["not", "a", "dict"]])
def test_contract_violations_raise_response_error(body):
    rec = Recorder(json_response(200, body))
    with pytest.raises(GnaniResponseError):
        client(rec).transcribe(b"ID3x", "a.mp3", language="en")


def test_non_json_response_raises_response_error():
    rec = Recorder(httpx.Response(200, text="<html>gateway</html>"))
    with pytest.raises(GnaniResponseError):
        client(rec).transcribe(b"ID3x", "a.mp3", language="en")


def test_empty_audio_and_bad_extension_rejected_before_network():
    rec = Recorder(json_response(200, REAL_PRISMA_BODY))
    c = client(rec)
    with pytest.raises(GnaniBadRequest):
        c.transcribe(b"", "a.mp3", language="en")
    with pytest.raises(GnaniBadRequest):
        c.transcribe(b"data", "a.exe", language="en")
    assert rec.requests == []
