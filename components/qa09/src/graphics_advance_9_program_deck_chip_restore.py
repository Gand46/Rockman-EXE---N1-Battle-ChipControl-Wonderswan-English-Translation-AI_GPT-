#!/usr/bin/env python3
"""Restore the single Program Deck MegaMan-chip quadrant damaged by a tile alias."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw


ROM_SIZE = 0x400000
SOURCE_SHA256 = "4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed"
BASE_A8_SHA256 = "aafa083e8781d58858c35cf729ed18c9269126cba70c789e1e631844071e3749"
MAP_OFFSET = 0x04323C
MAP_LENGTH = 0x0680
BANK_OFFSET = 0x07CD20
BANK_LENGTH = 0x1EF0
BASE_BANK_SHA256 = "87a5b6bde66075a6c92974968b2a486a53584bfd5d63bd568fd2ee25f4f4cc07"
SOURCE_BANK_SHA256 = "ef6d011c4d289338ecbd8c3bdf93da37b271295b442c066e3963ea0d1421bd97"
TILE_BYTES = 32
ASSET_INDEX = 0x0E8
RUNTIME_TILE_ID = ASSET_INDEX + 1
TARGET_CELL = (14, 7)
TARGET_MAP_WORD = 0x2AE9
SOURCE_TILE_SHA256 = "4d8e330c6058c4f08c395eb86258c585499b4fb0a5948a6bf5db68e66c9b75ec"
BASE_TILE_SHA256 = "deb0e38ced1e41de6f92e70e80c418d2d356afaaa99e26f5939dbc7d3ef4772a"
ASSET_NAME = "program_deck_live_ui_tiles_graphics_a9.bin"
REPORT_NAME = "graphics_advance_9_program_deck_chip_restore_report.json"
PREVIEW_NAME = "graphics_advance_9_program_deck_chip_restore_preview.png"


def sha256(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def unpack_tile(payload: bytes) -> list[int]:
    if len(payload) != TILE_BYTES:
        raise ValueError("a 4bpp tile must contain 32 bytes")
    return [value for byte in payload for value in (byte >> 4, byte & 0x0F)]


def consumers(tilemap: bytes, tile_id: int) -> list[list[int]]:
    result: list[list[int]] = []
    for offset in range(0, len(tilemap), 2):
        word = int.from_bytes(tilemap[offset:offset + 2], "little")
        if word & 0x01FF == tile_id:
            cell = offset // 2
            result.append([cell % 32, cell // 32])
    return result


def restore_tile(source_rom: bytes, a8_rom: bytes) -> bytes:
    source_bank = source_rom[BANK_OFFSET:BANK_OFFSET + BANK_LENGTH]
    base_bank = a8_rom[BANK_OFFSET:BANK_OFFSET + BANK_LENGTH]
    if sha256(source_bank) != SOURCE_BANK_SHA256:
        raise ValueError("the verified Japanese Program Deck bank differs")
    if sha256(base_bank) != BASE_BANK_SHA256:
        raise ValueError("the approved A8 Program Deck bank differs")
    start = ASSET_INDEX * TILE_BYTES
    source_tile = source_bank[start:start + TILE_BYTES]
    base_tile = base_bank[start:start + TILE_BYTES]
    if sha256(source_tile) != SOURCE_TILE_SHA256 or sha256(base_tile) != BASE_TILE_SHA256:
        raise ValueError("the aliased Program Deck tile identity differs")
    output = bytearray(base_bank)
    output[start:start + TILE_BYTES] = source_tile
    if output[:start] != base_bank[:start] or output[start + TILE_BYTES:] != base_bank[start + TILE_BYTES:]:
        raise AssertionError("the restoration escaped its exclusive tile")
    return bytes(output)


def write_preview(before: bytes, after: bytes, path: Path) -> None:
    # An indexed preview makes every restored 4bpp pixel visible without
    # depending on runtime palette state. Runtime screenshots remain the
    # authoritative visual gate.
    colours = [
        (18, 18, 18), (45, 51, 64), (75, 83, 98), (238, 221, 170),
        (119, 95, 119), (170, 136, 153), (255, 238, 204), (255, 255, 255),
        (34, 85, 119), (51, 119, 170), (85, 170, 221), (34, 34, 34),
        (102, 102, 119), (153, 153, 170), (204, 204, 204), (255, 255, 255),
    ]
    scale = 24
    cards = []
    for bank in (before, after):
        start = ASSET_INDEX * TILE_BYTES
        pixels = unpack_tile(bank[start:start + TILE_BYTES])
        tile = Image.new("RGB", (8, 8))
        tile.putdata([colours[value] for value in pixels])
        cards.append(tile.resize((8 * scale, 8 * scale), Image.Resampling.NEAREST))
    output = Image.new("RGB", (cards[0].width * 2 + 16, cards[0].height + 32), (12, 12, 12))
    output.paste(cards[0], (0, 32))
    output.paste(cards[1], (cards[0].width + 16, 32))
    draw = ImageDraw.Draw(output)
    draw.text((6, 8), "A8: uniform beige alias", fill="white")
    draw.text((cards[0].width + 22, 8), "A9: original chip quadrant", fill="white")
    output.save(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-rom", required=True, type=Path)
    parser.add_argument("--a8-rom", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    source = args.source_rom.read_bytes()
    base = args.a8_rom.read_bytes()
    if len(source) != ROM_SIZE or sha256(source) != SOURCE_SHA256:
        raise ValueError("Advance 9 requires the verified Japanese Rev 1 ROM")
    if len(base) != ROM_SIZE or sha256(base) != BASE_A8_SHA256:
        raise ValueError("Advance 9 requires the exact approved A8 ROM")
    tilemap = base[MAP_OFFSET:MAP_OFFSET + MAP_LENGTH]
    position = (TARGET_CELL[1] * 32 + TARGET_CELL[0]) * 2
    if int.from_bytes(tilemap[position:position + 2], "little") != TARGET_MAP_WORD:
        raise ValueError("the target Program Deck map word differs")
    target_consumers = consumers(tilemap, RUNTIME_TILE_ID)
    if target_consumers != [list(TARGET_CELL)]:
        raise AssertionError(f"runtime tile 0x{RUNTIME_TILE_ID:03X} is not exclusive: {target_consumers}")

    base_bank = base[BANK_OFFSET:BANK_OFFSET + BANK_LENGTH]
    output_bank = restore_tile(source, base)
    differences = [i for i, pair in enumerate(zip(base_bank, output_bank, strict=True)) if pair[0] != pair[1]]
    expected_range = range(ASSET_INDEX * TILE_BYTES, (ASSET_INDEX + 1) * TILE_BYTES)
    if len(differences) != 29 or any(i not in expected_range for i in differences):
        raise AssertionError("unexpected A8-to-A9 tile-bank delta")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    asset_path = args.output_dir / ASSET_NAME
    preview_path = args.output_dir / PREVIEW_NAME
    asset_path.write_bytes(output_bank)
    write_preview(base_bank, output_bank, preview_path)
    report = {
        "status": "PASS",
        "project_version": "0.10.7-graphics-a9",
        "base_advance_8_sha256": BASE_A8_SHA256,
        "root_cause": "runtime tile N consumes Program Deck asset slot N-1; the earlier toolbar pool patched asset 0x0E8 although map tile 0x0E9 exclusively owns the MegaMan-chip lower-left quadrant",
        "bank_offset": f"0x{BANK_OFFSET:06X}",
        "bank_length": BANK_LENGTH,
        "base_bank_sha256": BASE_BANK_SHA256,
        "output_bank_sha256": sha256(output_bank),
        "asset": ASSET_NAME,
        "asset_sha256": sha256(asset_path.read_bytes()),
        "asset_index_restored": f"0x{ASSET_INDEX:03X}",
        "runtime_tile_id": f"0x{RUNTIME_TILE_ID:03X}",
        "runtime_map_cell": list(TARGET_CELL),
        "runtime_map_word": f"0x{TARGET_MAP_WORD:04X}",
        "screen_rectangle": [112, 56, 120, 64],
        "runtime_consumers": target_consumers,
        "source_tile_sha256": SOURCE_TILE_SHA256,
        "a8_uniform_tile_sha256": BASE_TILE_SHA256,
        "changed_bytes_vs_advance_8": len(differences),
        "maps_palettes_code_pointers_text_changed_bytes": 0,
        "toolbar_tile_ids_protected": [f"0x{tile:03X}" for tile in range(0x0E2, 0x0E9)],
        "preview": PREVIEW_NAME,
        "preview_sha256": sha256(preview_path.read_bytes()),
    }
    (args.output_dir / REPORT_NAME).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
