import logging

import httpx
import pytest
from pydantic import SecretStr

from app.gnani.base import GnaniHttp
from app.gnani.errors import (
    GnaniAuthError,
    GnaniBadRequest,
    GnaniCreditError,
    GnaniNotConfigured,
    GnaniRateLimited,
    GnaniUnavailable,
)
from app.tests.unit.gnani_fakes import TEST_KEY, Recorder, fake_settings, json_response, make_http

RATE_LIMITED = json_response(429, {"detail": {"error_code": "RATE_LIMITED", "message": "Only 1 active request is "
                                              "allowed at a time.", "status_code": 429}})


def test_sends_api_key_header_and_returns_success():
    rec = Recorder(json_response(200, {"ok": True}))
    resp = make_http(rec).request("GET", "/x", operation="t")
    assert resp.status_code == 200
    assert rec.requests[0].headers["X-API-Key-ID"] == TEST_KEY
    assert rec.requests[0].url.host == "api.vachana.ai"


def test_429_is_retried_with_backoff_then_succeeds():
    sleeps: list[float] = []
    rec = Recorder(RATE_LIMITED, json_response(200, {"ok": True}))
    resp = make_http(rec, sleeps).request("GET", "/x", operation="t")
    assert resp.status_code == 200
    assert len(rec.requests) == 2
    assert sleeps == [0.5]


def test_persistent_429_raises_rate_limited_after_all_attempts():
    sleeps: list[float] = []
    rec = Recorder(RATE_LIMITED)
    with pytest.raises(GnaniRateLimited) as e:
        make_http(rec, sleeps).request("GET", "/x", operation="t")
    assert len(rec.requests) == 4  # 1 + 3 retries
    assert sleeps == [0.5, 1.0, 2.0]
    assert e.value.gnani_code == "RATE_LIMITED"


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_server_errors_are_retried(status):
    rec = Recorder(json_response(status, {"success": False, "message": "boom"}), json_response(200, {}))
    assert make_http(rec).request("GET", "/x", operation="t").status_code == 200
    assert len(rec.requests) == 2


def test_501_is_not_retried():
    rec = Recorder(json_response(501, {"message": "nope"}))
    with pytest.raises(GnaniUnavailable):
        make_http(rec).request("GET", "/x", operation="t")
    assert len(rec.requests) == 1


def test_timeout_is_retried_then_reported_unavailable():
    rec = Recorder(httpx.ReadTimeout("slow"))
    with pytest.raises(GnaniUnavailable, match="timed out"):
        make_http(rec, gnani_max_retries=1).request("GET", "/x", operation="t")
    assert len(rec.requests) == 2


def test_connection_error_reported_unavailable():
    rec = Recorder(httpx.ConnectError("dns"))
    with pytest.raises(GnaniUnavailable, match="Could not reach"):
        make_http(rec, gnani_max_retries=0).request("GET", "/x", operation="t")


def test_invalid_key_maps_to_auth_error_without_retry():
    # Exact body returned by the real API for an invalid key (2026-11-10).
    rec = Recorder(json_response(401, {"detail": {"error_code": "INVALID_API_KEY", "message": "Unauthorized",
                                                  "status_code": 401}}))
    with pytest.raises(GnaniAuthError) as e:
        make_http(rec).request("GET", "/x", operation="t")
    assert e.value.gnani_code == "INVALID_API_KEY"
    assert len(rec.requests) == 1


def test_scope_not_allowed_maps_to_auth_error():
    rec = Recorder(json_response(403, {"detail": {"error_code": "SCOPE_NOT_ALLOWED", "message": "Service 'STT' "
                                                  "not in allowed scopes", "status_code": 403}}))
    with pytest.raises(GnaniAuthError):
        make_http(rec).request("GET", "/x", operation="t")


def test_insufficient_credit_maps_to_credit_error():
    rec = Recorder(json_response(402, {"detail": {"error_code": "INSUFFICIENT_CREDIT", "message": "Insufficient "
                                                  "credit", "status_code": 402}}))
    with pytest.raises(GnaniCreditError):
        make_http(rec).request("GET", "/x", operation="t")
    assert len(rec.requests) == 1


def test_tts_error_envelope_message_is_preserved():
    rec = Recorder(json_response(400, {"success": False, "message": "Voice 'X' is not supported by model "
                                                                    "'timbre-v2.5'", "status_code": 400}))
    with pytest.raises(GnaniBadRequest, match="Voice 'X' is not supported"):
        make_http(rec).request("GET", "/x", operation="t")


def test_stt_error_envelope_type_is_preserved():
    rec = Recorder(json_response(400, {"success": False, "error": {"type": "UNSUPPORTED_AUDIO_FORMAT",
                                                                    "message": "bad"}}))
    with pytest.raises(GnaniBadRequest) as e:
        make_http(rec).request("GET", "/x", operation="t")
    assert e.value.gnani_code == "UNSUPPORTED_AUDIO_FORMAT"


def test_validation_422_list_is_mapped():
    # Exact shape returned by the real API when language_code is missing.
    rec = Recorder(json_response(422, {"detail": [{"type": "missing", "loc": ["body", "language_code"],
                                                   "msg": "Field required", "input": None}]}))
    with pytest.raises(GnaniBadRequest) as e:
        make_http(rec).request("GET", "/x", operation="t")
    assert e.value.gnani_code == "VALIDATION_ERROR"
    assert "Field required" in e.value.message


def test_missing_key_fails_before_any_network_call():
    rec = Recorder(json_response(200, {}))
    http = GnaniHttp(fake_settings(gnani_api_key=SecretStr("  ")), transport=httpx.MockTransport(rec))
    with pytest.raises(GnaniNotConfigured):
        http.request("GET", "/x", operation="t")
    assert rec.requests == []


def test_request_id_header_is_captured_on_errors():
    rec = Recorder(json_response(400, {"message": "bad"}, headers={"x-api-request-id": "req-123"}))
    with pytest.raises(GnaniBadRequest) as e:
        make_http(rec).request("GET", "/x", operation="t")
    assert e.value.request_id == "req-123"


def test_logs_never_contain_the_api_key(caplog):
    caplog.set_level(logging.DEBUG)
    rec = Recorder(RATE_LIMITED, json_response(200, {}))
    make_http(rec).request("GET", "/x", operation="t")
    for record in caplog.records:
        assert TEST_KEY not in record.getMessage()
        assert TEST_KEY not in str(getattr(record, "ctx", ""))
