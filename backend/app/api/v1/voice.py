import base64
import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError

from app.config import get_settings
from app.core.deps import CurrentUser, DbSession
from app.core.errors import Unprocessable
from app.core.rate_limit import rate_limit
from app.gnani.prisma import PrismaClient
from app.gnani.timbre import TimbreClient
from app.intelligence.models import FollowUpField, ReportDraft
from app.schemas.common import ErrorResponse
from app.schemas.report import EvaluateDraftRequest, ProcessTextRequest, ReportOutcome
from app.schemas.voice import SynthesisOut, SynthesizeRequest, TranscribeLanguage, TranscriptionOut
from app.services import speech
from app.workflows import orchestrator

router = APIRouter(
    prefix="/voice",
    tags=["voice"],
    dependencies=[Depends(rate_limit("voice", lambda: get_settings().rate_limit_voice_per_minute))],
)

_ERRORS = {
    401: {"model": ErrorResponse}, 413: {"model": ErrorResponse}, 415: {"model": ErrorResponse},
    422: {"model": ErrorResponse}, 429: {"model": ErrorResponse}, 502: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


def _read_capped(upload: UploadFile) -> bytes:
    # Read one byte past the limit so oversize uploads are detected without loading unbounded data.
    return upload.file.read(get_settings().max_audio_upload_mb * 1024 * 1024 + 1)


@router.post("/transcribe", response_model=TranscriptionOut, responses=_ERRORS)
def transcribe(
    user: CurrentUser,
    db: DbSession,
    prisma: Annotated[PrismaClient, Depends(speech.get_prisma_client)],
    audio: Annotated[UploadFile, File(description="Recording up to 30 s: m4a, wav, mp3, ogg, flac or aac")],
    language: Annotated[TranscribeLanguage | None, Form(description="Defaults to the user's preferred language")] = None,
) -> TranscriptionOut:
    """Transcribe a recording with Gnani Prisma. Registered equipment codes are sent as recognition hints."""
    result, info = speech.transcribe_upload(db, user, prisma, _read_capped(audio), language)
    return TranscriptionOut(
        transcript=result.transcript,
        language_requested=result.language_code_requested,
        detected_language=result.detected_language,
        model=result.model,
        gnani_request_id=result.request_id,
        processing_time_s=result.processing_time_s,
        truncated=result.truncated,
        audio_format=info.format,
        audio_duration_s=round(info.duration_seconds, 2) if info.duration_seconds else None,
    )


@router.post(
    "/synthesize",
    # Default 200 is audio/mpeg; with ?as_base64=true the body is SynthesisOut JSON.
    responses={200: {"model": SynthesisOut, "content": {"audio/mpeg": {}}}, **_ERRORS},
)
def synthesize(
    body: SynthesizeRequest,
    _: CurrentUser,
    timbre: Annotated[TimbreClient, Depends(speech.get_timbre_client)],
    as_base64: Annotated[bool, Query(description="Return JSON with base64 audio (for mobile clients)")] = False,
):
    """Speak short text with Gnani Timbre in the given language. Returns audio bytes, or JSON with ?as_base64=true."""
    result = speech.synthesize(timbre, body.text, body.language.value, body.speed)
    if as_base64:
        return SynthesisOut(
            audio_base64=base64.b64encode(result.audio).decode("ascii"),
            content_type=result.content_type,
            voice=result.voice,
            language_code=result.language_code,
            model=result.model,
            gnani_request_id=result.request_id,
        )
    headers = {"X-Voice": result.voice, "Cache-Control": "no-store"}
    if result.request_id:
        headers["X-Gnani-Request-ID"] = result.request_id
    return Response(content=result.audio, media_type=result.content_type, headers=headers)


# ── report pipeline (Phase 3) ────────────────────────────────────────────

Prisma = Annotated[PrismaClient, Depends(speech.get_prisma_client)]
Timbre = Annotated[TimbreClient, Depends(speech.get_timbre_client)]


@router.post("/process-report", response_model=ReportOutcome, responses=_ERRORS)
def process_report(
    user: CurrentUser,
    db: DbSession,
    prisma: Prisma,
    timbre: Timbre,
    audio: Annotated[UploadFile, File(description="Fault report recording, up to 30 s")],
    language: Annotated[TranscribeLanguage | None, Form()] = None,
    speak: Annotated[bool, Form(description="Also return the response spoken by Timbre")] = True,
) -> ReportOutcome:
    """Voice report -> Prisma transcript -> structured, registry-validated work-order preview.

    Nothing is saved. The technician reviews the preview, answers any follow-up question, then submits.
    """
    return orchestrator.process_voice(db, user, prisma, timbre if speak else None, _read_capped(audio), language)


@router.post("/process-text", response_model=ReportOutcome, responses=_ERRORS)
def process_text(body: ProcessTextRequest, user: CurrentUser, db: DbSession, timbre: Timbre) -> ReportOutcome:
    """Typed report (fallback when voice is unavailable), or a corrected transcript when evidence_token is sent.

    A correction keeps the original Prisma transcript in the evidence and re-extracts from the corrected text.
    """
    return orchestrator.process_text(db, user, timbre if body.speak else None, body.text, body.language,
                                     body.evidence_token)


@router.post("/follow-up", response_model=ReportOutcome, responses=_ERRORS)
def follow_up(
    user: CurrentUser,
    db: DbSession,
    prisma: Prisma,
    timbre: Timbre,
    evidence_token: Annotated[str, Form()],
    draft: Annotated[str, Form(description="Current ReportDraft as JSON")],
    field: Annotated[FollowUpField, Form(description="The field the question asked about")],
    answer_text: Annotated[str | None, Form(max_length=2000)] = None,
    audio: Annotated[UploadFile | None, File(description="Spoken answer (instead of answer_text)")] = None,
    speak: Annotated[bool, Form()] = True,
) -> ReportOutcome:
    """Answer the follow-up question by voice or text; returns the updated preview and the next question, if any."""
    try:
        parsed = ReportDraft.model_validate(json.loads(draft))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise Unprocessable("draft must be a valid ReportDraft JSON object", code="invalid_draft") from exc
    audio_bytes = _read_capped(audio) if audio is not None else None
    return orchestrator.follow_up(db, user, prisma, timbre if speak else None, evidence_token, parsed, field,
                                  answer_text, audio_bytes)


@router.post("/evaluate-draft", response_model=ReportOutcome, responses=_ERRORS)
def evaluate_draft(body: EvaluateDraftRequest, user: CurrentUser, db: DbSession, timbre: Timbre) -> ReportOutcome:
    """Re-validate a draft after manual edits in the preview, such as picking a machine from the suggestions."""
    return orchestrator.evaluate_draft(db, user, timbre if body.speak else None, body.evidence_token, body.draft)
