#!/usr/bin/env python3
"""Build the isolated ``1 MONTH LATER...`` centering adjustment for A7."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import n1tool  # noqa: E402


VERSION = "0.10.7-graphics-a7"
BASE_A6_SHA256 = "9b135e34db6b20d8135c79476bd72a7118500e176ee8f5eee3c0c99fe3bb333b"
ROM_SIZE = 0x400000

# Runtime physical PC 0x2A6F7 maps to ROM offset 0x32A6F7.  This is the
# scene-state 0x0D call that pushes y=8 and x=11 before resolving auxiliary
# string pointer 0x10.  Only its x argument is changed.
CALL_OFFSET = 0x32A6F7
ORIGINAL_CALL = bytes.fromhex("6A 0B")
PATCHED_CALL = bytes.fromhex("6A 06")
CALL_ASSET = "month_later_x_callsite_graphics_a7.bin"
CALL_ASSET_SHA256 = "8fb92af601334ca5905b034f643e675e81f5eb7c13eff845d3a0085d19aad419"

AUX_POINTER_INDEX = 0x10
AUX_POINTER_TABLE = 0x34AB10
AUX_POOL_START = 0x34ACB0
AUX_POINTER_OFFSET = AUX_POINTER_TABLE + AUX_POINTER_INDEX * 2
AUX_POINTER_ASSET = "aux_text_pointers_v0_9.bin"
AUX_POOL_ASSET = "aux_text_pool_v0_10_6.bin"
AUX_EXPECTED_TEXT_BYTES = bytes.fromhex(
    "020000006A006C006B0071006500000069005E00710062006F008700870087000080"
)

SCREEN_WIDTH = 224
CELL_WIDTH = 8
TEXT_CELLS = 16
ORIGINAL_X_CELL = 11
CENTERED_X_CELL = 6
Y_CELL = 8
CHECKSUM_SPAN = (ROM_SIZE - 2, ROM_SIZE)


def sha256(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def changed_runs(before: bytes, after: bytes) -> list[tuple[int, int]]:
    indices = [i for i, pair in enumerate(zip(before, after, strict=True)) if pair[0] != pair[1]]
    if not indices:
        return []
    runs: list[tuple[int, int]] = []
    start = previous = indices[0]
    for index in indices[1:]:
        if index != previous + 1:
            runs.append((start, previous + 1))
            start = index
        previous = index
    runs.append((start, previous + 1))
    return runs


def decode_pool_pointer(payload: bytes) -> tuple[int, int]:
    relative_words = int.from_bytes(payload, "little")
    return relative_words, AUX_POOL_START + relative_words * 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-rom", required=True, type=Path)
    parser.add_argument("--output-rom", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    base = args.base_rom.read_bytes()
    if len(base) != ROM_SIZE or sha256(base) != BASE_A6_SHA256:
        raise ValueError("Graphics Advance 7 requires the exact approved A6 ROM")
    if base[CALL_OFFSET:CALL_OFFSET + len(ORIGINAL_CALL)] != ORIGINAL_CALL:
        raise AssertionError("month-later call site differs from the traced A6 call")

    assets = ROOT / "translation/assets"
    pointers = (assets / AUX_POINTER_ASSET).read_bytes()
    pool = (assets / AUX_POOL_ASSET).read_bytes()
    pointer_position = AUX_POINTER_INDEX * 2
    pointer = pointers[pointer_position:pointer_position + 2]
    relative_words, target = decode_pool_pointer(pointer)
    if target != 0x34AE1A:
        raise AssertionError("auxiliary pointer 0x10 no longer targets the approved pool entry")
    relative = target - AUX_POOL_START
    actual_text = pool[relative:relative + len(AUX_EXPECTED_TEXT_BYTES)]
    if actual_text != AUX_EXPECTED_TEXT_BYTES:
        raise AssertionError("the approved 1 MONTH LATER... text record differs")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    call_path = args.output_dir / CALL_ASSET
    call_path.write_bytes(PATCHED_CALL)
    if sha256(call_path.read_bytes()) != CALL_ASSET_SHA256:
        raise AssertionError("A7 call-site asset identity differs")

    output = bytearray(base)
    output[CALL_OFFSET:CALL_OFFSET + len(PATCHED_CALL)] = PATCHED_CALL
    checksum = n1tool.repair_checksum(output)
    args.output_rom.parent.mkdir(parents=True, exist_ok=True)
    args.output_rom.write_bytes(output)

    allowed = (
        (CALL_OFFSET, CALL_OFFSET + len(PATCHED_CALL)),
        CHECKSUM_SPAN,
    )
    changed = [i for i, pair in enumerate(zip(base, output, strict=True)) if pair[0] != pair[1]]
    outside = [i for i in changed if not any(start <= i < end for start, end in allowed)]
    if outside:
        raise AssertionError(f"A7 changed bytes outside its allowlist: {outside[:8]}")

    report = {
        "status": "PASS",
        "version": VERSION,
        "base_a6_rom_sha256": BASE_A6_SHA256,
        "candidate_rom_sha256": sha256(output),
        "wonder_swan_checksum": f"0x{checksum:04X}",
        "scope": "center only the 1 MONTH LATER... intertitle by changing its scene-specific x argument",
        "trace": {
            "runtime_frame_first_map_write": 2537,
            "runtime_frame_first_visible": 2542,
            "physical_pc": "0x2A6F7",
            "rom_offset": f"0x{CALL_OFFSET:06X}",
            "state": "0x0D",
            "auxiliary_pointer_index": f"0x{AUX_POINTER_INDEX:02X}",
            "auxiliary_pointer_word_offset": f"0x{relative_words:04X}",
            "auxiliary_target": f"0x{target:06X}",
        },
        "geometry": {
            "native_screen": [224, 144],
            "text_cells": TEXT_CELLS,
            "cell_size": [CELL_WIDTH, 16],
            "original_cell_origin": [ORIGINAL_X_CELL, Y_CELL],
            "centered_cell_origin": [CENTERED_X_CELL, Y_CELL],
            "original_pixel_span": [ORIGINAL_X_CELL * CELL_WIDTH,
                                    (ORIGINAL_X_CELL + TEXT_CELLS) * CELL_WIDTH],
            "centered_pixel_span": [CENTERED_X_CELL * CELL_WIDTH,
                                    (CENTERED_X_CELL + TEXT_CELLS) * CELL_WIDTH],
            "screen_center_x": SCREEN_WIDTH // 2,
            "centered_span_center_x": (CENTERED_X_CELL * CELL_WIDTH
                                       + (CENTERED_X_CELL + TEXT_CELLS) * CELL_WIDTH) // 2,
            "horizontal_shift_pixels": (CENTERED_X_CELL - ORIGINAL_X_CELL) * CELL_WIDTH,
            "vertical_position_changed": False,
        },
        "call_site": {
            "before": ORIGINAL_CALL.hex().upper(),
            "after": PATCHED_CALL.hex().upper(),
            "changed_argument": "x cell only: 11 -> 6",
        },
        "protected": {
            "text_record_changed_bytes": 0,
            "auxiliary_pointer_changed_bytes": 0,
            "shared_renderer_changed_bytes": 0,
            "font_tiles_changed_bytes": 0,
            "palettes_changed_bytes": 0,
            "background_maps_changed_bytes": 0,
            "y_argument_changed": False,
        },
        "binary_allowlist": [[f"0x{start:06X}", f"0x{end:06X}"] for start, end in allowed],
        "changed_bytes_vs_a6": len(changed),
        "changed_runs_vs_a6": [[f"0x{start:06X}", f"0x{end:06X}"]
                               for start, end in changed_runs(base, output)],
        "bytes_outside_allowlist": len(outside),
        "call_asset": CALL_ASSET,
        "call_asset_sha256": sha256(call_path.read_bytes()),
    }
    report_path = args.output_dir / "graphics_advance_7_month_later_centering_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
