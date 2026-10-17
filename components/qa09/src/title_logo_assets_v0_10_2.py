#!/usr/bin/env python3
"""Build the isolated English title-logo assets for N1 Battle v0.10.2.

The user reference is a JPEG-compressed, enlarged composite screenshot.  It is
not inserted directly.  The checked-in 224x112 RGBA master contains only the
clean logo layer, already snapped to the native RGB444 colours.  This tool
encodes that master into the game's fixed 208-tile budget, updates only the
visible logo rows of the existing map, and keeps palettes, background,
PRESS START and credits outside the generated assets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw


SOURCE_ROM_SHA256 = "4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed"
BASE_V0101_SHA256 = "5affee17034c24a17fbc50096ae534b463f6879896c6dd320a54fe0db53bf64b"
REFERENCE_IMAGE_SHA256 = "b71924ad32e3870b8c4be33335991621cd5e22120349528c0639308857381d24"
MASTER_SHA256 = "9f6a15918f5a8016aae4ddef21e71621af3dc0ec137f1adb0f1b21d88cebf83f"

ROM_SIZE = 0x400000
MAP_WIDTH = 32
VISIBLE_WIDTH = 28
LOGO_ROWS = 14
SCREEN_ROWS = 18
TILE_BYTES = 32
TILE_CAPACITY = 208
TILE_BANK_FLAG = 0x2000
TILE_MASK = 0x01FF


@dataclass(frozen=True)
class Region:
    offset: int
    length: int
    source_sha256: str


MAP_REGION = Region(
    0x0409A6,
    0x0480,
    "d873b618f601aad1430fe2bb99b68966808d0aeac0f52223f8c58d245391ff56",
)
TILE_REGION = Region(
    0x071BC0,
    0x1A00,
    "a0d931ca05357275d2410dba82a61ee90dd7e673437e89e4f0b506945829c95c",
)
PALETTE_REGION = Region(
    0x074C68,
    0x00A0,
    "5bbabe397d4dec9fda37d9f6a2e0e5b871118eace3fb1790d8718ce9f7359602",
)

EXPECTED_TILE_SHA256 = "70e121351d3077b8c4e89c6085ed85b0d0e4fc321c4dbbfc632657721e085d2b"
EXPECTED_MAP_SHA256 = "d16eaa95a1829c462f2e036fa4cde8c8c5416579cb8f0a00c128132358535036"


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def source_region(rom: bytes, region: Region, label: str) -> bytes:
    payload = rom[region.offset:region.offset + region.length]
    if len(payload) != region.length:
        raise ValueError(f"{label}: truncated source region")
    actual = sha256(payload)
    if actual != region.source_sha256:
        raise ValueError(
            f"{label}: source SHA-256 {actual} != {region.source_sha256}"
        )
    return payload


def decode_palettes(payload: bytes) -> dict[int, list[tuple[int, int, int]]]:
    if len(payload) != 5 * 16 * 2:
        raise ValueError("title palette block must contain five 16-colour banks")
    result: dict[int, list[tuple[int, int, int]]] = {}
    for palette in range(2, 7):
        colours = []
        base = (palette - 2) * 0x20
        for index in range(16):
            value = int.from_bytes(
                payload[base + index * 2:base + index * 2 + 2], "little"
            )
            # WonderSwan stores these title colours as BGR444.
            colours.append(
                (
                    ((value >> 8) & 0x0F) * 17,
                    ((value >> 4) & 0x0F) * 17,
                    (value & 0x0F) * 17,
                )
            )
        result[palette] = colours
    return result


def pack_tile(pattern: tuple[int, ...]) -> bytes:
    if len(pattern) != 64 or any(not 0 <= value <= 15 for value in pattern):
        raise ValueError("a packed title tile must contain 64 4-bpp pixels")
    return bytes(
        (pattern[y * 8 + x] << 4) | pattern[y * 8 + x + 1]
        for y in range(8)
        for x in range(0, 8, 2)
    )


def unpack_pixel(tiles: bytes, tile: int, x: int, y: int) -> int:
    if not 1 <= tile <= TILE_CAPACITY:
        raise ValueError(f"tile {tile} is outside the logo bank")
    value = tiles[(tile - 1) * TILE_BYTES + y * 4 + x // 2]
    return (value >> 4) & 0x0F if x % 2 == 0 else value & 0x0F


def load_master(path: Path) -> Image.Image:
    payload = path.read_bytes()
    if sha256(payload) != MASTER_SHA256:
        raise ValueError("unexpected v0.10.2 title-logo master")
    with Image.open(path) as source:
        if source.format != "PNG" or source.mode != "RGBA" or source.size != (224, 112):
            raise ValueError("title-logo master must be a native 224x112 RGBA PNG")
        master = source.copy()
    pixels = [
        master.getpixel((x, y))
        for y in range(master.height)
        for x in range(master.width)
    ]
    alpha_values = {pixel[3] for pixel in pixels}
    if not alpha_values <= {0, 255}:
        raise ValueError("title-logo master contains antialiased alpha")
    if any(pixel[:3] != (0, 0, 0) for pixel in pixels if pixel[3] == 0):
        raise ValueError("transparent master pixels must have zero RGB")
    return master


def build_assets(
    master: Image.Image,
    source_map: bytes,
    palettes: dict[int, list[tuple[int, int, int]]],
) -> tuple[bytes, bytes, dict[str, object]]:
    if len(source_map) != MAP_REGION.length:
        raise ValueError("unexpected title-map length")
    pixels = master.load()
    tilemap = bytearray(source_map)
    tile_ids: dict[bytes, int] = {}
    tile_payloads: list[bytes] = []
    cell_records = []
    placement_count = 0
    palette_placements: Counter[int] = Counter()

    for cell_y in range(LOGO_ROWS):
        for cell_x in range(VISIBLE_WIDTH):
            opaque_colours = {
                pixels[cell_x * 8 + x, cell_y * 8 + y][:3]
                for y in range(8)
                for x in range(8)
                if pixels[cell_x * 8 + x, cell_y * 8 + y][3] == 255
            }
            compatible = [
                palette
                for palette in range(2, 7)
                if opaque_colours <= set(palettes[palette][1:])
            ]
            if not compatible:
                raise ValueError(
                    f"cell ({cell_x},{cell_y}) cannot be represented by palettes 2-6"
                )
            # Lowest compatible bank is a stable canonical choice.  The clean
            # master was constructed so this reproduces the reviewed asset.
            palette = compatible[0]
            pattern = []
            for y in range(8):
                for x in range(8):
                    red, green, blue, alpha = pixels[
                        cell_x * 8 + x, cell_y * 8 + y
                    ]
                    if alpha == 0:
                        pattern.append(0)
                    else:
                        pattern.append(
                            palettes[palette].index((red, green, blue))
                        )
            packed = pack_tile(tuple(pattern))
            if any(pattern):
                placement_count += 1
                tile = tile_ids.get(packed)
                if tile is None:
                    tile = len(tile_payloads) + 1
                    if tile > TILE_CAPACITY:
                        raise ValueError(
                            f"title logo needs {tile} unique tiles; capacity is {TILE_CAPACITY}"
                        )
                    tile_ids[packed] = tile
                    tile_payloads.append(packed)
                palette_placements[palette] += 1
            else:
                tile = 0
                palette = 2
            word = TILE_BANK_FLAG | (palette << 9) | tile
            offset = (cell_y * MAP_WIDTH + cell_x) * 2
            tilemap[offset:offset + 2] = word.to_bytes(2, "little")
            cell_records.append(
                {
                    "x": cell_x,
                    "y": cell_y,
                    "tile": tile,
                    "palette": palette,
                    "opaque_pixels": sum(value != 0 for value in pattern),
                }
            )

    tiles = b"".join(tile_payloads)
    tiles += bytes((TILE_CAPACITY - len(tile_payloads)) * TILE_BYTES)
    if len(tiles) != TILE_REGION.length:
        raise AssertionError("generated title bank has the wrong length")

    map_changed_cells = []
    added_cells = []
    cleared_cells = []
    remapped_cells = []
    for cell_y in range(SCREEN_ROWS):
        for cell_x in range(MAP_WIDTH):
            offset = (cell_y * MAP_WIDTH + cell_x) * 2
            old_word = int.from_bytes(source_map[offset:offset + 2], "little")
            new_word = int.from_bytes(tilemap[offset:offset + 2], "little")
            if old_word == new_word:
                continue
            map_changed_cells.append([cell_x, cell_y])
            old_tile, new_tile = old_word & TILE_MASK, new_word & TILE_MASK
            if old_tile == 0 and new_tile != 0:
                added_cells.append([cell_x, cell_y])
            elif old_tile != 0 and new_tile == 0:
                cleared_cells.append([cell_x, cell_y])
            else:
                remapped_cells.append([cell_x, cell_y])

    lower_start = LOGO_ROWS * MAP_WIDTH * 2
    lower_rows_unchanged = source_map[lower_start:] == tilemap[lower_start:]
    hidden_columns_unchanged = all(
        source_map[(y * MAP_WIDTH + x) * 2:(y * MAP_WIDTH + x + 1) * 2]
        == tilemap[(y * MAP_WIDTH + x) * 2:(y * MAP_WIDTH + x + 1) * 2]
        for y in range(LOGO_ROWS)
        for x in range(VISIBLE_WIDTH, MAP_WIDTH)
    )
    if not lower_rows_unchanged or not hidden_columns_unchanged:
        raise AssertionError("generated map escaped the title-logo allowlist")
    if any(y >= LOGO_ROWS or x >= VISIBLE_WIDTH for x, y in map_changed_cells):
        raise AssertionError("generated map changes a protected cell")

    metrics: dict[str, object] = {
        "unique_tiles_used": len(tile_payloads),
        "tile_capacity": TILE_CAPACITY,
        "spare_tiles": TILE_CAPACITY - len(tile_payloads),
        "nonempty_map_placements": placement_count,
        "palette_placements": {
            str(palette): palette_placements[palette]
            for palette in range(2, 7)
        },
        "map_changed_bytes": sum(
            old != new for old, new in zip(source_map, tilemap)
        ),
        "map_changed_cells": len(map_changed_cells),
        "added_cells": len(added_cells),
        "cleared_cells": len(cleared_cells),
        "remapped_cells": len(remapped_cells),
        "changed_cell_coordinates": map_changed_cells,
        "added_cell_coordinates": added_cells,
        "cleared_cell_coordinates": cleared_cells,
        "changed_rows": sorted({y for _x, y in map_changed_cells}),
        "rows_14_17_byte_identical": lower_rows_unchanged,
        "hidden_columns_28_31_byte_identical": hidden_columns_unchanged,
        "cells": cell_records,
    }
    return tiles, bytes(tilemap), metrics


def roundtrip_master(
    tilemap: bytes,
    tiles: bytes,
    palettes: dict[int, list[tuple[int, int, int]]],
) -> Image.Image:
    output = Image.new("RGBA", (224, 112), (0, 0, 0, 0))
    pixels = output.load()
    for y in range(112):
        for x in range(224):
            map_offset = ((y // 8) * MAP_WIDTH + x // 8) * 2
            word = int.from_bytes(tilemap[map_offset:map_offset + 2], "little")
            tile = word & TILE_MASK
            if tile == 0:
                continue
            palette = (word >> 9) & 0x0F
            colour = unpack_pixel(tiles, tile, x & 7, y & 7)
            if colour:
                pixels[x, y] = (*palettes[palette][colour], 255)
    return output


def create_preview(master: Image.Image, output: Path) -> None:
    background = Image.new("RGB", master.size, (5, 12, 16))
    draw = ImageDraw.Draw(background)
    for y in range(0, master.height, 8):
        for x in range(0, master.width, 8):
            if (x // 8 + y // 8) % 2:
                draw.rectangle((x, y, x + 7, y + 7), fill=(11, 28, 32))
    background.paste(master.convert("RGB"), mask=master.getchannel("A"))
    scale = 3
    preview = background.resize(
        (background.width * scale, background.height * scale),
        Image.Resampling.NEAREST,
    )
    preview.save(output)


def patch_qa_rom(
    base_path: Path,
    output_path: Path,
    tiles: bytes,
    tilemap: bytes,
) -> dict[str, object]:
    base = base_path.read_bytes()
    if len(base) != ROM_SIZE or sha256(base) != BASE_V0101_SHA256:
        raise ValueError("optional QA base must be the exact v0.10.1 rebuilt ROM")
    patched = bytearray(base)
    patched[TILE_REGION.offset:TILE_REGION.offset + TILE_REGION.length] = tiles
    patched[MAP_REGION.offset:MAP_REGION.offset + MAP_REGION.length] = tilemap
    patched[-2:] = (sum(patched[:-2]) & 0xFFFF).to_bytes(2, "little")

    allowed = set(range(TILE_REGION.offset, TILE_REGION.offset + TILE_REGION.length))
    allowed.update(
        range(MAP_REGION.offset, MAP_REGION.offset + LOGO_ROWS * MAP_WIDTH * 2)
    )
    allowed.update((ROM_SIZE - 2, ROM_SIZE - 1))
    changed = [index for index, (old, new) in enumerate(zip(base, patched)) if old != new]
    outside = [index for index in changed if index not in allowed]
    if outside:
        raise AssertionError(f"QA ROM changed outside the title allowlist: {outside[:8]}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(patched)
    return {
        "base_sha256": sha256(base),
        "built_sha256": sha256(patched),
        "changed_bytes": len(changed),
        "outside_allowlist": len(outside),
        "stored_checksum": f"0x{int.from_bytes(patched[-2:], 'little'):04X}",
        "calculated_checksum": f"0x{sum(patched[:-2]) & 0xFFFF:04X}",
        "checksum_valid": int.from_bytes(patched[-2:], "little") == sum(patched[:-2]) & 0xFFFF,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-rom", required=True, type=Path)
    parser.add_argument(
        "--master",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "translation/assets/title_logo_master_v0_10_2.png",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "translation/assets",
    )
    parser.add_argument("--base-rom", type=Path)
    parser.add_argument("--patched-rom", type=Path)
    args = parser.parse_args()

    rom = args.source_rom.read_bytes()
    if len(rom) != ROM_SIZE or sha256(rom) != SOURCE_ROM_SHA256:
        raise ValueError("unsupported source ROM; expected verified Japanese Rev 1")
    source_map = source_region(rom, MAP_REGION, "title map")
    source_tiles = source_region(rom, TILE_REGION, "title tiles")
    source_palette = source_region(rom, PALETTE_REGION, "title palettes")
    palettes = decode_palettes(source_palette)
    master = load_master(args.master)
    tiles, tilemap, metrics = build_assets(master, source_map, palettes)
    if sha256(tiles) != EXPECTED_TILE_SHA256:
        raise AssertionError("generated title tiles do not match the reviewed asset")
    if sha256(tilemap) != EXPECTED_MAP_SHA256:
        raise AssertionError("generated title map does not match the reviewed asset")

    roundtrip = roundtrip_master(tilemap, tiles, palettes)
    if roundtrip.tobytes() != master.tobytes():
        raise AssertionError("title asset round-trip differs from the clean master")

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    tile_path = output_dir / "main_logo_tiles_v0_10_2.bin"
    map_path = output_dir / "main_logo_bg0_map_v0_10_2.bin"
    preview_path = output_dir / "title_logo_master_preview_v0_10_2.png"
    report_path = output_dir / "title_logo_asset_report_v0_10_2.json"
    tile_path.write_bytes(tiles)
    map_path.write_bytes(tilemap)
    create_preview(master, preview_path)

    qa = None
    if args.base_rom or args.patched_rom:
        if not args.base_rom or not args.patched_rom:
            raise ValueError("--base-rom and --patched-rom must be supplied together")
        qa = patch_qa_rom(args.base_rom, args.patched_rom, tiles, tilemap)

    opaque_pixels = sum(
        master.getpixel((x, y))[3] == 255
        for y in range(master.height)
        for x in range(master.width)
    )
    opaque_colours = {
        master.getpixel((x, y))[:3]
        for y in range(master.height)
        for x in range(master.width)
        if master.getpixel((x, y))[3] == 255
    }
    report = {
        "format": "n1-title-logo-assets-v0.10.2",
        "status": "PASS",
        "art_direction": (
            "User-supplied English presentation reconstructed as an isolated "
            "native WonderSwan Color logo layer."
        ),
        "reference": {
            "sha256": REFERENCE_IMAGE_SHA256,
            "container_detected": "JPEG/JFIF despite .png filename",
            "dimensions": [1536, 987],
            "distributed": False,
        },
        "master": {
            "file": args.master.name,
            "sha256": MASTER_SHA256,
            "dimensions": [224, 112],
            "format": "RGBA PNG, binary alpha, RGB444 colours only",
            "opaque_pixels": opaque_pixels,
            "transparent_pixels": master.width * master.height - opaque_pixels,
            "unique_opaque_rgb_colours": len(opaque_colours),
        },
        "source_guards": {
            "rom_sha256": SOURCE_ROM_SHA256,
            "tiles": {
                "offset": f"0x{TILE_REGION.offset:06X}",
                "length": TILE_REGION.length,
                "sha256": sha256(source_tiles),
            },
            "map": {
                "offset": f"0x{MAP_REGION.offset:06X}",
                "length": MAP_REGION.length,
                "sha256": sha256(source_map),
            },
            "palettes": {
                "offset": f"0x{PALETTE_REGION.offset:06X}",
                "length": PALETTE_REGION.length,
                "sha256": sha256(source_palette),
                "byte_identical": True,
            },
        },
        "outputs": {
            "tiles": {
                "file": tile_path.name,
                "length": len(tiles),
                "sha256": sha256(tiles),
                "changed_bytes_vs_source": sum(
                    old != new for old, new in zip(source_tiles, tiles)
                ),
            },
            "map": {
                "file": map_path.name,
                "length": len(tilemap),
                "sha256": sha256(tilemap),
            },
            "preview": {
                "file": preview_path.name,
                "sha256": sha256(preview_path.read_bytes()),
                "scale": "3x nearest-neighbour",
            },
        },
        "encoding": {
            "native_screen": [224, 144],
            "logo_layer": [224, 112],
            "tile_format": "8x8 packed 4-bpp, high nibble first",
            "transparent_index": 0,
            "tile_bank_flag": "0x2000",
            "palette_ids": [2, 3, 4, 5, 6],
            "dithering": False,
            "roundtrip_master_exact": True,
        },
        "map_and_capacity_audit": metrics,
        "protected_runtime_elements": {
            "animated_background": "separate map/tiles; not emitted",
            "press_start": "sprite layer; not emitted",
            "credits_and_copyright": "map rows 15-17 byte-identical",
            "row_14": "byte-identical",
            "palettes": "byte-identical",
        },
        "qa_rom": qa,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "tiles_sha256": sha256(tiles),
                "map_sha256": sha256(tilemap),
                "unique_tiles_used": metrics["unique_tiles_used"],
                "spare_tiles": metrics["spare_tiles"],
                "map_changed_cells": metrics["map_changed_cells"],
                "qa_rom": qa,
                "report": report_path.as_posix(),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
