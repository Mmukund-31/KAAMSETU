"""Signed report evidence.

Between recording and submission the draft lives on the technician's device. The original
transcript, every correction and every follow-up answer travel with it in a signed token, so
the server can later store exactly what Prisma returned (immutable evidence, Phase 4) even
though the draft fields themselves are editable by the technician.

The token is an HS256 JWT signed with the server secret, bound to one user, valid for 2 hours.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt
from pydantic import BaseModel, Field

from app.config import get_settings
from app.core.errors import Forbidden, Unprocessable
from app.intelligence.config_loader import workflow_policy

TOKEN_TYPE = "report_evidence"
TOKEN_TTL = timedelta(hours=2)
MAX_TEXT = 2000

UtteranceKind = Literal["voice", "text", "correction", "follow_up_voice", "follow_up_text"]


class Utterance(BaseModel):
    kind: UtteranceKind
    text: str = Field(max_length=MAX_TEXT)
    field: str | None = Field(default=None, description="Follow-up question this answers")
    gnani_request_id: str | None = None
    model: str | None = None
    language_requested: str | None = None
    detected_language: str | None = None
    at: datetime


class Evidence(BaseModel):
    report_id: uuid.UUID
    user_id: uuid.UUID
    language: str
    utterances: list[Utterance]

    @property
    def original(self) -> Utterance:
        return self.utterances[0]

    @property
    def report_text(self) -> str:
        """The latest correction of the main report, or the original if never corrected."""
        main = [u for u in self.utterances if u.kind in ("voice", "text", "correction")]
        return main[-1].text

    @property
    def answered_fields(self) -> set[str]:
        return {u.field for u in self.utterances if u.field}

    def with_utterance(self, utterance: Utterance) -> "Evidence":
        if len(self.utterances) >= workflow_policy().max_utterances:
            raise Unprocessable("This report has too many corrections and answers. Please start a new report.",
                                code="too_many_utterances")
        return self.model_copy(update={"utterances": [*self.utterances, utterance]})


def new_utterance(kind: UtteranceKind, text: str, **kw) -> Utterance:
    return Utterance(kind=kind, text=text.strip()[:MAX_TEXT], at=datetime.now(UTC), **kw)


def start(user_id: uuid.UUID, language: str, first: Utterance) -> Evidence:
    return Evidence(report_id=uuid.uuid4(), user_id=user_id, language=language, utterances=[first])


def sign(evidence: Evidence) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "type": TOKEN_TYPE,
        "sub": str(evidence.user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + TOKEN_TTL).timestamp()),
        "ev": evidence.model_dump(mode="json"),
    }
    return jwt.encode(payload, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm)


def verify(token: str, user_id: uuid.UUID) -> Evidence:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key.get_secret_value(),
                             algorithms=[settings.jwt_algorithm], options={"require": ["exp", "sub", "type"]})
    except jwt.ExpiredSignatureError as exc:
        raise Unprocessable("This report draft has expired. Please record it again.",
                            code="evidence_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise Unprocessable("Report evidence is invalid or was modified.", code="evidence_invalid") from exc
    if payload.get("type") != TOKEN_TYPE:
        raise Unprocessable("Report evidence is invalid or was modified.", code="evidence_invalid")
    if payload["sub"] != str(user_id):
        raise Forbidden("This report draft belongs to another user.", code="evidence_wrong_user")
    return Evidence.model_validate(payload["ev"])
