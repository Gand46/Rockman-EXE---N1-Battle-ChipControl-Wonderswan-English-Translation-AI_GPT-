#!/usr/bin/env python3
"""Translate the previously omitted Shop purchase panel for v0.10.

The panel is a native 32x18 BG0 map with packed 4-bpp 8x8 tiles.  Only the
three Japanese product labels are redrawn; the frame, cursor, prices, Zenny
box, palettes and dialogue layer remain byte-identical to the source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw


SOURCE_SHA256 = "4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed"
ROM_SIZE = 0x400000
MAP_OFFSET = 0x04604C
MAP_LENGTH = 0x0480
MAP_SHA256 = "1d4d2dd43625d48932229ce4a024448cdddea03f9d4c8e16febcc7cca5e702f4"
TILES_OFFSET = 0x0818A0
TILES_LENGTH = 0x0600
TILES_SHA256 = "bb8fa918bf89494e808e4be16c087df68226518ba9ee690e14fbb86b9faa1152"
MAP_WIDTH = 32
TILE_BYTES = 32
TILE_MASK = 0x01FF
BACKGROUND_TILE = 0x05
BACKGROUND_COLOUR = 0x02
FACE_COLOUR = 0x0F


# Palette 2 read from the clean MesenCore Shop route at CPU:0xFE40.
PALETTE_2_RGB444 = (
    0x000, 0xFFF, 0xFFC, 0xEDC, 0xABA, 0x788, 0x000, 0x788,
    0x566, 0x456, 0x333, 0xEDC, 0xF80, 0xE71, 0xC50, 0x000,
)


FONT = {
    "0": ("010", "101", "101", "101", "101", "101", "010"),
    "1": ("010", "110", "010", "010", "010", "010", "111"),
    "A": ("010", "101", "101", "111", "101", "101", "101"),
    "C": ("011", "100", "100", "100", "100", "100", "011"),
    "F": ("111", "100", "100", "110", "100", "100", "100"),
    "H": ("101", "101", "101", "111", "101", "101", "101"),
    "I": ("111", "010", "010", "010", "010", "010", "111"),
    "N": ("101", "111", "111", "111", "111", "111", "101"),
    "O": ("010", "101", "101", "101", "101", "101", "010"),
    "P": ("110", "101", "101", "110", "100", "100", "100"),
    "S": ("011", "100", "100", "010", "001", "001", "110"),
}


@dataclass(frozen=True)
class Label:
    id: str
    original: str
    replacement: str
    x: int
    y: int
    capacity: int


LABELS = (
    Label("shop_one_chip", "バトルチップ1枚", "1 CHIP", 2, 1, 8),
    Label("shop_ten_chips", "バトルチップ10枚", "10 CHIPS", 2, 3, 9),
    Label("shop_information", "じょうほう", "INFO", 2, 7, 5),
)


# These source tiles occur only inside the three label rectangles.  Price
# glyphs 19/1B/23/25/2E/2F are deliberately excluded and never rewritten.
LABEL_TILE_POOL = (
    0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x1A, 0x1C,
    0x1D, 0x1E, 0x1F, 0x20, 0x21, 0x22, 0x24, 0x26,
    0x27, 0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2D,
)
PRICE_CELLS = {
    *((x, y) for y in (1, 2) for x in range(14, 18)),
    *((x, y) for y in (3, 4) for x in range(13, 18)),
    *((x, y) for y in (7, 8) for x in range(16, 18)),
}


def sha256(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def map_word(tilemap: bytes | bytearray, x: int, y: int) -> int:
    position = (y * MAP_WIDTH + x) * 2
    return int.from_bytes(tilemap[position:position + 2], "little")


def put_map_word(tilemap: bytearray, x: int, y: int, value: int) -> None:
    position = (y * MAP_WIDTH + x) * 2
    tilemap[position:position + 2] = value.to_bytes(2, "little")


def pack_tile(pixels: list[int]) -> bytes:
    if len(pixels) != 64:
        raise ValueError("tile must contain 64 pixels")
    return bytes(
        (pixels[index] << 4) | pixels[index + 1]
        for index in range(0, 64, 2)
    )


def unpack_tile(tiles: bytes | bytearray, tile: int) -> list[int]:
    payload = tiles[tile * TILE_BYTES:(tile + 1) * TILE_BYTES]
    return [nibble for byte in payload for nibble in (byte >> 4, byte & 0x0F)]


def write_tile(tiles: bytearray, tile: int, payload: bytes) -> None:
    if len(payload) != TILE_BYTES:
        raise ValueError("packed tile must contain 32 bytes")
    tiles[tile * TILE_BYTES:(tile + 1) * TILE_BYTES] = payload


def text_width(text: str) -> int:
    return sum(3 if character == " " else 4 for character in text) - 1


def raster_text(text: str) -> list[list[int]]:
    unsupported = sorted(set(text.replace(" ", "")) - FONT.keys())
    if unsupported:
        raise ValueError(f"unsupported Shop glyphs: {unsupported}")
    width = text_width(text)
    canvas = [[BACKGROUND_COLOUR] * width for _ in range(16)]
    cursor = 0
    for character in text:
        if character == " ":
            cursor += 3
            continue
        for glyph_y, row in enumerate(FONT[character]):
            for glyph_x, enabled in enumerate(row):
                if enabled == "1":
                    canvas[1 + glyph_y * 2][cursor + glyph_x] = FACE_COLOUR
                    canvas[2 + glyph_y * 2][cursor + glyph_x] = FACE_COLOUR
        cursor += 4
    return canvas


def label_cells() -> set[tuple[int, int]]:
    return {
        (label.x + column, label.y + row)
        for label in LABELS
        for column in range(label.capacity)
        for row in range(2)
    }


def assert_tile_exclusivity(tilemap: bytes) -> dict[str, list[list[int]]]:
    allowed = label_cells()
    references: dict[str, list[list[int]]] = {
        f"0x{tile:02X}": [] for tile in LABEL_TILE_POOL
    }
    for position in range(0, len(tilemap), 2):
        word = int.from_bytes(tilemap[position:position + 2], "little")
        tile = word & TILE_MASK
        if tile not in LABEL_TILE_POOL:
            continue
        cell = ((position // 2) % MAP_WIDTH, (position // 2) // MAP_WIDTH)
        if cell not in allowed:
            raise AssertionError(
                f"label tile 0x{tile:02X} is shared at map cell {cell}"
            )
        references[f"0x{tile:02X}"].append(list(cell))
    if any(not cells for cells in references.values()):
        raise AssertionError("an expected source label tile is not referenced")
    return references


def draw_labels(tilemap: bytearray, tiles: bytearray) -> list[dict[str, object]]:
    solid_background = bytes([(BACKGROUND_COLOUR << 4) | BACKGROUND_COLOUR]) * TILE_BYTES
    if bytes(tiles[BACKGROUND_TILE * TILE_BYTES:(BACKGROUND_TILE + 1) * TILE_BYTES]) != solid_background:
        raise AssertionError("Shop background tile 0x05 is not solid colour 2")
    for tile in LABEL_TILE_POOL:
        write_tile(tiles, tile, solid_background)

    pattern_to_tile: dict[bytes, int] = {}
    pool_index = 0
    records = []
    for label in LABELS:
        canvas = raster_text(label.replacement)
        width = len(canvas[0])
        used_columns = (width + 7) // 8
        if used_columns > label.capacity:
            raise AssertionError(f"{label.id} exceeds its {label.capacity}-tile field")
        cell_records = []
        for tile_y in range(2):
            for column in range(label.capacity):
                pixels = [
                    canvas[tile_y * 8 + pixel_y][column * 8 + pixel_x]
                    if column * 8 + pixel_x < width else BACKGROUND_COLOUR
                    for pixel_y in range(8)
                    for pixel_x in range(8)
                ]
                packed = pack_tile(pixels)
                if set(pixels) == {BACKGROUND_COLOUR}:
                    tile = BACKGROUND_TILE
                elif packed in pattern_to_tile:
                    tile = pattern_to_tile[packed]
                else:
                    if pool_index >= len(LABEL_TILE_POOL):
                        raise AssertionError("English Shop labels exceed exclusive tile pool")
                    tile = LABEL_TILE_POOL[pool_index]
                    pool_index += 1
                    pattern_to_tile[packed] = tile
                    write_tile(tiles, tile, packed)
                x, y = label.x + column, label.y + tile_y
                old = map_word(tilemap, x, y)
                put_map_word(tilemap, x, y, (old & ~TILE_MASK) | tile)
                cell_records.append({"x": x, "y": y, "tile": f"0x{tile:02X}"})
        records.append(
            {
                "id": label.id,
                "original": label.original,
                "replacement": label.replacement,
                "field": {"x": label.x, "y": label.y, "width": label.capacity, "height": 2},
                "render_width_pixels": width,
                "used_columns": used_columns,
                "cells": cell_records,
            }
        )
    if pool_index > len(LABEL_TILE_POOL):
        raise AssertionError("tile allocation overflow")
    for record in records:
        record["shared_unique_pattern_count"] = len(pattern_to_tile)
    return records


def rgb444(value: int) -> tuple[int, int, int]:
    return (
        (value & 0x0F) * 17,
        ((value >> 4) & 0x0F) * 17,
        ((value >> 8) & 0x0F) * 17,
    )


def render_panel(tilemap: bytes | bytearray, tiles: bytes | bytearray) -> Image.Image:
    palette = [rgb444(value) for value in PALETTE_2_RGB444]
    image = Image.new("RGB", (224, 80))
    pixels = image.load()
    for y in range(80):
        for x in range(224):
            word = map_word(tilemap, x // 8, y // 8)
            tile = word & TILE_MASK
            tile_pixels = unpack_tile(tiles, tile)
            colour = tile_pixels[(y & 7) * 8 + (x & 7)]
            pixels[x, y] = palette[colour]
    return image


def write_preview(
    original_map: bytes,
    original_tiles: bytes,
    patched_map: bytes,
    patched_tiles: bytes,
    output: Path,
) -> None:
    before = render_panel(original_map, original_tiles)
    after = render_panel(patched_map, patched_tiles)
    scale = 3
    before = before.resize((before.width * scale, before.height * scale), Image.Resampling.NEAREST)
    after = after.resize((after.width * scale, after.height * scale), Image.Resampling.NEAREST)
    gap, caption = 8, 26
    canvas = Image.new("RGB", (before.width + after.width + gap, before.height + caption), (24, 24, 24))
    canvas.paste(before, (0, caption))
    canvas.paste(after, (before.width + gap, caption))
    draw = ImageDraw.Draw(canvas)
    draw.text((6, 6), "SHOP SOURCE (224x144)", fill="white")
    draw.text((before.width + gap + 6, 6), "SHOP ENGLISH v0.10 (224x144)", fill="white")
    canvas.save(output)


def changed_indexes(before: bytes, after: bytes) -> set[int]:
    return {index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_rom", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    rom = args.source_rom.read_bytes()
    if len(rom) != ROM_SIZE or sha256(rom) != SOURCE_SHA256:
        raise ValueError("unsupported source ROM; expected verified Japanese Rev 1")
    original_map = rom[MAP_OFFSET:MAP_OFFSET + MAP_LENGTH]
    original_tiles = rom[TILES_OFFSET:TILES_OFFSET + TILES_LENGTH]
    if sha256(original_map) != MAP_SHA256 or sha256(original_tiles) != TILES_SHA256:
        raise ValueError("unexpected Shop source assets")

    references = assert_tile_exclusivity(original_map)
    tilemap = bytearray(original_map)
    tiles = bytearray(original_tiles)
    price_words_before = {cell: map_word(original_map, *cell) for cell in PRICE_CELLS}
    labels = draw_labels(tilemap, tiles)
    price_words_after = {cell: map_word(tilemap, *cell) for cell in PRICE_CELLS}
    if price_words_before != price_words_after:
        raise AssertionError("price cells changed")

    map_changes = changed_indexes(original_map, bytes(tilemap))
    allowed_map_bytes = {
        byte
        for x, y in label_cells()
        for byte in ((y * MAP_WIDTH + x) * 2, (y * MAP_WIDTH + x) * 2 + 1)
    }
    if map_changes - allowed_map_bytes:
        raise AssertionError("Shop map changed outside label rectangles")
    tile_changes = changed_indexes(original_tiles, bytes(tiles))
    allowed_tile_bytes = {
        byte
        for tile in LABEL_TILE_POOL
        for byte in range(tile * TILE_BYTES, (tile + 1) * TILE_BYTES)
    }
    if tile_changes - allowed_tile_bytes:
        raise AssertionError("Shop tiles changed outside exclusive label pool")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    map_path = args.output_dir / "shop_purchase_bg0_map_v0_10.bin"
    tiles_path = args.output_dir / "shop_purchase_bg0_tiles_v0_10.bin"
    preview_path = args.output_dir / "shop_purchase_comparison_v0_10.png"
    report_path = args.output_dir / "shop_purchase_asset_report_v0_10.json"
    map_path.write_bytes(tilemap)
    tiles_path.write_bytes(tiles)
    write_preview(original_map, original_tiles, tilemap, tiles, preview_path)

    report = {
        "format": "n1-shop-purchase-assets-v0.10",
        "status": "PASS",
        "native_display": [224, 144],
        "grid": {"visible_tiles": [28, 18], "map_tiles": [32, 18], "tile_pixels": [8, 8]},
        "source": {
            "rom_sha256": SOURCE_SHA256,
            "map": {"offset": f"0x{MAP_OFFSET:06X}", "length": MAP_LENGTH, "sha256": MAP_SHA256},
            "tiles": {"offset": f"0x{TILES_OFFSET:06X}", "length": TILES_LENGTH, "sha256": TILES_SHA256},
        },
        "labels": labels,
        "protected_prices": ["500z", "5000z", "0z"],
        "price_cells_byte_identical": True,
        "exclusive_source_tile_references": references,
        "changes": {
            "map_bytes": len(map_changes),
            "tile_bytes": len(tile_changes),
            "outside_allowlist": 0,
        },
        "outputs": {
            map_path.name: sha256(map_path.read_bytes()),
            tiles_path.name: sha256(tiles_path.read_bytes()),
            preview_path.name: sha256(preview_path.read_bytes()),
        },
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
