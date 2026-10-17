#!/usr/bin/env python3
"""Generate the fully English three-page entry-name keyboard for v0.9.

Version 0.8 selected the built-in Latin page by default but still exposed two
kana pages as JP1/JP2.  The auxiliary-text repack now supplies lowercase and
uppercase rows for those pages.  This generator changes their selector labels
to LOW/CAP, keeps the original numeric/A-Z page as ABC, and preserves BACK/OK.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import struct
import sys
from pathlib import Path
from typing import Any


ASSET_TILES = "name_keyboard_tiles_v0_9.bin"
ASSET_MAP = "name_keyboard_bg0_map_v0_9.bin"
REPORT_NAME = "name_keyboard_asset_report_v0_9.json"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_v08(root: Path) -> Any:
    path = root / "src" / "name_keyboard_assets_v0_8.py"
    spec = importlib.util.spec_from_file_location("name_keyboard_v08_for_v09", path)
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
    rom = args.rom.read_bytes()
    if len(rom) != 0x400000 or sha256(rom) != old.SOURCE_ROM_SHA256:
        raise ValueError("unexpected source ROM; expected verified Japanese Rev 1")

    source_tiles = rom[old.TILE_START:old.TILE_START + old.TILE_LENGTH]
    source_map = rom[old.MAP_START:old.MAP_START + old.MAP_LENGTH]
    palette = rom[old.PALETTE_START:old.PALETTE_START + old.PALETTE_LENGTH]
    if sha256(source_tiles) != old.TILE_SOURCE_SHA256:
        raise ValueError("unexpected keyboard tile source span")
    if sha256(source_map) != old.MAP_SOURCE_SHA256:
        raise ValueError("unexpected keyboard map source span")
    if sha256(palette) != old.PALETTE_SOURCE_SHA256:
        raise ValueError("unexpected keyboard palette")

    # Extend the compact alphabet only with glyphs needed by LOW.  CAP, ABC,
    # BACK and OK! already exist in the v0.8 renderer.
    old.FONT_3X5.update({
        "L": ("100", "100", "100", "100", "111"),
        "W": ("101", "101", "111", "111", "101"),
    })

    tiles = bytearray(source_tiles)
    tilemap = bytearray(source_map)
    header = old.replace_header(tiles, tilemap)

    values = list(struct.unpack("<" + "H" * (len(tilemap) // 2), tilemap))
    for tile_id in range(0x10, 0x17):
        if any((entry & 0x01FF) == tile_id for entry in values):
            raise ValueError(f"reserved CAP tile 0x{tile_id:02X} is unexpectedly referenced")

    # LOW keeps the first selector's original exclusive 3x2 tile rectangle.
    old.write_canvas(
        tiles,
        old.compact_canvas("LOW", 24, 16, 2, 2),
        24,
        ((0x23, 0x24, 0x25), (0x26, 0x27, 0x28)),
    )

    # The Japanese source shared four tiles between selectors one and two.
    # The English header freed 0x10-0x16, so CAP gets six independent tiles.
    old.write_canvas(
        tiles,
        old.compact_canvas("CAP", 24, 16, 2, 2),
        24,
        ((0x10, 0x11, 0x12), (0x13, 0x14, 0x15)),
    )
    cap_positions = (
        (23, 9, 0x10), (24, 9, 0x11), (25, 9, 0x12),
        (23, 10, 0x13), (24, 10, 0x14), (25, 10, 0x15),
    )
    for x, y, tile_id in cap_positions:
        index = y * old.MAP_WIDTH + x
        values[index] = (values[index] & ~0x01FF) | tile_id

    labels = (
        ("ABC", 16, 16, 1, 2, ((0x2B, 0x2C), (0x2D, 0x2E))),
        ("BACK", 24, 16, 1, 2, ((0x2F, 0x30, 0x31), (0x32, 0x33, 0x34))),
        ("OK!", 24, 16, 2, 2, ((0x35, 0x36, 0x37), (0x38, 0x39, 0x3A))),
    )
    for text, width, height, scale_x, scale_y, tile_ids in labels:
        old.write_canvas(
            tiles,
            old.compact_canvas(text, width, height, scale_x, scale_y),
            width,
            tile_ids,
        )
    tilemap[:] = struct.pack("<" + "H" * len(values), *values)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    tile_path = args.output_dir / ASSET_TILES
    map_path = args.output_dir / ASSET_MAP
    preview_path = args.output_dir / "name_keyboard_preview_v0_9.png"
    tile_path.write_bytes(tiles)
    map_path.write_bytes(tilemap)
    old.render_preview(bytes(tiles), bytes(tilemap), palette, preview_path)

    report = {
        "family": "name_keyboard",
        "project_version": "0.9.0",
        "source_rom_sha256": old.SOURCE_ROM_SHA256,
        "format": "WSC 8x8 packed 4-bpp; high nibble is left pixel",
        "spans": [
            {
                "id": "tiles",
                "offset": f"0x{old.TILE_START:06X}",
                "length": old.TILE_LENGTH,
                "source_sha256": old.TILE_SOURCE_SHA256,
                "output_sha256": sha256(tiles),
                "asset": ASSET_TILES,
            },
            {
                "id": "bg0_map",
                "offset": f"0x{old.MAP_START:06X}",
                "length": old.MAP_LENGTH,
                "source_sha256": old.MAP_SOURCE_SHA256,
                "output_sha256": sha256(tilemap),
                "asset": ASSET_MAP,
            },
        ],
        "header": header,
        "selector_labels": [
            {"page": 0, "label": "LOW", "input_rows": "aux pointers 05:01-05:05"},
            {"page": 1, "label": "CAP", "input_rows": "aux pointers 05:06-05:0A"},
            {"page": 2, "label": "ABC", "input_rows": "aux pointers 05:0B-05:0F"},
            {"action": "return", "label": "BACK"},
            {"action": "confirm", "label": "OK!"},
        ],
        "default_page": {
            "value": 2,
            "meaning": "built-in numeric/A-Z page selected on entry",
            "constructor_asset": "name_keyboard_default_latin_v0_8.bin",
        },
        "preview": preview_path.name,
    }
    (args.output_dir / REPORT_NAME).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
