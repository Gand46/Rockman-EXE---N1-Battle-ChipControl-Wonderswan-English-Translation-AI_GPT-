#!/usr/bin/env python3
"""Harmonize the main CHIP FOLDER header with the approved Advance 3 art."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import graphics_advance_3_header as a3  # noqa: E402


VERSION = "0.10.7-graphics-a5"
BASE_ROM_SHA256 = "e640da75a810a3cc7699c93333d164dfbf444baef006c5d26bbec176d84d62c8"
ROM_SIZE = 0x400000
MAP_OFFSET = 0x043F40
MAP_LENGTH = 0x0680
MAP_SHA256 = "41e54fd79cc046fa9b5cadfd1c47d2a884f4db2a7dda7ad763185cc40c79f80c"
MAP_OUTPUT_SHA256 = "23172a777fb2f55434e275171a8dbe60868300977469690107cd4864e8b5eb85"
PROGRAM_ALT_MAP_OFFSET = 0x0438BE
PROGRAM_ALT_MAP_LENGTH = 0x0680
PROGRAM_ALT_MAP_SHA256 = "6559d3beccaaeeabb1aaf80f918e1e01cc05de10fd3ddc669f7402ba36892a5b"
TILES_OFFSET = 0x07EC10
TILES_LENGTH = 0x16C0
TILES_SHA256 = "cf7edb4fac473457eb051623d9317f71f4153f61eaf8c3590346160221a26c0f"
STATS_MAP_OFFSET = 0x04EC24
STATS_MAP_LENGTH = 0x0400
STATS_MAP_SHA256 = "ed8ae281f04b285ce93c5ad92411ce2643fd1ece8600a0042f7a10ec1b2d1cad"
STATS_TILES_OFFSET = 0x0ACA20
STATS_TILES_LENGTH = 0x5B60
STATS_TILES_SHA256 = "f465f7ecb14960d06156a34970dc4d98db1f19b101bd68b16ddacd4358a88218"
MAP_WIDTH = 32
TILE_MASK = 0x01FF
TARGET_CELLS = tuple((x, y) for y in range(2) for x in range(11, 17))
APPROVED_TILE_IDS = (
    0x02A, 0x02B, 0x02C, 0x02D, 0x02E, 0x02F,
    0x030, 0x037, 0x038, 0x039, 0x03A, 0x03B,
)
EXPECTED_SOURCE_WORDS = (
    0x2405, 0x2406, 0x2407, 0x2408, 0x2409, 0x240A,
    0x2417, 0x2418, 0x2419, 0x241A, 0x241B, 0x241C,
)
MAPS = {
    "program_alt": (0x0438BE, 0x0680),
    "chip_folder": (0x043F40, 0x0680),
    "backpack": (0x0445C2, 0x0680),
    "data_library": (0x044C44, 0x0680),
}


def sha256(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def word_at(tilemap: bytes | bytearray, x: int, y: int) -> int:
    offset = (y * MAP_WIDTH + x) * 2
    return int.from_bytes(tilemap[offset:offset + 2], "little")


def set_tile_id(tilemap: bytearray, x: int, y: int, tile_id: int) -> tuple[int, int]:
    offset = (y * MAP_WIDTH + x) * 2
    before = int.from_bytes(tilemap[offset:offset + 2], "little")
    after = (before & ~TILE_MASK) | tile_id
    tilemap[offset:offset + 2] = after.to_bytes(2, "little")
    return before, after


def consumers(rom: bytes, override: bytes | None = None) -> dict[str, list[list[object]]]:
    graph = {f"0x{tile:03X}": [] for tile in APPROVED_TILE_IDS}
    for name, (offset, length) in MAPS.items():
        tilemap = override if name == "chip_folder" and override is not None else rom[offset:offset + length]
        for position in range(0, length, 2):
            tile = int.from_bytes(tilemap[position:position + 2], "little") & TILE_MASK
            key = f"0x{tile:03X}"
            if key in graph:
                cell = position // 2
                graph[key].append([name, cell % MAP_WIDTH, cell // MAP_WIDTH])
    return graph


def expected_consumers(after: bool) -> dict[str, list[list[object]]]:
    result: dict[str, list[list[object]]] = {}
    for index, tile in enumerate(APPROVED_TILE_IDS):
        y, column = divmod(index, 6)
        rows = [["program_alt", 10 + column, y]]
        if after:
            rows.append(["chip_folder", 11 + column, y])
        result[f"0x{tile:03X}"] = rows
    return result


def render_header(tilemap: bytes, bank: bytes) -> Image.Image:
    image = Image.new("RGB", (48, 16), (85, 102, 102))
    colours = {
        2: (51, 51, 51), 3: (85, 102, 102), 6: (255, 136, 0),
        9: (51, 51, 51), 15: (238, 221, 204),
    }
    for y in range(2):
        for column, x in enumerate(range(11, 17)):
            tile_id = word_at(tilemap, x, y) & TILE_MASK
            tile = a3.unpack_tile(bank[tile_id * a3.TILE_BYTES:(tile_id + 1) * a3.TILE_BYTES])
            for py in range(8):
                for px in range(8):
                    value = tile[py * 8 + px]
                    image.putpixel((column * 8 + px, y * 8 + py), colours.get(value, (value * 17,) * 3))
    return image


def save_preview(before_map: bytes, after_map: bytes, bank: bytes, output: Path) -> None:
    scale, gap, caption = 8, 24, 28
    source = render_header(before_map, bank).resize((384, 128), Image.Resampling.NEAREST)
    target = render_header(after_map, bank).resize((384, 128), Image.Resampling.NEAREST)
    image = Image.new("RGB", (384 * 2 + gap, 128 + caption), (24, 24, 24))
    draw = ImageDraw.Draw(image)
    draw.text((0, 6), "A4 main CHIP FOLDER", fill="white")
    draw.text((384 + gap, 6), "A5 approved A3 pattern", fill="white")
    image.paste(source, (0, caption))
    image.paste(target, (384 + gap, caption))
    image.save(output, optimize=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-rom", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    rom = args.base_rom.read_bytes()
    if len(rom) != ROM_SIZE or sha256(rom) != BASE_ROM_SHA256:
        raise ValueError("Graphics Advance 5 requires the exact approved A4 ROM")

    source_map = rom[MAP_OFFSET:MAP_OFFSET + MAP_LENGTH]
    alt_map = rom[PROGRAM_ALT_MAP_OFFSET:PROGRAM_ALT_MAP_OFFSET + PROGRAM_ALT_MAP_LENGTH]
    bank = rom[TILES_OFFSET:TILES_OFFSET + TILES_LENGTH]
    stats_map = rom[STATS_MAP_OFFSET:STATS_MAP_OFFSET + STATS_MAP_LENGTH]
    stats_tiles = rom[STATS_TILES_OFFSET:STATS_TILES_OFFSET + STATS_TILES_LENGTH]
    identities = (
        ("main CHIP FOLDER map", source_map, MAP_SHA256),
        ("alternate Program Deck map", alt_map, PROGRAM_ALT_MAP_SHA256),
        ("shared CHIP FOLDER bank", bank, TILES_SHA256),
        ("A4 statistics map", stats_map, STATS_MAP_SHA256),
        ("A4 statistics tiles", stats_tiles, STATS_TILES_SHA256),
    )
    for name, payload, expected in identities:
        if sha256(payload) != expected:
            raise ValueError(f"{name} differs from the approved A4 resource")

    source_words = tuple(word_at(source_map, x, y) for x, y in TARGET_CELLS)
    if source_words != EXPECTED_SOURCE_WORDS:
        raise AssertionError("main CHIP FOLDER source words differ")
    approved_words = tuple(word_at(alt_map, 10 + index % 6, index // 6) for index in range(12))
    if tuple(word & TILE_MASK for word in approved_words) != APPROVED_TILE_IDS:
        raise AssertionError("A3 approved CHIP FOLDER references differ")
    if any((word & ~TILE_MASK) != 0x2400 for word in source_words + approved_words):
        raise AssertionError("target palette/attribute words differ")
    before_graph = consumers(rom)
    if before_graph != expected_consumers(False):
        raise AssertionError("approved A3 tile consumers differ before A5")

    output_map = bytearray(source_map)
    changes = []
    for (x, y), tile_id in zip(TARGET_CELLS, APPROVED_TILE_IDS, strict=True):
        before, after = set_tile_id(output_map, x, y, tile_id)
        if (before & ~TILE_MASK) != (after & ~TILE_MASK):
            raise AssertionError("A5 altered a map attribute")
        changes.append({
            "cell": [x, y], "before": f"0x{before:04X}", "after": f"0x{after:04X}",
            "approved_tile_id": f"0x{tile_id:03X}",
        })
    output_map = bytes(output_map)
    if sha256(output_map) != MAP_OUTPUT_SHA256:
        raise AssertionError("A5 main map output identity differs")
    changed_bytes = [i for i, pair in enumerate(zip(source_map, output_map, strict=True)) if pair[0] != pair[1]]
    if len(changed_bytes) != 12 or any(index % 2 for index in changed_bytes):
        raise AssertionError("A5 must change exactly the low byte of twelve map words")
    after_graph = consumers(rom, output_map)
    if after_graph != expected_consumers(True):
        raise AssertionError("A5 consumer graph is not exactly two consumers per approved tile")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    map_asset = args.output_dir / "pet_submenu_chip_folder_bg0_map_graphics_a5.bin"
    map_asset.write_bytes(output_map)
    (args.output_dir / "program_deck_manual_stats_bg0_map_graphics_a4.bin").write_bytes(stats_map)
    (args.output_dir / "program_deck_manual_internal_tiles_graphics_a4.bin").write_bytes(stats_tiles)
    preview = args.output_dir / "graphics_advance_5_chip_folder_preview.png"
    save_preview(source_map, output_map, bank, preview)
    report = {
        "status": "PASS",
        "version": VERSION,
        "advance": "5 of 6",
        "base_a4_rom_sha256": BASE_ROM_SHA256,
        "scope": "map-only reuse of the approved A3 CHIP FOLDER pattern in the main CHIP FOLDER screen",
        "semantic_source": {"japanese": "チップフォルダ", "english": "CHIP FOLDER"},
        "target_map_offset": f"0x{MAP_OFFSET:06X}",
        "target_cells": [list(cell) for cell in TARGET_CELLS],
        "runtime_rectangle": [88, 0, 136, 16],
        "source_map_sha256": MAP_SHA256,
        "output_map_sha256": sha256(output_map),
        "changed_map_cells": changes,
        "changed_map_bytes": len(changed_bytes),
        "changed_tile_bytes": 0,
        "changed_palette_bytes": 0,
        "changed_map_attributes": 0,
        "approved_tile_ids": [f"0x{tile:03X}" for tile in APPROVED_TILE_IDS],
        "approved_tile_bank_sha256": TILES_SHA256,
        "approved_pattern_bytes_reused_without_modification": True,
        "consumer_graph_before": before_graph,
        "consumer_graph_after": after_graph,
        "consumers_per_approved_tile_after": 2,
        "unresolved_external_consumers": 0,
        "a4_assets_recovered_from_verified_a4_rom": {
            "program_deck_manual_stats_bg0_map_graphics_a4.bin": STATS_MAP_SHA256,
            "program_deck_manual_internal_tiles_graphics_a4.bin": STATS_TILES_SHA256,
        },
        "output_asset": map_asset.name,
        "preview": preview.name,
        "preview_sha256": sha256(preview.read_bytes()),
    }
    report_path = args.output_dir / "graphics_advance_5_chip_folder_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
