#!/usr/bin/env python3
"""Replay RC6 selection/Y1/battle fixtures against the MANT04 and new ROM pairs.

The documented synthetic savestates and hash-pinned emulator core are explicit
optional QA inputs. The pinned capture tool is included in this source package.
Private QA inputs are not required to build either translation. This emits PNG/JSON
evidence to --out; ROMs, states, WRAM and SRAM remain under --work-dir.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
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

import qa14_chipcontrol as rc6

CORE_SHA256 = "a7cb2b6eae8787c6757e076b56be00ad7c9b19b511c33d7cd8f4055fdcc1d68d"
CAPTURE_SHA256 = "6b46d507613de96536db6866ea1c1680713ee8511ac0415e8a00ac4c0a2e0327"
CAPTURE = Path(__file__).resolve().parents[1] / "components/qa09/src/qa08_battle_capture.py"
CASES = {
    "guard_fire_native": {
        "state": "docs/qa09/runtime/guard_fire_native/Rockman_N1_English_QA08_guard_fire_native_injected.state",
        "sha256": "47cc1ca97114d3a76925879dcf5fafb8db8da92924395f5ff2467f9ef34a67fe",
        "provenance": "docs/qa09/replay_index.json; guard_fire_native route first step",
    },
    "pierce_shield": {
        "state": "docs/qa09/runtime/pierce_shield/Rockman_N1_English_QA08_pierce_shield_injected.state",
        "sha256": "30296a76ef1f350532be1cdaf9d9873f8568c12c61f3be2aa4a0e9ae98d1ef31",
        "provenance": "docs/qa09/replay_index.json; pierce_shield route first step",
    },
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pinned(path: Path, expected: str) -> None:
    rc6.ensure(path.is_file(), f"Private QA dependency is missing: {path}")
    rc6.ensure(sha(path) == expected, f"Private QA dependency SHA-256 mismatch: {path}")


def selection_route() -> list[dict]:
    # The archived state is on BATTLE START, after the documented diagnostic
    # setup. Confirm it and let the candidate ROM initialize its own selector.
    route = [{"keys": ["a"], "frames": 6}, {"frames": 360, "name": "selection_initial"}]
    route.extend({"keys": ["yup"], "frames": 10, "name": f"y1_hold_{n:03d}"}
                 for n in range(10, 121, 10))
    route.extend([{"frames": 10, "name": "release_010"},
                  {"keys": ["a"], "frames": 15, "name": "confirm_015"},
                  {"frames": 150, "name": "post_confirm_150"}])
    return route


def run_capture(private: Path, rom: Path, state: Path, route: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, QA_ENGINE_DIR=str(private / "qa"),
               AUDIT_ROM_DIR=str(rom.parent), QA_CAPTURE_DIR=str(output))
    command = [sys.executable, str(CAPTURE),
               rom.stem, str(route), str(state), "-", str(output / "cartridge_memory.srm")]
    with (output / "capture.log").open("w", encoding="utf-8") as log:
        subprocess.run(command, cwd=private, env=env, stdout=log,
                       stderr=subprocess.STDOUT, check=True, timeout=45)


def compare(left: Path, right: Path) -> dict:
    a, b = [np.asarray(Image.open(p).convert("RGB"), dtype=np.uint8) for p in (left, right)]
    rc6.ensure(a.shape == b.shape == (144, 224, 3), "A runtime image is not native 224x144")
    x, y = left.with_suffix(".ram").read_bytes(), right.with_suffix(".ram").read_bytes()
    rc6.ensure(len(x) == len(y) == 65536, "Unexpected runtime WRAM length")
    pixel_differences = np.any(a != b, axis=2)
    return {"different_pixels": int(np.count_nonzero(pixel_differences)),
            "player_deck_panel_different_pixels": int(np.count_nonzero(pixel_differences[64:144, 0:110])),
            "different_wram_bytes": sum(m != n for m, n in zip(x, y)),
            "left_png_sha256": sha(left), "right_png_sha256": sha(right),
            "left_wram_sha256": hashlib.sha256(x).hexdigest(),
            "right_wram_sha256": hashlib.sha256(y).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-english", type=Path, required=True)
    parser.add_argument("--reference-chip-control", type=Path, required=True)
    parser.add_argument("--english", type=Path, required=True)
    parser.add_argument("--chip-control", type=Path, required=True)
    parser.add_argument("--private-qa-root", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    private = args.private_qa_root.resolve()
    pinned(private / "qa/emulator/mednafen_wswan_libretro.so", CORE_SHA256)
    pinned(CAPTURE, CAPTURE_SHA256)
    for case in CASES.values():
        pinned(private / case["state"], case["sha256"])
    files = {"mant04_en": args.reference_english, "mant04_cc": args.reference_chip_control,
             "english": args.english, "chip_control": args.chip_control}
    raw = {key: path.read_bytes() for key, path in files.items()}
    static = rc6.verify_pair(raw["mant04_en"], raw["mant04_cc"], raw["english"], raw["chip_control"])

    args.work_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="rc6-runtime-", dir=args.work_dir.resolve()))
    evidence = args.out.resolve()
    # Safe evidence may be in docs/. The raw work path must remain elsewhere.
    rc6.ensure(not work.is_relative_to(evidence), "Raw work cannot be inside distributable evidence")
    evidence.mkdir(parents=True, exist_ok=True)
    paths = {}
    for key, data in raw.items():
        paths[key] = work / (key + ".wsc")
        paths[key].write_bytes(data)
    route = work / "route.json"
    steps = selection_route()
    route.write_text(json.dumps(steps, indent=2) + "\n", encoding="utf-8")
    stages = [step["name"] for step in steps if "name" in step]
    shutil.copyfile(route, evidence / "battle_route.json")
    results = []
    failures = []
    for name, case in CASES.items():
        out = work / name
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = {key: pool.submit(run_capture, private, rom, private / case["state"],
                                    route, out / key) for key, rom in paths.items()}
            for key, job in jobs.items():
                try:
                    job.result()
                except (OSError, subprocess.SubprocessError) as error:
                    failures.append(f"{name}/{key}: {type(error).__name__}: {error}")
        if any(not (out / key / (key + "_post_confirm_150.png")).exists() for key in paths):
            continue
        frames = []
        for stage in stages:
            p = {key: out / key / (key + "_" + stage + ".png") for key in paths}
            comparison = compare(p["mant04_cc"], p["chip_control"])
            english_comparison = compare(p["mant04_en"], p["english"])
            overlay_comparison = compare(p["english"], p["chip_control"])
            if comparison["different_pixels"] or comparison["different_wram_bytes"]:
                failures.append(f"{name}/{stage}: Chip Control changed relative to MANT04")
            if english_comparison["different_pixels"] or english_comparison["different_wram_bytes"]:
                failures.append(f"{name}/{stage}: ordinary English battle changed relative to MANT04")
            if stage.startswith("y1_hold_") and overlay_comparison["player_deck_panel_different_pixels"] == 0:
                failures.append(f"{name}/{stage}: no visible Y1 overlay difference")
            if stage in ("selection_initial", "release_010") and overlay_comparison["player_deck_panel_different_pixels"]:
                failures.append(f"{name}/{stage}: player deck does not match ordinary English with Y1 released")
            frames.append({"stage": stage, "chip_control_vs_mant04": comparison,
                           "english_vs_mant04": english_comparison,
                           "chip_control_vs_english": overlay_comparison})
            # Native, unedited PNGs only; RAM/savestates remain in private work.
            for key, path in p.items():
                destination = evidence / name / key / (stage + ".png")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
        saves = {key: (out / key / "cartridge_memory.srm").read_bytes() for key in paths}
        same_save = len({hashlib.sha256(data).hexdigest() for data in saves.values()}) == 1
        if not same_save or any(len(data) != 32768 for data in saves.values()):
            failures.append(f"{name}: exported cartridge memories differ")
        results.append({"case": name, "access": "INHERITED_SYNTHETIC_SAVESTATE + INPUT_ONLY_REPLAY",
                        "state": case["state"], "state_sha256": case["sha256"],
                        "provenance": case["provenance"], "frames_per_rom": len(frames),
                        "frames": frames, "all_end_sram_identical": same_save,
                        "end_sram_sha256": {key: hashlib.sha256(data).hexdigest() for key, data in saves.items()}})

    report = {"status": "PASS_SCOPED_RC6_RUNTIME_REGRESSION" if not failures and len(results) == len(CASES)
                       else "FAIL_OR_REVIEW_REQUIRED",
              "rom_sha256": {key: hashlib.sha256(data).hexdigest() for key, data in raw.items()},
              "emulator": "Mednafen WonderSwan libretro", "emulator_sha256": CORE_SHA256,
              "capture_script_sha256": CAPTURE_SHA256, "native_resolution": [224, 144],
              "overlay_restore_comparison_bbox_exclusive": [0, 64, 110, 144],
              "route_sha256": sha(route), "static_compatibility": static,
              "cases": results, "failures": failures,
              "compared_chip_control_frames": sum(row["frames_per_rom"] for row in results),
              "direct_visual_review": "RECORDED_SEPARATELY_AFTER_READING_NATIVE_PNGS",
              "limitations": ["Synthetic access; inherited setups include diagnostic WRAM edits",
                              "The replay itself writes only controller inputs, not ROM/WRAM/SRAM",
                              "End-SRAM equality does not prove saving after natural progression",
                              "RC6 intentionally changes the opponent deck; restoration is checked on the player panel while whole-screen regression is checked against MANT04 RC6",
                              "No exhaustive battle combination or physical hardware claim",
                              "Original RC6 assembly sources remain unavailable"]}
    (evidence / "runtime.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "compared_chip_control_frames": report["compared_chip_control_frames"],
                      "failures": failures, "raw_work_dir": str(work),
                      "evidence": str(evidence)}, indent=2))
    return 0 if report["status"] == "PASS_SCOPED_RC6_RUNTIME_REGRESSION" else 1


if __name__ == "__main__":
    raise SystemExit(main())
