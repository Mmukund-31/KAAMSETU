import base64
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response

from app.config import get_settings
from app.core.deps import CurrentUser, DbSession
from app.core.rate_limit import rate_limit
from app.gnani.prisma import PrismaClient
from app.gnani.timbre import TimbreClient
from app.schemas.common import ErrorResponse
from app.schemas.voice import SynthesisOut, SynthesizeRequest, TranscribeLanguage, TranscriptionOut
from app.services import speech

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
    responses={200: {"content": {"audio/mpeg": {}, "application/json": {"model": SynthesisOut}}}, **_ERRORS},
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
