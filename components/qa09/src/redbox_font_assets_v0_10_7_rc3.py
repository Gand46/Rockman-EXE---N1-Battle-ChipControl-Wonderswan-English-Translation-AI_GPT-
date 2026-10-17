#!/usr/bin/env python3
"""Rebuild the red-box UI labels from the approved v0.10.6 pixel-art logic.

This generator deliberately starts from the pixel-polished v0.10.6 ROM.  It
does not consume any v0.10.7 RC2 asset.  Both supplied TTF files are verified,
but the marked PET and Program Deck fields use BN5DSEU Thin as their master
face because it matches the established v0.10.6 menu roles.  Every visible
glyph is then replaced by a deterministic proportional 1:1 mask: no hinted
glyph is accepted unreviewed at this resolution.

The regular masks are three to five pixels wide and seven pixels high.  A
compact mask from the same design is used only in fields whose immutable tile
geometry requires it.  Lines are never scaled, filtered, antialiased or
condensed after composition.  One native empty column remains between glyph
faces and shadows extend downward only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from PIL import Image, ImageDraw


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from font_atlas_assets_v0_10_6 import (  # noqa: E402
    Label as FontLabel,
    PIXEL_ART_PATTERNS,
    TTFFontSet,
)
from quality_graphics_assets_v0_10_3 import render_program_page  # noqa: E402


VERSION = "0.10.7-rc3"
ROM_SIZE = 0x400000
BASE_ROM_SHA256 = "fb78269238806807616cfe622a3be9239dc5b95bbd454ee02127919dd463e3cc"
BN5_TTF_SHA256 = "8f01cacff269f66e3f4d80beae13d6f86a30d00b297da32aa0af90461662ac2d"
SF3_TTF_SHA256 = "c21fece52fb8b49f8347f60b5cf4cefc5cb5cb19aac56f4e004f4ad22bd5a220"
MAP_WIDTH = 32
TILE_BYTES = 32
TILE_MASK = 0x01FF


@dataclass(frozen=True)
class Span:
    id: str
    offset: int
    length: int
    sha256: str
    output: str


SPANS = {
    "program_map": Span("program_map", 0x04323C, 0x0400, "ab70da1102f0d0f6c07416e2e5be2178e3b2f5a5f74497e483df33ebccab476f", "program_deck_live_bg0_map_v0_10_7_rc3.bin"),
    "program_alt_map": Span("program_alt_map", 0x0438BE, 0x0680, "d9e6f17908ad2da229bdf53a339e20a4e78a2641e447dd700d852d14485ef2cf", "program_deck_auto_control_bg0_map_v0_10_7_rc3.bin"),
    "backpack_map": Span("backpack_map", 0x0445C2, 0x0680, "782e352204c6e53684b8579668a3f1a8d6cdf9487247387bc5cb5334adec4c59", "pet_submenu_backpack_bg0_map_v0_10_7_rc3.bin"),
    "data_map": Span("data_map", 0x044C44, 0x0680, "0cea35569bcfe6b0302a51dd777653ca3089bcd23f87211d5b60d96aa0327f32", "pet_submenu_data_library_bg0_map_v0_10_7_rc3.bin"),
    "netnavi_map": Span("netnavi_map", 0x0452C6, 0x0480, "3966864b141ae128b02cf1020f199879b1aebe636da60e21d7776d7565aa329c", "pet_submenu_netnavi_bg0_map_v0_10_7_rc3.bin"),
    "netnavi_stats_map": Span("netnavi_stats_map", 0x045748, 0x0480, "51d99c5d476ad281e3e454a81c24723bdd0ac4863ef36e7c0b5038d3f1b1940f", "pet_submenu_netnavi_stats_bg0_map_v0_10_7_rc3.bin"),
    "overview_map": Span("overview_map", 0x04E7A2, 0x0400, "62a4dfc9378cc2158fad79259b49b6565b67927bb7abe5b139afd9d388a6e275", "program_deck_manual_overview_bg0_map_v0_10_7_rc3.bin"),
    "stats_map": Span("stats_map", 0x04EC24, 0x0400, "3dee6f7defb7d4b76c9223660140d861a4c2b0bdb1fffeaa7c9062d327eb4996", "program_deck_manual_stats_bg0_map_v0_10_7_rc3.bin"),
    "program_tiles": Span("program_tiles", 0x07CD20, 0x1EF0, "fafec0b9d72bf2c1a6222e8bf074f2e41aeb3d3f94b8b8c4db45572deb73cf37", "program_deck_live_ui_tiles_v0_10_7_rc3.bin"),
    "shared_tiles": Span("shared_tiles", 0x07EC10, 0x16C0, "6df9cb1a34503c6996b31d29ac569b0c4827bf5c43deb7c65f789e4e8144f0ea", "pet_submenu_chip_library_tiles_v0_10_7_rc3.bin"),
    "netnavi_tiles": Span("netnavi_tiles", 0x080300, 0x0D40, "9630d2731ff5ed25b818f1164d2163846df521a0ee4ed7fcb9c1ba6a800fdf91", "pet_submenu_netnavi_tiles_v0_10_7_rc3.bin"),
    "manual_tiles": Span("manual_tiles", 0x0ACA20, 0x5B60, "e73fb7e716cafeea1f5c5c707621cf6749694ea982a446b5a4e1ddea8d83df11", "program_deck_manual_internal_tiles_v0_10_7_rc3.bin"),
}


# Proportional seven-pixel alphabet.  Narrow glyphs are narrow because of
# their structure, not because a completed line was compressed.  Open
# counters, continuous stems and 45-degree diagonals are reviewed explicitly.
REGULAR_PATTERNS: dict[str, tuple[str, ...]] = {
    "0": (".##.", "#..#", "#..#", "#.##", "##.#", "#..#", ".##."),
    "2": (".##.", "#..#", "...#", "..#.", ".#..", "#...", "####"),
    "3": ("###.", "...#", "...#", ".##.", "...#", "...#", "###."),
    "/": ("..#", "..#", ".#.", ".#.", "#..", "#..", "..."),
    "A": (".##.", "#..#", "#..#", "####", "#..#", "#..#", "#..#"),
    "B": ("###.", "#..#", "#..#", "###.", "#..#", "#..#", "###."),
    "C": (".##", "#..", "#..", "#..", "#..", "#..", ".##"),
    "D": ("###.", "#..#", "#..#", "#..#", "#..#", "#..#", "###."),
    "E": ("###", "#..", "#..", "##.", "#..", "#..", "###"),
    "F": ("###", "#..", "#..", "##.", "#..", "#..", "#.."),
    "G": (".##.", "#...", "#...", "#.##", "#..#", "#..#", ".###"),
    "H": ("#..#", "#..#", "#..#", "####", "#..#", "#..#", "#..#"),
    "I": ("#", "#", "#", "#", "#", "#", "#"),
    "K": ("#..#", "#.#.", "##..", "#...", "##..", "#.#.", "#..#"),
    "L": ("#..", "#..", "#..", "#..", "#..", "#..", "###"),
    "M": ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "##..#", "##..#", "#.#.#", "#.#.#", "#..##", "#...#"),
    "O": (".##.", "#..#", "#..#", "#..#", "#..#", "#..#", ".##."),
    "P": ("###.", "#..#", "#..#", "###.", "#...", "#...", "#..."),
    "R": ("###.", "#..#", "#..#", "###.", "#.#.", "#..#", "#..#"),
    "S": (".###", "#...", "#...", ".##.", "...#", "...#", "###."),
    "T": ("###", ".#.", ".#.", ".#.", ".#.", ".#.", ".#."),
    "U": ("#..#", "#..#", "#..#", "#..#", "#..#", "#..#", ".##."),
    "V": ("#...#", "#...#", "#...#", "#...#", ".#.#.", ".#.#.", "..#.."),
    "W": ("#...#", "#...#", "#...#", "#...#", "#.#.#", "#.#.#", ".#.#."),
    "Y": ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
}


# Same visual grammar, reduced only for the one immutable 48-pixel plaque.
COMPACT_PATTERNS: dict[str, tuple[str, ...]] = {
    "2": (".##", "..#", "..#", ".#.", "#..", "#..", "###"),
    "A": (".#.", "#.#", "#.#", "###", "#.#", "#.#", "#.#"),
    "B": ("##.", "#.#", "#.#", "##.", "#.#", "#.#", "##."),
    "C": (".##", "#..", "#..", "#..", "#..", "#..", ".##"),
    "D": ("##.", "#.#", "#.#", "#.#", "#.#", "#.#", "##."),
    "E": ("###", "#..", "#..", "##.", "#..", "#..", "###"),
    "F": ("###", "#..", "#..", "##.", "#..", "#..", "#.."),
    "G": (".##", "#..", "#..", "#.#", "#.#", "#.#", ".##"),
    "H": ("#.#", "#.#", "#.#", "###", "#.#", "#.#", "#.#"),
    "I": ("#", "#", "#", "#", "#", "#", "#"),
    "K": ("#.#", "#.#", "##.", "#..", "##.", "#.#", "#.#"),
    "L": ("#..", "#..", "#..", "#..", "#..", "#..", "###"),
    # M keeps the regular five-pixel construction.  The previous four-pixel
    # block closed its internal valleys and could be mistaken for H.
    "M": ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    "N": ("#..#", "##.#", "##.#", "#.##", "#.##", "#..#", "#..#"),
    "O": (".#.", "#.#", "#.#", "#.#", "#.#", "#.#", ".#."),
    "P": ("##.", "#.#", "#.#", "##.", "#..", "#..", "#.."),
    "R": ("##.", "#.#", "#.#", "##.", "##.", "#.#", "#.#"),
    "T": ("###", ".#.", ".#.", ".#.", ".#.", ".#.", ".#."),
    "U": ("#.#", "#.#", "#.#", "#.#", "#.#", "#.#", ".#."),
    "V": ("#.#", "#.#", "#.#", "#.#", "#.#", ".#.", ".#."),
    "Y": ("#.#", "#.#", ".#.", ".#.", ".#.", ".#.", ".#."),
}

PIXEL_ART_PATTERNS[("bn5", 7)] = REGULAR_PATTERNS
PIXEL_ART_PATTERNS[("bn5", 6)] = COMPACT_PATTERNS


@dataclass(frozen=True)
class MarkedLabel:
    id: str
    text: str | None
    map_name: str
    x: int
    y: int
    columns: int
    rows: int
    face: int | None
    base_mode: str
    background: int | None = None
    shadow: int | None = None
    repeat_tile: int | None = None
    compact: bool = False
    erase: tuple[int, ...] = ()
    logical_id: str | None = None
    logical_text: str | None = None


def sha256(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def guarded_span(rom: bytes, spec: Span) -> bytes:
    payload = rom[spec.offset:spec.offset + spec.length]
    if len(payload) != spec.length or sha256(payload) != spec.sha256:
        raise ValueError(f"{spec.id}: approved v0.10.6 span differs")
    return payload


def map_word(tilemap: bytes | bytearray, x: int, y: int) -> int:
    start = (y * MAP_WIDTH + x) * 2
    return int.from_bytes(tilemap[start:start + 2], "little")


def put_map_word(tilemap: bytearray, x: int, y: int, value: int) -> None:
    start = (y * MAP_WIDTH + x) * 2
    tilemap[start:start + 2] = value.to_bytes(2, "little")


def unpack_tile(payload: bytes | bytearray) -> list[int]:
    if len(payload) != TILE_BYTES:
        raise ValueError("tile payload must contain 32 bytes")
    return [value for byte in payload for value in (byte >> 4, byte & 15)]


def pack_tile(pixels: Sequence[int]) -> bytes:
    if len(pixels) != 64 or any(not 0 <= value <= 15 for value in pixels):
        raise ValueError("invalid 4-bpp tile")
    return bytes((pixels[index] << 4) | pixels[index + 1] for index in range(0, 64, 2))


def tile_pattern(bank: bytes | bytearray, tile_id: int) -> bytes:
    start = tile_id * TILE_BYTES
    payload = bytes(bank[start:start + TILE_BYTES])
    if len(payload) != TILE_BYTES:
        raise ValueError(f"tile 0x{tile_id:03X} is outside the bank")
    return payload


def put_tile(bank: bytearray, tile_id: int, pattern: bytes) -> None:
    start = tile_id * TILE_BYTES
    if len(pattern) != TILE_BYTES or start + TILE_BYTES > len(bank):
        raise ValueError(f"invalid write to tile 0x{tile_id:03X}")
    bank[start:start + TILE_BYTES] = pattern


def visual_cell_snapshot(
    tilemap: bytes | bytearray, bank: bytes | bytearray, x: int, y: int,
) -> tuple[int, bytes]:
    """Return map attributes and final pixels for an explicitly protected cell."""
    word = map_word(tilemap, x, y)
    return word & ~TILE_MASK, tile_pattern(bank, word & TILE_MASK)


def visual_map_sha256(tilemap: bytes | bytearray, bank: bytes | bytearray) -> str:
    """Hash every map attribute and referenced tile pattern in display order."""
    payload = bytearray()
    for position in range(0, len(tilemap), 2):
        word = int.from_bytes(tilemap[position:position + 2], "little")
        payload.extend((word & ~TILE_MASK).to_bytes(2, "little"))
        payload.extend(tile_pattern(bank, word & TILE_MASK))
    return sha256(payload)


def assert_visual_cells_unchanged(
    source_map: bytes | bytearray,
    source_bank: bytes | bytearray,
    output_map: bytes | bytearray,
    output_bank: bytes | bytearray,
    cells: Iterable[tuple[int, int]],
    context: str,
) -> None:
    for x, y in cells:
        if visual_cell_snapshot(source_map, source_bank, x, y) != visual_cell_snapshot(
            output_map, output_bank, x, y,
        ):
            raise AssertionError(f"{context}: protected visual cell changed at ({x},{y})")


def assert_untargeted_visual_cells_unchanged(
    source_maps: dict[str, bytes],
    source_bank: bytes,
    output_maps: dict[str, bytes],
    output_bank: bytes,
    labels: Sequence[MarkedLabel],
) -> None:
    targets = label_targets(labels)
    for name, tilemap in source_maps.items():
        for position in range(0, len(tilemap), 2):
            cell = position // 2
            x, y = cell % MAP_WIDTH, cell // MAP_WIDTH
            if (name, x, y) in targets:
                continue
            if visual_cell_snapshot(tilemap, source_bank, x, y) != visual_cell_snapshot(
                output_maps[name], output_bank, x, y,
            ):
                raise AssertionError(f"{name}: untargeted visual cell changed at ({x},{y})")


def label_targets(labels: Iterable[MarkedLabel]) -> set[tuple[str, int, int]]:
    return {
        (label.map_name, label.x + dx, label.y + dy)
        for label in labels
        for dy in range(label.rows)
        for dx in range(label.columns)
    }


def decode_rect(tilemap: bytes, bank: bytes, label: MarkedLabel) -> list[list[int]]:
    canvas = [[0] * (label.columns * 8) for _ in range(label.rows * 8)]
    for cell_y in range(label.rows):
        for cell_x in range(label.columns):
            word = map_word(tilemap, label.x + cell_x, label.y + cell_y)
            if word & 0xC000:
                raise ValueError(f"{label.id}: flipped target tile is unsupported")
            pixels = unpack_tile(tile_pattern(bank, word & TILE_MASK))
            for py in range(8):
                for px in range(8):
                    canvas[cell_y * 8 + py][cell_x * 8 + px] = pixels[py * 8 + px]
    return canvas


def blank_canvas(tilemap: bytes, bank: bytes, label: MarkedLabel) -> list[list[int]]:
    width, height = label.columns * 8, label.rows * 8
    if label.base_mode == "solid":
        if label.background is None:
            raise ValueError(f"{label.id}: solid field lacks a background colour")
        return [[label.background] * width for _ in range(height)]
    if label.base_mode == "repeat":
        if label.repeat_tile is None:
            raise ValueError(f"{label.id}: repeated field lacks a source tile")
        pattern = unpack_tile(tile_pattern(bank, label.repeat_tile))
        return [[pattern[(y & 7) * 8 + (x & 7)] for x in range(width)] for y in range(height)]
    if label.base_mode == "clear":
        if label.background is None or not label.erase:
            raise ValueError(f"{label.id}: clear field lacks erase colours")
        return [
            [label.background if value in label.erase else value for value in row]
            for row in decode_rect(tilemap, bank, label)
        ]
    raise ValueError(f"{label.id}: unsupported base mode")


def render_label(
    font: TTFFontSet, tilemap: bytes, bank: bytes, label: MarkedLabel,
) -> tuple[list[list[int]], dict[str, object]]:
    canvas = blank_canvas(tilemap, bank, label)
    width, height = label.columns * 8, label.rows * 8
    if label.text is None:
        return canvas, {"render_width_pixels": 0, "render_height_pixels": 0, "manual_glyphs": 0}
    point_size = 6 if label.compact else 7
    specification = FontLabel(
        label.id, label.text, 0, 0, label.columns, label.rows,
        label.background or 0, label.face or 0,
        target_width=width, font_id="bn5", point_size=point_size,
    )
    # A zero-width word body is safe for the compact PROGRAM DECK masks: the
    # composer's fixed spacing leaves two native blank columns around it.  It
    # recovers balanced margins without narrowing any completed glyph.
    previous_space_width = font.SPACE_WIDTH
    font.SPACE_WIDTH = 0 if label.compact else 2
    try:
        mask, metrics = font.line(specification)
    finally:
        font.SPACE_WIDTH = previous_space_width
    nonspace = sum(character != " " for character in label.text)
    if metrics["manual_pixel_corrected_glyph_instances"] != nonspace:
        raise AssertionError(f"{label.id}: a glyph escaped manual pixel review")
    extra_y = 1 if label.shadow is not None else 0
    if mask.width > width or mask.height + extra_y > height:
        raise ValueError(f"{label.id}: native mask does not fit {width}x{height}")
    offset_x = (width - mask.width) // 2
    offset_y = (height - mask.height - extra_y) // 2
    face_points = [
        (offset_x + x, offset_y + y)
        for y in range(mask.height)
        for x in range(mask.width)
        if mask.getpixel((x, y))
    ]
    if label.shadow is not None:
        for x, y in face_points:
            if y + 1 < height:
                canvas[y + 1][x] = label.shadow
    if label.face is None:
        raise ValueError(f"{label.id}: text field has no face colour")
    for x, y in face_points:
        canvas[y][x] = label.face
    return canvas, {
        **metrics,
        "font_role": "BN5 compact" if label.compact else "BN5 regular",
        "field_width_pixels": width,
        "field_height_pixels": height,
        "offset_x_pixels": offset_x,
        "offset_y_pixels": offset_y,
        "manual_glyphs": nonspace,
        "shadow_pixels": extra_y,
    }


def canvas_patterns(canvas: list[list[int]]) -> list[bytes]:
    height, width = len(canvas), len(canvas[0])
    if width % 8 or height % 8:
        raise ValueError("canvas is not tile aligned")
    return [
        pack_tile([
            canvas[cell_y * 8 + py][cell_x * 8 + px]
            for py in range(8) for px in range(8)
        ])
        for cell_y in range(height // 8)
        for cell_x in range(width // 8)
    ]


def refs(maps: dict[str, bytes], tile_id: int) -> list[tuple[str, int, int]]:
    result = []
    for name, tilemap in maps.items():
        for position in range(0, len(tilemap), 2):
            if int.from_bytes(tilemap[position:position + 2], "little") & TILE_MASK == tile_id:
                cell = position // 2
                result.append((name, cell % MAP_WIDTH, cell // MAP_WIDTH))
    return result


def allocate_group(
    font: TTFFontSet,
    maps_source: dict[str, bytes],
    bank_source: bytes,
    labels: Sequence[MarkedLabel],
    protected_ids: Iterable[int] = (),
    orphan_allowlist: Iterable[int] = (),
) -> tuple[dict[str, bytes], bytes, dict[str, object], dict[str, list[list[int]]]]:
    maps = {name: bytearray(payload) for name, payload in maps_source.items()}
    bank = bytearray(bank_source)
    tile_count = len(bank_source) // TILE_BYTES
    targets = label_targets(labels)
    protected = set(protected_ids)
    allowed_orphans = set(orphan_allowlist)
    rendered: dict[str, tuple[list[list[int]], dict[str, object]]] = {}
    unique_patterns: list[bytes] = []
    for label in labels:
        canvas, metrics = render_label(font, maps_source[label.map_name], bank_source, label)
        rendered[label.id] = (canvas, metrics)
        for pattern in canvas_patterns(canvas):
            if pattern not in unique_patterns:
                unique_patterns.append(pattern)

    references = {tile_id: refs(maps_source, tile_id) for tile_id in range(tile_count)}
    for tile_id in sorted(allowed_orphans):
        if not 0 <= tile_id < tile_count:
            raise ValueError(f"orphan allowlist tile 0x{tile_id:03X} is outside the bank")
        if tile_id in protected:
            raise ValueError(f"orphan allowlist tile 0x{tile_id:03X} is protected")
        if references[tile_id]:
            raise ValueError(
                f"orphan allowlist tile 0x{tile_id:03X} has mapped consumers: "
                f"{references[tile_id][:4]}"
            )
    modifiable = [
        tile_id for tile_id in range(tile_count)
        if tile_id not in protected
        and (
            (bool(references[tile_id]) and all(reference in targets for reference in references[tile_id]))
            or tile_id in allowed_orphans
        )
    ]
    existing: dict[bytes, list[int]] = defaultdict(list)
    for tile_id in range(tile_count):
        existing[tile_pattern(bank_source, tile_id)].append(tile_id)

    assigned: dict[bytes, int] = {}
    claimed: set[int] = set()
    changed_tile_ids: set[int] = set()
    for pattern in unique_patterns:
        matches = sorted(existing.get(pattern, []), key=lambda tile_id: (tile_id in modifiable, tile_id))
        if matches:
            assigned[pattern] = matches[0]
            claimed.add(matches[0])
            continue
        candidates = [tile_id for tile_id in modifiable if tile_id not in claimed]
        if not candidates:
            raise ValueError(f"tile pool exhausted: need {len(unique_patterns)} patterns")
        tile_id = candidates[0]
        assigned[pattern] = tile_id
        claimed.add(tile_id)
        put_tile(bank, tile_id, pattern)
        changed_tile_ids.add(tile_id)

    records = []
    for label in labels:
        canvas, metrics = rendered[label.id]
        assignments = []
        for index, pattern in enumerate(canvas_patterns(canvas)):
            x = label.x + index % label.columns
            y = label.y + index // label.columns
            old = map_word(maps_source[label.map_name], x, y)
            tile_id = assigned[pattern]
            put_map_word(maps[label.map_name], x, y, (old & ~TILE_MASK) | tile_id)
            assignments.append([x, y, tile_id])
        records.append({
            "id": label.id,
            "text": label.text,
            "logical_id": label.logical_id or label.id,
            "logical_text": label.logical_text or label.text,
            "map": label.map_name,
            "rectangle": [label.x, label.y, label.columns, label.rows],
            "base_mode": label.base_mode,
            "background": label.background,
            "face": label.face,
            "shadow": label.shadow,
            "assignments": assignments,
            **metrics,
        })

    changed_cells = []
    for name, source in maps_source.items():
        for position in range(0, len(source), 2):
            output = maps[name]
            if source[position:position + 2] == output[position:position + 2]:
                continue
            cell = position // 2
            reference = (name, cell % MAP_WIDTH, cell // MAP_WIDTH)
            if reference not in targets:
                raise AssertionError(f"map write escaped target: {reference}")
            before_word = int.from_bytes(source[position:position + 2], "little")
            after_word = int.from_bytes(output[position:position + 2], "little")
            if (before_word ^ after_word) & ~TILE_MASK:
                raise AssertionError(f"map attributes changed at {reference}")
            changed_cells.append(reference)

    actual_changed_tiles = {
        tile_id for tile_id in range(tile_count)
        if tile_pattern(bank_source, tile_id) != tile_pattern(bank, tile_id)
    }
    if actual_changed_tiles != changed_tile_ids:
        raise AssertionError("tile change accounting mismatch")
    for tile_id in actual_changed_tiles:
        outside = [reference for reference in references[tile_id] if reference not in targets]
        if outside:
            raise AssertionError(f"tile 0x{tile_id:03X} aliases protected cells: {outside[:4]}")
    changed_orphans = sorted(tile_id for tile_id in actual_changed_tiles if not references[tile_id])
    if any(tile_id not in allowed_orphans for tile_id in changed_orphans):
        raise AssertionError("an unlisted orphan tile was modified")

    return (
        {name: bytes(payload) for name, payload in maps.items()},
        bytes(bank),
        {
            "labels": records,
            "target_cells": len(targets),
            "unique_patterns": len(unique_patterns),
            "modifiable_pool": len(modifiable),
            "changed_map_cells": len(changed_cells),
            "changed_tile_ids": [f"0x{tile_id:03X}" for tile_id in sorted(actual_changed_tiles)],
            "orphan_allowlist": [f"0x{tile_id:03X}" for tile_id in sorted(allowed_orphans)],
            "changed_orphan_tile_ids": [f"0x{tile_id:03X}" for tile_id in changed_orphans],
            "orphan_allowlist_all_unreferenced": True,
            "tile_aliases_outside_targets": 0,
        },
        {label.id: rendered[label.id][0] for label in labels},
    )


PREVIEW_COLOURS = {
    0: (0, 0, 0), 1: (20, 20, 20), 2: (65, 65, 65), 3: (70, 70, 70),
    4: (88, 104, 104), 5: (255, 220, 45), 6: (255, 238, 155),
    7: (245, 245, 235), 8: (75, 90, 90), 9: (45, 45, 45),
    10: (235, 235, 220), 11: (70, 70, 70), 12: (245, 235, 220),
    13: (225, 210, 90), 14: (240, 240, 225), 15: (255, 255, 245),
}

PREVIEW_LABEL_COLOURS = {
    # Program Deck palette 2: native dark-teal ground, orange face and dark
    # shadow.  The generic index table deliberately cannot represent every
    # screen palette and otherwise makes this clean label look low-contrast.
    "live_y2_chip_folder": {
        1: (25, 28, 28), 4: (62, 82, 78), 8: (255, 160, 0),
    },
}


def canvas_image(canvas: list[list[int]], label_id: str | None = None) -> Image.Image:
    image = Image.new("RGB", (len(canvas[0]), len(canvas)), (20, 20, 20))
    colours = dict(PREVIEW_COLOURS)
    colours.update(PREVIEW_LABEL_COLOURS.get(label_id or "", {}))
    for y, row in enumerate(canvas):
        for x, value in enumerate(row):
            image.putpixel((x, y), colours.get(value, (value * 17,) * 3))
    return image


def write_payload(output_dir: Path, name: str, payload: bytes) -> dict[str, object]:
    path = output_dir / name
    path.write_bytes(payload)
    return {"length": len(payload), "sha256": sha256(payload)}


def build_montage(
    before: dict[str, Image.Image], after: dict[str, Image.Image], output: Path,
) -> None:
    order = list(after)
    scale = 4
    caption_width = 190
    maximum = max(after[name].width * scale for name in order)
    heights = [max(48, after[name].height * scale + 10) for name in order]
    canvas = Image.new("RGB", (caption_width + maximum * 2 + 22, 34 + sum(heights)), (24, 24, 24))
    draw = ImageDraw.Draw(canvas)
    draw.text((caption_width, 9), "v0.10.6 base", fill=(238, 238, 238))
    draw.text((caption_width + maximum + 14, 9), "RC3 BN5 manual", fill=(238, 238, 238))
    y = 32
    for name, row_height in zip(order, heights):
        draw.text((8, y + 7), name, fill=(238, 238, 238))
        left = before[name].resize((before[name].width * scale, before[name].height * scale), Image.Resampling.NEAREST)
        right = after[name].resize((after[name].width * scale, after[name].height * scale), Image.Resampling.NEAREST)
        canvas.paste(left, (caption_width, y))
        canvas.paste(right, (caption_width + maximum + 14, y))
        y += row_height
    canvas.save(output, format="PNG", optimize=False)


def build_stats_palette_preview(
    source_map: bytes,
    source_tiles: bytes,
    output_map: bytes,
    output_tiles: bytes,
    output: Path,
) -> None:
    """Render the manual statistics page with its real map-selected palette."""
    scale, caption = 3, 28
    before = render_program_page(source_map, source_tiles, "stats")
    after = render_program_page(output_map, output_tiles, "stats")
    before = before.resize((before.width * scale, before.height * scale), Image.Resampling.NEAREST)
    after = after.resize((after.width * scale, after.height * scale), Image.Resampling.NEAREST)
    montage = Image.new("RGB", (before.width * 2 + 12, before.height + caption), (24, 24, 24))
    montage.paste(before, (0, caption))
    montage.paste(after, (before.width + 12, caption))
    draw = ImageDraw.Draw(montage)
    draw.text((8, 8), "v0.10.6 base — active palette", fill=(238, 238, 238))
    draw.text((before.width + 20, 8), "RC3 pixel-art correction — active palette", fill=(238, 238, 238))
    montage.save(output, format="PNG", optimize=False)


def source_image(tilemap: bytes, bank: bytes, label: MarkedLabel) -> Image.Image:
    return canvas_image(decode_rect(tilemap, bank, label), label.id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-rom", type=Path, default=PROJECT_ROOT / "build/Rockman_EXE_N1_Battle_English_v0.10.6.wsc")
    parser.add_argument("--bn5-font", required=True, type=Path)
    parser.add_argument("--sf3-font", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "translation/assets")
    args = parser.parse_args()

    rom = args.base_rom.read_bytes()
    if len(rom) != ROM_SIZE or sha256(rom) != BASE_ROM_SHA256:
        raise ValueError("expected the approved pixel-polished v0.10.6 ROM")
    if sha256(args.bn5_font.read_bytes()) != BN5_TTF_SHA256:
        raise ValueError("BN5DSEU Font Thin differs from the supplied source")
    if sha256(args.sf3_font.read_bytes()) != SF3_TTF_SHA256:
        raise ValueError("SF3FontSmall differs from the supplied source")
    sources = {name: guarded_span(rom, spec) for name, spec in SPANS.items()}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    font = TTFFontSet(args.bn5_font, args.sf3_font)
    font.SPACE_WIDTH = 2

    before: dict[str, Image.Image] = {}
    after: dict[str, Image.Image] = {}
    groups: dict[str, object] = {}

    program_full_map = rom[0x04323C:0x04323C + 0x0680]
    program_labels = (
        # The title owns six cells.  The seventh source cell at (17,0) is the
        # unrelated white symbol marked by the user and is cleared separately.
        # The same 46-pixel mask also serves the manual plaque, giving both
        # PROGRAM DECK occurrences identical letter construction and margins.
        MarkedLabel("live_program_deck", "PROGRAM DECK", "program", 11, 0, 6, 2, 12, "repeat", shadow=8, repeat_tile=0x00D, compact=True),
        MarkedLabel("live_unrelated_symbol", None, "program", 17, 0, 1, 1, None, "repeat", repeat_tile=0x00D),
        # Cell x=27 contains the functional arrow/pictogram and is excluded.
        # Tile 0x00D contains seven index-8 grid/accent pixels.  Repeating it
        # under an index-8 face contaminates the letter silhouettes, so this
        # particular one-row plaque is cleared to its native index-4 ground.
        MarkedLabel("live_y2_chip_folder", "Y2 CHIP FOLDER", "program", 20, 0, 7, 1, 8, "solid", background=4, shadow=1, compact=True),
    )
    for label in program_labels:
        before[label.id] = source_image(program_full_map, sources["program_tiles"], label)
    program_maps, program_tiles, groups["live_program_deck"], canvases = allocate_group(
        font, {"program": program_full_map}, sources["program_tiles"], program_labels,
        protected_ids={0x00C, 0x00D, 0x019, 0x050, 0x051, 0x058, 0x059, 0x05E, 0x05F},
        orphan_allowlist={0x010, 0x01A, 0x01C, 0x01D, 0x01E},
    )
    after.update({name: canvas_image(canvas, name) for name, canvas in canvases.items()})
    assert_untargeted_visual_cells_unchanged(
        {"program": program_full_map}, sources["program_tiles"],
        program_maps, program_tiles, program_labels,
    )
    assert_visual_cells_unchanged(
        program_full_map, sources["program_tiles"], program_maps["program"], program_tiles,
        ((27, 0), (27, 1)), "Y2 functional pictogram",
    )
    assert_visual_cells_unchanged(
        program_full_map, sources["program_tiles"], program_maps["program"], program_tiles,
        ((18, 1),), "unrelated tiny source mark outside the red target",
    )
    if program_maps["program"][0x400:] != program_full_map[0x400:]:
        raise AssertionError("Program Deck map changed below its public span")
    symbol = program_labels[1]
    symbol_canvas = decode_rect(program_maps["program"], program_tiles, symbol)
    grid_canvas = [unpack_tile(tile_pattern(program_tiles, 0x00D))[row * 8:(row + 1) * 8] for row in range(8)]
    if symbol_canvas != grid_canvas:
        raise AssertionError("unrelated symbol was not replaced by the clean grid")

    shared_maps = {
        "auto": sources["program_alt_map"],
        "chip_folder_guard": rom[0x043F40:0x043F40 + 0x0680],
        "backpack": sources["backpack_map"],
        "data": sources["data_map"],
    }
    shared_labels = (
        # AUTO CONTROL starts at x=10; x=16 contains its functional icon.
        MarkedLabel("submenu_auto_control", "AUTO CONTROL", "auto", 10, 0, 6, 2, 15, "solid", background=3, shadow=9, compact=True),
        MarkedLabel("submenu_data_library", "DATA LIBRARY", "data", 11, 0, 8, 2, 15, "solid", background=3, shadow=9),
        MarkedLabel("submenu_backpack", "BACKPACK", "backpack", 11, 0, 7, 2, 15, "solid", background=3, shadow=9),
    )
    for label in shared_labels:
        before[label.id] = source_image(shared_maps[label.map_name], sources["shared_tiles"], label)
    shared_outputs, shared_tiles, groups["pet_shared_headers"], canvases = allocate_group(
        font, shared_maps, sources["shared_tiles"], shared_labels,
        protected_ids={0x04, 0x0B, 0x1C, *range(0x10, 0x17), *range(0x97, 0xA0), *range(0xB1, 0xB5)},
        orphan_allowlist={0x044, 0x045, 0x046, 0x051, 0x052, 0x057, 0x05E, 0x066, 0x067, 0x068},
    )
    after.update({name: canvas_image(canvas, name) for name, canvas in canvases.items()})
    assert_untargeted_visual_cells_unchanged(
        shared_maps, sources["shared_tiles"], shared_outputs, shared_tiles, shared_labels,
    )
    assert_visual_cells_unchanged(
        shared_maps["auto"], sources["shared_tiles"], shared_outputs["auto"], shared_tiles,
        ((16, 0), (16, 1)), "AUTO CONTROL functional icon",
    )
    if shared_outputs["chip_folder_guard"] != shared_maps["chip_folder_guard"]:
        raise AssertionError("unmarked CHIP FOLDER map changed")
    if visual_map_sha256(shared_outputs["chip_folder_guard"], shared_tiles) != visual_map_sha256(
        shared_maps["chip_folder_guard"], sources["shared_tiles"],
    ):
        raise AssertionError("unmarked CHIP FOLDER visuals changed through the shared bank")

    net_labels = (
        MarkedLabel("submenu_netnavi", "NETNAVI", "netnavi", 11, 0, 6, 2, 10, "solid", background=8, shadow=3),
        MarkedLabel("submenu_netnavi_stats", "NETNAVI", "netnavi_stats", 11, 0, 6, 2, 10, "clear", background=8, shadow=3, erase=(10, 3)),
    )
    for label in net_labels:
        source_map = sources["netnavi_map"] if label.map_name == "netnavi" else sources["netnavi_stats_map"]
        before[label.id] = source_image(source_map, sources["netnavi_tiles"], label)
    net_source_maps = {
        "netnavi": sources["netnavi_map"],
        # The user marked the statistics-screen instance.  Rebuilding the
        # root instance with the same patterns keeps both consumers uniform;
        # cells outside these two identical header rectangles remain guards.
        "netnavi_stats": sources["netnavi_stats_map"],
    }
    net_maps, net_tiles, groups["netnavi_header"], canvases = allocate_group(
        font, net_source_maps, sources["netnavi_tiles"], net_labels,
        protected_ids={0x04, *range(0x0F, 0x14), 0x39, 0x3B, 0x3E, 0x3F, 0x65, 0x66, 0x67, 0x68},
    )
    after.update({name: canvas_image(canvas, name) for name, canvas in canvases.items()})
    assert_untargeted_visual_cells_unchanged(
        net_source_maps, sources["netnavi_tiles"], net_maps, net_tiles, net_labels,
    )
    stats_net_label = next(label for label in net_labels if label.id == "submenu_netnavi_stats")
    source_stats_net = decode_rect(sources["netnavi_stats_map"], sources["netnavi_tiles"], stats_net_label)
    output_stats_net = decode_rect(net_maps["netnavi_stats"], net_tiles, stats_net_label)
    for x, y in ((40, 3), (42, 3)):
        if source_stats_net[y][x] != 4 or output_stats_net[y][x] != 4:
            raise AssertionError(f"NETNAVI non-text accent pixel changed at ({x},{y})")

    manual = bytearray(sources["manual_tiles"])
    overview_source = bytes(manual[:0x1140])
    overview_labels = (
        # Only the text-only cells are rewritten.  Mixed artwork at (1,2),
        # (6,2), (3,7), (6,7) and (27,7) remains mapped byte-for-byte.
        MarkedLabel("manual_program_deck", "PROGRAM DECK", "overview", 1, 1, 6, 1, 7, "solid", background=8, compact=True),
        MarkedLabel("manual_program_deck_tail_cleanup", None, "overview", 2, 2, 4, 1, None, "solid", background=8),
        MarkedLabel("manual_navichip_navi", "NAVI", "overview", 1, 7, 2, 1, 5, "solid", background=8, compact=True, logical_id="manual_navichip", logical_text="NAVICHIP"),
        MarkedLabel("manual_navichip_chip", "CHIP", "overview", 4, 7, 2, 1, 5, "solid", background=8, compact=True, logical_id="manual_navichip", logical_text="NAVICHIP"),
        MarkedLabel("manual_battlechip", "BATTLECHIP", "overview", 22, 7, 5, 1, 6, "solid", background=8, compact=True),
    )
    for label in overview_labels:
        before[label.id] = source_image(sources["overview_map"], overview_source, label)
    overview_maps, overview_tiles, groups["manual_overview"], canvases = allocate_group(
        font, {"overview": sources["overview_map"]}, overview_source, overview_labels,
        protected_ids={0x000, 0x001, 0x00F, 0x021},
    )
    after.update({name: canvas_image(canvas, name) for name, canvas in canvases.items()})
    assert_untargeted_visual_cells_unchanged(
        {"overview": sources["overview_map"]}, overview_source,
        overview_maps, overview_tiles, overview_labels,
    )
    assert_visual_cells_unchanged(
        sources["overview_map"], overview_source, overview_maps["overview"], overview_tiles,
        ((1, 2), (6, 2), (3, 7), (6, 7), (27, 7)),
        "Program Deck manual mixed artwork",
    )
    manual[:0x1140] = overview_tiles

    stats_start, stats_end = 0x1150, 0x3990
    stats_source = bytes(manual[stats_start:stats_end])
    stats_labels = (
        MarkedLabel("manual_normal30", "NORMAL30", "stats", 2, 0, 7, 2, 15, "solid", background=4),
        MarkedLabel("manual_attack_power", "ATTACK POWER", "stats", 11, 0, 7, 2, 14, "solid", background=15),
        MarkedLabel("manual_retreat", "RETREAT", "stats", 11, 2, 6, 2, 14, "solid", background=15),
        MarkedLabel("manual_victory", "VICTORY", "stats", 11, 4, 6, 2, 14, "solid", background=15),
        MarkedLabel("manual_capacity", "CAPACITY", "stats", 10, 6, 5, 2, 14, "solid", background=15),
        MarkedLabel("manual_navi_chip", "NAVI CHIP", "stats", 18, 2, 7, 2, 12, "solid", background=4),
        MarkedLabel("manual_battle_chip", "BATTLE CHIP", "stats", 18, 4, 7, 2, 12, "solid", background=4),
        MarkedLabel("manual_chip_type_legend", "BATTLE CHIP / NAVI CHIP", "stats", 13, 8, 12, 2, 13, "solid", background=15),
    )
    for label in stats_labels:
        before[label.id] = source_image(sources["stats_map"], stats_source, label)
    stats_maps, stats_tiles, groups["manual_stats"], canvases = allocate_group(
        font, {"stats": sources["stats_map"]}, stats_source, stats_labels,
        protected_ids={0x000, 0x00A, 0x019, 0x032, 0x05E, 0x091, 0x093, 0x0AF},
    )
    after.update({name: canvas_image(canvas, name) for name, canvas in canvases.items()})
    assert_untargeted_visual_cells_unchanged(
        {"stats": sources["stats_map"]}, stats_source, stats_maps, stats_tiles, stats_labels,
    )
    manual[stats_start:stats_end] = stats_tiles

    output_payloads = {
        SPANS["program_map"].output: program_maps["program"][:0x400],
        SPANS["program_alt_map"].output: shared_outputs["auto"],
        SPANS["backpack_map"].output: shared_outputs["backpack"],
        SPANS["data_map"].output: shared_outputs["data"],
        SPANS["netnavi_map"].output: net_maps["netnavi"],
        SPANS["netnavi_stats_map"].output: net_maps["netnavi_stats"],
        SPANS["overview_map"].output: overview_maps["overview"],
        SPANS["stats_map"].output: stats_maps["stats"],
        SPANS["program_tiles"].output: program_tiles,
        SPANS["shared_tiles"].output: shared_tiles,
        SPANS["netnavi_tiles"].output: net_tiles,
        SPANS["manual_tiles"].output: bytes(manual),
    }
    outputs = {
        name: write_payload(args.output_dir, name, payload)
        for name, payload in sorted(output_payloads.items())
    }

    preview = args.output_dir / "redbox_font_comparison_v0_10_7_rc3.png"
    build_montage(before, after, preview)
    outputs[preview.name] = {
        "length": preview.stat().st_size,
        "sha256": sha256(preview.read_bytes()),
        "dimensions": list(Image.open(preview).size),
    }
    palette_preview = args.output_dir / "program_deck_stats_palette_comparison_v0_10_7_rc3.png"
    build_stats_palette_preview(
        sources["stats_map"], sources["manual_tiles"], stats_maps["stats"], bytes(manual), palette_preview,
    )
    outputs[palette_preview.name] = {
        "length": palette_preview.stat().st_size,
        "sha256": sha256(palette_preview.read_bytes()),
        "dimensions": list(Image.open(palette_preview).size),
    }

    changed_spans = []
    total_changed = 0
    for name, spec in SPANS.items():
        payload = output_payloads[spec.output]
        source = sources[name]
        changed = sum(left != right for left, right in zip(source, payload))
        total_changed += changed
        changed_spans.append({
            "id": name,
            "offset": f"0x{spec.offset:06X}",
            "length": spec.length,
            "base_sha256": spec.sha256,
            "output": spec.output,
            "output_sha256": sha256(payload),
            "changed_bytes": changed,
        })

    labels = [row for group in groups.values() for row in group["labels"] if row["text"] is not None]
    semantic_labels = []
    seen_logical_ids: set[str] = set()
    for row in labels:
        logical_id = str(row["logical_id"])
        if logical_id in seen_logical_ids:
            continue
        seen_logical_ids.add(logical_id)
        semantic_labels.append({"id": logical_id, "text": row["logical_text"]})
    harmonized_ids = {"submenu_netnavi"}
    marked_semantic_labels = [row for row in semantic_labels if row["id"] not in harmonized_ids]
    if len(marked_semantic_labels) != 17 or len(semantic_labels) != 18 or len(labels) != 19:
        raise AssertionError("semantic/segmented label accounting differs from the reviewed scope")
    glyph_counts = Counter(character for row in labels for character in row["text"] if character != " ")
    report = {
        "status": "PASS",
        "version": VERSION,
        "base": {
            "description": "approved v0.10.6 pixel-art revision; RC2 excluded",
            "rom_sha256": BASE_ROM_SHA256,
        },
        "rc2_assets_reused": False,
        "native_resolution": [224, 144],
        "support_screenshots": 7,
        "support_unique_screenshots": 7,
        "marked_text_instances": len(marked_semantic_labels),
        "harmonized_duplicate_instances": len(harmonized_ids),
        "harmonized_duplicate_ids": sorted(harmonized_ids),
        "corrected_text_instances": len(semantic_labels),
        "rendered_text_segments": len(labels),
        "removed_non_text_symbols": 1,
        "font_policy": {
            "master_selected": "BN5DSEU Font Thin",
            "master_sha256": BN5_TTF_SHA256,
            "alternative_file_verified": "SF3FontSmall",
            "alternative_not_selected": True,
            "alternative_sha256": SF3_TTF_SHA256,
            "regular_geometry": "proportional 3-5x7 native masks",
            "compact_geometry": "proportional 1-5x7 native masks for immutable constrained fields",
            "rasterization": "all visible glyphs manually authored at final 1:1 resolution after TTF role selection",
            "resampling": "none",
            "antialiasing": False,
            "line_scaling": False,
            "interglyph_face_gap_pixels": 1,
            "regular_word_body_pixels": 2,
            "compact_word_body_pixels": 0,
            "compact_word_visible_gap_pixels": 2,
            "shadow_policy": "downward only",
            "manual_glyph_instances": sum(glyph_counts.values()),
            "glyph_inventory": dict(sorted(glyph_counts.items())),
            "ttf_files_in_public_package": False,
        },
        "literal_text_preserved": [row["text"] for row in semantic_labels],
        "marked_logical_ids": [row["id"] for row in marked_semantic_labels],
        "groups": groups,
        "symbol_removal": {
            "map_cell": [17, 0],
            "replacement_tile_pattern": "clean grid tile 0x00D",
            "pixel_exact": True,
        },
        "protections": {
            "bottom_dialogue_boxes_modified": False,
            "dialogue_font_or_strings_modified": False,
            "dynamic_values_modified": False,
            "cursors_modified": False,
            "frames_modified": False,
            "auto_control_icon_modified": False,
            "program_deck_pictograms_modified": False,
            "program_deck_tiny_unmarked_cell_modified": False,
            "chip_folder_unmarked_screen_modified": False,
            "netnavi_non_text_accent_pixels_modified": False,
            "manual_overview_mixed_art_cells_modified": False,
            "all_untargeted_visual_cells_unchanged": True,
            "map_palette_priority_flip_bits_preserved": True,
            "tile_aliases_outside_targets": 0,
        },
        "changed_spans": changed_spans,
        "changed_bytes_across_full_spans": total_changed,
        "outputs": outputs,
        "preview": preview.name,
        "palette_preview": palette_preview.name,
    }
    report_path = args.output_dir / "redbox_font_asset_report_v0_10_7_rc3.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "PASS",
        "version": VERSION,
        "labels": len(labels),
        "removed_symbols": 1,
        "changed_bytes": total_changed,
        "report": report_path.as_posix(),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
