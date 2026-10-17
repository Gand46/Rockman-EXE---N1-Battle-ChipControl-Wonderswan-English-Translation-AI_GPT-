#!/usr/bin/env python3
"""Build the remaining English PET-submenu graphics for N1 Battle v0.9.

The Chip Folder, Data Library, NetNavi and Save screens copy their maps and
packed 4-bpp tiles directly from ROM.  This generator is deliberately
conservative: it source-hashes every complete input asset, renders compact
English labels into audited text-only tiles, rewrites only audited map cells,
and verifies that every byte outside those targets remains identical.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw


SOURCE_ROM_SHA256 = "4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed"
MAP_WORD_PREFIX = 0x2400
TILE_BYTES = 32
MAP_WIDTH = 32
PREVIEW_ROWS = 18


@dataclass(frozen=True)
class Region:
    name: str
    offset: int
    length: int
    source_sha256: str


@dataclass(frozen=True)
class Label:
    id: str
    original: str
    translation: str
    screen: str
    bank: str
    x: int
    y: int
    capacity: int
    top_tiles: tuple[int, ...]
    bottom_tiles: tuple[int, ...]
    background_tile: int
    background_colour: int
    face_colour: int
    outline_colour: int | None = None


@dataclass(frozen=True)
class BannerLabel:
    """One-tile-high text inside the PET's asymmetric Y2 arrow banner."""

    id: str
    original: str
    translation: str
    screen: str
    bank: str
    x: int
    y: int
    tiles: tuple[int, ...]
    fill_colour: int
    outside_colour: int
    face_colour: int


TILE_REGIONS = {
    "chip_library": Region(
        "chip_library_tiles", 0x07EC10, 0x16C0,
        "848239b8a63279baf5f7e2c243d97f677fa810fc6f1699f8b5aa3920fb1a707c",
    ),
    "netnavi": Region(
        "netnavi_tiles", 0x080300, 0x0D40,
        "48d4c0245741ce07669fc476817f6d440dbde161c0b5ce1788ce030942c2a539",
    ),
    "save": Region(
        "save_tiles", 0x081070, 0x0800,
        "80911b2f494f5671a1ca1d701e7e84af47533194cceffa7cba5fe2fa1e7b1863",
    ),
}

MAP_REGIONS = {
    "chip_folder": Region(
        "chip_folder_bg0_map", 0x043F40, 0x0680,
        "20f8cc49ceec3ca227a9f3d7f1b1882b05fb51458afdab5fa0c5abe6fa4ee2c4",
    ),
    "data_library": Region(
        "data_library_bg0_map", 0x044C44, 0x0680,
        "07ebe88de45c645949f644ff211d3b2333e02d332122d493abe0bd129d50699e",
    ),
    "netnavi": Region(
        "netnavi_bg0_map", 0x0452C6, 0x0480,
        "a9c6a387067b6b0f062e03e22f78aeb7f75f3939534b4bb0119045ddcc4278b2",
    ),
    "save": Region(
        "save_bg0_map", 0x045BCA, 0x0480,
        "3af1dc0c58926b8947e67f789145694fafc2d2c8adc0c86415e4c78264dbda17",
    ),
}

SCREEN_BANKS = {
    "chip_folder": "chip_library",
    "data_library": "chip_library",
    "netnavi": "netnavi",
    "save": "save",
}


# Compact 3x7 capitals, rendered with two vertical pixels per source row.
FONT = {
    "A": ("010", "101", "101", "111", "101", "101", "101"),
    "B": ("110", "101", "101", "110", "101", "101", "110"),
    "C": ("011", "100", "100", "100", "100", "100", "011"),
    "D": ("110", "101", "101", "101", "101", "101", "110"),
    "E": ("111", "100", "100", "110", "100", "100", "111"),
    "F": ("111", "100", "100", "110", "100", "100", "100"),
    "G": ("011", "100", "100", "101", "101", "101", "011"),
    "H": ("101", "101", "101", "111", "101", "101", "101"),
    "I": ("111", "010", "010", "010", "010", "010", "111"),
    "K": ("101", "101", "110", "100", "110", "101", "101"),
    "L": ("100", "100", "100", "100", "100", "100", "111"),
    "M": ("101", "111", "111", "101", "101", "101", "101"),
    "N": ("101", "111", "111", "111", "111", "111", "101"),
    "O": ("010", "101", "101", "101", "101", "101", "010"),
    "P": ("110", "101", "101", "110", "100", "100", "100"),
    "R": ("110", "101", "101", "110", "110", "101", "101"),
    "S": ("011", "100", "100", "010", "001", "001", "110"),
    "T": ("111", "010", "010", "010", "010", "010", "010"),
    "V": ("101", "101", "101", "101", "101", "101", "010"),
    "Y": ("101", "101", "101", "010", "010", "010", "010"),
    "2": ("110", "001", "001", "010", "100", "100", "111"),
}


LABELS = (
    Label(
        "chip_folder_header", "チップフォルダ", "CHIP FOLDER",
        "chip_folder", "chip_library", 11, 0, 7,
        (0x05, 0x06, 0x07, 0x08, 0x09, 0x0A),
        (0x17, 0x18, 0x19, 0x1A, 0x1B, 0x1C),
        0x04, 3, 15, 9,
    ),
    Label(
        "data_library_header", "データライブラリ", "DATA LIBRARY",
        "data_library", "chip_library", 11, 0, 8,
        (0x3E, 0x3F, 0x40, 0x41, 0x42, 0x43),
        (0x4B, 0x4C, 0x4D, 0x4E, 0x4F, 0x50),
        0x04, 3, 15, 9,
    ),
    Label(
        "netnavi_header", "ネットナビ", "NETNAVI",
        "netnavi", "netnavi", 11, 0, 6,
        (0x05, 0x06, 0x07, 0x08),
        (0x14, 0x15, 0x16, 0x17),
        0x04, 8, 10, 3,
    ),
    Label(
        "netnavi_kind_unit", "種", "T",
        "netnavi", "netnavi", 20, 4, 1,
        (0x39,), (0x3E,), 0x04, 8, 6,
    ),
    Label(
        "netnavi_chip_unit", "枚", "C",
        "netnavi", "netnavi", 25, 4, 1,
        (0x3B,), (0x3F,), 0x04, 8, 6,
    ),
    Label(
        "save_header", "セーブ", "SAVE",
        "save", "save", 12, 0, 3,
        (0x02, 0x03), (0x05, 0x06), 0x01, 2, 11, 1,
    ),
    Label(
        "save_data_library", "データライブラリ", "DATA LIBRARY",
        "save", "save", 3, 3, 8,
        (0x0E, 0x0F, 0x10, 0x11, 0x12, 0x13),
        (0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E),
        0x0D, 10, 15,
    ),
    Label(
        "save_battle_chips", "バトルチップ", "BATTLE CHIPS",
        "save", "save", 3, 5, 6,
        (0x24, 0x25, 0x26, 0x27, 0x28, 0x3A),
        (0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x2F),
        0x0C, 12, 15,
    ),
    Label(
        "save_chip_unit", "枚", "C",
        "save", "save", 24, 5, 1,
        (0x29,), (0x30,), 0x0C, 12, 15,
    ),
    Label(
        "save_credits", "クレジット", "CREDITS",
        "save", "save", 3, 7, 5,
        (0x31, 0x32, 0x33, 0x34),
        (0x36, 0x37, 0x38, 0x39),
        0x0D, 10, 15,
    ),
)


BANNER_LABELS = (
    BannerLabel(
        "chip_folder_y2_pack", "Y2 リュック", "Y2 PACK",
        "chip_folder", "chip_library", 22, 1,
        (0x31, 0x32, 0x33, 0x34, 0x35), 6, 3, 2,
    ),
    BannerLabel(
        "netnavi_y2_megaman", "Y2 ロックマン", "Y2 MEGAMAN",
        "netnavi", "netnavi", 22, 1,
        (0x1B, 0x1C, 0x1D, 0x1E, 0x1F), 12, 8, 9,
    ),
)

ALL_LABELS = (*LABELS, *BANNER_LABELS)


OUTPUT_NAMES = {
    "chip_library": "pet_submenu_chip_library_tiles_v0_9.bin",
    "netnavi": "pet_submenu_netnavi_tiles_v0_9.bin",
    "save": "pet_submenu_save_tiles_v0_9.bin",
    "chip_folder": "pet_submenu_chip_folder_bg0_map_v0_9.bin",
    "data_library": "pet_submenu_data_library_bg0_map_v0_9.bin",
    "netnavi_map": "pet_submenu_netnavi_bg0_map_v0_9.bin",
    "save_map": "pet_submenu_save_bg0_map_v0_9.bin",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_asset(rom: bytes, region: Region) -> bytes:
    data = rom[region.offset:region.offset + region.length]
    if len(data) != region.length:
        raise ValueError(f"{region.name}: source region is truncated")
    actual = sha256(data)
    if actual != region.source_sha256:
        raise ValueError(
            f"{region.name}: unexpected source SHA-256 {actual}; "
            f"expected {region.source_sha256}"
        )
    return data


def map_word(data: bytes | bytearray, x: int, y: int) -> int:
    position = (y * MAP_WIDTH + x) * 2
    return int.from_bytes(data[position:position + 2], "little")


def put_map_word(data: bytearray, x: int, y: int, value: int) -> None:
    position = (y * MAP_WIDTH + x) * 2
    data[position:position + 2] = value.to_bytes(2, "little")


def solid_tile(colour: int) -> bytes:
    return bytes([(colour << 4) | colour]) * TILE_BYTES


def set_tile_pixel(asset: bytearray, tile: int, x: int, y: int, colour: int) -> None:
    position = tile * TILE_BYTES + y * 4 + x // 2
    if x & 1:
        asset[position] = (asset[position] & 0xF0) | colour
    else:
        asset[position] = (asset[position] & 0x0F) | (colour << 4)


def text_width(text: str) -> int:
    return sum(3 if char == " " else 4 for char in text) - 1


def raster_text(label: Label) -> list[list[int]]:
    width = text_width(label.translation)
    canvas = [[label.background_colour] * width for _ in range(16)]
    face: list[tuple[int, int]] = []
    cursor = 0
    for char in label.translation:
        if char == " ":
            cursor += 3
            continue
        try:
            glyph = FONT[char]
        except KeyError as error:
            raise ValueError(f"Unsupported glyph {char!r} in {label.id}") from error
        for gy, row in enumerate(glyph):
            for gx, enabled in enumerate(row):
                if enabled == "1":
                    for dy in (0, 1):
                        x = cursor + gx
                        y = 1 + gy * 2 + dy
                        canvas[y][x] = label.face_colour
                        face.append((x, y))
        cursor += 4

    if label.outline_colour is not None:
        for x, y in face:
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nx, ny = x + dx, y + dy
                if (
                    0 <= nx < width
                    and 0 <= ny < 16
                    and canvas[ny][nx] == label.background_colour
                ):
                    canvas[ny][nx] = label.outline_colour
    return canvas


def draw_label(tile_asset: bytearray, tilemap: bytearray, label: Label) -> dict:
    pixels = raster_text(label)
    used_columns = (len(pixels[0]) + 7) // 8
    if used_columns != len(label.top_tiles) or used_columns != len(label.bottom_tiles):
        raise ValueError(
            f"{label.id}: raster needs {used_columns} columns, allocation is "
            f"{len(label.top_tiles)}/{len(label.bottom_tiles)}"
        )
    if used_columns > label.capacity:
        raise ValueError(
            f"{label.id}: {label.translation!r} needs {used_columns} columns, "
            f"capacity is {label.capacity}"
        )

    for tile in (*label.top_tiles, *label.bottom_tiles):
        start = tile * TILE_BYTES
        tile_asset[start:start + TILE_BYTES] = solid_tile(label.background_colour)

    for y, row in enumerate(pixels):
        tile_row = label.top_tiles if y < 8 else label.bottom_tiles
        for x, colour in enumerate(row):
            tile = tile_row[x // 8]
            set_tile_pixel(tile_asset, tile, x & 7, y & 7, colour)

    for column in range(label.capacity):
        if column < used_columns:
            top = label.top_tiles[column]
            bottom = label.bottom_tiles[column]
        else:
            top = bottom = label.background_tile
        put_map_word(tilemap, label.x + column, label.y, MAP_WORD_PREFIX | top)
        put_map_word(tilemap, label.x + column, label.y + 1, MAP_WORD_PREFIX | bottom)

    return {
        "id": label.id,
        "original": label.original,
        "translation": label.translation,
        "screen": label.screen,
        "bank": label.bank,
        "position": {"x": label.x, "y": label.y},
        "capacity_columns": label.capacity,
        "render_width_pixels": len(pixels[0]),
        "used_columns": used_columns,
        "top_tiles": [f"0x{tile:02X}" for tile in label.top_tiles],
        "bottom_tiles": [f"0x{tile:02X}" for tile in label.bottom_tiles],
        "background_tile": f"0x{label.background_tile:02X}",
    }


def raster_banner_text(label: BannerLabel) -> list[list[int]]:
    capacity_pixels = len(label.tiles) * 8
    width = text_width(label.translation)
    if width > capacity_pixels:
        raise ValueError(
            f"{label.id}: {label.translation!r} needs {width}px, "
            f"capacity is {capacity_pixels}px"
        )
    canvas = [[label.fill_colour] * capacity_pixels for _ in range(8)]
    canvas[7] = [label.outside_colour] * capacity_pixels
    cursor = (capacity_pixels - width) // 2
    for char in label.translation:
        if char == " ":
            cursor += 3
            continue
        try:
            glyph = FONT[char]
        except KeyError as error:
            raise ValueError(f"Unsupported glyph {char!r} in {label.id}") from error
        for gy, row in enumerate(glyph):
            for gx, enabled in enumerate(row):
                if enabled == "1":
                    canvas[gy][cursor + gx] = label.face_colour
        cursor += 4
    return canvas


def draw_banner_label(
    tile_asset: bytearray, tilemap: bytearray, label: BannerLabel
) -> dict:
    pixels = raster_banner_text(label)
    for tile in label.tiles:
        start = tile * TILE_BYTES
        tile_asset[start:start + TILE_BYTES] = solid_tile(label.fill_colour)
        for x in range(8):
            set_tile_pixel(tile_asset, tile, x, 7, label.outside_colour)

    for y, row in enumerate(pixels):
        for x, colour in enumerate(row):
            tile = label.tiles[x // 8]
            set_tile_pixel(tile_asset, tile, x & 7, y, colour)

    # These five source tiles are exclusive to the banner.  Keep the existing
    # map order so the untouched sixth tile continues to form the arrow point.
    for column, tile in enumerate(label.tiles):
        actual = map_word(tilemap, label.x + column, label.y)
        expected = MAP_WORD_PREFIX | tile
        if actual != expected:
            raise AssertionError(
                f"{label.id}: source map word at column {column} is "
                f"0x{actual:04X}, expected 0x{expected:04X}"
            )

    return {
        "id": label.id,
        "original": label.original,
        "translation": label.translation,
        "screen": label.screen,
        "bank": label.bank,
        "position": {"x": label.x, "y": label.y},
        "capacity_columns": len(label.tiles),
        "render_width_pixels": text_width(label.translation),
        "used_columns": (text_width(label.translation) + 7) // 8,
        "tiles": [f"0x{tile:02X}" for tile in label.tiles],
        "preserved_arrow_tile": (
            "0x36" if label.screen == "chip_folder" else "0x20"
        ),
    }


def changed_indexes(before: bytes, after: bytes) -> set[int]:
    if len(before) != len(after):
        raise ValueError("Cannot compare assets of different lengths")
    return {index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]}


def allocated_tiles(label: Label | BannerLabel) -> tuple[int, ...]:
    if isinstance(label, BannerLabel):
        return label.tiles
    return (*label.top_tiles, *label.bottom_tiles)


def target_tile_bytes(labels: Iterable[Label | BannerLabel], bank: str) -> set[int]:
    result: set[int] = set()
    for label in labels:
        if label.bank != bank:
            continue
        for tile in allocated_tiles(label):
            result.update(range(tile * TILE_BYTES, (tile + 1) * TILE_BYTES))
    return result


def target_map_bytes(labels: Iterable[Label | BannerLabel], screen: str) -> set[int]:
    result: set[int] = set()
    for label in labels:
        if label.screen != screen:
            continue
        if isinstance(label, BannerLabel):
            for x in range(label.x, label.x + len(label.tiles)):
                position = (label.y * MAP_WIDTH + x) * 2
                result.update((position, position + 1))
            continue
        for y in (label.y, label.y + 1):
            for x in range(label.x, label.x + label.capacity):
                position = (y * MAP_WIDTH + x) * 2
                result.update((position, position + 1))
    return result


def target_map_cells(
    labels: Iterable[Label | BannerLabel], screen: str
) -> set[tuple[int, int]]:
    result: set[tuple[int, int]] = set()
    for label in labels:
        if label.screen != screen:
            continue
        if isinstance(label, BannerLabel):
            result.update(
                (x, label.y) for x in range(label.x, label.x + len(label.tiles))
            )
        else:
            result.update(
                (x, y)
                for y in (label.y, label.y + 1)
                for x in range(label.x, label.x + label.capacity)
            )
    return result


def validate_source_aliases(
    original_maps: dict[str, bytes], allocations: dict[str, dict[int, str]]
) -> dict:
    """Prove allocated tiles are not referenced outside audited cells."""
    report: dict[str, dict] = {}
    for bank, tile_owners in allocations.items():
        allocated = set(tile_owners)
        references = []
        for screen, tilemap in original_maps.items():
            if SCREEN_BANKS[screen] != bank:
                continue
            allowed_cells = target_map_cells(ALL_LABELS, screen)
            for position in range(0, len(tilemap), 2):
                tile = int.from_bytes(tilemap[position:position + 2], "little") & 0x1FF
                if tile not in allocated:
                    continue
                word_index = position // 2
                x, y = word_index % MAP_WIDTH, word_index // MAP_WIDTH
                if (x, y) not in allowed_cells:
                    raise AssertionError(
                        f"{bank}: allocated tile 0x{tile:02X} ({tile_owners[tile]}) "
                        f"is also referenced by {screen} at ({x},{y})"
                    )
                references.append(
                    {"screen": screen, "x": x, "y": y, "tile": f"0x{tile:02X}"}
                )
        report[bank] = {
            "allocated_tile_ids": len(allocated),
            "source_references_in_audited_cells": len(references),
            "references_outside_audited_cells": 0,
        }
    return report


def validate_label_render(tile_asset: bytes, tilemap: bytes, label: Label) -> None:
    expected = raster_text(label)
    used_columns = len(label.top_tiles)
    for column in range(label.capacity):
        expected_top = (
            label.top_tiles[column] if column < used_columns else label.background_tile
        )
        expected_bottom = (
            label.bottom_tiles[column] if column < used_columns else label.background_tile
        )
        if map_word(tilemap, label.x + column, label.y) != MAP_WORD_PREFIX | expected_top:
            raise AssertionError(f"{label.id}: unexpected top map word at column {column}")
        if map_word(tilemap, label.x + column, label.y + 1) != MAP_WORD_PREFIX | expected_bottom:
            raise AssertionError(f"{label.id}: unexpected bottom map word at column {column}")

    for y, row in enumerate(expected):
        tiles = label.top_tiles if y < 8 else label.bottom_tiles
        for x, expected_colour in enumerate(row):
            tile = tiles[x // 8]
            position = tile * TILE_BYTES + (y & 7) * 4 + (x & 7) // 2
            packed = tile_asset[position]
            actual = packed & 0x0F if x & 1 else packed >> 4
            if actual != expected_colour:
                raise AssertionError(
                    f"{label.id}: pixel mismatch at ({x},{y}): "
                    f"{actual} != {expected_colour}"
                )


def validate_banner_render(
    tile_asset: bytes, tilemap: bytes, label: BannerLabel
) -> None:
    expected = raster_banner_text(label)
    for column, tile in enumerate(label.tiles):
        if map_word(tilemap, label.x + column, label.y) != MAP_WORD_PREFIX | tile:
            raise AssertionError(f"{label.id}: map order changed at column {column}")
    for y, row in enumerate(expected):
        for x, expected_colour in enumerate(row):
            tile = label.tiles[x // 8]
            position = tile * TILE_BYTES + y * 4 + (x & 7) // 2
            packed = tile_asset[position]
            actual = packed & 0x0F if x & 1 else packed >> 4
            if actual != expected_colour:
                raise AssertionError(
                    f"{label.id}: pixel mismatch at ({x},{y}): "
                    f"{actual} != {expected_colour}"
                )


def render_map(tile_asset: bytes, tilemap: bytes, rows: int = PREVIEW_ROWS) -> Image.Image:
    width = MAP_WIDTH * 8
    height = rows * 8
    image = Image.new("RGB", (width, height), "black")
    pixels = image.load()
    for tile_y in range(rows):
        for tile_x in range(MAP_WIDTH):
            tile = map_word(tilemap, tile_x, tile_y) & 0x1FF
            start = tile * TILE_BYTES
            if start + TILE_BYTES > len(tile_asset):
                continue
            for y in range(8):
                for byte_x, packed in enumerate(
                    tile_asset[start + y * 4:start + y * 4 + 4]
                ):
                    for nibble_x, colour in enumerate((packed >> 4, packed & 0x0F)):
                        shade = colour * 17
                        pixels[tile_x * 8 + byte_x * 2 + nibble_x, tile_y * 8 + y] = (
                            shade, shade, shade,
                        )
    return image


def comparison_preview(
    original_tiles: bytes,
    original_map: bytes,
    patched_tiles: bytes,
    patched_map: bytes,
    screen: str,
    output: Path,
) -> None:
    scale = 3
    before = render_map(original_tiles, original_map).resize(
        (MAP_WIDTH * 8 * scale, PREVIEW_ROWS * 8 * scale), Image.Resampling.NEAREST
    )
    after = render_map(patched_tiles, patched_map).resize(
        before.size, Image.Resampling.NEAREST
    )
    caption_height = 28
    gap = 8
    montage = Image.new(
        "RGB", (before.width * 2 + gap, before.height + caption_height), (24, 24, 24)
    )
    montage.paste(before, (0, caption_height))
    montage.paste(after, (before.width + gap, caption_height))
    draw = ImageDraw.Draw(montage)
    draw.text((8, 7), f"{screen}: ORIGINAL", fill="white")
    draw.text((before.width + gap + 8, 7), f"{screen}: ENGLISH v0.9", fill="white")
    montage.save(output)


def build(source_rom: Path, output_dir: Path) -> dict:
    rom = source_rom.read_bytes()
    actual_rom_sha = sha256(rom)
    if actual_rom_sha != SOURCE_ROM_SHA256:
        raise ValueError(
            f"Unexpected source ROM SHA-256 {actual_rom_sha}; expected {SOURCE_ROM_SHA256}"
        )

    original_tiles = {
        name: source_asset(rom, region) for name, region in TILE_REGIONS.items()
    }
    original_maps = {
        name: source_asset(rom, region) for name, region in MAP_REGIONS.items()
    }
    patched_tiles = {name: bytearray(data) for name, data in original_tiles.items()}
    patched_maps = {name: bytearray(data) for name, data in original_maps.items()}

    # No allocated tile may be shared by two English labels in one bank.
    allocations: dict[str, dict[int, str]] = {name: {} for name in TILE_REGIONS}
    for label in ALL_LABELS:
        if not label.translation.isascii() or label.translation != label.translation.upper():
            raise ValueError(f"{label.id}: translation must be uppercase ASCII")
        for tile in allocated_tiles(label):
            previous = allocations[label.bank].get(tile)
            if previous is not None:
                raise ValueError(
                    f"Tile 0x{tile:02X} in {label.bank} is shared by {previous} and {label.id}"
                )
            allocations[label.bank][tile] = label.id

    alias_report = validate_source_aliases(original_maps, allocations)

    label_reports = []
    for label in LABELS:
        label_reports.append(
            draw_label(patched_tiles[label.bank], patched_maps[label.screen], label)
        )
    for label in BANNER_LABELS:
        label_reports.append(
            draw_banner_label(
                patched_tiles[label.bank], patched_maps[label.screen], label
            )
        )

    validation = {
        "source_hashes_match": True,
        "uppercase_ascii_translations": True,
        "outside_target_tile_bytes_unchanged": True,
        "outside_target_map_bytes_unchanged": True,
        "rendered_labels_match_expected_pixels": True,
        "allocated_tile_ids_exclusive_to_target_cells": True,
        "labels_validated": len(ALL_LABELS),
    }
    changed_summary = {"tile_banks": {}, "maps": {}}
    for bank in TILE_REGIONS:
        changes = changed_indexes(original_tiles[bank], patched_tiles[bank])
        allowed = target_tile_bytes(ALL_LABELS, bank)
        unexpected = changes - allowed
        if unexpected:
            validation["outside_target_tile_bytes_unchanged"] = False
            raise AssertionError(
                f"{bank}: {len(unexpected)} bytes changed outside allocated tiles"
            )
        changed_summary["tile_banks"][bank] = {
            "changed_bytes": len(changes),
            "allowed_target_bytes": len(allowed),
            "changed_tile_ids": [
                f"0x{tile:02X}" for tile in sorted({index // TILE_BYTES for index in changes})
            ],
        }

    for screen in MAP_REGIONS:
        changes = changed_indexes(original_maps[screen], patched_maps[screen])
        allowed = target_map_bytes(ALL_LABELS, screen)
        unexpected = changes - allowed
        if unexpected:
            validation["outside_target_map_bytes_unchanged"] = False
            raise AssertionError(
                f"{screen}: {len(unexpected)} bytes changed outside audited map cells"
            )
        changed_summary["maps"][screen] = {
            "changed_bytes": len(changes),
            "allowed_target_bytes": len(allowed),
            "changed_word_offsets": [
                f"0x{index:04X}" for index in sorted({position // 2 * 2 for position in changes})
            ],
        }

    for label in LABELS:
        validate_label_render(
            patched_tiles[label.bank], patched_maps[label.screen], label
        )
    for label in BANNER_LABELS:
        validate_banner_render(
            patched_tiles[label.bank], patched_maps[label.screen], label
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    assets: dict[str, dict] = {}
    for bank, payload in patched_tiles.items():
        filename = OUTPUT_NAMES[bank]
        path = output_dir / filename
        path.write_bytes(payload)
        region = TILE_REGIONS[bank]
        assets[filename] = {
            "kind": "packed_4bpp_tiles",
            "rom_offset": f"0x{region.offset:06X}",
            "length": len(payload),
            "source_sha256": region.source_sha256,
            "output_sha256": sha256(payload),
        }

    map_output_keys = {
        "chip_folder": "chip_folder",
        "data_library": "data_library",
        "netnavi": "netnavi_map",
        "save": "save_map",
    }
    for screen, payload in patched_maps.items():
        filename = OUTPUT_NAMES[map_output_keys[screen]]
        path = output_dir / filename
        path.write_bytes(payload)
        region = MAP_REGIONS[screen]
        assets[filename] = {
            "kind": "bg0_tilemap",
            "rom_offset": f"0x{region.offset:06X}",
            "length": len(payload),
            "source_sha256": region.source_sha256,
            "output_sha256": sha256(payload),
        }

    previews = {}
    screen_banks = {
        "chip_folder": "chip_library",
        "data_library": "chip_library",
        "netnavi": "netnavi",
        "save": "save",
    }
    for screen, bank in screen_banks.items():
        filename = f"pet_submenu_{screen}_comparison_v0_9.png"
        path = output_dir / filename
        comparison_preview(
            original_tiles[bank], original_maps[screen],
            patched_tiles[bank], patched_maps[screen], screen, path,
        )
        previews[filename] = {"sha256": sha256(path.read_bytes())}

    report = {
        "generator": Path(__file__).name,
        "version": "0.9",
        "source_rom": {"path": str(source_rom), "sha256": actual_rom_sha},
        "format": {
            "tiles": "8x8 packed 4bpp, 32 bytes per tile, high nibble first",
            "map": "little-endian 16-bit BG0 words; tile index is word & 0x1FF",
            "runtime_mapping": {"tiles": "CPU:0x8000", "maps": "CPU:0x2000"},
        },
        "labels": label_reports,
        "assets": assets,
        "previews": previews,
        "changed": changed_summary,
        "source_alias_validation": alias_report,
        "validation": validation,
        "notes": [
            "All complete source assets are hash-guarded.",
            "Only allocated text tiles and audited map cells may differ.",
            "Unused original Japanese glyph tiles are preserved but no longer referenced by visible target cells.",
            "NetNavi units render as T (types) and C (chips); Save uses C for the chip count.",
            "Y2 リュック and Y2 ロックマン render with official English names Y2 PACK and Y2 MEGAMAN.",
        ],
    }
    report_path = output_dir / "pet_submenu_asset_report_v0_9.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "report": str(report_path),
                "assets": {
                    name: details["output_sha256"] for name, details in assets.items()
                },
                "validation": validation,
            },
            indent=2,
        )
    )
    return report


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", required=True, type=Path, help="verified Japanese WSC ROM")
    parser.add_argument(
        "--output-dir", type=Path,
        default=project_root / "translation" / "assets",
        help="directory for complete binary assets, comparisons and report",
    )
    args = parser.parse_args()
    build(args.rom, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
