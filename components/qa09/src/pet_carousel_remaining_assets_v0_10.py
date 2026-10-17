#!/usr/bin/env python3
"""Translate the two PET carousel banners omitted by v0.9.

The original audit patched Battle Prep, Shop and BattleChip GP but did not
catalogue the Free Battle or Host Tournament preview maps.  This generator
uses their exclusive 4-bpp banner tiles and keeps all surrounding artwork,
map cells and palettes untouched at the native 224x144 resolution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import location_graphics_assets_v0_9 as gfx


SOURCE_SHA256 = "4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed"
ROM_SIZE = 0x400000


@dataclass(frozen=True)
class CarouselScreen:
    id: str
    original: str
    replacement: str
    map_offset: int
    map_length: int
    map_sha256: str
    tiles_offset: int
    tiles_length: int
    tiles_sha256: str
    columns: int
    tile_pool: tuple[int, ...]


SCREENS = (
    CarouselScreen(
        "free_battle", "フリーバトル", "FREE BATTLE",
        0x0424B6, 0x0480,
        "834a4914cc5ba67c40dfd423a8286d427c516809775e59571b7e155d150c6aae",
        0x079650, 0x1580,
        "263ed97ad2d875bbeaa127f91c168df5f11f9d4c70fad669468e5c6add599dd4",
        9,
        (0x004, 0x006, 0x007, 0x008, 0x009, 0x00A, 0x00B,
         0x00C, 0x00F, 0x010, 0x013, 0x014, 0x0A9),
    ),
    CarouselScreen(
        "host_tournament", "バトルかいさい", "HOST TOURNEY",
        0x042938, 0x0480,
        "9b4a0d7914ad0e29a1eb12a540eaec1552c1ce7edfca74ea06582d05d2547fb2",
        0x07ACA0, 0x15C0,
        "a3a82671c8c6e79b1876ef3f7a903ded219778cf74b32567d28d5012f3d5ee49",
        10,
        (0x004, 0x006, 0x007, 0x008, 0x009, 0x00A, 0x00B,
         0x00C, 0x00D, 0x00E, 0x00F, 0x010, 0x011, 0x012),
    ),
)


def sha256(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def source_span(rom: bytes, offset: int, length: int, expected: str) -> bytes:
    payload = rom[offset:offset + length]
    if len(payload) != length or sha256(payload) != expected:
        raise ValueError(f"unexpected source span at 0x{offset:06X}")
    return payload


def changed_indexes(before: bytes, after: bytes | bytearray) -> set[int]:
    return {
        index
        for index, (source, target) in enumerate(zip(before, after))
        if source != target
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_rom", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    rom = args.source_rom.read_bytes()
    if len(rom) != ROM_SIZE or sha256(rom) != SOURCE_SHA256:
        raise ValueError("unsupported source ROM; expected verified Japanese Rev 1")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Add only the glyphs needed by these two labels to the established 3x5
    # banner alphabet used by v0.9's SHOP and BATTLE CHIP GP patches.
    gfx.FONT.update(
        {
            "D": ("110", "101", "101", "101", "110"),
            "F": ("111", "100", "110", "100", "100"),
            "M": ("101", "111", "111", "101", "101"),
            "R": ("110", "101", "110", "101", "101"),
        }
    )

    reports = []
    outputs = {}
    for spec in SCREENS:
        original_map = source_span(
            rom, spec.map_offset, spec.map_length, spec.map_sha256
        )
        original_tiles = source_span(
            rom, spec.tiles_offset, spec.tiles_length, spec.tiles_sha256
        )
        tilemap = bytearray(original_map)
        tiles = bytearray(original_tiles)
        cells = {
            (x, y)
            for y in (1, 2)
            for x in range(1, 1 + spec.columns)
        }
        references = gfx.assert_exclusive(
            original_map, spec.tile_pool, cells, spec.id
        )
        if gfx.unpack_tile(original_tiles, 0x005) != [10] * 64:
            raise AssertionError(f"{spec.id}: background tile is not solid black")

        record = gfx.draw_banner(
            tilemap,
            tiles,
            label_id=spec.id,
            text=spec.replacement,
            x=1,
            y=1,
            columns=spec.columns,
            pool=spec.tile_pool,
            background_tile=0x005,
            background_colour=10,
            face_colour=7,
            scale_x=1,
            scale_y=2,
        )
        record["original"] = spec.original
        record["replacement"] = spec.replacement

        map_changes = changed_indexes(original_map, tilemap)
        allowed_map = gfx.allowed_map_bytes(cells)
        if map_changes - allowed_map:
            raise AssertionError(f"{spec.id}: map changed outside banner")
        tile_changes = changed_indexes(original_tiles, tiles)
        allowed_tiles = gfx.allowed_tile_bytes(set(spec.tile_pool))
        if tile_changes - allowed_tiles:
            raise AssertionError(f"{spec.id}: tiles changed outside exclusive pool")

        map_name = f"pet_carousel_{spec.id}_bg0_map_v0_10.bin"
        tiles_name = f"pet_carousel_{spec.id}_bg0_tiles_v0_10.bin"
        preview_name = f"pet_carousel_{spec.id}_comparison_v0_10.png"
        map_path = args.output_dir / map_name
        tiles_path = args.output_dir / tiles_name
        preview_path = args.output_dir / preview_name
        map_path.write_bytes(tilemap)
        tiles_path.write_bytes(tiles)

        # The carousel shares the palette-2 banner colours already verified
        # on adjacent Shop/GP previews.  Only the 8x16 banner is rendered.
        gfx.PALETTES[(spec.id, 2)] = gfx.PALETTES[("shop", 2)]
        gfx.comparison_preview(
            spec.id,
            original_map,
            original_tiles,
            tilemap,
            tiles,
            (8, 8, spec.columns * 8, 16),
            spec.replacement,
            preview_path,
        )
        outputs.update(
            {
                map_name: sha256(map_path.read_bytes()),
                tiles_name: sha256(tiles_path.read_bytes()),
                preview_name: sha256(preview_path.read_bytes()),
            }
        )
        reports.append(
            {
                "id": spec.id,
                "source": spec.original,
                "replacement": spec.replacement,
                "native_rect_pixels": [8, 8, spec.columns * 8, 16],
                "map": {
                    "offset": f"0x{spec.map_offset:06X}",
                    "length": spec.map_length,
                    "source_sha256": spec.map_sha256,
                    "output": map_name,
                },
                "tiles": {
                    "offset": f"0x{spec.tiles_offset:06X}",
                    "length": spec.tiles_length,
                    "source_sha256": spec.tiles_sha256,
                    "output": tiles_name,
                },
                "exclusive_references": references,
                "label": record,
                "changes": {
                    "map_bytes": len(map_changes),
                    "tile_bytes": len(tile_changes),
                    "outside_allowlist": 0,
                },
            }
        )

    report = {
        "format": "n1-pet-carousel-remaining-assets-v0.10",
        "status": "PASS",
        "native_display": [224, 144],
        "tile_grid": [28, 18],
        "source_rom_sha256": SOURCE_SHA256,
        "screens": reports,
        "outputs": outputs,
    }
    report_path = args.output_dir / "pet_carousel_remaining_asset_report_v0_10.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
