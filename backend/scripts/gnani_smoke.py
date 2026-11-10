"""Gnani smoke test: one real Timbre call and one real Prisma call per language.

Speaks a short maintenance sentence with Timbre, transcribes that audio with Prisma, and prints
latency, request ids and the transcript. Spends a few programme credits (8 calls).
Never prints the API key.

Run from backend/:   .venv\\Scripts\\python.exe scripts\\gnani_smoke.py [--save DIR]
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.gnani.base import GnaniHttp  # noqa: E402
from app.gnani.errors import GnaniError  # noqa: E402
from app.gnani.prisma import PrismaClient  # noqa: E402
from app.gnani.timbre import TimbreClient  # noqa: E402

SENTENCES = {
    "en": "Machine H-401 has an oil leak near the pump. Production is still running.",
    "hi": "मशीन एम दो सौ चार में बेयरिंग से आवाज़ आ रही है। उत्पादन रुक गया है।",
    "te": "మెషిన్ ఎం రెండు వందల నాలుగు లో వైబ్రేషన్ వస్తోంది. ప్రొడక్షన్ నడుస్తోంది.",
    "hinglish": "Motor ka pressure abnormal hai. Bearing mein vibration aa raha hai. Machine number M-204 hai.",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", type=Path, help="directory to write the synthesised audio into")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.gnani_configured:
        print("GNANI_API_KEY is not set in backend/.env")
        return 2
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"Host {settings.gnani_api_base_url} | Prisma {settings.gnani_prisma_model} | "
          f"Timbre {settings.gnani_timbre_model} | key configured: yes\n")

    http = GnaniHttp(settings)
    timbre, prisma = TimbreClient(http, settings), PrismaClient(http, settings)
    failures = 0
    for lang, text in SENTENCES.items():
        try:
            t0 = time.perf_counter()
            spoken = timbre.synthesize(text, language=lang)
            t1 = time.perf_counter()
            heard = prisma.transcribe(spoken.audio, f"smoke.{spoken.container}", language=lang)
            t2 = time.perf_counter()
        except GnaniError as exc:
            failures += 1
            print(f"[{lang}] FAILED: {type(exc).__name__}: {exc}\n")
            continue
        if args.save:
            args.save.mkdir(parents=True, exist_ok=True)
            (args.save / f"smoke_{lang}.{spoken.container}").write_bytes(spoken.audio)
        print(f"[{lang}] Timbre {spoken.voice}/{spoken.language_code}: {len(spoken.audio)} bytes in {t1 - t0:.2f}s "
              f"(request {spoken.request_id})")
        print(f"[{lang}] Prisma {heard.language_code_requested} -> detected {heard.detected_language} in {t2 - t1:.2f}s "
              f"(request {heard.request_id})")
        print(f"[{lang}] said:  {text}\n[{lang}] heard: {heard.transcript}\n")
    http.close()
    print("Smoke test", "FAILED" if failures else "passed", f"({failures} failure(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
