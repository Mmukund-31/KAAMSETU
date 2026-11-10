"""Audio upload validation.

Checks run before any audio leaves the server:
  * size (empty / over MAX_AUDIO_UPLOAD_MB),
  * real format from magic bytes (the filename and declared content type are not trusted),
  * duration (Prisma REST accepts at most 30 s).

Retention: uploads are held in memory for the request only. Nothing is written to disk while
AUDIO_RETENTION=none (the default); see docs/GNANI_INTEGRATION.md "Security and privacy".
"""

import io
import struct
from dataclasses import dataclass

from app.config import Settings, get_settings
from app.core.errors import AppError, Unprocessable

SUPPORTED_FORMATS = ("wav", "mp3", "ogg", "flac", "aac", "m4a")
MIN_SECONDS = 0.1
_RIFF_PLACEHOLDER = 0xFFFFFFFF  # streaming encoders (including Timbre) write this instead of a real size


@dataclass(frozen=True)
class AudioInfo:
    format: str
    size_bytes: int
    duration_seconds: float | None

    @property
    def filename(self) -> str:
        return f"audio.{self.format}"


def detect_format(data: bytes) -> str | None:
    head = data[:16]
    if len(head) < 4:
        return None
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if head[:4] == b"OggS":
        return "ogg"
    if head[:4] == b"fLaC":
        return "flac"
    if head[4:8] == b"ftyp":  # MP4 / M4A container (Expo's default recording format)
        return "m4a"
    if head[:3] == b"ID3":
        return "mp3"
    if head[0] == 0xFF and (head[1] & 0xF6) == 0xF0:  # ADTS AAC: sync word + layer bits 00
        return "aac"
    if head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:  # MPEG audio frame sync
        return "mp3"
    return None


def wav_duration(data: bytes) -> float | None:
    """Parse RIFF chunks directly; tolerates the 0xFFFFFFFF placeholder sizes streaming encoders write."""
    pos, byte_rate = 12, None
    while pos + 8 <= len(data):
        chunk_id = data[pos:pos + 4]
        (size,) = struct.unpack("<I", data[pos + 4:pos + 8])
        body = pos + 8
        if chunk_id == b"fmt " and body + 12 <= len(data):
            (byte_rate,) = struct.unpack("<I", data[body + 8:body + 12])
        elif chunk_id == b"data":
            remaining = len(data) - body
            if size == _RIFF_PLACEHOLDER or size > remaining:
                size = remaining
            return size / byte_rate if byte_rate else None
        if size == _RIFF_PLACEHOLDER:
            return None
        pos = body + size + (size & 1)  # chunks are word-aligned
    return None


def audio_duration(data: bytes, fmt: str) -> float | None:
    if fmt == "wav":
        return wav_duration(data)
    try:
        import mutagen

        info = mutagen.File(io.BytesIO(data))
        length = getattr(getattr(info, "info", None), "length", None)
        return float(length) if length else None
    except Exception:  # noqa: BLE001 - unreadable metadata just means "unknown"; Prisma still enforces limits
        return None


def validate_audio(data: bytes, settings: Settings | None = None) -> AudioInfo:
    settings = settings or get_settings()
    if not data:
        raise Unprocessable("The recording is empty. Please record again.", code="empty_audio")
    max_bytes = settings.max_audio_upload_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise AppError(f"Audio exceeds {settings.max_audio_upload_mb} MB", code="audio_too_large", status_code=413)

    fmt = detect_format(data)
    if fmt is None:
        raise AppError(
            "Unsupported audio format. Use WAV, MP3, OGG, FLAC, AAC or M4A.",
            code="unsupported_audio_format",
            status_code=415,
            details={"supported": list(SUPPORTED_FORMATS)},
        )

    duration = audio_duration(data, fmt)
    if duration is not None:
        if duration < MIN_SECONDS:
            raise Unprocessable("The recording is too short. Please hold the button and speak.", code="audio_too_short")
        if duration > settings.max_audio_seconds + 0.5:
            raise Unprocessable(
                f"Recordings can be at most {settings.max_audio_seconds} seconds.",
                code="audio_too_long",
                details={"duration_seconds": round(duration, 1), "max_seconds": settings.max_audio_seconds},
            )
    return AudioInfo(format=fmt, size_bytes=len(data), duration_seconds=duration)
