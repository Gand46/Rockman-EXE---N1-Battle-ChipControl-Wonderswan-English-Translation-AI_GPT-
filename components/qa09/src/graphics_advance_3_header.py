#!/usr/bin/env python3
"""Rebuild PROGRAM DECK Y4 and CHIP FOLDER at native WonderSwan pixels."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw


VERSION = "0.10.7-graphics-a3"
BASE_ROM_SHA256 = "55616bc011c8439a693587c08dae9cf814801e61879ce280e253b0674e6004e5"
ROM_SIZE = 0x400000
MAP_OFFSET = 0x0438BE
MAP_LENGTH = 0x0680
MAP_SHA256 = "9e42f97603c3367d56c1040d3de8925ac52d104ca48ca3131cb58c136d97b0d0"
TILES_OFFSET = 0x07EC10
TILES_LENGTH = 0x16C0
TILES_SHA256 = "178c0ee009c76edf96f9a4104cc07a7d47bb230928d08b1c08ff69adea30da66"
TILE_BYTES = 32
MAP_WIDTH = 32
TILE_MASK = 0x01FF
RESIDUE_CELLS = ((16, 0), (16, 1))
BLANK_MAP_WORD = 0x2404

LEFT_TILE_IDS = tuple(range(0x010, 0x017))
RIGHT_TILE_IDS = (
    0x02A, 0x02B, 0x02C, 0x02D, 0x02E, 0x02F,
    0x030, 0x037, 0x038, 0x039, 0x03A, 0x03B,
)
TARGET_IDS = set(LEFT_TILE_IDS) | set(RIGHT_TILE_IDS)
MAPS = {
    "program_alt": (0x0438BE, 0x0680),
    "chip_folder": (0x043F40, 0x0680),
    "backpack": (0x0445C2, 0x0680),
    "data_library": (0x044C44, 0x0680),
}

FONT_3X5 = {
    "A": ("010", "101", "111", "101", "101"),
    "C": ("011", "100", "100", "100", "011"),
    "D": ("110", "101", "101", "101", "110"),
    "E": ("111", "100", "110", "100", "111"),
    "G": ("011", "100", "101", "101", "011"),
    "K": ("101", "101", "110", "101", "101"),
    "M": ("101", "111", "111", "101", "101"),
    "O": ("010", "101", "101", "101", "010"),
    "P": ("110", "101", "110", "100", "100"),
    "R": ("110", "101", "110", "101", "101"),
    "Y": ("101", "101", "010", "010", "010"),
    "4": ("101", "101", "111", "001", "001"),
}

# Native nine-pixel masks retain the approved BN5-derived structure used by
# Graphics Advance 2.  F is added for CHIP FOLDER with the same three-pixel
# stem/bars and the same one-column interglyph rhythm.
FONT_9 = {
    "C": (".##", "#..", "#..", "#..", "#..", "#..", "#..", "#..", ".##"),
    "D": ("##.", "#.#", "#.#", "#.#", "#.#", "#.#", "#.#", "#.#", "##."),
    "E": ("###", "#..", "#..", "#..", "##.", "#..", "#..", "#..", "###"),
    "F": ("###", "#..", "#..", "#..", "##.", "#..", "#..", "#..", "#.."),
    "H": ("#.#", "#.#", "#.#", "#.#", "###", "#.#", "#.#", "#.#", "#.#"),
    "I": ("#", "#", "#", "#", "#", "#", "#", "#", "#"),
    "L": ("#..", "#..", "#..", "#..", "#..", "#..", "#..", "#..", "###"),
    "O": (".#.", "#.#", "#.#", "#.#", "#.#", "#.#", "#.#", "#.#", ".#."),
    "P": ("##.", "#.#", "#.#", "#.#", "##.", "#..", "#..", "#..", "#.."),
    "R": ("##.", "#.#", "#.#", "#.#", "##.", "#.#", "#.#", "#.#", "#.#"),
}


def sha256(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def unpack_tile(payload: bytes) -> list[int]:
    if len(payload) != TILE_BYTES:
        raise ValueError("invalid tile length")
    return [value for byte in payload for value in (byte >> 4, byte & 0x0F)]


def pack_tile(pixels: list[int]) -> bytes:
    if len(pixels) != 64 or any(not 0 <= value <= 15 for value in pixels):
        raise ValueError("invalid 4bpp tile")
    return bytes((pixels[index] << 4) | pixels[index + 1] for index in range(0, 64, 2))


def read_canvas(bank: bytes | bytearray, tile_ids: tuple[int, ...], columns: int) -> list[list[int]]:
    rows = len(tile_ids) // columns
    canvas = [[0] * (columns * 8) for _ in range(rows * 8)]
    for index, tile_id in enumerate(tile_ids):
        pixels = unpack_tile(bytes(bank[tile_id * TILE_BYTES:(tile_id + 1) * TILE_BYTES]))
        cell_x, cell_y = index % columns, index // columns
        for y in range(8):
            for x in range(8):
                canvas[cell_y * 8 + y][cell_x * 8 + x] = pixels[y * 8 + x]
    return canvas


def write_canvas(bank: bytearray, tile_ids: tuple[int, ...], columns: int,
                 canvas: list[list[int]]) -> None:
    rows = len(tile_ids) // columns
    if len(canvas) != rows * 8 or len(canvas[0]) != columns * 8:
        raise ValueError("canvas geometry differs from tile allocation")
    for index, tile_id in enumerate(tile_ids):
        cell_x, cell_y = index % columns, index // columns
        pixels = [
            canvas[cell_y * 8 + y][cell_x * 8 + x]
            for y in range(8) for x in range(8)
        ]
        bank[tile_id * TILE_BYTES:(tile_id + 1) * TILE_BYTES] = pack_tile(pixels)


def draw_3x5(canvas: list[list[int]], text: str, x0: int, y0: int, face: int,
             space_width: int = 1) -> list[list[object]]:
    cursor = x0
    boxes = []
    for character in text:
        if character == " ":
            cursor += space_width
            continue
        rows = FONT_3X5[character]
        for y, row in enumerate(rows):
            for x, enabled in enumerate(row):
                if enabled == "1":
                    canvas[y0 + y][cursor + x] = face
        boxes.append([character, cursor, y0, 3, 5])
        cursor += 4
    return boxes


def render_left(bank: bytearray) -> dict[str, object]:
    canvas = read_canvas(bank, LEFT_TILE_IDS, 7)
    # The prior renderer left the already-present orange Y4 underneath a
    # second dark Y4.  Recover the two semantic colour zones explicitly.
    for y in range(7):
        for x in range(46):
            if canvas[y][x] == 2:
                canvas[y][x] = 6
    for y in range(8):
        for x in range(46, 56):
            canvas[y][x] = 3
    program_boxes = draw_3x5(canvas, "PROGRAM DECK", 1, 1, 2, 1)
    y4_boxes = draw_3x5(canvas, "Y4", 48, 1, 6, 1)
    write_canvas(bank, LEFT_TILE_IDS, 7, canvas)
    if any(canvas[y][x] == 2 for y in range(8) for x in range(46, 56)):
        raise AssertionError("dark PROGRAM DECK pixels entered the Y4 field")
    if any(canvas[y][x] == 6 for y in range(8) for x in range(46, 56)
           if not (1 <= y <= 5 and 48 <= x <= 54)):
        raise AssertionError("orange residue remains outside the rebuilt Y4 mask")
    return {
        "text": "PROGRAM DECK Y4",
        "map_rectangle": [1, 1, 7, 1],
        "runtime_rectangle": [8, 8, 64, 16],
        "tile_ids": [f"0x{value:03X}" for value in LEFT_TILE_IDS],
        "program_deck_boxes": program_boxes,
        "y4_boxes": y4_boxes,
        "program_deck_face_index": 2,
        "y4_face_index": 6,
        "semantic_colour_zones_separated": True,
        "minimum_interglyph_gap_pixels": 1,
    }


def field_width_9(text: str) -> int:
    return sum(1 if character == " " else len(FONT_9[character][0]) for character in text) + len(text) - 1


def render_right(bank: bytearray) -> dict[str, object]:
    canvas = read_canvas(bank, RIGHT_TILE_IDS, 6)
    width, height = 48, 16
    for y in range(height):
        for x in range(width):
            canvas[y][x] = 3
    text = "CHIP FOLDER"
    used = field_width_9(text)
    left = (width - used) // 2
    top = 3
    cursor = left
    face_points = []
    boxes = []
    for character in text:
        if character == " ":
            cursor += 2
            continue
        rows = FONT_9[character]
        glyph_width = len(rows[0])
        points = []
        for y, row in enumerate(rows):
            for x, value in enumerate(row):
                if value == "#":
                    points.append((cursor + x, top + y))
        face_points.extend(points)
        boxes.append([character, cursor, top, glyph_width, 9])
        cursor += glyph_width + 1
    for x, y in face_points:
        if x + 1 < width and y + 1 < height:
            canvas[y + 1][x + 1] = 9
    for x, y in face_points:
        canvas[y][x] = 15
    write_canvas(bank, RIGHT_TILE_IDS, 6, canvas)
    palette = {value for row in canvas for value in row}
    if palette != {3, 9, 15}:
        raise AssertionError(f"CHIP FOLDER palette differs: {sorted(palette)}")
    return {
        "text": text,
        "map_rectangle": [10, 0, 6, 2],
        "runtime_rectangle": [80, 0, 128, 16],
        "tile_ids": [f"0x{value:03X}" for value in RIGHT_TILE_IDS],
        "field_pixels": [width, height],
        "render_width_pixels": used,
        "left_margin_pixels": left,
        "right_margin_pixels": width - used - left,
        "top_margin_pixels": top,
        "bottom_margin_pixels": height - top - 9,
        "glyph_boxes": boxes,
        "face_index": 15,
        "shadow_index": 9,
        "background_index": 3,
        "minimum_interglyph_gap_pixels": 1,
        "word_gap_pixels": 3,
    }


def map_tile(tilemap: bytes, x: int, y: int) -> int:
    start = (y * MAP_WIDTH + x) * 2
    return int.from_bytes(tilemap[start:start + 2], "little") & TILE_MASK


def clear_residue(tilemap: bytes) -> tuple[bytes, list[dict[str, object]]]:
    output = bytearray(tilemap)
    changes = []
    for x, y in RESIDUE_CELLS:
        start = (y * MAP_WIDTH + x) * 2
        before = int.from_bytes(output[start:start + 2], "little")
        output[start:start + 2] = BLANK_MAP_WORD.to_bytes(2, "little")
        changes.append({
            "cell": [x, y],
            "previous_word": f"0x{before:04X}",
            "previous_tile_id": f"0x{before & TILE_MASK:03X}",
            "replacement_word": f"0x{BLANK_MAP_WORD:04X}",
        })
    changed = [index for index, pair in enumerate(zip(tilemap, output, strict=True)) if pair[0] != pair[1]]
    allowed = {
        (y * MAP_WIDTH + x) * 2 + byte
        for x, y in RESIDUE_CELLS for byte in range(2)
    }
    if not set(changed) <= allowed:
        raise AssertionError("Program Deck map changed outside the residue cells")
    return bytes(output), changes


def consumer_graph(rom: bytes) -> dict[str, list[list[object]]]:
    graph = {f"0x{tile:03X}": [] for tile in sorted(TARGET_IDS)}
    for map_name, (offset, length) in MAPS.items():
        tilemap = rom[offset:offset + length]
        for position in range(0, length, 2):
            tile = int.from_bytes(tilemap[position:position + 2], "little") & TILE_MASK
            if tile in TARGET_IDS:
                cell = position // 2
                graph[f"0x{tile:03X}"].append([map_name, cell % MAP_WIDTH, cell // MAP_WIDTH])
    expected_left = [["program_alt", x, 1] for x in range(1, 8)]
    actual_left = [graph[f"0x{tile:03X}"][0] for tile in LEFT_TILE_IDS]
    if actual_left != expected_left or any(len(graph[f"0x{tile:03X}"]) != 1 for tile in LEFT_TILE_IDS):
        raise AssertionError("PROGRAM DECK Y4 tiles are not exclusive")
    expected_right = [
        ["program_alt", x, y]
        for y, xs in ((0, range(10, 16)), (1, range(10, 16))) for x in xs
    ]
    actual_right = [graph[f"0x{tile:03X}"][0] for tile in RIGHT_TILE_IDS]
    if actual_right != expected_right or any(len(graph[f"0x{tile:03X}"]) != 1 for tile in RIGHT_TILE_IDS):
        raise AssertionError("CHIP FOLDER tiles are not exclusive")
    return graph


def preview(before: bytes, after: bytes, output: Path) -> None:
    def render(bank: bytes, ids: tuple[int, ...], columns: int) -> Image.Image:
        canvas = read_canvas(bank, ids, columns)
        colours = {
            2: (51, 51, 51), 3: (85, 102, 102), 6: (255, 136, 0),
            9: (51, 51, 51), 15: (238, 221, 204),
        }
        image = Image.new("RGB", (len(canvas[0]), len(canvas)), colours[3])
        for y, row in enumerate(canvas):
            for x, value in enumerate(row):
                image.putpixel((x, y), colours.get(value, (value * 17,) * 3))
        return image
    rows = (("PROGRAM DECK Y4", LEFT_TILE_IDS, 7), ("CHIP FOLDER", RIGHT_TILE_IDS, 6))
    scale, gap, caption = 8, 20, 22
    width = 56 * scale * 2 + gap
    height = sum((len(ids) // columns * 8) * scale + caption for _, ids, columns in rows)
    image = Image.new("RGB", (width, height), (24, 24, 24))
    draw = ImageDraw.Draw(image)
    y0 = 0
    for title, ids, columns in rows:
        h = len(ids) // columns * 8
        left = render(before, ids, columns).resize((columns * 8 * scale, h * scale), Image.Resampling.NEAREST)
        right = render(after, ids, columns).resize((columns * 8 * scale, h * scale), Image.Resampling.NEAREST)
        draw.text((0, y0 + 4), f"A2 {title}", fill="white")
        draw.text((56 * scale + gap, y0 + 4), f"A3 {title}", fill="white")
        image.paste(left, (0, y0 + caption))
        image.paste(right, (56 * scale + gap, y0 + caption))
        y0 += h * scale + caption
    image.save(output, optimize=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-rom", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    rom = args.base_rom.read_bytes()
    if len(rom) != ROM_SIZE or sha256(rom) != BASE_ROM_SHA256:
        raise ValueError("Graphics Advance 3 requires the exact approved A2 ROM")
    tilemap = rom[MAP_OFFSET:MAP_OFFSET + MAP_LENGTH]
    before = rom[TILES_OFFSET:TILES_OFFSET + TILES_LENGTH]
    if sha256(tilemap) != MAP_SHA256 or sha256(before) != TILES_SHA256:
        raise ValueError("A2 Program Deck alternate resources differ")
    graph = consumer_graph(rom)
    output_map, residue_changes = clear_residue(tilemap)
    after = bytearray(before)
    left = render_left(after)
    right = render_right(after)
    changed = {index for index, pair in enumerate(zip(before, after, strict=True)) if pair[0] != pair[1]}
    allowed = {
        tile * TILE_BYTES + byte for tile in TARGET_IDS for byte in range(TILE_BYTES)
    }
    if not changed <= allowed:
        raise AssertionError("tile bank changed outside the two target headers")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    asset = args.output_dir / "pet_submenu_chip_library_tiles_graphics_a3.bin"
    asset.write_bytes(after)
    map_asset = args.output_dir / "program_deck_chip_folder_bg0_map_graphics_a3.bin"
    map_asset.write_bytes(output_map)
    preview_path = args.output_dir / "graphics_advance_3_header_preview.png"
    preview(before, after, preview_path)
    report = {
        "status": "PASS",
        "version": VERSION,
        "advance": "3 of 6",
        "base_rom_sha256": BASE_ROM_SHA256,
        "map_source_sha256": MAP_SHA256,
        "map_output_sha256": sha256(output_map),
        "map_modified": True,
        "map_changed_bytes": sum(left != right for left, right in zip(tilemap, output_map, strict=True)),
        "map_changed_cells": residue_changes,
        "residue_runtime_rectangle": [128, 0, 136, 16],
        "replacement_blank_map_word": f"0x{BLANK_MAP_WORD:04X}",
        "shared_residue_tile_preserved": "0x01C",
        "tile_bank_source_sha256": TILES_SHA256,
        "tile_bank_output_sha256": sha256(after),
        "changed_bytes_vs_a2": len(changed),
        "changed_tile_ids": [f"0x{tile:03X}" for tile in sorted({index // TILE_BYTES for index in changed})],
        "outside_target_tile_bytes": 0,
        "exclusive_target_tiles": len(TARGET_IDS),
        "unresolved_external_consumers": 0,
        "consumer_graph": graph,
        "labels": {"program_deck_y4": left, "chip_folder": right},
        "semantic_source": {
            "japanese_left": "プログラムデッキ Y4",
            "english_left": "PROGRAM DECK Y4",
            "japanese_right": "チップフォルダ",
            "english_right": "CHIP FOLDER",
            "auto_control_rejected_as_semantically_incorrect": True,
        },
        "output_asset": asset.name,
        "output_asset_sha256": sha256(after),
        "output_map_asset": map_asset.name,
        "output_map_asset_sha256": sha256(output_map),
        "preview": preview_path.name,
        "preview_sha256": sha256(preview_path.read_bytes()),
    }
    report_path = args.output_dir / "graphics_advance_3_header_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
