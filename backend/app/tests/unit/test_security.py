import logging
import uuid

import jwt
import pytest

from app.core.logging import RedactingFilter, redact
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models import normalize_equipment_code


def test_password_hash_roundtrip():
    h = hash_password("Secret123")
    assert h.startswith("$argon2id$")
    assert verify_password("Secret123", h)
    assert not verify_password("secret123", h)


def test_verify_handles_missing_and_corrupt_hash():
    assert not verify_password("anything", None)
    assert not verify_password("anything", "not-a-hash")


def test_token_roundtrip():
    uid = uuid.uuid4()
    token, expires_at = create_access_token(uid, "supervisor")
    payload = decode_access_token(token)
    assert payload["sub"] == str(uid)
    assert payload["role"] == "supervisor"
    assert payload["type"] == "access"
    assert expires_at.tzinfo is not None


def test_tampered_token_rejected():
    token, _ = create_access_token(uuid.uuid4(), "technician")
    header, body, sig = token.split(".")
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(f"{header}.{body}.{sig[:-2]}xx")


@pytest.mark.parametrize(
    "raw, must_not_contain",
    [
        ("headers={'X-API-Key-ID': 'sk_live_abcdef123456'}", "sk_live_abcdef123456"),
        ("Authorization: Bearer abc.def.ghi", "abc.def.ghi"),
        ('{"password": "hunter2pass"}', "hunter2pass"),
        ("token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl", "eyJhbGciOiJIUzI1NiJ9"),
    ],
)
def test_redact_patterns(raw, must_not_contain):
    assert must_not_contain not in redact(raw)


def test_redact_configured_secret_anywhere():
    assert "my-gnani-key-123" not in redact("calling with my-gnani-key-123 now", secrets=("my-gnani-key-123",))


def test_redacting_filter_applies_to_args_and_ctx():
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "key=%s", ("SECRETVALUE99",), None)
    record.ctx = {"note": "SECRETVALUE99"}
    RedactingFilter(secrets=("SECRETVALUE99",)).filter(record)
    assert "SECRETVALUE99" not in record.getMessage()
    assert "SECRETVALUE99" not in str(record.ctx)


@pytest.mark.parametrize("raw", ["M-204", "m 204", "m204", " M-204 ", "M_204"])
def test_equipment_code_normalisation(raw):
    assert normalize_equipment_code(raw) == "M204"
