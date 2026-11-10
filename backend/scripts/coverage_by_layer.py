"""Summarise a coverage JSON report by backend layer (app/<layer>/...), excluding the tests.

    python -m pytest --cov=app --cov-report=json:coverage.json
    python scripts/coverage_by_layer.py coverage.json
"""

import json
import sys
from collections import defaultdict
from pathlib import PurePath

files = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "coverage.json", encoding="utf-8"))["files"]
layers: dict[str, list[int]] = defaultdict(lambda: [0, 0])
below = []
for name, data in files.items():
    parts = PurePath(name.replace("\\", "/")).parts
    if "tests" in parts:
        continue
    layer = parts[1] if len(parts) > 2 else "(app root)"
    summary = data["summary"]
    layers[layer][0] += summary["num_statements"]
    layers[layer][1] += summary["covered_lines"]
    if summary["percent_covered"] < 85:
        below.append((round(summary["percent_covered"]), "/".join(parts), summary["missing_lines"]))

statements = sum(v[0] for v in layers.values())
covered = sum(v[1] for v in layers.values())
for layer, (n, c) in sorted(layers.items()):
    print(f"{layer:14} {c:5}/{n:<5} {100 * c / n:5.1f}%")
print(f"{'app total':14} {covered:5}/{statements:<5} {100 * covered / statements:5.1f}%")
for pct, path, missing in sorted(below):
    print(f"below 85%: {pct:3}% {path} ({missing} lines missing)")
