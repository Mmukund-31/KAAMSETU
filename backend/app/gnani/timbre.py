"""Gnani Timbre text-to-speech adapter.

Contract (docs.gnani.ai, verified with real requests on 2026-11-10):
  POST /api/v1/tts/inference, JSON
    {"text", "model": "timbre-v2.5", "voice", "language", "speed"?,
     "audio_config": {"sample_rate", "num_channels", "sample_width", "encoding", "container", "bitrate"?}}
  200 -> raw audio bytes; Content-Type audio/wav | audio/mpeg | audio/ogg ...; header x-api-request-id
On timbre-v2.5 each voice belongs to one language; a mismatched voice/model pair returns 400.
"""

from dataclasses import dataclass
from typing import Any

from app.config import Settings, get_settings
from app.gnani.base import GnaniHttp
from app.gnani.errors import GnaniBadRequest, GnaniResponseError

TTS_PATH = "/api/v1/tts/inference"
# The docs give no maximum; KAAMSETU only speaks short acknowledgements and questions.
MAX_TEXT_CHARS = 500
MIN_SPEED, MAX_SPEED = 0.85, 1.15

_CONTAINER_MIME = {"wav": "audio/wav", "mp3": "audio/mpeg", "ogg": "audio/ogg"}


@dataclass(frozen=True)
class SynthesisResult:
    audio: bytes
    content_type: str
    container: str
    voice: str
    language_code: str
    model: str
    request_id: str | None


def voice_for(ui_language: str, settings: Settings) -> tuple[str, str]:
    """Return (timbre language code, voice) for the app's language choice."""
    mapping = {
        "en": ("en-IN", settings.gnani_timbre_voice_en),
        "hi": ("hi-IN", settings.gnani_timbre_voice_hi),
        "te": ("te-IN", settings.gnani_timbre_voice_te),
        "hinglish": (settings.gnani_timbre_hinglish_language, settings.gnani_timbre_voice_hinglish),
    }
    try:
        return mapping[ui_language]
    except KeyError as exc:
        raise ValueError(f"Unsupported language: {ui_language}") from exc


class TimbreClient:
    def __init__(self, http: GnaniHttp | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.http = http or GnaniHttp(self.settings)

    def audio_config(self, container: str) -> dict[str, Any]:
        config: dict[str, Any] = {
            "sample_rate": self.settings.gnani_timbre_sample_rate,
            "num_channels": 1,
            "sample_width": 2,
            "container": container,
        }
        if container == "wav":
            config["encoding"] = "linear_pcm"
        elif container == "mp3":
            config["bitrate"] = self.settings.gnani_timbre_mp3_bitrate
        elif container == "ogg":
            config["encoding"] = "oggopus"
        return config

    def synthesize(
        self,
        text: str,
        *,
        language: str,
        speed: float | None = None,
        container: str | None = None,
    ) -> SynthesisResult:
        text = " ".join(text.split())
        if not text:
            raise GnaniBadRequest("Text is empty")
        if len(text) > MAX_TEXT_CHARS:
            raise GnaniBadRequest(f"Text exceeds {MAX_TEXT_CHARS} characters")
        container = container or self.settings.gnani_timbre_container
        if container not in _CONTAINER_MIME:
            raise GnaniBadRequest(f"Unsupported audio container '{container}'")

        language_code, voice = voice_for(language, self.settings)
        body: dict[str, Any] = {
            "text": text,
            "model": self.settings.gnani_timbre_model,
            "voice": voice,
            "language": language_code,
            "audio_config": self.audio_config(container),
        }
        if speed is not None:
            body["speed"] = round(min(MAX_SPEED, max(MIN_SPEED, speed)), 2)

        response = self.http.request("POST", TTS_PATH, operation="timbre.synthesize", json=body)
        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        request_id = response.headers.get("x-api-request-id")
        if not content_type.startswith("audio/") or not response.content:
            raise GnaniResponseError(
                f"Timbre returned '{content_type or 'no content type'}' instead of audio", request_id=request_id
            )
        return SynthesisResult(
            audio=response.content,
            content_type=content_type,
            container=container,
            voice=voice,
            language_code=language_code,
            model=self.settings.gnani_timbre_model,
            request_id=request_id,
        )
