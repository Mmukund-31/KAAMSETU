import struct
from pathlib import Path

import pytest

from app.core.errors import AppError
from app.services.audio import detect_format, validate_audio, wav_duration
from app.tests.unit.gnani_fakes import fake_settings

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "audio"


def make_wav(seconds: float, rate: int = 16000, placeholder_sizes: bool = False) -> bytes:
    pcm = b"\x00\x00" * int(rate * seconds)
    riff_size = 0xFFFFFFFF if placeholder_sizes else 36 + len(pcm)
    data_size = 0xFFFFFFFF if placeholder_sizes else len(pcm)
    fmt = struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
    return b"RIFF" + struct.pack("<I", riff_size) + b"WAVEfmt " + fmt + b"data" + struct.pack("<I", data_size) + pcm


@pytest.mark.parametrize("data, fmt", [
    (b"RIFF\x00\x00\x00\x00WAVEfmt ", "wav"),
    (b"OggS\x00\x02" + b"\x00" * 10, "ogg"),
    (b"fLaC\x00\x00\x00\x22", "flac"),
    (b"\x00\x00\x00\x1cftypM4A \x00\x00", "m4a"),
    (b"ID3\x04\x00\x00\x00\x00", "mp3"),
    (b"\xff\xfb\x90\x64\x00\x00", "mp3"),
    (b"\xff\xf1\x50\x80\x00\x1f", "aac"),
    (b"MZ\x90\x00 executable", None),
    (b"<html>", None),
])
def test_detect_format_from_magic_bytes(data, fmt):
    assert detect_format(data) == fmt


def test_wav_duration_normal_header():
    assert wav_duration(make_wav(2.0)) == pytest.approx(2.0)


def test_wav_duration_with_streaming_placeholder_sizes():
    assert wav_duration(make_wav(1.5, placeholder_sizes=True)) == pytest.approx(1.5)


def test_real_timbre_wav_with_placeholder_header():
    """Timbre writes RIFF/data sizes as 0xFFFFFFFF; stdlib wave and mutagen report ~134,217 s for this file."""
    data = (FIXTURES / "hindi_m204_streaming_header.wav").read_bytes()
    info = validate_audio(data, fake_settings())
    assert info.format == "wav"
    assert info.duration_seconds == pytest.approx(2.56, abs=0.01)


@pytest.mark.parametrize("name, fmt", [("hinglish_m204.mp3", "mp3"), ("hinglish_m204.ogg", "ogg"),
                                       ("english_h401.mp3", "mp3"), ("hinglish_m204.m4a", "m4a")])
def test_real_compressed_fixtures(name, fmt):
    info = validate_audio((FIXTURES / name).read_bytes(), fake_settings())
    assert info.format == fmt
    assert 1.0 < info.duration_seconds < 15.0


def test_empty_rejected():
    with pytest.raises(AppError) as e:
        validate_audio(b"", fake_settings())
    assert e.value.code == "empty_audio" and e.value.status_code == 422


def test_oversize_rejected_with_413():
    with pytest.raises(AppError) as e:
        validate_audio(b"ID3" + b"\x00" * (2 * 1024 * 1024), fake_settings(max_audio_upload_mb=1))
    assert e.value.status_code == 413 and e.value.code == "audio_too_large"


def test_unknown_format_rejected_with_415():
    with pytest.raises(AppError) as e:
        validate_audio(b"MZ\x90\x00 not audio at all", fake_settings())
    assert e.value.status_code == 415 and e.value.code == "unsupported_audio_format"


def test_too_long_rejected():
    with pytest.raises(AppError) as e:
        validate_audio(make_wav(31.0, rate=8000), fake_settings())
    assert e.value.code == "audio_too_long"
    assert e.value.details["max_seconds"] == 30


def test_too_short_rejected():
    with pytest.raises(AppError) as e:
        validate_audio(make_wav(0.05), fake_settings())
    assert e.value.code == "audio_too_short"


def test_unreadable_duration_is_allowed_through():
    # Prisma enforces its own limits; an unknown duration must not block a valid recording.
    info = validate_audio(b"\x00\x00\x00\x1cftypM4A " + b"\x00" * 64, fake_settings())
    assert info.format == "m4a" and info.duration_seconds is None
