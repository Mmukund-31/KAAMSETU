"""Gnani Prisma speech-to-text adapter.

Contract (docs.gnani.ai, verified with real requests on 2026-11-10):
  POST /stt/v3, multipart/form-data
    audio_file     file (WAV, MP3, OGG, FLAC, AAC, M4A; format detected from the filename extension)
    language_code  e.g. hi-IN | en-IN | te-IN | "hi-IN,en-IN" (hints) | indic-auto
    model          prisma-v3.0
    format         verbatim (default) | transcribe | codemix | transliterate   (v3.0)
    keyterms       JSON array, up to 200 terms to bias recognition            (v3.0)
    topic          free-text context, up to 1600 chars                        (v3.0)
  200 -> {"success": true, "request_id", "transcript", "model", "detected_language_code",
          "processing_time", "end_to_end_latency", "truncated"?}
Clips are limited to 30 seconds on this endpoint.
"""

import json
import logging
from dataclasses import dataclass

from app.config import Settings, get_settings
from app.gnani.base import GnaniHttp
from app.gnani.errors import GnaniBadRequest, GnaniResponseError

logger = logging.getLogger("kaamsetu.gnani")

STT_PATH = "/stt/v3"
MAX_KEYTERMS = 200
MAX_TOPIC_CHARS = 1600
DEFAULT_TOPIC = "Factory maintenance fault report about a machine, its equipment code and symptoms"

_MIME_BY_EXT = {
    "wav": "audio/wav", "mp3": "audio/mpeg", "ogg": "audio/ogg", "flac": "audio/flac",
    "aac": "audio/aac", "m4a": "audio/mp4",
}


@dataclass(frozen=True)
class TranscriptionResult:
    transcript: str
    model: str
    language_code_requested: str
    detected_language: str | None
    request_id: str | None
    processing_time_s: float | None
    end_to_end_latency_s: float | None
    truncated: bool


def language_code_for(ui_language: str | None, settings: Settings) -> str:
    """Map the app's language choice to Prisma's language_code. None -> configured default."""
    mapping = {
        "en": "en-IN",
        "hi": "hi-IN",
        "te": "te-IN",
        "hinglish": settings.gnani_prisma_hinglish_language,
    }
    if ui_language is None:
        return settings.gnani_prisma_default_language
    try:
        return mapping[ui_language]
    except KeyError as exc:
        raise ValueError(f"Unsupported language: {ui_language}") from exc


class PrismaClient:
    def __init__(self, http: GnaniHttp | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.http = http or GnaniHttp(self.settings)

    def transcribe(
        self,
        audio: bytes,
        filename: str,
        *,
        language: str | None = None,
        keyterms: list[str] | None = None,
        topic: str | None = DEFAULT_TOPIC,
        output_format: str | None = None,
    ) -> TranscriptionResult:
        if not audio:
            raise GnaniBadRequest("Audio is empty", gnani_code="EMPTY_AUDIO")
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in _MIME_BY_EXT:
            raise GnaniBadRequest(f"Unsupported audio type '.{ext}'", gnani_code="UNSUPPORTED_AUDIO_FORMAT")

        language_code = language_code_for(language, self.settings)
        data: dict[str, str] = {"model": self.settings.gnani_prisma_model, "language_code": language_code}
        fmt = output_format or (self.settings.gnani_prisma_hinglish_format if language == "hinglish" else None)
        if fmt:
            data["format"] = fmt
        if keyterms:
            unique = list(dict.fromkeys(t.strip() for t in keyterms if t and t.strip()))[:MAX_KEYTERMS]
            if unique:
                data["keyterms"] = json.dumps(unique, ensure_ascii=False)
        if topic:
            data["topic"] = topic[:MAX_TOPIC_CHARS]

        response = self.http.request(
            "POST", STT_PATH, operation="prisma.transcribe",
            files={"audio_file": (f"audio.{ext}", audio, _MIME_BY_EXT[ext])},
            data=data,
        )
        try:
            body = response.json()
        except ValueError as exc:
            raise GnaniResponseError("Prisma returned a non-JSON response", status_code=response.status_code) from exc

        request_id = body.get("request_id") if isinstance(body, dict) else None
        if not isinstance(body, dict) or body.get("success") is not True or not isinstance(body.get("transcript"), str):
            raise GnaniResponseError("Prisma response did not contain a transcript", request_id=request_id)

        # Prisma returns its request id in the body, not in a header (verified), so log it here.
        logger.info("prisma result", extra={"ctx": {
            "gnani_request_id": request_id, "detected_language": body.get("detected_language_code"),
            "transcript_chars": len(body["transcript"]), "truncated": bool(body.get("truncated", False))}})
        return TranscriptionResult(
            transcript=body["transcript"].strip(),
            model=str(body.get("model") or self.settings.gnani_prisma_model),
            language_code_requested=language_code,
            detected_language=body.get("detected_language_code"),
            request_id=request_id,
            processing_time_s=_as_float(body.get("processing_time")),
            end_to_end_latency_s=_as_float(body.get("end_to_end_latency")),
            truncated=bool(body.get("truncated", False)),
        )


def _as_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
