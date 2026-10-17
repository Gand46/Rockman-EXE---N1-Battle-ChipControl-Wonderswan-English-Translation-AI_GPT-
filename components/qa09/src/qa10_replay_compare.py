#!/usr/bin/env python3
"""Compare matched QA08 / QA09 emulator runs from one archived state.

This is a narrowly scoped **synthetic** regression check. It does not prove
natural progression or that every possible game event has been exercised.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

from qa09_paths import QA08_SHA256, qa08_rom

ROOT = Path(__file__).resolve().parents[1]
QA09_SHA256 = "d729823bbe6cf9132e6345ed734eb2dbe51885c13d5a17a44a9f7cfae086c326"
DEFAULT_CASES = ("guard_fire_native", "pierce_shield")


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def ensure_sha(path: Path, expected: str) -> None:
    actual = sha(path.read_bytes())
    if actual != expected:
        raise ValueError(f"Unexpected SHA256 for {path}: {actual} != {expected}")


def execute(case: str, rom: Path, route: Path, state: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, AUDIT_ROM_DIR=str(rom.parent.resolve()), QA_CAPTURE_DIR=str(output.resolve()))
    subprocess.run(
        [sys.executable, str(ROOT / "src/qa09_capture.py"), rom.stem, str(route), str(state)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, check=True, timeout=90,
    )


def compare_case(case: str, entry: dict, rom8: Path, rom9: Path, work: Path,
                 samples: Path | None) -> dict:
    route = ROOT / entry["route"]
    state = ROOT / entry["state"]
    ensure_sha(state, entry["state_sha256"])
    if entry["status"] != "EXECUTED":
        raise ValueError(f"Cannot replay invalid/discarded fixture {case}: {entry['status']}")
    old, new = work / "qa08", work / "qa09"
    execute(case, rom8, route, state, old)
    execute(case, rom9, route, state, new)
    old_png = sorted(old.glob("*.png"))
    new_png = sorted(new.glob("*.png"))
    if not old_png or len(old_png) != len(new_png):
        raise AssertionError(f"Unequal or empty frame counts in {case}: {len(old_png)} vs {len(new_png)}")
    differences = []
    totals = {"png": 0, "ram": 0, "state_samples": 0}
    pairs = []
    for base in old_png:
        candidate = new / base.name.replace("QA08", "QA09")
        if not candidate.exists():
            raise FileNotFoundError(f"Missing corresponding final-QA09 capture: {candidate.name}")
        x = np.asarray(Image.open(base).convert("RGB"), dtype=np.uint8)
        y = np.asarray(Image.open(candidate).convert("RGB"), dtype=np.uint8)
        if x.shape != y.shape or x.shape != (144, 224, 3):
            raise AssertionError(f"Non-native / inconsistent frame geometry in {case}: {x.shape} vs {y.shape}")
        count = int(np.count_nonzero(np.any(x != y, axis=2)))
        totals["png"] += count
        if count:
            differences.append({"frame": base.stem, "different_pixels": count})
        old_ram = base.with_suffix(".ram")
        new_ram = candidate.with_suffix(".ram")
        if not old_ram.is_file() or not new_ram.is_file():
            raise FileNotFoundError("Missing matching RAM capture")
        a, b = old_ram.read_bytes(), new_ram.read_bytes()
        if len(a) != len(b) or len(a) != 65536:
            raise AssertionError("Unexpected WRAM capture size")
        memory_changes = sum(p != q for p, q in zip(a, b))
        totals["ram"] += memory_changes
        if memory_changes:
            differences.append({"frame": base.stem, "different_ram_bytes": memory_changes})
        pairs.append((base, candidate))
    if samples is not None:
        samples.mkdir(parents=True, exist_ok=True)
        # Native-resolution entry/exit evidence, not resized or visually altered.
        for i in sorted(set((0, len(pairs) - 1))):
            for image_path in pairs[i]:
                shutil.copyfile(image_path, samples / image_path.name)
                totals["state_samples"] += 1
    return {
        "case": case,
        "status": "PASS_PIXEL_RAM_EQUIVALENCE" if not differences else "DIFFERENCE_REQUIRES_REVIEW",
        "route": entry["route"], "route_sha256": sha(route.read_bytes()),
        "input_state": entry["state"], "input_state_sha256": entry["state_sha256"],
        "screenshots_per_rom": len(pairs),
        "screen_size": "224x144", "wram_bytes_per_screen": 65536,
        "different_pixels": totals["png"], "different_wram_bytes": totals["ram"],
        "retained_screenshot_samples": totals["state_samples"],
        "differences": differences,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cases", nargs="+", default=list(DEFAULT_CASES), help="Case names in qa09 replay_index")
    p.add_argument("--out", type=Path, default=ROOT / "build/qa10_replay_comparison.json")
    p.add_argument("--samples", type=Path, help="Save the first and last native screenshots of each case")
    args = p.parse_args()
    rom8 = qa08_rom(ROOT)
    rom9 = ROOT / "build/qa09/Rockman_N1_English_QA09.wsc"
    ensure_sha(rom8, QA08_SHA256)
    ensure_sha(rom9, QA09_SHA256)
    rows = {x["case"]: x for x in json.loads((ROOT / "evidence/qa09/replay_index.json").read_text())}
    cases = []
    failures = []
    with tempfile.TemporaryDirectory(prefix="n1-qa09-regression-") as temporary:
        for index, case in enumerate(args.cases):
            if case not in rows:
                failures.append(f"Unknown case: {case}")
                continue
            try:
                result = compare_case(case, rows[case], rom8, rom9,
                                      Path(temporary) / str(index), args.samples)
                cases.append(result)
            except (OSError, AssertionError, ValueError, subprocess.SubprocessError) as exc:
                failures.append(f"{case}: {type(exc).__name__}: {exc}")
    report = {
        "status": "PASS_SYNTHETIC_REGRESSION" if not failures and all(
            x["status"] == "PASS_PIXEL_RAM_EQUIVALENCE" for x in cases
        ) else "FAIL_OR_REVIEW_REQUIRED",
        "scope": "Replay comparison on unchanged text-resource consumers; no natural victory or hardware claims",
        "qa08_rom_sha256": QA08_SHA256, "qa09_rom_sha256": QA09_SHA256,
        "cases": cases, "failures": failures,
        "total_compared_frames": sum(x["screenshots_per_rom"] for x in cases),
        "total_changed_pixels": sum(x["different_pixels"] for x in cases),
        "total_changed_wram_bytes": sum(x["different_wram_bytes"] for x in cases),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("cases", "failures")}, indent=2))
    for entry in cases:
        print(entry["case"], entry["status"], entry["screenshots_per_rom"], "frames")
    for message in failures:
        print(message, file=sys.stderr)
    return 0 if report["status"] == "PASS_SYNTHETIC_REGRESSION" else 1


if __name__ == "__main__":
    raise SystemExit(main())
