#!/usr/bin/env python3
"""Build the block-style PET root menu labels for N1 Battle v0.10.4.

The PET root is not rendered with the dialogue font.  Its five menu options
are pre-rendered graphics in a 32x16 BG0 map and a fixed 76-tile, packed 4-bpp
bank.  This generator replaces only the five audited label rectangles.  The
frame, selector sprite, CLASS panel, static credit suffix and runtime-drawn
rank/credit digits remain outside the write allowlist.

The new face is inspired by the supplied block-letter reference, but is drawn
at native WonderSwan pixels: integer coordinates, binary pixels, no scaling
filter and no antialiasing.  It retains the original BG palette indices
(cream 1, grey 9, dark outline 11), so the game palettes are not changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


SOURCE_ROM_SHA256 = "4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed"
BASE_V0103_SHA256 = "eb53372aa5e7e3b202dab7959669d6787c4776c487f9860951012ffb6d8f08dc"
REFERENCE_MENU_SHA256 = "768d6735a55f4b07bab9e6a70127f0a1a4067da0aff7d1d28501617c101ff282"
OBSERVED_MENU_SHA256 = "97b731d05dd7e533c1ed38cadf8a310bb48ba5e381aa52935e3108f278d0e9bf"

MAP_OFFSET = 0x042DBA
MAP_LENGTH = 0x0400
MAP_SOURCE_SHA256 = "1e816281c017da01c3a882416a619f82af51e7ec5de45cd30a8c1880571f4d2b"
TILES_OFFSET = 0x07C330
TILES_LENGTH = 0x0980
TILES_SOURCE_SHA256 = "578f8463a08f42a0e1d175f01177db119c2418b2f859c575e1972480ae95710e"

BASE_MAP_NAME = "pet_labels_bg0_map_v0_8.bin"
BASE_MAP_SHA256 = "11a007a699e9b665f80f9b92d2ff59a0632454c04f5f936c6bd2d738950d4162"
BASE_TILES_NAME = "pet_labels_tiles_v0_8.bin"
BASE_TILES_SHA256 = "778b7b1a4d7000f53910544e7c2c4d7f2a0f692627e3b5ffaaf39bd2bedd951f"
BASE_SCREENSHOT_NAME = "pet_root_clean_v0_8.png"
BASE_SCREENSHOT_SHA256 = "31608f3f64de32dae2501c74f921941ec284a75c5296a975c3668e7bb749478a"

OUTPUT_MAP_NAME = "pet_labels_bg0_map_v0_10_4.bin"
OUTPUT_TILES_NAME = "pet_labels_tiles_v0_10_4.bin"
OUTPUT_PREVIEW_NAME = "pet_root_menu_font_preview_v0_10_4.png"
OUTPUT_REPORT_NAME = "pet_root_menu_font_asset_report_v0_10_4.json"
OUTPUT_MAP_SHA256 = "926376a47eaca5620b0fd2e58a0a9d85d01dd3cc0588d3c59acfe02f3c590c9c"
OUTPUT_TILES_SHA256 = "f1767e86841d884a737d0b7137be1eefa287a3849e41a2d04c6abfc18357d2a2"
OUTPUT_PREVIEW_SHA256 = "751c0b0490e82a3785cc7aed22b631848b9e91da64fa9d3abf0cfa1c2f118f73"

MAP_WIDTH = 32
TILE_BYTES = 32
FIRST_TILE_ID = 1
LAST_TILE_ID = 0x4C
BACKGROUND_TILE_ID = 0x06
BACKGROUND_INDEX = 9
FACE_INDEX = 1
OUTLINE_INDEX = 11


@dataclass(frozen=True)
class Label:
    id: str
    text: str
    x: int
    y: int
    columns: int
    inset: int


# Two map rows per label.  The rectangles stop before the vertical frame at
# x=11 and do not include the right-hand CLASS panel.
LABELS = (
    Label("program_deck", "PROGRAM DECK", 2, 2, 8, 1),
    Label("chip_folder", "CHIP FOLDER", 2, 5, 7, 1),
    Label("data_library", "DATA LIBRARY", 2, 8, 8, 0),
    Label("netnavi", "NETNAVI", 2, 11, 5, 1),
    Label("save", "SAVE", 2, 14, 3, 1),
)


# Tile IDs used by the v0.8 narrow menu lettering.  They occur only in the
# rectangles above.  Nine Japanese-only patterns retired by v0.8 complete the
# fixed-capacity replacement pool.  Tile 0x45 is not retired: runtime appends
# row 16 to the 32x16 ROM map and uses it for the panel's lower-right corner.
# CLASS (0x3C-0x41) and frame tiles 0x45/0x46 are intentionally absent.
RETIRED_TILE_IDS = (0x42, 0x43, 0x44, 0x47, 0x48, 0x49, 0x4A, 0x4B, 0x4C)


# Variable-width block capitals.  Unlike the v0.8 face, the 7-pixel glyphs are
# not stretched vertically: their near-square proportions are the defining
# feature of the supplied reference.  A one-pixel dark outline is added at
# native resolution.  Glyphs deliberately remain uppercase to preserve the
# PET interface's established hierarchy.
FONT = {
    "A": (".##.", "#..#", "#..#", "####", "#..#", "#..#", "#..#"),
    "B": ("###.", "#..#", "#..#", "###.", "#..#", "#..#", "###."),
    "C": (".###", "#...", "#...", "#...", "#...", "#...", ".###"),
    "D": ("###.", "#..#", "#..#", "#..#", "#..#", "#..#", "###."),
    "E": ("####", "#...", "#...", "###.", "#...", "#...", "####"),
    "F": ("####", "#...", "#...", "###.", "#...", "#...", "#..."),
    "G": (".###", "#...", "#...", "#.##", "#..#", "#..#", ".###"),
    "H": ("#..#", "#..#", "#..#", "####", "#..#", "#..#", "#..#"),
    "I": ("###", ".#.", ".#.", ".#.", ".#.", ".#.", "###"),
    "K": ("#..#", "#.#.", "##..", "#...", "##..", "#.#.", "#..#"),
    "L": ("#...", "#...", "#...", "#...", "#...", "#...", "####"),
    "M": ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    "N": ("#..#", "##.#", "##.#", "#.##", "#.##", "#..#", "#..#"),
    "O": (".##.", "#..#", "#..#", "#..#", "#..#", "#..#", ".##."),
    "P": ("###.", "#..#", "#..#", "###.", "#...", "#...", "#..."),
    "R": ("###.", "#..#", "#..#", "###.", "##..", "#.#.", "#..#"),
    "S": (".###", "#...", "#...", ".##.", "...#", "...#", "###."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "V": ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "Y": ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
}


def sha256(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_guarded(path: Path, expected_length: int, expected_sha256: str, label: str) -> bytes:
    payload = path.read_bytes()
    if len(payload) != expected_length:
        raise ValueError(f"{label}: length {len(payload)} != {expected_length}")
    actual = sha256(payload)
    if actual != expected_sha256:
        raise ValueError(f"{label}: SHA-256 {actual} != {expected_sha256}")
    return payload


def map_word(tilemap: bytes | bytearray, x: int, y: int) -> int:
    offset = (y * MAP_WIDTH + x) * 2
    return int.from_bytes(tilemap[offset:offset + 2], "little")


def put_map_word(tilemap: bytearray, x: int, y: int, word: int) -> None:
    offset = (y * MAP_WIDTH + x) * 2
    tilemap[offset:offset + 2] = word.to_bytes(2, "little")


def unpack_tile(payload: bytes | bytearray) -> tuple[int, ...]:
    if len(payload) != TILE_BYTES:
        raise ValueError("a menu tile must contain 32 bytes")
    return tuple(value for byte in payload for value in (byte >> 4, byte & 15))


def pack_tile(pixels: tuple[int, ...] | list[int]) -> bytes:
    if len(pixels) != 64 or any(not 0 <= value <= 15 for value in pixels):
        raise ValueError("a menu tile must contain 64 4-bpp pixels")
    return bytes((pixels[index] << 4) | pixels[index + 1] for index in range(0, 64, 2))


def tile_bytes(tiles: bytes | bytearray, tile_id: int) -> bytes:
    if not FIRST_TILE_ID <= tile_id <= LAST_TILE_ID:
        raise ValueError(f"tile ID {tile_id:#x} is outside the PET bank")
    start = (tile_id - FIRST_TILE_ID) * TILE_BYTES
    return bytes(tiles[start:start + TILE_BYTES])


def put_tile(tiles: bytearray, tile_id: int, pattern: bytes) -> None:
    if len(pattern) != TILE_BYTES:
        raise ValueError("invalid packed pattern")
    start = (tile_id - FIRST_TILE_ID) * TILE_BYTES
    tiles[start:start + TILE_BYTES] = pattern


def text_width(text: str) -> int:
    width = 0
    for index, character in enumerate(text):
        if character == " ":
            width += 3
        else:
            if character not in FONT:
                raise ValueError(f"missing block glyph {character!r}")
            width += len(FONT[character][0])
            if index + 1 < len(text) and text[index + 1] != " ":
                width += 1
    return width


def render_label(label: Label) -> tuple[list[bytes], dict[str, int]]:
    width = label.columns * 8
    height = 16
    face_width = text_width(label.text)
    outlined_width = face_width + 2
    if label.inset < 0 or label.inset + outlined_width > width:
        raise ValueError(f"{label.id}: {outlined_width}px text does not fit {width}px")

    mask = [[False] * width for _ in range(height)]
    cursor = label.inset + 1
    for index, character in enumerate(label.text):
        if character == " ":
            cursor += 3
            continue
        glyph = FONT[character]
        face_y = 4
        for glyph_y, row in enumerate(glyph):
            for glyph_x, value in enumerate(row):
                if value == "#":
                    mask[face_y + glyph_y][cursor + glyph_x] = True
        cursor += len(glyph[0])
        if index + 1 < len(label.text) and label.text[index + 1] != " ":
            cursor += 1

    canvas = [[BACKGROUND_INDEX] * width for _ in range(height)]
    for y in range(height):
        for x in range(width):
            if not mask[y][x]:
                continue
            for delta_y in (-1, 0, 1):
                for delta_x in (-1, 0, 1):
                    target_x, target_y = x + delta_x, y + delta_y
                    if 0 <= target_x < width and 0 <= target_y < height:
                        canvas[target_y][target_x] = OUTLINE_INDEX
    for y in range(height):
        for x in range(width):
            if mask[y][x]:
                canvas[y][x] = FACE_INDEX

    patterns = []
    for cell_y in range(2):
        for cell_x in range(label.columns):
            pixels = tuple(
                canvas[cell_y * 8 + y][cell_x * 8 + x]
                for y in range(8) for x in range(8)
            )
            patterns.append(pack_tile(pixels))
    metrics = {
        "face_width_pixels": face_width,
        "outlined_width_pixels": outlined_width,
        "rectangle_width_pixels": width,
        "height_pixels": height,
        "glyph_height_pixels": 7,
        "outlined_height_pixels": 9,
        "inset_pixels": label.inset,
    }
    return patterns, metrics


def target_cells() -> set[tuple[int, int]]:
    return {
        (label.x + cell_x, label.y + cell_y)
        for label in LABELS
        for cell_y in range(2)
        for cell_x in range(label.columns)
    }


def existing_label_tile_ids(tilemap: bytes) -> tuple[int, ...]:
    result = []
    seen = set()
    for x, y in sorted(target_cells(), key=lambda cell: (cell[1], cell[0])):
        tile_id = map_word(tilemap, x, y) & 0x01FF
        if tile_id != BACKGROUND_TILE_ID and tile_id not in seen:
            result.append(tile_id)
            seen.add(tile_id)
    return tuple(result)


def build_assets(base_map: bytes, base_tiles: bytes) -> tuple[bytes, bytes, dict[str, object]]:
    if len(base_map) != MAP_LENGTH or len(base_tiles) != TILES_LENGTH:
        raise ValueError("unexpected PET base asset dimensions")
    allowed_cells = target_cells()
    label_tile_ids = existing_label_tile_ids(base_map)
    if len(label_tile_ids) != 48:
        raise AssertionError(f"expected 48 v0.8 menu tiles, found {len(label_tile_ids)}")
    allocation_pool = (*label_tile_ids, *RETIRED_TILE_IDS)
    if len(allocation_pool) != 57 or len(set(allocation_pool)) != 57:
        raise AssertionError("replacement tile pool is not 57 unique IDs")

    # Every reusable v0.8 lettering tile must be confined to the audited
    # label rectangles.  Retired IDs must not be referenced by the base map.
    for index in range(0, len(base_map), 2):
        x = (index // 2) % MAP_WIDTH
        y = (index // 2) // MAP_WIDTH
        tile_id = int.from_bytes(base_map[index:index + 2], "little") & 0x01FF
        if tile_id in label_tile_ids and (x, y) not in allowed_cells:
            raise AssertionError(f"menu tile {tile_id:#x} escapes at ({x},{y})")
        if tile_id in RETIRED_TILE_IDS:
            raise AssertionError(f"retired tile {tile_id:#x} is still mapped at ({x},{y})")

    tilemap = bytearray(base_map)
    tiles = bytearray(base_tiles)
    protected_pattern_ids = tuple(
        tile_id for tile_id in range(FIRST_TILE_ID, LAST_TILE_ID + 1)
        if tile_id not in allocation_pool
    )
    pattern_to_tile = {
        tile_bytes(base_tiles, tile_id): tile_id for tile_id in protected_pattern_ids
    }
    allocated: dict[bytes, int] = {}
    next_pool_index = 0
    label_metrics = []

    for label in LABELS:
        patterns, metrics = render_label(label)
        assigned = []
        for cell_index, pattern in enumerate(patterns):
            tile_id = pattern_to_tile.get(pattern) or allocated.get(pattern)
            if tile_id is None:
                if next_pool_index >= len(allocation_pool):
                    raise ValueError("block menu exceeds the fixed 58-tile replacement pool")
                tile_id = allocation_pool[next_pool_index]
                next_pool_index += 1
                put_tile(tiles, tile_id, pattern)
                allocated[pattern] = tile_id
            cell_x = label.x + cell_index % label.columns
            cell_y = label.y + cell_index // label.columns
            old_word = map_word(tilemap, cell_x, cell_y)
            # Preserve palette, priority/bank and flip attributes; only replace
            # the 9-bit tile number.
            put_map_word(tilemap, cell_x, cell_y, (old_word & ~0x01FF) | tile_id)
            assigned.append(tile_id)
        label_metrics.append({
            "id": label.id,
            "text": label.text,
            "map_rectangle": {"x": label.x, "y": label.y, "columns": label.columns, "rows": 2},
            "assigned_tile_ids": assigned,
            **metrics,
        })

    # The exact allowlists are checked byte-for-byte.
    changed_cells = []
    for index in range(0, MAP_LENGTH, 2):
        old = base_map[index:index + 2]
        new = tilemap[index:index + 2]
        if old != new:
            cell = ((index // 2) % MAP_WIDTH, (index // 2) // MAP_WIDTH)
            if cell not in allowed_cells:
                raise AssertionError(f"map changed outside labels at {cell}")
            changed_cells.append(list(cell))

    changed_tile_ids = []
    for tile_id in range(FIRST_TILE_ID, LAST_TILE_ID + 1):
        if tile_bytes(base_tiles, tile_id) != tile_bytes(tiles, tile_id):
            if tile_id not in allocation_pool:
                raise AssertionError(f"protected tile {tile_id:#x} changed")
            changed_tile_ids.append(tile_id)

    # x=11..31 contains the separator, CLASS panel, right frame and dynamic
    # display background.  It must remain identical.  CLASS uses 0x3C-0x41.
    protected_right = b"".join(
        base_map[(y * MAP_WIDTH + 11) * 2:(y * MAP_WIDTH + 32) * 2]
        for y in range(16)
    )
    output_right = b"".join(
        tilemap[(y * MAP_WIDTH + 11) * 2:(y * MAP_WIDTH + 32) * 2]
        for y in range(16)
    )
    if protected_right != output_right:
        raise AssertionError("CLASS/right panel map was modified")
    # 0x2B/0x30 are the two halves of the static credit suffix Z.
    # 0x0F/0x10/0x31/0x45/0x46 belong to the separator/frame.  Tile 0x45 is
    # referenced by the runtime-only row 16 and therefore cannot be inferred
    # as unused by scanning the 32x16 ROM map alone.
    explicitly_protected = (*range(0x3C, 0x42), 0x2B, 0x30, 0x0F, 0x10, 0x31, 0x45, 0x46)
    for tile_id in explicitly_protected:
        if tile_bytes(base_tiles, tile_id) != tile_bytes(tiles, tile_id):
            raise AssertionError(f"protected PET tile {tile_id:#x} was modified")

    metrics: dict[str, object] = {
        "format": {
            "map": "32x16 little-endian BG0 words",
            "tiles": "76 packed 4-bpp tiles, IDs 1-76",
            "palette": 2,
            "palette_indices": {"face": FACE_INDEX, "background": BACKGROUND_INDEX, "outline": OUTLINE_INDEX},
        },
        "labels": label_metrics,
        "capacity": {
            "replacement_tile_ids": len(allocation_pool),
            "unique_patterns_allocated": len(allocated),
            "replacement_tile_ids_used": next_pool_index,
            "replacement_tile_ids_free": len(allocation_pool) - next_pool_index,
        },
        "allowlist": {
            "map_target_cells": len(allowed_cells),
            "map_changed_cells": changed_cells,
            "tile_pool_ids": list(allocation_pool),
            "tile_changed_ids": changed_tile_ids,
        },
        "protections": {
            "right_panel_map_unchanged": protected_right == output_right,
            "class_tile_ids_0x3c_0x41_unchanged": True,
            "static_credit_suffix_z_tiles_0x2b_0x30_unchanged": True,
            "frame_tiles_0x45_0x46_unchanged": True,
            "runtime_row_16_corner_tile_0x45_protected": True,
            "cursor_sprite_outside_bg0_assets": True,
            "dynamic_rank_and_credit_digits_outside_bg0_assets": True,
            "integer_pixels_only": True,
            "antialiasing": False,
        },
    }
    return bytes(tilemap), bytes(tiles), metrics


def build_preview(base_screenshot: Path, tilemap: bytes, tiles: bytes) -> Image.Image:
    screenshot = base_screenshot.read_bytes()
    actual = sha256(screenshot)
    if actual != BASE_SCREENSHOT_SHA256:
        raise ValueError(
            f"v0.8 PET runtime screenshot: SHA-256 {actual} != {BASE_SCREENSHOT_SHA256}"
        )
    with Image.open(base_screenshot) as source:
        if source.format != "PNG" or source.size != (224, 144):
            raise ValueError("PET base screenshot must be a native 224x144 PNG")
        preview = source.convert("RGB")
    colours = {
        BACKGROUND_INDEX: (85, 102, 102),
        FACE_INDEX: (238, 221, 204),
        OUTLINE_INDEX: (51, 51, 51),
    }
    for cell_x, cell_y in sorted(target_cells(), key=lambda cell: (cell[1], cell[0])):
        tile_id = map_word(tilemap, cell_x, cell_y) & 0x01FF
        pixels = unpack_tile(tile_bytes(tiles, tile_id))
        target_x, target_y = cell_x * 8, cell_y * 8
        for y in range(8):
            for x in range(8):
                preview.putpixel((target_x + x, target_y + y), colours[pixels[y * 8 + x]])
    return preview


def validate_reference(path: Path, expected_sha256: str, label: str) -> None:
    if not path.exists():
        return
    actual = sha256(path.read_bytes())
    if actual != expected_sha256:
        raise ValueError(f"{label}: SHA-256 {actual} != {expected_sha256}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", required=True, type=Path)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--reference-menu", type=Path)
    parser.add_argument("--observed-menu", type=Path)
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    assets = project_root / "translation" / "assets"
    docs = project_root / "evidence" / "runtime_v0_9_regressions"
    rom = args.rom.read_bytes()
    if len(rom) != 0x400000:
        raise ValueError("PET input ROM must be exactly 4 MiB")
    rom_sha = sha256(rom)
    if rom_sha == SOURCE_ROM_SHA256:
        input_kind = "verified Japanese Rev 1"
        expected_map = MAP_SOURCE_SHA256
        expected_tiles = TILES_SOURCE_SHA256
    elif rom_sha == BASE_V0103_SHA256:
        input_kind = "verified v0.10.3 QA base"
        expected_map = BASE_MAP_SHA256
        expected_tiles = BASE_TILES_SHA256
    else:
        raise ValueError("expected Japanese Rev 1 or the canonical v0.10.3 QA base")
    if sha256(rom[MAP_OFFSET:MAP_OFFSET + MAP_LENGTH]) != expected_map:
        raise ValueError("unexpected PET root map in input ROM")
    if sha256(rom[TILES_OFFSET:TILES_OFFSET + TILES_LENGTH]) != expected_tiles:
        raise ValueError("unexpected PET root tile bank in input ROM")
    if args.reference_menu:
        validate_reference(args.reference_menu, REFERENCE_MENU_SHA256, "menu-style reference")
    if args.observed_menu:
        validate_reference(args.observed_menu, OBSERVED_MENU_SHA256, "observed v0.10.3 menu")

    base_map = read_guarded(assets / BASE_MAP_NAME, MAP_LENGTH, BASE_MAP_SHA256, "v0.8 PET map")
    base_tiles = read_guarded(assets / BASE_TILES_NAME, TILES_LENGTH, BASE_TILES_SHA256, "v0.8 PET tiles")
    output_map, output_tiles, metrics = build_assets(base_map, base_tiles)
    if sha256(output_map) != OUTPUT_MAP_SHA256:
        raise AssertionError("generated PET menu map differs from the reviewed v0.10.4 asset")
    if sha256(output_tiles) != OUTPUT_TILES_SHA256:
        raise AssertionError("generated PET menu tiles differ from the reviewed v0.10.4 asset")
    (assets / OUTPUT_MAP_NAME).write_bytes(output_map)
    (assets / OUTPUT_TILES_NAME).write_bytes(output_tiles)

    preview = build_preview(docs / BASE_SCREENSHOT_NAME, output_map, output_tiles)
    preview.save(assets / OUTPUT_PREVIEW_NAME, format="PNG", optimize=False)
    if sha256((assets / OUTPUT_PREVIEW_NAME).read_bytes()) != OUTPUT_PREVIEW_SHA256:
        raise AssertionError("generated PET menu preview differs from the reviewed v0.10.4 image")

    report = {
        "status": "PASS",
        "version": "0.10.4",
        "scope": "PET root static menu labels only",
        "references": {
            "observed_v0_10_3_menu_sha256": OBSERVED_MENU_SHA256,
            "requested_block_style_sha256": REFERENCE_MENU_SHA256,
        },
        "source": {
            "canonical_rom_sha256": SOURCE_ROM_SHA256,
            "map": {"offset": f"0x{MAP_OFFSET:06X}", "length": MAP_LENGTH, "sha256": MAP_SOURCE_SHA256},
            "tiles": {"offset": f"0x{TILES_OFFSET:06X}", "length": TILES_LENGTH, "sha256": TILES_SOURCE_SHA256},
        },
        "input_rom": {"kind": input_kind, "sha256": rom_sha},
        "base_assets": {
            BASE_MAP_NAME: BASE_MAP_SHA256,
            BASE_TILES_NAME: BASE_TILES_SHA256,
            BASE_SCREENSHOT_NAME: BASE_SCREENSHOT_SHA256,
        },
        "outputs": {
            OUTPUT_MAP_NAME: {"length": len(output_map), "sha256": sha256(output_map)},
            OUTPUT_TILES_NAME: {"length": len(output_tiles), "sha256": sha256(output_tiles)},
            OUTPUT_PREVIEW_NAME: {"dimensions": list(preview.size), "sha256": sha256((assets / OUTPUT_PREVIEW_NAME).read_bytes())},
        },
        **metrics,
    }
    (assets / OUTPUT_REPORT_NAME).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
