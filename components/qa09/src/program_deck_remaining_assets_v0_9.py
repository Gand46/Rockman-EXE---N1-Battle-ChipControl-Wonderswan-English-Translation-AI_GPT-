#!/usr/bin/env python3
"""Replace the last mapped Japanese Program Deck label with NORMAL30.

The v0.8 manual atlas translated the structural labels but retained
``ノーマル30`` on the Data and Capacity page.  Its sixteen tiles are exclusive
to that mapped rectangle, so the change needs no tilemap rewrite.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


V08_ASSET = "program_deck_manual_internal_tiles_v0_8.bin"
V08_ASSET_SHA256 = "524475266b0fb24ad1bd4b513f2d0a1ba9316699852fe66debdd1affe2d4f3d8"
V09_ASSET = "program_deck_manual_internal_tiles_v0_9.bin"
REPORT_NAME = "program_deck_remaining_asset_report_v0_9.json"

LABEL_RECT = (16, 0, 56, 16)
LABEL_TEXT = "NORMAL30"
ALLOWED_TILE_RANGES = ((0x0ADB90, 0x0ADC90), (0x0ADEB0, 0x0ADFB0))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_v08(root: Path) -> Any:
    path = root / "src" / "program_deck_labels_assets_v0_8.py"
    spec = importlib.util.spec_from_file_location("program_deck_v08_for_v09", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path, help="verified Japanese Rev 1 ROM")
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    old = load_v08(root)
    old.FONT["3"] = ("110", "001", "010", "001", "110")
    source = args.rom.read_bytes()
    if len(source) != 0x400000 or sha256(source) != old.SOURCE_ROM_SHA256:
        raise ValueError("unexpected source ROM; expected verified Japanese Rev 1")

    atlas = old.ATLASES["manual"]
    start, length = int(atlas["offset"]), int(atlas["length"])
    if sha256(source[start:start + length]) != str(atlas["sha256"]):
        raise ValueError("unexpected source Program Deck manual atlas")

    v08_path = root / "translation" / "assets" / V08_ASSET
    v08_asset = v08_path.read_bytes()
    if len(v08_asset) != length or sha256(v08_asset) != V08_ASSET_SHA256:
        raise ValueError("unexpected v0.8 Program Deck manual asset")

    reference_path, expected_reference_hash = old.REFERENCES["manual_stats"]
    reference_payload = reference_path.read_bytes()
    if sha256(reference_payload) != expected_reference_hash:
        raise ValueError("unexpected manual_stats reference capture")
    image_module = __import__("PIL.Image", fromlist=["Image"])
    reference = image_module.open(reference_path).convert("RGB")

    output = bytearray(source)
    output[start:start + length] = v08_asset
    before = bytes(output)

    # This page's runtime loader starts its tile stream at a 16-byte phase
    # relative to the larger atlas, so the generic v0.8 atlas index (which
    # assumes one global 32-byte phase) cannot address these tiles.  Rebuild
    # the proven 8x2 exclusive composite directly.  The first column is the
    # small status icon and remains byte-identical; NORMAL30 occupies columns
    # two through eight.
    source_tiles = [
        [old.unpack_tile(source, tile) for tile in range(a, b, 32)]
        for a, b in ALLOWED_TILE_RANGES
    ]
    canvas = [
        source_tiles[y // 8][x // 8][(y % 8) * 8 + x % 8]
        for y in range(16)
        for x in range(64)
    ]
    source_canvas = canvas.copy()
    label_values = [canvas[y * 64 + x] for y in range(16) for x in range(8, 64)]
    background = max(set(label_values), key=label_values.count)
    foreground = max(label_values)
    for y in range(16):
        for x in range(8, 64):
            canvas[y * 64 + x] = background
    glyphs = old.glyph_pixels(LABEL_TEXT, 56, 16)
    for x, y in glyphs:
        canvas[y * 64 + 8 + x] = foreground
    for tile_y, (a, b) in enumerate(ALLOWED_TILE_RANGES):
        for tile_x, tile_offset in enumerate(range(a, b, 32)):
            pixels = [
                canvas[(tile_y * 8 + y) * 64 + tile_x * 8 + x]
                for y in range(8)
                for x in range(8)
            ]
            output[tile_offset:tile_offset + 32] = old.pack_tile(pixels)
    changed_pixels = sum(a != b for a, b in zip(source_canvas, canvas))

    changed_offsets = [index for index, (a, b) in enumerate(zip(before, output)) if a != b]
    if not changed_offsets:
        raise ValueError("NORMAL30 generated no byte changes")
    outside = [
        offset
        for offset in changed_offsets
        if not any(range_start <= offset < range_end for range_start, range_end in ALLOWED_TILE_RANGES)
    ]
    if outside:
        raise ValueError(f"NORMAL30 escaped exclusive tiles: 0x{outside[0]:06X}")
    touched_tiles = sorted({
        range_start + ((offset - range_start) // 32) * 32
        for offset in changed_offsets
        for range_start, range_end in ALLOWED_TILE_RANGES
        if range_start <= offset < range_end
    })
    expected_tiles = [
        tile
        for range_start, range_end in ALLOWED_TILE_RANGES
        for tile in range(range_start + 32, range_end, 32)
    ]
    if touched_tiles != expected_tiles:
        raise ValueError(
            "unexpected NORMAL30 tile set: "
            f"actual={[f'0x{x:06X}' for x in touched_tiles]}"
        )
    changed_tiles = len(touched_tiles)
    if changed_tiles != 14:
        raise ValueError(f"expected 14 changed label tiles, got {changed_tiles}")

    asset = bytes(output[start:start + length])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    asset_path = args.output_dir / V09_ASSET
    asset_path.write_bytes(asset)
    preview_path = args.output_dir / "program_deck_manual_stats_preview_v0_9.png"
    old.render_reference_preview(reference, [(*LABEL_RECT, LABEL_TEXT)], preview_path)

    report = {
        "family": "program_deck_manual_stats",
        "project_version": "0.9.0",
        "source_rom_sha256": old.SOURCE_ROM_SHA256,
        "source_text": "ノーマル30",
        "translation": LABEL_TEXT,
        "screen_rect": list(LABEL_RECT),
        "map_cells": {"composite": {"x": [1, 8], "y": [0, 1]}, "label": {"x": [2, 8], "y": [0, 1]}},
        "atlas": {
            "offset": f"0x{start:06X}",
            "length": length,
            "source_sha256": str(atlas["sha256"]),
            "v0_8_asset_sha256": V08_ASSET_SHA256,
            "v0_9_asset": V09_ASSET,
            "v0_9_asset_sha256": sha256(asset),
        },
        "exclusive_tile_ranges": [
            {"start": f"0x{a:06X}", "end_exclusive": f"0x{b:06X}"}
            for a, b in ALLOWED_TILE_RANGES
        ],
        "changed_tiles": changed_tiles,
        "changed_pixels": changed_pixels,
        "changed_bytes": len(changed_offsets),
        "preview": preview_path.name,
    }
    (args.output_dir / REPORT_NAME).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
