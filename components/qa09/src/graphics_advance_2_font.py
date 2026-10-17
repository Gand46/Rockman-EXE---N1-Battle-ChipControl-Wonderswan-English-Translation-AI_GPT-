#!/usr/bin/env python3
"""Rebuild the three marked Program Deck overview labels at native pixels."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import n1tool  # noqa: E402


VERSION = "0.10.7-graphics-a2"
ROM_SIZE = 0x400000
BASE_ROM_SHA256 = "63ce8069d89106fdc96167a14d139641db202d23e0a2cd539347e19f8fcd8575"
REFERENCE_ROM_SHA256 = "fb78269238806807616cfe622a3be9239dc5b95bbd454ee02127919dd463e3cc"
BN5_TTF_SHA256 = "8f01cacff269f66e3f4d80beae13d6f86a30d00b297da32aa0af90461662ac2d"
SF3_TTF_SHA256 = "c21fece52fb8b49f8347f60b5cf4cefc5cb5cb19aac56f4e004f4ad22bd5a220"
OVERVIEW_MAP_OFFSET = 0x04E7A2
OVERVIEW_MAP_LENGTH = 0x0400
OVERVIEW_MAP_SHA256 = "dae21d3008c802577d494f9a0cff498c695ae01b395c9dfbd6f0c70da32d6ded"
MANUAL_TILES_OFFSET = 0x0ACA20
MANUAL_TILES_LENGTH = 0x5B60
MANUAL_TILES_SHA256 = "55a35c591c32ba40b45adae4e1eac4f3c4cb63b4eaf1fb5742c168e0703adf6e"
OVERVIEW_TILES_LENGTH = 0x1140
OVERVIEW_TILES_SHA256 = "c5e5905e18b4852308f05305e0b5583492bf85dd7248ee292832881cdd999324"
REFERENCE_MANUAL_TILES_SHA256 = "e73fb7e716cafeea1f5c5c707621cf6749694ea982a446b5a4e1ddea8d83df11"
TILE_BYTES = 32
TILE_MASK = 0x01FF
MAP_WIDTH = 32


# BN5-derived native masks, manually polished after reviewing the TTF and the
# 224x144 runtime capture.  These labels are physically two tiles high.  A
# narrow nine-pixel cap height matches the original sign proportions while
# retaining a full-pixel gap between glyphs and clean space above/below.
PATTERNS: dict[str, tuple[str, ...]] = {
    "A": (".#.", "#.#", "#.#", "#.#", "###", "#.#", "#.#", "#.#", "#.#"),
    "B": ("##.", "#.#", "#.#", "##.", "#.#", "#.#", "#.#", "#.#", "##."),
    "C": (".##", "#..", "#..", "#..", "#..", "#..", "#..", "#..", ".##"),
    "D": ("##.", "#.#", "#.#", "#.#", "#.#", "#.#", "#.#", "#.#", "##."),
    "E": ("###", "#..", "#..", "#..", "##.", "#..", "#..", "#..", "###"),
    "G": (".##", "#..", "#..", "#..", "#.#", "#.#", "#.#", "#.#", ".##"),
    "H": ("#.#", "#.#", "#.#", "#.#", "###", "#.#", "#.#", "#.#", "#.#"),
    "I": ("#", "#", "#", "#", "#", "#", "#", "#", "#"),
    "K": ("#.#", "#.#", "#.#", "##.", "#..", "##.", "#.#", "#.#", "#.#"),
    "L": ("#..", "#..", "#..", "#..", "#..", "#..", "#..", "#..", "###"),
    "M": ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#", "#...#", "#...#"),
    "N": ("#..#", "##.#", "##.#", "#..#", "#..#", "#.##", "#.##", "#..#", "#..#"),
    "O": (".#.", "#.#", "#.#", "#.#", "#.#", "#.#", "#.#", "#.#", ".#."),
    "P": ("##.", "#.#", "#.#", "#.#", "##.", "#..", "#..", "#..", "#.."),
    "R": ("##.", "#.#", "#.#", "#.#", "##.", "#.#", "#.#", "#.#", "#.#"),
    "T": ("###", ".#.", ".#.", ".#.", ".#.", ".#.", ".#.", ".#.", ".#."),
    "V": ("#.#", "#.#", "#.#", "#.#", "#.#", "#.#", "#.#", "#.#", ".#."),
}


@dataclass(frozen=True)
class Label:
    id: str
    text: str
    x: int
    y: int
    columns: int
    rows: int
    source_tile_ids: tuple[int, ...]
    tile_ids: tuple[int, ...]
    face: int


LABELS = (
    Label("manual_program_deck", "PROGRAM DECK", 1, 1, 6, 2,
          (0x010, 0x011, 0x012, 0x013, 0x014, 0x015,
           0x016, 0x00E, 0x00E, 0x00E, 0x00E, 0x026),
          (0x010, 0x011, 0x012, 0x013, 0x014, 0x015,
           0x016, 0x06C, 0x06D, 0x06E, 0x06F, 0x026), 7),
    Label("manual_navichip", "NAVICHIP", 1, 7, 5, 2,
          (0x022, 0x023, 0x029, 0x024, 0x025,
           0x057, 0x058, 0x059, 0x05A, 0x05B),
          (0x022, 0x023, 0x029, 0x024, 0x025,
           0x057, 0x058, 0x059, 0x05A, 0x05B), 5),
    # Unlike the two left signs, BATTLECHIP occupies map rows 6-7.  The
    # rejected candidate incorrectly treated rows 7-8 as its two-line field,
    # leaving the old upper half visible and painting into the purple grid.
    Label("manual_battlechip", "BATTLECHIP", 22, 6, 5, 2,
          (0x05C, 0x05D, 0x05E, 0x05F, 0x06A,
           0x027, 0x028, 0x055, 0x056, 0x06B),
          (0x05C, 0x05D, 0x05E, 0x05F, 0x06A,
           0x027, 0x028, 0x055, 0x056, 0x06B), 6),
)
BACKGROUND = 8


def sha256(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def map_word(tilemap: bytes, x: int, y: int) -> int:
    start = (y * MAP_WIDTH + x) * 2
    return int.from_bytes(tilemap[start:start + 2], "little")


def pack_tile(pixels: list[int]) -> bytes:
    if len(pixels) != 64 or any(not 0 <= value <= 15 for value in pixels):
        raise ValueError("invalid 4bpp tile")
    return bytes((pixels[index] << 4) | pixels[index + 1] for index in range(0, 64, 2))


def unpack_tile(payload: bytes) -> list[int]:
    if len(payload) != TILE_BYTES:
        raise ValueError("invalid packed tile length")
    return [value for byte in payload for value in (byte >> 4, byte & 0x0F)]


def field_width(text: str) -> int:
    return sum(0 if character == " " else len(PATTERNS[character][0]) for character in text) + len(text) - 1


def render_label(label: Label) -> tuple[list[int], dict[str, object]]:
    width, height = label.columns * 8, label.rows * 8
    used = field_width(label.text)
    if used > width:
        raise ValueError(f"{label.id}: {used}px exceeds {width}px")
    left = (width - used) // 2
    right = width - used - left
    if min(left, right) < 1:
        raise ValueError(f"{label.id}: native side margin is below one pixel")
    canvas = [BACKGROUND] * (width * height)
    cursor = left
    glyph_boxes = []
    glyph_height = len(next(iter(PATTERNS.values())))
    top = (height - glyph_height) // 2
    for character in label.text:
        if character == " ":
            cursor += 1
            continue
        rows = PATTERNS[character]
        glyph_width = len(rows[0])
        for glyph_y, row in enumerate(rows):
            for glyph_x, value in enumerate(row):
                if value == "#":
                    canvas[(top + glyph_y) * width + cursor + glyph_x] = label.face
        glyph_boxes.append([character, cursor, top, glyph_width, glyph_height])
        cursor += glyph_width + 1
    patterns = []
    for cell_y in range(label.rows):
        for cell_x in range(label.columns):
            patterns.append(pack_tile([
                canvas[(cell_y * 8 + y) * width + cell_x * 8 + x]
                for y in range(8) for x in range(8)
            ]))
    return patterns, {
        "id": label.id,
        "text": label.text,
        "rectangle": [label.x, label.y, label.columns, label.rows],
        "tile_ids": [f"0x{value:03X}" for value in label.tile_ids],
        "field_width_pixels": width,
        "render_width_pixels": used,
        "left_margin_pixels": left,
        "right_margin_pixels": right,
        "glyph_height_pixels": glyph_height,
        "top_margin_pixels": top,
        "bottom_margin_pixels": height - glyph_height - top,
        "minimum_interglyph_gap_pixels": 1,
        "glyph_boxes": glyph_boxes,
        "face_index": label.face,
        "background_index": BACKGROUND,
    }


def asset_consumers(tilemap: bytes, asset_index: int) -> list[list[int]]:
    # Runtime loads the first asset slot at CPU 0x8020.  A map tile ID N
    # therefore consumes asset slot N-1.
    tile_id = asset_index + 1
    consumers = []
    for position in range(0, len(tilemap), 2):
        if int.from_bytes(tilemap[position:position + 2], "little") & TILE_MASK == tile_id:
            cell = position // 2
            consumers.append([cell % MAP_WIDTH, cell // MAP_WIDTH])
    return consumers


def label_image(tilemap: bytes, tiles: bytes, label: Label) -> Image.Image:
    colours = {BACKGROUND: (84, 102, 102), 5: (255, 221, 34), 6: (255, 238, 153), 7: (255, 255, 238)}
    image = Image.new("RGB", (label.columns * 8, label.rows * 8), colours[BACKGROUND])
    for cell_y in range(label.rows):
        for cell_x in range(label.columns):
            tile_id = map_word(tilemap, label.x + cell_x, label.y + cell_y) & TILE_MASK
            start = (tile_id - 1) * TILE_BYTES
            pixels = unpack_tile(tiles[start:start + TILE_BYTES])
            for y in range(8):
                for x in range(8):
                    image.putpixel(
                        (cell_x * 8 + x, cell_y * 8 + y),
                        colours.get(pixels[y * 8 + x], (0, 0, 0)),
                    )
    return image


def build_preview(
    before_map: bytes, before_tiles: bytes, after_map: bytes, after_tiles: bytes, output: Path
) -> None:
    scale = 8
    width = max(label.columns * 8 for label in LABELS) * scale
    label_height = max(label.rows * 8 for label in LABELS)
    row_height = label_height * scale + 24
    canvas = Image.new("RGB", (width * 2 + 24, row_height * len(LABELS) + 28), (24, 24, 24))
    draw = ImageDraw.Draw(canvas)
    draw.text((0, 6), "A1", fill=(255, 255, 255))
    draw.text((width + 24, 6), "A2 pixel-art", fill=(255, 255, 255))
    for index, label in enumerate(LABELS):
        y = 28 + index * row_height
        before = label_image(before_map, before_tiles, label).resize(
            (label.columns * 8 * scale, label.rows * 8 * scale), Image.Resampling.NEAREST
        )
        after = label_image(after_map, after_tiles, label).resize(
            (label.columns * 8 * scale, label.rows * 8 * scale), Image.Resampling.NEAREST
        )
        canvas.paste(before, (0, y))
        canvas.paste(after, (width + 24, y))
        draw.text((0, y + label.rows * 8 * scale + 4), label.id, fill=(220, 220, 220))
    canvas.save(output, optimize=False)


def validate_patterns() -> dict[str, object]:
    required = sorted(set("".join(label.text.replace(" ", "") for label in LABELS)))
    missing = sorted(set(required) - PATTERNS.keys())
    if missing:
        raise ValueError(f"missing glyph patterns: {missing}")
    for character in required:
        rows = PATTERNS[character]
        if len(rows) != 9 or len({len(row) for row in rows}) != 1:
            raise ValueError(f"{character}: invalid native geometry")
        if any(set(row) - {".", "#"} for row in rows):
            raise ValueError(f"{character}: invalid pixel value")
    pairs = (("C", "G"), ("P", "R"), ("B", "P"), ("I", "T"), ("M", "N"))
    distinctions = {}
    for left, right in pairs:
        a = "".join(PATTERNS[left])
        b = "".join(PATTERNS[right])
        if len(a) == len(b):
            distance = sum(x != y for x, y in zip(a, b))
        else:
            distance = abs(len(a) - len(b)) + sum(x != y for x, y in zip(a, b))
        if distance < 2:
            raise AssertionError(f"ambiguous glyph pair: {left}/{right}")
        distinctions[f"{left}/{right}"] = distance
    return {"required_glyphs": required, "ambiguous_pair_pixel_distances": distinctions}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-rom", required=True, type=Path)
    parser.add_argument("--reference-rom", required=True, type=Path)
    parser.add_argument("--bn5-font", required=True, type=Path)
    parser.add_argument("--sf3-font", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "translation/assets")
    args = parser.parse_args()
    rom = args.base_rom.read_bytes()
    reference_rom = args.reference_rom.read_bytes()
    if len(rom) != ROM_SIZE or sha256(rom) != BASE_ROM_SHA256:
        raise ValueError("Advance 2 requires the exact approved Graphics Advance 1 ROM")
    if len(reference_rom) != ROM_SIZE or sha256(reference_rom) != REFERENCE_ROM_SHA256:
        raise ValueError("Advance 2 requires the approved v0.10.6 intact-art reference")
    if sha256(args.bn5_font.read_bytes()) != BN5_TTF_SHA256:
        raise ValueError("BN5DSEU Font Thin identity differs")
    if sha256(args.sf3_font.read_bytes()) != SF3_TTF_SHA256:
        raise ValueError("SF3FontSmall identity differs")
    # Loading both files proves they remain valid TrueType masters. BN5 is the
    # selected role for these labels; SF3 remains a verified alternative.
    ImageFont.truetype(str(args.bn5_font), 7, layout_engine=ImageFont.Layout.BASIC)
    ImageFont.truetype(str(args.sf3_font), 7, layout_engine=ImageFont.Layout.BASIC)
    pattern_report = validate_patterns()

    overview_map = rom[OVERVIEW_MAP_OFFSET:OVERVIEW_MAP_OFFSET + OVERVIEW_MAP_LENGTH]
    manual_source = rom[MANUAL_TILES_OFFSET:MANUAL_TILES_OFFSET + MANUAL_TILES_LENGTH]
    manual_reference = reference_rom[
        MANUAL_TILES_OFFSET:MANUAL_TILES_OFFSET + MANUAL_TILES_LENGTH
    ]
    if sha256(overview_map) != OVERVIEW_MAP_SHA256:
        raise ValueError("approved overview map differs")
    if sha256(manual_source) != MANUAL_TILES_SHA256:
        raise ValueError("approved manual tile atlas differs")
    if sha256(manual_source[:OVERVIEW_TILES_LENGTH]) != OVERVIEW_TILES_SHA256:
        raise ValueError("approved overview tile segment differs")
    if sha256(manual_reference) != REFERENCE_MANUAL_TILES_SHA256:
        raise ValueError("approved v0.10.6 manual tile reference differs")

    target_cells = {
        (label.x + cell_x, label.y + cell_y)
        for label in LABELS
        for cell_y in range(label.rows)
        for cell_x in range(label.columns)
    }
    target_asset_indices = {tile_id - 1 for label in LABELS for tile_id in label.tile_ids}
    map_output = bytearray(overview_map)
    consumer_graph = {}
    for label in LABELS:
        if len(label.tile_ids) != label.columns * label.rows:
            raise AssertionError(f"{label.id}: tile count differs from field")
        if len(label.source_tile_ids) != len(label.tile_ids):
            raise AssertionError(f"{label.id}: source tile count differs from field")
        for cell, (source_tile_id, tile_id) in enumerate(
            zip(label.source_tile_ids, label.tile_ids, strict=True)
        ):
            cell_x, cell_y = cell % label.columns, cell // label.columns
            coordinate = [label.x + cell_x, label.y + cell_y]
            word = map_word(overview_map, *coordinate)
            if word & TILE_MASK != source_tile_id:
                raise AssertionError(f"{label.id}: source map identity differs at {coordinate}")
            position = (coordinate[1] * MAP_WIDTH + coordinate[0]) * 2
            new_word = (word & ~TILE_MASK) | tile_id
            map_output[position:position + 2] = new_word.to_bytes(2, "little")

    for label in LABELS:
        for cell, tile_id in enumerate(label.tile_ids):
            cell_x, cell_y = cell % label.columns, cell // label.columns
            coordinate = [label.x + cell_x, label.y + cell_y]
            asset_index = tile_id - 1
            consumers = asset_consumers(bytes(map_output), asset_index)
            if consumers != [coordinate]:
                raise AssertionError(f"asset 0x{asset_index:03X} aliases cells {consumers}")
            consumer_graph[f"0x{asset_index:03X}"] = consumers

    manual_output = bytearray(manual_source)
    label_reports = []
    for label in LABELS:
        patterns, metrics = render_label(label)
        for tile_id, pattern in zip(label.tile_ids, patterns, strict=True):
            start = (tile_id - 1) * TILE_BYTES
            manual_output[start:start + TILE_BYTES] = pattern
        label_reports.append(metrics)

    allowed_asset_indices = target_asset_indices
    changed_asset_indices = {
        asset_index for asset_index in range(OVERVIEW_TILES_LENGTH // TILE_BYTES)
        if manual_source[asset_index * TILE_BYTES:(asset_index + 1) * TILE_BYTES]
        != manual_output[asset_index * TILE_BYTES:(asset_index + 1) * TILE_BYTES]
    }
    if not changed_asset_indices <= allowed_asset_indices:
        raise AssertionError("a non-target overview tile changed")
    if manual_output[OVERVIEW_TILES_LENGTH:] != manual_source[OVERVIEW_TILES_LENGTH:]:
        raise AssertionError("another Program Deck page tile segment changed")
    if any(tuple(cell) not in target_cells for cells in consumer_graph.values() for cell in cells):
        raise AssertionError("consumer graph escaped the semantic target")
    changed_map_cells = {
        (position // 2 % MAP_WIDTH, position // 2 // MAP_WIDTH)
        for position in range(0, OVERVIEW_MAP_LENGTH, 2)
        if overview_map[position:position + 2] != map_output[position:position + 2]
    }
    if not changed_map_cells <= target_cells:
        raise AssertionError("overview map changed outside the three label rectangles")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    map_path = args.output_dir / "program_deck_manual_overview_bg0_map_graphics_a2.bin"
    map_path.write_bytes(map_output)
    asset_path = args.output_dir / "program_deck_manual_internal_tiles_graphics_a2.bin"
    asset_path.write_bytes(manual_output)
    preview_path = args.output_dir / "graphics_advance_2_font_preview.png"
    build_preview(overview_map, manual_source, bytes(map_output), bytes(manual_output), preview_path)

    candidate = bytearray(rom)
    candidate[OVERVIEW_MAP_OFFSET:OVERVIEW_MAP_OFFSET + OVERVIEW_MAP_LENGTH] = map_output
    candidate[MANUAL_TILES_OFFSET:MANUAL_TILES_OFFSET + MANUAL_TILES_LENGTH] = manual_output
    checksum = n1tool.repair_checksum(candidate)
    changed_offsets = [index for index, (left, right) in enumerate(zip(rom, candidate)) if left != right]
    allowed_offsets = {
        MANUAL_TILES_OFFSET + asset_index * TILE_BYTES + byte
        for asset_index in allowed_asset_indices for byte in range(TILE_BYTES)
    } | {
        OVERVIEW_MAP_OFFSET + (y * MAP_WIDTH + x) * 2 + byte
        for x, y in target_cells for byte in range(2)
    } | {ROM_SIZE - 2, ROM_SIZE - 1}
    outside = [offset for offset in changed_offsets if offset not in allowed_offsets]
    if outside:
        raise AssertionError(f"ROM delta escaped allowlist at 0x{outside[0]:06X}")

    report = {
        "status": "PASS",
        "version": VERSION,
        "advance": "2 of 6",
        "base_rom_sha256": BASE_ROM_SHA256,
        "scope": ["PROGRAM DECK", "NAVICHIP", "BATTLECHIP"],
        "font_policy": {
            "master": "BN5DSEU Font Thin",
            "master_sha256": BN5_TTF_SHA256,
            "verified_alternative": "SF3FontSmall",
            "verified_alternative_sha256": SF3_TTF_SHA256,
            "rendering": "manual native masks derived from the selected TTF role",
            "antialiasing": False,
            "scaling": False,
            "filtering": False
        },
        "native_resolution": [224, 144],
        "overview_map_source_sha256": sha256(overview_map),
        "overview_map_output_sha256": sha256(map_output),
        "overview_map_modified": True,
        "overview_map_changed_cells": [list(cell) for cell in sorted(changed_map_cells)],
        "overview_map_changes_confined_to_label_rectangles": True,
        "runtime_tile_mapping": {
            "asset_load_cpu_base": "0x8020",
            "map_tile_id_to_asset_index": -1
        },
        "labels": label_reports,
        "pattern_validation": pattern_report,
        "consumer_graph": consumer_graph,
        "target_map_tile_ids": [
            f"0x{value:03X}" for value in sorted(
                tile_id for label in LABELS for tile_id in label.tile_ids
            )
        ],
        "target_asset_indices": [f"0x{value:03X}" for value in sorted(target_asset_indices)],
        "changed_asset_indices": [
            f"0x{value:03X}" for value in sorted(changed_asset_indices)
        ],
        "unresolved_external_consumers": 0,
        "shared_non_target_assets_modified": 0,
        "other_manual_page_segments_unchanged": True,
        "output_map_asset": map_path.name,
        "output_map_asset_sha256": sha256(map_output),
        "output_asset": asset_path.name,
        "output_asset_sha256": sha256(manual_output),
        "preview": preview_path.name,
        "preview_sha256": sha256(preview_path.read_bytes()),
        "rom_delta_vs_a1": {
            "changed_bytes": len(changed_offsets),
            "outside_allowlist": len(outside),
            "checksum": f"0x{checksum:04X}",
            "candidate_sha256_before_manifest_build": sha256(candidate)
        }
    }
    report_path = args.output_dir / "graphics_advance_2_font_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
