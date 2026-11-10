"""Synthesise the demo-video voiceover with Gnani Timbre (real API calls, spends a few credits).

Reads narration.json, writes audio/<id>.wav (44.1 kHz mono PCM) and audio/manifest.json with durations.
Lines whose text, voice and speed are unchanged are skipped, so re-running after editing one line costs one call.
With --check, each English/Hinglish line is also transcribed by Gnani Prisma so the pronunciation can be read.

Run from the repository root:
    backend\\.venv\\Scripts\\python.exe demo-video\\gen_voice.py [--only n01,n05] [--check]
Never prints the API key.
"""

import argparse
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent / "backend"
os.chdir(BACKEND)  # so backend/.env is found
sys.path.insert(0, str(BACKEND))

from app.config import get_settings  # noqa: E402
from app.gnani.base import GnaniHttp  # noqa: E402
from app.gnani.prisma import PrismaClient  # noqa: E402
from app.gnani.timbre import TTS_PATH  # noqa: E402

SAMPLE_RATE = 44100


def pcm_from_wav(data: bytes) -> bytes:
    """Return the PCM payload. Timbre writes 0xFFFFFFFF chunk sizes, so walk the chunks by hand."""
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    pos = 12
    while pos + 8 <= len(data):
        chunk_id, size = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
        if chunk_id == b"data":
            return data[pos + 8:] if size in (0xFFFFFFFF, 0) or pos + 8 + size > len(data) else data[pos + 8:pos + 8 + size]
        pos += 8 + size + (size & 1)
    raise ValueError("no data chunk")


def clean_wav(pcm: bytes) -> bytes:
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack(
        "<IHHIIHH", 16, 1, 1, SAMPLE_RATE, SAMPLE_RATE * 2, 2, 16) + b"data" + struct.pack("<I", len(pcm))
    return header + pcm


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="comma-separated line ids to (re)generate")
    parser.add_argument("--check", action="store_true", help="transcribe the generated lines with Prisma")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    settings = get_settings()
    if not settings.gnani_configured:
        print("GNANI_API_KEY is not set in backend/.env")
        return 2
    spec = json.loads((HERE / "narration.json").read_text(encoding="utf-8"))
    out_dir = HERE / "audio"
    out_dir.mkdir(exist_ok=True)
    manifest_path = out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    only = set(args.only.split(",")) if args.only else None

    http = GnaniHttp(settings)
    prisma = PrismaClient(http, settings)
    calls = 0
    for line in spec["lines"]:
        voice = spec["voices"][line["who"]]
        digest = hashlib.sha256(json.dumps([line["say"], voice], ensure_ascii=False).encode()).hexdigest()[:16]
        target = out_dir / f"{line['id']}.wav"
        known = manifest.get(line["id"])
        fresh = bool(known and known["digest"] == digest and target.exists())
        if only is not None and line["id"] not in only:
            continue
        if not fresh or (only is not None):
            body = {
                "text": line["say"], "model": settings.gnani_timbre_model, "voice": voice["voice"],
                "language": voice["language"], "speed": voice["speed"],
                "audio_config": {"sample_rate": SAMPLE_RATE, "num_channels": 1, "sample_width": 2,
                                 "container": "wav", "encoding": "linear_pcm"},
            }
            response = http.request("POST", TTS_PATH, operation="timbre.synthesize", json=body)
            calls += 1
            pcm = pcm_from_wav(response.content)
            target.write_bytes(clean_wav(pcm))
            manifest[line["id"]] = {"digest": digest, "seconds": round(len(pcm) / (SAMPLE_RATE * 2), 3),
                                    "voice": voice["voice"], "request_id": response.headers.get("x-api-request-id")}
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        entry = manifest[line["id"]]
        heard = ""
        if args.check and line["who"] in ("motor", "ravi", "app_hinglish"):
            language = "en" if line["who"] == "motor" else "hinglish"
            heard = " | Prisma heard: " + prisma.transcribe(target.read_bytes(), target.name, language=language).transcript
            calls += 1
        print(f"{line['id']} {entry['voice']:8} {entry['seconds']:6.2f}s{heard}")
    total = sum(v["seconds"] for v in manifest.values())
    print(f"\n{calls} Gnani calls this run. Total speech: {total:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
