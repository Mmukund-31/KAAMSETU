from typing import Literal

from pydantic import BaseModel, Field

from app.gnani.timbre import MAX_SPEED, MAX_TEXT_CHARS, MIN_SPEED
from app.models.enums import LanguageCode

# "auto" asks Prisma to detect the language; otherwise one of the app languages.
TranscribeLanguage = Literal["en", "hi", "te", "hinglish", "auto"]


class TranscriptionOut(BaseModel):
    transcript: str
    language_requested: str = Field(description="language_code sent to Prisma, e.g. en-IN or indic-auto")
    detected_language: str | None
    model: str
    gnani_request_id: str | None
    processing_time_s: float | None
    truncated: bool
    audio_format: str
    audio_duration_s: float | None


class SynthesizeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    language: LanguageCode
    speed: float | None = Field(default=None, ge=MIN_SPEED, le=MAX_SPEED)


class SynthesisOut(BaseModel):
    audio_base64: str
    content_type: str
    voice: str
    language_code: str
    model: str
    gnani_request_id: str | None
