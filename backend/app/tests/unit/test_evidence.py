import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.config import get_settings
from app.core.errors import AppError
from app.workflows import evidence as ev


def sample(user_id=None) -> ev.Evidence:
    return ev.start(user_id or uuid.uuid4(), "hinglish",
                    ev.new_utterance("voice", "M-204 mein vibration", gnani_request_id="req-1", model="prisma-v3.0"))


def test_round_trip_preserves_original_transcript():
    e = sample()
    back = ev.verify(ev.sign(e), e.user_id)
    assert back == e
    assert back.original.text == "M-204 mein vibration" and back.original.gnani_request_id == "req-1"


def test_report_text_prefers_latest_correction_but_keeps_original():
    e = sample().with_utterance(ev.new_utterance("correction", "M-204 mein bearing vibration"))
    e = e.with_utterance(ev.new_utterance("follow_up_text", "haan", field="production_impact"))
    assert e.report_text == "M-204 mein bearing vibration"
    assert e.original.text == "M-204 mein vibration"
    assert e.answered_fields == {"production_impact"}


def test_tampered_token_rejected():
    token = ev.sign(sample())
    head, body, sig = token.split(".")
    with pytest.raises(AppError) as exc:
        ev.verify(f"{head}.{body}x.{sig}", uuid.uuid4())
    assert exc.value.code == "evidence_invalid"


def test_forged_transcript_with_other_secret_rejected():
    e = sample()
    forged = jwt.encode({"type": "report_evidence", "sub": str(e.user_id), "iat": 0, "exp": 9999999999,
                         "ev": e.model_dump(mode="json")}, "x" * 40, algorithm="HS256")
    with pytest.raises(AppError) as exc:
        ev.verify(forged, e.user_id)
    assert exc.value.code == "evidence_invalid"


def test_token_bound_to_user():
    e = sample()
    with pytest.raises(AppError) as exc:
        ev.verify(ev.sign(e), uuid.uuid4())
    assert exc.value.status_code == 403 and exc.value.code == "evidence_wrong_user"


def test_access_token_is_not_accepted_as_evidence():
    from app.core.security import create_access_token

    uid = uuid.uuid4()
    access, _ = create_access_token(uid, "technician")
    with pytest.raises(AppError) as exc:
        ev.verify(access, uid)
    assert exc.value.code == "evidence_invalid"


def test_expired_evidence():
    e = sample()
    s = get_settings()
    old = jwt.encode({"type": "report_evidence", "sub": str(e.user_id),
                      "iat": int((datetime.now(UTC) - timedelta(hours=3)).timestamp()),
                      "exp": int((datetime.now(UTC) - timedelta(hours=1)).timestamp()),
                      "ev": e.model_dump(mode="json")}, s.jwt_secret_key.get_secret_value(), algorithm="HS256")
    with pytest.raises(AppError) as exc:
        ev.verify(old, e.user_id)
    assert exc.value.code == "evidence_expired"


def test_utterance_limit():
    e = sample()
    for _ in range(7):
        e = e.with_utterance(ev.new_utterance("follow_up_text", "haan", field="production_impact"))
    with pytest.raises(AppError) as exc:
        e.with_utterance(ev.new_utterance("follow_up_text", "haan"))
    assert exc.value.code == "too_many_utterances"
