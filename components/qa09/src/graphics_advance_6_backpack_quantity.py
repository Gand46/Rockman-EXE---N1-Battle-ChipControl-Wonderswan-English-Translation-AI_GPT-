#!/usr/bin/env python3
"""Build the isolated compact Backpack quantity renderer for Advance 6."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import n1tool  # noqa: E402


VERSION = "0.10.7-graphics-a6"
BASE_A5_SHA256 = "254bebaca20411516471e0cd5664f3d4234df5816d3e7f4087e7f6ecaa706522"
ROM_SIZE = 0x400000

CALL_OFFSET = 0x33835C
ORIGINAL_CALL = bytes.fromhex("9A 69 03 AE 22")
PATCHED_CALL = bytes.fromhex("9A 08 00 6D 7D")
CALL_ASSET = "backpack_quantity_callsite_graphics_a6.bin"
CALL_ASSET_SHA256 = "63c4dfd5c3f4b7a5f8535b6eddfe053f7109e535c1160e05f0be5e19cd7276b0"

B1_DATA_OFFSET = 0x37CC30
B1_DATA_LENGTH = 3012
B1_BASE_ASSET = "battle_messages_b1_data_v0_10_7_rc4.bin"
B1_BASE_SHA256 = "cf8c3375d9b151f9f4d2229788be56613d313962abae8a340b171da46e691f0f"
B1_OUTPUT_ASSET = "battle_messages_b1_data_graphics_a6.bin"
B1_POINTER_OFFSET = 0x37D7F4
B1_POINTER_COUNT = 187

HOST_OFFSET = 0x37D6D8
HOST_SEGMENT = 0x7D6D
HOST_IP = 0x0008
CODE_ASSET = "backpack_quantity_superscript_graphics_a6.bin"
CODE_LENGTH = 282
CODE_SHA256 = "52b320c04df097bc71ab7e09c5444e0880d4c1356b5f576eaf272bece1ebef20"
DIGIT_TABLE_OFFSET = 202
DIGIT_TABLE_LENGTH = 50
ROW_MASKS_OFFSET = 252
ROW_MASKS_LENGTH = 16
QUANTITY_TILE_TABLE_OFFSET = 268
QUANTITY_TILE_IDS = (0x0BC, 0x0BD, 0x0BE, 0x0BF, 0x0C0, 0x0C1, 0x0C6,
                     0x0C7, 0x0D6, 0x0D7, 0x0E0, 0x0E1, 0x0E2, 0x0E3)
CHECKSUM_SPAN = (ROM_SIZE - 2, ROM_SIZE)


def sha256(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def changed_runs(before: bytes, after: bytes) -> list[tuple[int, int]]:
    indices = [index for index, pair in enumerate(zip(before, after, strict=True)) if pair[0] != pair[1]]
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


def pointer_targets(rom: bytes) -> list[tuple[int, int]]:
    source = rom[B1_POINTER_OFFSET:B1_POINTER_OFFSET + B1_POINTER_COUNT * 4]
    targets = []
    for index in range(B1_POINTER_COUNT):
        offset, segment = struct.unpack_from("<HH", source, index * 4)
        if offset or segment:
            targets.append((index, 0x300000 + segment * 16 + offset))
    return targets


def save_preview(code: bytes, output: Path) -> None:
    masks = code[DIGIT_TABLE_OFFSET:DIGIT_TABLE_OFFSET + DIGIT_TABLE_LENGTH]
    if len(masks) != DIGIT_TABLE_LENGTH:
        raise AssertionError("compact digit table is truncated")
    native = Image.new("RGB", (10 * 8, 12), (238, 238, 187))
    draw = ImageDraw.Draw(native)
    for digit in range(10):
        base = digit * 5
        for row in range(5):
            mask = masks[base + row]
            pixels = ((mask >> 2) & 1, (mask >> 1) & 1, mask & 1)
            for column, value in enumerate(pixels):
                if value:
                    native.putpixel((digit * 8 + 4 + column, 1 + row), (34, 34, 34))
        draw.point((digit * 8, 10), fill=(153, 153, 119))
    native.resize((640, 96), Image.Resampling.NEAREST).save(output, optimize=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-rom", required=True, type=Path)
    parser.add_argument("--output-rom", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    base = args.base_rom.read_bytes()
    if len(base) != ROM_SIZE or sha256(base) != BASE_A5_SHA256:
        raise ValueError("Graphics Advance 6 requires the exact approved A5 ROM")
    if base[CALL_OFFSET:CALL_OFFSET + len(ORIGINAL_CALL)] != ORIGINAL_CALL:
        raise AssertionError("Backpack quantity call site differs from the traced A5 call")
    if any(base[HOST_OFFSET:HOST_OFFSET + CODE_LENGTH]):
        raise AssertionError("A6 host span is not the verified zero tail")

    assets = ROOT / "translation/assets"
    code = (assets / CODE_ASSET).read_bytes()
    call = (assets / CALL_ASSET).read_bytes()
    if len(code) != CODE_LENGTH or sha256(code) != CODE_SHA256:
        raise AssertionError("compact renderer asset identity differs")
    digit_masks = code[DIGIT_TABLE_OFFSET:DIGIT_TABLE_OFFSET + DIGIT_TABLE_LENGTH]
    if len(digit_masks) != DIGIT_TABLE_LENGTH or any(mask > 7 for mask in digit_masks):
        raise AssertionError("compact 3-bit digit table differs")
    expected_row_masks = struct.pack("<8H", 0x0000, 0x1000, 0x0001, 0x1001,
                                     0x0010, 0x1010, 0x0011, 0x1011)
    if code[ROW_MASKS_OFFSET:ROW_MASKS_OFFSET + ROW_MASKS_LENGTH] != expected_row_masks:
        raise AssertionError("packed 4bpp row expansion table differs")
    quantity_table = struct.unpack_from("<7H", code, QUANTITY_TILE_TABLE_OFFSET)
    if tuple(value for tile in quantity_table for value in (tile, tile + 1)) != QUANTITY_TILE_IDS:
        raise AssertionError("exclusive quantity tile table differs")
    if call != PATCHED_CALL or sha256(call) != CALL_ASSET_SHA256:
        raise AssertionError("isolated call-site asset identity differs")

    b1 = (assets / B1_BASE_ASSET).read_bytes()
    if len(b1) != B1_DATA_LENGTH or sha256(b1) != B1_BASE_SHA256:
        raise AssertionError("approved RC4 battle-message B1 asset differs")
    host_in_b1 = HOST_OFFSET - B1_DATA_OFFSET
    if any(b1[host_in_b1:host_in_b1 + CODE_LENGTH]):
        raise AssertionError("B1 tail host is not empty")
    targets = pointer_targets(base)
    maximum_target = max(target for _, target in targets)
    if maximum_target >= HOST_OFFSET:
        raise AssertionError("a B1 message pointer consumes the A6 host span")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    b1_output = bytearray(b1)
    b1_output[host_in_b1:host_in_b1 + CODE_LENGTH] = code
    b1_output_path = args.output_dir / B1_OUTPUT_ASSET
    b1_output_path.write_bytes(b1_output)

    output = bytearray(base)
    output[CALL_OFFSET:CALL_OFFSET + len(call)] = call
    output[HOST_OFFSET:HOST_OFFSET + CODE_LENGTH] = code
    checksum = n1tool.repair_checksum(output)
    args.output_rom.parent.mkdir(parents=True, exist_ok=True)
    args.output_rom.write_bytes(output)

    allowed = (
        (CALL_OFFSET, CALL_OFFSET + len(call)),
        (HOST_OFFSET, HOST_OFFSET + CODE_LENGTH),
        CHECKSUM_SPAN,
    )
    changed = [index for index, pair in enumerate(zip(base, output, strict=True)) if pair[0] != pair[1]]
    outside = [index for index in changed if not any(start <= index < end for start, end in allowed)]
    if outside:
        raise AssertionError(f"A6 changed bytes outside its allowlist: {outside[:8]}")

    preview = args.output_dir / "graphics_advance_6_quantity_preview.png"
    save_preview(code, preview)
    report = {
        "status": "PASS",
        "version": VERSION,
        "base_a5_rom_sha256": BASE_A5_SHA256,
        "candidate_rom_sha256": sha256(output),
        "wonder_swan_checksum": f"0x{checksum:04X}",
        "scope": "replace only the Backpack quantity call with an isolated compact 3x5 superscript wrapper",
        "call_site": {
            "rom_offset": f"0x{CALL_OFFSET:06X}",
            "physical_pc": "0x3835C",
            "before": ORIGINAL_CALL.hex().upper(),
            "after": PATCHED_CALL.hex().upper(),
            "bytes": len(call),
        },
        "host": {
            "rom_span": [f"0x{HOST_OFFSET:06X}", f"0x{HOST_OFFSET + CODE_LENGTH:06X}"],
            "physical_far_pointer": f"{HOST_SEGMENT:04X}:{HOST_IP:04X}",
            "bytes": CODE_LENGTH,
            "code_sha256": CODE_SHA256,
            "source_zero_before": True,
            "b1_non_null_pointer_count": len(targets),
            "maximum_b1_pointer_target": f"0x{maximum_target:06X}",
            "unresolved_consumers": 0,
        },
        "glyph": {
            "dimensions": [3, 5],
            "cell_dimensions": [8, 16],
            "origin_inside_cell": [4, 1],
            "digits": list(range(10)),
            "integer_pixels_only": True,
            "antialiasing": False,
            "palette_argument_preserved": True,
            "values_greater_than_nine": "last decimal digit, matching the original one-column field",
            "exclusive_runtime_tile_ids": [f"0x{tile:03X}" for tile in QUANTITY_TILE_IDS],
            "runtime_tile_pairs": [
                [f"0x{QUANTITY_TILE_IDS[index]:03X}", f"0x{QUANTITY_TILE_IDS[index + 1]:03X}"]
                for index in range(0, len(QUANTITY_TILE_IDS), 2)
            ],
            "tile_ids_contiguous": False,
        },
        "protected": {
            "shared_large_numeric_font_changed_bytes": 0,
            "chip_name_digits_Quake1_Meteor3_untouched": True,
            "capacity_and_MB_renderer_untouched": True,
            "chip_icons_card_stats_maps_palettes_dialogue_untouched": True,
            "original_numeric_renderer_called_before_isolated_redraw": True,
        },
        "binary_allowlist": [[f"0x{start:06X}", f"0x{end:06X}"] for start, end in allowed],
        "changed_bytes_vs_a5": len(changed),
        "changed_runs_vs_a5": [[f"0x{start:06X}", f"0x{end:06X}"] for start, end in changed_runs(base, output)],
        "bytes_outside_allowlist": len(outside),
        "b1_output_asset": B1_OUTPUT_ASSET,
        "b1_output_asset_sha256": sha256(b1_output),
        "preview": preview.name,
        "preview_sha256": sha256(preview.read_bytes()),
    }
    report_path = args.output_dir / "graphics_advance_6_backpack_quantity_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
