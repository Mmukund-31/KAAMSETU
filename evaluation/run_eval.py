"""KAAMSETU evaluation runner (Phase 8).

Measures the voice-to-work-order pipeline on evaluation/dataset.json under four conditions:

  text   the reference text through /voice/process-text  (extraction and rules only, no speech recognition)
  clean  Timbre-generated speech through /voice/process-report  (real Prisma, then the same pipeline)
  noisy  the same audio with factory-like noise mixed in at 10 dB SNR (deterministic, seeded per item)
  auto   the clean audio through /voice/transcribe with language=auto (Prisma language detection only)

It calls the real FastAPI app in-process against the dev database and the real Gnani API, so it spends credits:
40 Timbre calls the first time (audio is cached in evaluation/audio/generated/), then 120 Prisma calls per run.

    cd backend
    .\\.venv\\Scripts\\python.exe ..\\evaluation\\run_eval.py            # full run
    .\\.venv\\Scripts\\python.exe ..\\evaluation\\run_eval.py --text-only  # no Gnani calls

Writes evaluation/results/<name>.json and <name>.md (generated detail). evaluation/RESULTS.md is the written
summary of the runs.
All speech is synthetic (Gnani Timbre). These are not human recordings or pilot results.
"""

import argparse
import array
import hashlib
import json
import math
import os
import random
import statistics
import struct
import sys
import time
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")  # the backend reads backend/.env
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")  # 160 requests from one client in a few minutes
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("GNANI_TIMBRE_SAMPLE_RATE", "16000")  # Prisma resamples to 16 kHz anyway; smaller files

from fastapi.testclient import TestClient  # noqa: E402

from app.intelligence.config_loader import taxonomy  # noqa: E402
from app.intelligence.models import PriorityContext  # noqa: E402
from app.intelligence.prioritization import prioritize  # noqa: E402
from app.main import app  # noqa: E402
from app.services import speech  # noqa: E402

AUDIO = HERE / "audio" / "generated"
RESULTS_DIR = HERE / "results"
PASSWORD = "Kaamsetu@2026"
LANGS = ["en", "hinglish", "hi", "te"]
LANG_NAME = {"en": "English", "hinglish": "Hinglish", "hi": "Hindi", "te": "Telugu"}
EXPECTED_DETECTION = {"en": "en-IN", "hinglish": "en-IN", "hi": "hi-IN", "te": "te-IN"}
SPEEDS = [1.0, 0.92, 1.08]  # Timbre speaking rate, cycled across items
SNR_DB = 10.0

# Pairs of taxonomy keys a reviewer would accept for each other (lenient symptom scoring).
RELATED = {frozenset(p) for p in [
    ("vibration", "bearing_vibration"), ("bearing_issue", "bearing_vibration"), ("leak", "oil_leak"),
    ("leak", "air_leak"), ("leak", "gas_leak"), ("overheating", "high_temperature"),
    ("erratic_reading", "sensor_fault"), ("belt_issue", "misalignment"),
]}


# ── audio ────────────────────────────────────────────────────────────────

def read_wav(data: bytes) -> tuple[int, int, array.array]:
    """Returns (sample_rate, channels, int16 samples). Handles Timbre's 0xFFFFFFFF streaming sizes."""
    pos, rate, channels, samples = 12, 16000, 1, None
    while pos + 8 <= len(data):
        kind = data[pos:pos + 4]
        size = struct.unpack_from("<I", data, pos + 4)[0]
        body = pos + 8
        if kind == b"fmt ":
            channels, rate = struct.unpack_from("<HI", data, body + 2)
        elif kind == b"data":
            end = len(data) if size == 0xFFFFFFFF or body + size > len(data) else body + size
            chunk = data[body:end]
            samples = array.array("h", chunk[: len(chunk) // 2 * 2])
            break
        if size == 0xFFFFFFFF:
            break
        pos = body + size + (size & 1)
    if samples is None:
        raise ValueError("no PCM data in WAV")
    return rate, channels, samples


def write_wav(rate: int, samples: array.array) -> bytes:
    pcm = samples.tobytes()
    header = struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + len(pcm), b"WAVE", b"fmt ", 16, 1, 1, rate,
                         rate * 2, 2, 16, b"data", len(pcm))
    return header + pcm


def add_factory_noise(data: bytes, seed: str, snr_db: float = SNR_DB) -> bytes:
    """Speech + low rumble (low-passed noise) + 100/200 Hz mains hum, scaled to the given SNR."""
    rate, _, speech_pcm = read_wav(data)
    rng = random.Random(seed)
    voiced = [s for s in speech_pcm if abs(s) > 300] or list(speech_pcm)
    speech_rms = math.sqrt(sum(s * s for s in voiced) / len(voiced))
    noise, low = [], 0.0
    for i in range(len(speech_pcm)):
        low = 0.92 * low + 0.08 * rng.gauss(0, 1)
        hum = 0.6 * math.sin(2 * math.pi * 100 * i / rate) + 0.3 * math.sin(2 * math.pi * 200 * i / rate)
        noise.append(low * 3.0 + hum + 0.15 * rng.gauss(0, 1))
    noise_rms = math.sqrt(sum(n * n for n in noise) / len(noise)) or 1.0
    gain = speech_rms / (noise_rms * 10 ** (snr_db / 20))
    mixed = array.array("h", (max(-32768, min(32767, int(s + n * gain))) for s, n in zip(speech_pcm, noise, strict=True)))
    return write_wav(rate, mixed)


def generate_audio(items: list[dict]) -> dict:
    """Synthesises missing clips with Timbre (WAV) and records how each was made."""
    AUDIO.mkdir(parents=True, exist_ok=True)
    manifest_path = AUDIO / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8")) if manifest_path.exists() else {}
    timbre = speech.get_timbre_client()
    for index, item in enumerate(items):
        path = AUDIO / f"{item['id']}.wav"
        if path.exists() and item["id"] in manifest:
            continue
        speed = SPEEDS[index % len(SPEEDS)]
        result = timbre.synthesize(item["text"], language=speech_language(item["language"]), speed=speed, container="wav")
        path.write_bytes(result.audio)
        rate, _, pcm = read_wav(result.audio)
        manifest[item["id"]] = {"voice": result.voice, "speed": speed, "gnani_request_id": result.request_id,
                                "seconds": round(len(pcm) / rate, 2), "sha256": hashlib.sha256(result.audio).hexdigest()}
        print(f"  synthesised {item['id']} ({result.voice}, {manifest[item['id']]['seconds']} s)")
        manifest_path.write_text(json.dumps(manifest, indent=1), "utf-8")
    return manifest


def speech_language(language: str) -> str:
    return language  # the backend maps en / hi / te / hinglish to Timbre voices


# ── scoring ──────────────────────────────────────────────────────────────

def normalise(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text).lower()
    text = "".join(" " if unicodedata.category(c).startswith("P") or c in "-–—" else c for c in text)
    return text.split()


def edit_distance(a: list, b: list) -> int:
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (x != y)))
        previous = current
    return previous[-1]


def wer(reference: str, hypothesis: str) -> float:
    ref, hyp = normalise(reference), normalise(hypothesis)
    return edit_distance(ref, hyp) / max(1, len(ref))


def cer(reference: str, hypothesis: str) -> float:
    ref, hyp = list("".join(normalise(reference))), list("".join(normalise(hypothesis)))
    return edit_distance(ref, hyp) / max(1, len(ref))


def symptoms_lenient(expected: set, predicted: set) -> bool:
    def related(a, b):
        return a == b or frozenset((a, b)) in RELATED
    return all(any(related(e, p) for p in predicted) for e in expected) and \
        all(any(related(p, e) for e in expected) for p in predicted)


def expected_priority(expected: dict, register: dict) -> str:
    tax = taxonomy()
    severities = [tax.symptoms[s].severity for s in expected["symptoms"] if s in tax.symptoms]
    equipment = register.get(expected["equipment"]) if expected["equipment"] else None
    decision = prioritize(PriorityContext(
        safety_concern=expected["safety_concern"], production_impact=expected["production_impact"],
        equipment_critical=equipment["is_critical"] if equipment else None, symptom_severities=severities,
        category=expected["category"][0]))
    return decision.level.value


def score(item: dict, outcome: dict, register: dict) -> dict:
    exp = item["expected"]
    eq = outcome["equipment"]
    predicted_eq = eq["equipment"]["code"] if eq["status"] == "matched" and eq["equipment"] else None
    predicted_symptoms = set(outcome["draft"]["symptoms"])
    expected_symptoms = set(exp["symptoms"])
    tp = len(predicted_symptoms & expected_symptoms)
    fields = {
        "equipment": predicted_eq == exp["equipment"],
        "symptoms_exact": predicted_symptoms == expected_symptoms,
        "symptoms_lenient": symptoms_lenient(expected_symptoms, predicted_symptoms),
        "production_impact": outcome["draft"]["production_impact"] == exp["production_impact"],
        "safety_concern": outcome["draft"]["safety_concern"] == exp["safety_concern"],
        "category": outcome["category"]["value"] in exp["category"],
        "next_action": outcome["next_action"] == exp["next_action"],
        "priority": outcome["priority"]["level"] == expected_priority(exp, register),
    }
    fields["fully_correct"] = all(fields[k] for k in ("equipment", "symptoms_lenient", "production_impact",
                                                     "safety_concern", "category", "next_action"))
    return {
        "fields": fields, "tp": tp, "fp": len(predicted_symptoms - expected_symptoms),
        "fn": len(expected_symptoms - predicted_symptoms),
        "predicted": {"equipment": predicted_eq, "heard": eq.get("heard"), "symptoms": sorted(predicted_symptoms),
                      "production_impact": outcome["draft"]["production_impact"],
                      "safety_concern": outcome["draft"]["safety_concern"], "category": outcome["category"]["value"],
                      "next_action": outcome["next_action"], "priority": outcome["priority"]["level"]},
    }


# ── running ──────────────────────────────────────────────────────────────

def run(text_only: bool, dataset_path: Path) -> dict:
    dataset = json.loads(dataset_path.read_text("utf-8"))
    items = dataset["items"]
    client = TestClient(app)
    login = client.post("/api/v1/auth/login", json={"email": "tech1@kaamsetu.demo", "password": PASSWORD})
    login.raise_for_status()
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    sup = client.post("/api/v1/auth/login", json={"email": "supervisor@kaamsetu.demo", "password": PASSWORD}).json()
    register = {e["code"]: e for e in client.get("/api/v1/equipment?page_size=200",
                                                 headers={"Authorization": f"Bearer {sup['access_token']}"}).json()["items"]}

    conditions = ["text"] if text_only else ["text", "clean", "noisy", "auto"]
    manifest = {} if text_only else generate_audio(items)
    results = []
    for item in items:
        row = {"id": item["id"], "language": item["language"], "text": item["text"], "expected": item["expected"],
               "audio": manifest.get(item["id"]), "runs": {}}
        for condition in conditions:
            started = time.perf_counter()
            if condition == "text":
                response = client.post("/api/v1/voice/process-text", headers=headers,
                                       json={"text": item["text"], "language": item["language"], "speak": False})
            else:
                audio = (AUDIO / f"{item['id']}.wav").read_bytes()
                if condition == "noisy":
                    audio = add_factory_noise(audio, item["id"])
                if condition == "auto":
                    response = client.post("/api/v1/voice/transcribe", headers=headers,
                                           files={"audio": ("report.wav", audio, "audio/wav")}, data={"language": "auto"})
                else:
                    response = client.post("/api/v1/voice/process-report", headers=headers,
                                           files={"audio": ("report.wav", audio, "audio/wav")},
                                           data={"language": item["language"], "speak": "false"})
            seconds = round(time.perf_counter() - started, 2)
            body = response.json()
            run_row = {"status": response.status_code, "seconds": seconds}
            if response.status_code != 200:
                run_row["error"] = body.get("error", {}).get("code")
            elif condition == "auto":
                run_row.update(transcript=body["transcript"], detected=body["detected_language"],
                               detection_ok=body["detected_language"] == EXPECTED_DETECTION[item["language"]])
            else:
                transcript = body["original_transcript"]
                run_row.update(transcript=transcript, **score(item, body, register))
                if condition != "text":
                    run_row.update(wer=round(wer(item["text"], transcript), 3), cer=round(cer(item["text"], transcript), 3),
                                   prisma_request_id=(body["utterances"][0] or {}).get("gnani_request_id"))
            row["runs"][condition] = run_row
        results.append(row)
        print(f"  {item['id']}: " + "  ".join(
            f"{c}={'ok' if r.get('fields', {}).get('fully_correct') or r.get('detection_ok') else 'x'}"
            for c, r in row["runs"].items()))
    return {"dataset": dataset_path.name, "dataset_version": dataset["version"], "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "conditions": conditions, "snr_db": SNR_DB, "items": results}


# ── report ───────────────────────────────────────────────────────────────

FIELDS = ["equipment", "symptoms_exact", "symptoms_lenient", "production_impact", "safety_concern", "category",
          "next_action", "priority", "fully_correct"]
FIELD_LABEL = {"equipment": "Equipment (register match)", "symptoms_exact": "Symptoms, exact set",
               "symptoms_lenient": "Symptoms, lenient", "production_impact": "Production impact",
               "safety_concern": "Safety concern", "category": "Category", "next_action": "Next action",
               "priority": "Priority (policy on true fields)", "fully_correct": "**Whole report correct**"}


def pct(values: list[bool]) -> str:
    return f"{100 * sum(values) / len(values):.0f}% ({sum(values)}/{len(values)})" if values else "n/a"


def summarise(data: dict) -> str:
    items = data["items"]
    scored = [c for c in data["conditions"] if c != "auto"]
    lines = [
        "# Evaluation results",
        "",
        f"Run {data['run_at']} on `evaluation/{data.get('dataset', 'dataset.json')}` v{data['dataset_version']}: "
        f"{len(items)} synthetic reports (see `evaluation/RESULTS.md` for what each run means).",
        "",
        "**Read this first:** all speech is generated by Gnani Timbre, not spoken by people. The noisy condition adds "
        f"synthetic factory noise at {data['snr_db']:.0f} dB SNR. These numbers show how the pipeline behaves on clear and noisy "
        "machine speech. They are not accuracy on real technicians, accents or phone microphones, and not pilot results.",
        "",
        "Conditions: **text** = reference text typed in (rules only, no speech recognition) · **clean** = Timbre audio "
        "through real Prisma and the full pipeline · **noisy** = the same audio with noise.",
        "",
        "## Field accuracy",
        "",
        "| Field | " + " | ".join(scored) + " |",
        "|---|" + "---|" * len(scored),
    ]
    for field in FIELDS:
        cells = [pct([i["runs"][c]["fields"][field] for i in items if "fields" in i["runs"][c]]) for c in scored]
        lines.append(f"| {FIELD_LABEL[field]} | " + " | ".join(cells) + " |")
    lines += ["", "Symptom precision / recall (micro, exact keys):", ""]
    for c in scored:
        tp = sum(i["runs"][c].get("tp", 0) for i in items)
        fp = sum(i["runs"][c].get("fp", 0) for i in items)
        fn = sum(i["runs"][c].get("fn", 0) for i in items)
        lines.append(f"- {c}: precision {tp / max(1, tp + fp):.2f}, recall {tp / max(1, tp + fn):.2f} "
                     f"(tp {tp}, fp {fp}, fn {fn})")
    failed_requests = [(i["id"], c, i["runs"][c].get("error")) for i in items for c in data["conditions"]
                       if i["runs"][c]["status"] != 200]
    lines += ["", f"Requests that failed: {len(failed_requests)}"
              + (" (" + ", ".join(f"{a} {b}: {e}" for a, b, e in failed_requests) + ")" if failed_requests else "")]

    # What a miss does: a follow-up question is recoverable; a confident wrong preview is the dangerous case.
    lines += ["", "## Outcome of each report", "",
              "- **correct**: the preview is right and ready to send.",
              "- **asked**: the app asked a follow-up question or for the machine; the technician answers and the report "
              "completes (recoverable).",
              "- **wrong, not asked**: the app offered a preview with a wrong field, which the technician would have to "
              "notice in the preview.", "",
              "| Condition | correct | asked | wrong, not asked | of which safety missed |", "|---|---|---|---|---|"]
    for c in scored:
        runs = [(i, i["runs"][c]) for i in items if "fields" in i["runs"][c]]
        correct = sum(1 for _, r in runs if r["fields"]["fully_correct"])
        silent = [(i, r) for i, r in runs if not r["fields"]["fully_correct"] and r["predicted"]["next_action"] == "confirm_preview"]
        asked = len(runs) - correct - len(silent)
        safety = sum(1 for i, r in silent if i["expected"]["safety_concern"] and not r["predicted"]["safety_concern"])
        lines.append(f"| {c} | {correct} | {asked} | {len(silent)} | {safety} |")

    lines += ["", "## Whole report correct, by language", "", "| Language | " + " | ".join(scored) + " |",
              "|---|" + "---|" * len(scored)]
    for lang in LANGS:
        cells = [pct([i["runs"][c]["fields"]["fully_correct"] for i in items
                      if i["language"] == lang and "fields" in i["runs"][c]]) for c in scored]
        lines.append(f"| {LANG_NAME[lang]} | " + " | ".join(cells) + " |")

    if "clean" in data["conditions"]:
        lines += ["", "## Speech recognition (Prisma)", "",
                  "Word and character error rate of the transcript against the text Timbre was given (lower case, "
                  "punctuation removed). For Hindi and Telugu, Prisma may write English loanwords or numbers in another "
                  "script than the reference, which counts as an error here even when the meaning is intact.", "",
                  "| Language | WER clean | WER noisy | CER clean | CER noisy | Auto language detection | Median latency clean |",
                  "|---|---|---|---|---|---|---|"]
        for lang in LANGS:
            rows = [i for i in items if i["language"] == lang]
            def med(cond, key, rows=rows):
                vals = [i["runs"][cond][key] for i in rows if key in i["runs"][cond]]
                return statistics.median(vals) if vals else float("nan")
            det = [i["runs"]["auto"].get("detection_ok", False) for i in rows]
            lines.append(f"| {LANG_NAME[lang]} | {med('clean', 'wer'):.2f} | {med('noisy', 'wer'):.2f} | "
                         f"{med('clean', 'cer'):.2f} | {med('noisy', 'cer'):.2f} | {pct(det)} | {med('clean', 'seconds'):.2f} s |")
        lines += ["", "WER / CER are medians per language. Latency is the whole `/voice/process-report` request "
                  "(upload, Prisma, extraction, database lookups) measured in-process; Timbre is off (`speak=false`).",
                  "Auto detection expects en-IN for Hinglish (Latin-script output is what the app uses for Hinglish)."]

    lines += ["", "## Every miss", "", "| Item | Condition | Field(s) wrong | Expected | Got | Transcript |",
              "|---|---|---|---|---|---|"]
    for i in items:
        for c in scored:
            r = i["runs"][c]
            if r["status"] != 200:
                lines.append(f"| {i['id']} | {c} | request failed | | {r.get('error')} | |")
                continue
            wrong = [f for f in FIELDS[:-1] if not r["fields"][f] and f != "symptoms_exact"]
            if not wrong:
                continue
            exp, got = i["expected"], r["predicted"]
            expect_txt = "; ".join(f"{f}: {exp.get(f.replace('symptoms_lenient', 'symptoms'), '')}" for f in wrong
                                   if f != "priority")
            got_txt = "; ".join(f"{f}: {got.get(f.replace('symptoms_lenient', 'symptoms'), '')}" for f in wrong
                                if f != "priority")
            if "priority" in wrong:
                got_txt += f"; priority {got['priority']}"
            transcript = r.get("transcript", "") if c != "text" else ""
            lines.append(f"| {i['id']} | {c} | {', '.join(wrong)} | {expect_txt} | {got_txt} | {transcript[:90]} |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text-only", action="store_true", help="only the text condition (no Gnani calls)")
    parser.add_argument("--dataset", default="dataset.json", help="dataset file in evaluation/")
    parser.add_argument("--name", default="latest", help="output name: results/<name>.json and results/<name>.md")
    parser.add_argument("--report-only", action="store_true", help="rebuild results/<name>.md from <name>.json")
    args = parser.parse_args()
    if args.report_only:
        data = json.loads((RESULTS_DIR / f"{args.name}.json").read_text("utf-8"))
        (RESULTS_DIR / f"{args.name}.md").write_text(summarise(data), "utf-8")
        print(f"rebuilt evaluation/results/{args.name}.md")
        return
    data = run(args.text_only, HERE / args.dataset)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / f"{args.name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    (RESULTS_DIR / f"{args.name}.md").write_text(summarise(data), "utf-8")
    print(f"\nwrote evaluation/results/{args.name}.md and .json")


if __name__ == "__main__":
    main()
