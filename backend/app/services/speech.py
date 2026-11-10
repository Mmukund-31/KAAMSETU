"""Speech service: the only place the API layer talks to the Gnani adapters.

Maps Gnani failures to user-facing API errors. The technician sees a clear, honest message;
it never pretends speech was recognised or synthesised.
"""

import logging
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, Unprocessable
from app.gnani.base import GnaniHttp
from app.gnani.errors import (
    GnaniAuthError,
    GnaniBadRequest,
    GnaniCreditError,
    GnaniError,
    GnaniNotConfigured,
    GnaniRateLimited,
)
from app.gnani.prisma import MAX_KEYTERMS, PrismaClient, TranscriptionResult
from app.gnani.timbre import SynthesisResult, TimbreClient
from app.models import Equipment, User
from app.services.audio import AudioInfo, validate_audio

logger = logging.getLogger("kaamsetu.speech")


@lru_cache
def _shared_http() -> GnaniHttp:
    return GnaniHttp()


def get_prisma_client() -> PrismaClient:
    return PrismaClient(_shared_http())


def get_timbre_client() -> TimbreClient:
    return TimbreClient(_shared_http())


def to_app_error(exc: GnaniError) -> AppError:
    details = {"gnani_request_id": exc.request_id} if exc.request_id else {}
    if isinstance(exc, GnaniNotConfigured):
        return AppError("Voice service is not configured. Use text input.", code=exc.code, status_code=503)
    if isinstance(exc, GnaniAuthError | GnaniCreditError):
        # Operator problem (key or credit). Keep the message generic for users; the code tells admins what to fix.
        return AppError("Voice service is unavailable right now. Use text input.", code=exc.code,
                        status_code=502, details=details)
    if isinstance(exc, GnaniRateLimited):
        return AppError("Voice service is busy. Please try again in a moment.", code=exc.code, status_code=503,
                        details=details, headers={"Retry-After": "2"})
    if isinstance(exc, GnaniBadRequest):
        if exc.gnani_code:
            details["gnani_code"] = exc.gnani_code
        return Unprocessable(f"The voice service could not process this request: {exc.message}",
                             code=exc.code, details=details)
    return AppError("Voice service is temporarily unavailable. Use text input or try again.",
                    code=exc.code, status_code=503, details=details)


def site_keyterms(db: Session, user: User) -> list[str]:
    """Registered equipment codes at the user's site, passed to Prisma to bias recognition of IDs."""
    query = select(Equipment.equipment_code).order_by(Equipment.equipment_code).limit(MAX_KEYTERMS)
    if user.site_id is not None:
        query = query.where(Equipment.site_id == user.site_id)
    return list(db.scalars(query))


def resolve_language(requested: str | None, user: User) -> str | None:
    """None -> the user's preferred language. 'auto' -> Prisma auto-detect (returned as None)."""
    if requested == "auto":
        return None
    return requested or user.preferred_language.value


def transcribe_upload(
    db: Session, user: User, prisma: PrismaClient, data: bytes, language: str | None
) -> tuple[TranscriptionResult, AudioInfo]:
    info = validate_audio(data)
    try:
        result = prisma.transcribe(
            data, info.filename, language=resolve_language(language, user), keyterms=site_keyterms(db, user)
        )
    except GnaniError as exc:
        logger.warning("Transcription failed", extra={"ctx": {"error": str(exc), "user_id": str(user.id)}})
        raise to_app_error(exc) from exc
    if not result.transcript:
        # Prisma returns success with an empty transcript for silence (verified); report it honestly.
        raise Unprocessable(
            "No speech was detected. Please speak clearly and try again.",
            code="no_speech_detected",
            details={"gnani_request_id": result.request_id} if result.request_id else {},
        )
    return result, info


def synthesize(timbre: TimbreClient, text: str, language: str, speed: float | None) -> SynthesisResult:
    try:
        return timbre.synthesize(text, language=language, speed=speed)
    except GnaniError as exc:
        logger.warning("Synthesis failed", extra={"ctx": {"error": str(exc)}})
        raise to_app_error(exc) from exc


def spoken(timbre: TimbreClient | None, text: str, language: str):
    """Text response, plus Timbre audio when requested. A TTS failure never fails the action."""
    import base64

    from app.schemas.report import SpokenResponse

    response = SpokenResponse(text=text)
    if timbre is None:
        return response
    try:
        result = synthesize(timbre, text[:500], language, None)
    except AppError as exc:
        response.tts_available, response.tts_error = False, exc.code
        return response
    response.tts_available = True
    response.audio_base64 = base64.b64encode(result.audio).decode("ascii")
    response.content_type, response.voice, response.gnani_request_id = result.content_type, result.voice, \
        result.request_id
    return response
