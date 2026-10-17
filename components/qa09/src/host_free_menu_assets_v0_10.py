#!/usr/bin/env python3
"""Translate the uncatalogued Host Tournament and Free Battle UI graphics.

These screens are descriptor-driven WonderSwan Color BG0 resources: 32x18
tilemaps, packed 4-bpp 8x8 tiles and RGB444 palettes.  The v0.9 release did
not visit these branches and therefore left their raster text in Japanese.

This generator accepts only the verified Japanese Rev 1 ROM, hash-guards
every complete source map/tile/palette span, redraws compact English at the
native 224x144 resolution, and proves that no byte outside audited text cells
and exclusive glyph tiles changes.  Frames, cursors, counters, palettes and
all surrounding artwork remain source-identical.
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
MAP_WIDTH = 32
MAP_HEIGHT = 18
VISIBLE_WIDTH = 28
TILE_BYTES = 32
TILE_MASK = 0x01FF


@dataclass(frozen=True)
class Region:
    offset: int
    length: int
    sha256: str


@dataclass(frozen=True)
class Label:
    id: str
    original: str
    translation: str
    x: int
    y: int
    columns: int
    background_tile: int
    background_colour: int
    face_colour: int
    outline_colour: int | None = None


@dataclass(frozen=True)
class Screen:
    id: str
    maps: tuple[Region, ...]
    tiles: Region
    palette: Region
    palette_base: int
    labels: tuple[Label, ...]
    tile_pool: tuple[int, ...]
    preserve_map: bool = False
    guard_maps: tuple[Region, ...] = ()


def span(start: int, stop: int) -> tuple[int, ...]:
    return tuple(range(start, stop + 1))


SCREENS = (
    Screen(
        "host_setup",
        (Region(0x0464CE, 0x0480, "170da27f4d56eb2a6a4f27ad2877eaa932b7d9a7afb82813a7ef8af4da168bff"),),
        Region(0x081ED0, 0x0EC0, "95f9c9e107edb7274507e9b458ed052d4198082a9a2297e2b23db131f294d005"),
        Region(0x082D98, 0x0040, "264cf7ab9bb0ddf6cc35d667389c477ce1fc9cec8a0512dffc06c915b9e36119"),
        2,
        (
            Label("host_navi_roster", "ナビコードカンリ?", "NAVI ROSTER?", 9, 11, 9, 0x02, 1, 2),
            Label("host_tourney", "バトルカイサイ?", "HOST TOURNEY?", 9, 13, 8, 0x02, 1, 2),
        ),
        span(0x0E, 0x16) + span(0x2E, 0x36) + span(0x4E, 0x55) + span(0x6E, 0x75),
        True,
    ),
    Screen(
        "host_roster_actions",
        (Region(0x046950, 0x0480, "8e26365483e037a66b06a0f8f8bd470d0dda5ce6e78e37b0f52987191fc3d977"),),
        Region(0x082DE0, 0x0EC0, "36c4a7572eeed1f3d3d7a6edd11da7b3f2ab62fafa8592e4aff95da542ce27ac"),
        Region(0x083CA8, 0x0040, "264cf7ab9bb0ddf6cc35d667389c477ce1fc9cec8a0512dffc06c915b9e36119"),
        2,
        (
            Label("host_register_prompt", "ナビトウロク?", "REGISTER?", 9, 11, 7, 0x02, 1, 2),
            Label("host_delete_prompt", "サクジョ?", "DELETE?", 11, 13, 5, 0x02, 1, 2),
        ),
        span(0x0E, 0x14) + span(0x2E, 0x34) + span(0x50, 0x54) + span(0x70, 0x74),
        True,
    ),
    Screen(
        "host_navicode_register",
        (Region(0x046DD2, 0x0480, "ca62e549a20c4576a698eb2b1879bcca4d43ed720aa13f3cbddb934a145a3b8d"),),
        Region(0x083CF0, 0x0640, "4cbe92789672e0c6e86c431e1c24281ca5d26d94eb0e6ffbdcc56cc639be475f"),
        Region(0x084338, 0x0020, "ccdea4331ad8e0a12afb1bbd0811a5c482e2800e0d062f866afc336ea0e0cc77"),
        2,
        (
            Label("host_netnavi_code", "ネットナビコード", "NETNAVI CODE", 7, 0, 8, 0x01, 3, 7, 2),
            Label("host_register", "トウロク", "REGISTER", 17, 0, 4, 0x01, 3, 7, 2),
            Label("host_back", "もどる", "BACK", 23, 13, 3, 0x1D, 9, 1),
        ),
        span(0x02, 0x0C) + span(0x0E, 0x18) + span(0x24, 0x29),
    ),
    Screen(
        "host_brackets",
        (
            Region(0x047254, 0x0480, "6b26993aa6de45472c88d501bba21ff03e5ba57a8e641ef70d419731df15c185"),
            Region(0x0476D6, 0x0480, "e7080efdcbc99656f158f2e059df9f701983e6b6e00e9d562edb6d86579a73fb"),
            Region(0x047B58, 0x0480, "290e09a878ebba5db013c41a4e18fdeadd5a0fc71da3ad3592e5c899125fed10"),
        ),
        Region(0x084360, 0x03C0, "b16024387367c6b7c39641b4ba61e121968313578bc3b17b2ec2ec81e01eba34"),
        Region(0x084728, 0x0020, "b459232a4b3b317876eb5d1b2b7a32ce97f79b0eb650e7370539e14beb7c3922"),
        2,
        (
            # TOURNEY intentionally keeps the repeated outer source tiles blank,
            # allowing all three bracket maps to remain byte-identical.
            Label("host_tourney_header", "トーナメント", "TOURNEY", 7, 0, 6, 0x01, 3, 7, 1),
            Label("host_bracket_header", "ブロック", "BRACKET", 17, 0, 4, 0x01, 3, 7, 1),
        ),
        span(0x02, 0x13),
        True,
    ),
    Screen(
        "host_entrant_count",
        (Region(0x047FDA, 0x0480, "f01158620a654765b7e38f4610afaf998a8a75b31e17f0a75ab10fbfc29a68db"),),
        Region(0x084750, 0x06C0, "372d09efbb18d708b2c3433c1b110f656d68a8ee96d555094146a591529e3946"),
        Region(0x084E18, 0x0020, "433aa77cfce6e8aea6b8869521b128985f1aa76bdae8d0638f7cedf9dd0970f6"),
        2,
        (
            Label("host_entrants_16", "トーナメント16", "16 NAVIS", 4, 1, 8, 0x0A, 11, 15),
            Label("host_entrants_32", "トーナメント32", "32 NAVIS", 4, 3, 8, 0x05, 2, 15),
            Label("host_entrants_64", "トーナメント64", "64 NAVIS", 4, 5, 8, 0x0A, 11, 15),
            Label("host_entrants_128", "トーナメント128", "128 NAVIS", 4, 7, 9, 0x05, 2, 15),
        ),
        span(0x16, 0x35),
    ),
    Screen(
        "host_entry_select",
        (Region(0x04845C, 0x0480, "457015beb65dacd618dc0f028d0d49e6599cb564aa341312c4afc0bad9da5996"),),
        Region(0x084E40, 0x0780, "c31af9c2e611a259af2d092525548ac91c00a5cd8de5166e04f67bc9ada7093e"),
        Region(0x0855C8, 0x0020, "52e77b2fa6616b745bdf38ab0734ea338b78bef9e3f374873c0b8a476b96a811"),
        2,
        (
            Label("host_entry_name", "エントリーネーム", "ENTRY NAME", 7, 0, 8, 0x01, 4, 8, 2),
            Label("host_select", "センタク", "SELECT", 17, 0, 4, 0x01, 4, 8, 1),
        ),
        span(0x02, 0x17),
    ),
    Screen(
        "host_result_dialog",
        (Region(0x0488DE, 0x0480, "c3f443cd68cfcfa17947c03c7ab98a7fc9c847b2df09ddc174961d595161fc3d"),),
        Region(0x0855F0, 0x0640, "fb4c7b3048397bea8b82b97966430e4ba46e02df7f5c81e8bf8dcd9b38ab52eb"),
        Region(0x085C38, 0x0040, "264cf7ab9bb0ddf6cc35d667389c477ce1fc9cec8a0512dffc06c915b9e36119"),
        2,
        (Label("host_result_dialog_label", "リザルト", "RESULT", 9, 11, 4, 0x02, 1, 2),),
        span(0x0E, 0x11) + span(0x2E, 0x31),
        True,
    ),
    Screen(
        "host_result_table",
        (Region(0x048D60, 0x0480, "718654156b8278613cb2e024d46c7cc087c225f3b2f1ee8facb81dd04d844acb"),),
        Region(0x085C80, 0x0480, "97555940a9cd9427894872fb2a5f1a866e8b626dc30c06318d9e4d051fdf0392"),
        Region(0x086108, 0x0020, "fef1676a3a77e84acc3fcc81e7ed8f7a2af6fe92988bf48acb9991fcc162cf7c"),
        2,
        (
            Label("host_result_table_label", "リザルト", "RESULT", 12, 0, 4, 0x01, 8, 3, 10),
            Label("host_w_1", "勝", "W", 17, 3, 1, 0x0F, 11, 15),
            Label("host_l_1", "敗", "L", 21, 3, 1, 0x0F, 11, 15),
            Label("host_w_2", "勝", "W", 17, 5, 1, 0x0E, 2, 15),
            Label("host_l_2", "敗", "L", 21, 5, 1, 0x0E, 2, 15),
            Label("host_w_3", "勝", "W", 17, 7, 1, 0x0F, 11, 15),
            Label("host_l_3", "敗", "L", 21, 7, 1, 0x0F, 11, 15),
        ),
        span(0x02, 0x09) + span(0x14, 0x19) + (0x1B, 0x1C),
        True,
    ),
    Screen(
        "host_entry_delete",
        (Region(0x049664, 0x0480, "ff8f35ac95eda838879dd8bf1286c86a0476fcf0449dd294799a82fa8af1b84c"),),
        Region(0x089240, 0x0480, "8cb7fad96fe89393c9fe62947f488077b57f0d4676da73239241df3edbf6b4f3"),
        Region(0x0896C8, 0x0020, "1091441f0588d30b157700912daddba11cdc78e8b2f61c484575bb1d12c3ce40"),
        2,
        (
            Label("host_delete_entry_name", "エントリーネーム", "ENTRY NAME", 7, 0, 8, 0x01, 3, 7, 1),
            Label("host_delete", "サクジョ", "DELETE", 17, 0, 4, 0x01, 3, 7, 11),
        ),
        span(0x02, 0x17),
    ),
    Screen(
        "free_win_streak",
        (Region(0x049AE8, 0x0480, "3606fa7a483c7b0295a070926c9f2ba1cb3871848a42214f4c55e8c6cd4fcf4b"),),
        Region(0x0896F0, 0x26C0, "6d133d6c7c8037070b5b796258e8648839fd816e3af3e0daf0cd58979d9dfeba"),
        Region(0x08BDB8, 0x01C0, "5493412b042f4860cb3427c32de3673c50b066e03178970ce464926e4d045b1e"),
        2,
        (
            # The two-digit BG1 counter remains at x5..6.  English reads in
            # natural order as STREAK: [n]; the former right-hand JP label is
            # explicitly cleared without touching the counter cells.
            Label("free_streak", "ただ今", "STREAK:", 1, 1, 4, 0x125, 15, 14, 13),
            Label("free_clear_suffix", "連勝中", "", 7, 1, 4, 0x125, 15, 14, 13),
        ),
        (0x121, 0x122, 0x123, 0x124, 0x127, 0x128, 0x129, 0x12A,
         0x12C, 0x12D, 0x12E, 0x12F, 0x132, 0x133, 0x134, 0x135),
        True,
        (
            Region(0x049F72, 0x0480, "d47ba439dc6005cc06990cf16ca4f801a5c832e8e60de49a67f0cff7373be20a"),
            Region(0x04A3F4, 0x0480, "3c982fde9fa1e9e4db08ed7210bf101b6460629910766b358165b391caa50f73"),
        ),
    ),
)


# Native 3x7 uppercase pixel font.  Rows are doubled vertically to make the
# same 14-pixel-high lettering used by the adjacent v0.9 PET/menu patches.
FONT = {
    "0": ("010", "101", "101", "101", "101", "101", "010"),
    "1": ("010", "110", "010", "010", "010", "010", "111"),
    "2": ("110", "001", "001", "010", "100", "100", "111"),
    "3": ("110", "001", "001", "010", "001", "001", "110"),
    "4": ("101", "101", "101", "111", "001", "001", "001"),
    "5": ("111", "100", "100", "110", "001", "001", "110"),
    "6": ("011", "100", "100", "110", "101", "101", "010"),
    "7": ("111", "001", "001", "010", "010", "010", "010"),
    "8": ("010", "101", "101", "010", "101", "101", "010"),
    "9": ("010", "101", "101", "011", "001", "001", "110"),
    "A": ("010", "101", "101", "111", "101", "101", "101"),
    "B": ("110", "101", "101", "110", "101", "101", "110"),
    "C": ("011", "100", "100", "100", "100", "100", "011"),
    "D": ("110", "101", "101", "101", "101", "101", "110"),
    "E": ("111", "100", "100", "110", "100", "100", "111"),
    "F": ("111", "100", "100", "110", "100", "100", "100"),
    "G": ("011", "100", "100", "101", "101", "101", "011"),
    "H": ("101", "101", "101", "111", "101", "101", "101"),
    "I": ("111", "010", "010", "010", "010", "010", "111"),
    "J": ("001", "001", "001", "001", "101", "101", "010"),
    "K": ("101", "101", "110", "100", "110", "101", "101"),
    "L": ("100", "100", "100", "100", "100", "100", "111"),
    "M": ("101", "111", "111", "101", "101", "101", "101"),
    "N": ("101", "111", "111", "111", "111", "111", "101"),
    "O": ("010", "101", "101", "101", "101", "101", "010"),
    "P": ("110", "101", "101", "110", "100", "100", "100"),
    "Q": ("010", "101", "101", "101", "101", "110", "011"),
    "R": ("110", "101", "101", "110", "110", "101", "101"),
    "S": ("011", "100", "100", "010", "001", "001", "110"),
    "T": ("111", "010", "010", "010", "010", "010", "010"),
    "U": ("101", "101", "101", "101", "101", "101", "111"),
    "V": ("101", "101", "101", "101", "101", "101", "010"),
    "W": ("101", "101", "101", "101", "111", "111", "101"),
    "X": ("101", "101", "010", "010", "010", "101", "101"),
    "Y": ("101", "101", "101", "010", "010", "010", "010"),
    "Z": ("111", "001", "001", "010", "100", "100", "111"),
    "?": ("010", "101", "001", "010", "010", "000", "010"),
    ":": ("000", "010", "010", "000", "010", "010", "000"),
}


def digest(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def source_region(rom: bytes, region: Region, label: str) -> bytes:
    payload = rom[region.offset:region.offset + region.length]
    if len(payload) != region.length or digest(payload) != region.sha256:
        raise ValueError(f"{label}: unexpected source span at 0x{region.offset:06X}")
    return payload


def map_word(tilemap: bytes | bytearray, x: int, y: int) -> int:
    position = (y * MAP_WIDTH + x) * 2
    return int.from_bytes(tilemap[position:position + 2], "little")


def put_map_word(tilemap: bytearray, x: int, y: int, value: int) -> None:
    position = (y * MAP_WIDTH + x) * 2
    tilemap[position:position + 2] = value.to_bytes(2, "little")


def pack_tile(pixels: list[int]) -> bytes:
    if len(pixels) != 64 or any(not 0 <= value <= 15 for value in pixels):
        raise ValueError("invalid 8x8 4-bpp tile")
    return bytes((pixels[i] << 4) | pixels[i + 1] for i in range(0, 64, 2))


def unpack_tile(tiles: bytes | bytearray, tile: int) -> list[int]:
    payload = tiles[tile * TILE_BYTES:(tile + 1) * TILE_BYTES]
    if len(payload) != TILE_BYTES:
        raise ValueError(f"tile 0x{tile:03X} is outside its bank")
    return [value for byte in payload for value in (byte >> 4, byte & 15)]


def write_packed_tile(tiles: bytearray, tile: int, payload: bytes) -> None:
    if len(payload) != TILE_BYTES:
        raise ValueError("packed tile must contain 32 bytes")
    start = tile * TILE_BYTES
    tiles[start:start + TILE_BYTES] = payload


def text_width(text: str) -> int:
    if not text:
        return 0
    return sum(3 if character == " " else 4 for character in text) - 1


def raster_label(label: Label) -> list[list[int]]:
    unsupported = sorted(set(label.translation.replace(" ", "")) - FONT.keys())
    if unsupported:
        raise ValueError(f"{label.id}: unsupported glyphs {unsupported}")
    width = label.columns * 8
    rendered_width = text_width(label.translation)
    if rendered_width > width:
        raise ValueError(
            f"{label.id}: {rendered_width}px exceeds its {width}px native field"
        )
    canvas = [[label.background_colour] * width for _ in range(16)]
    origin_x = (width - rendered_width) // 2
    face: list[tuple[int, int]] = []
    cursor = origin_x
    for character in label.translation:
        if character == " ":
            cursor += 3
            continue
        for glyph_y, row in enumerate(FONT[character]):
            for glyph_x, enabled in enumerate(row):
                if enabled != "1":
                    continue
                for dy in (0, 1):
                    point = (cursor + glyph_x, 1 + glyph_y * 2 + dy)
                    canvas[point[1]][point[0]] = label.face_colour
                    face.append(point)
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


def label_cells(screen: Screen) -> set[tuple[int, int]]:
    return {
        (label.x + column, label.y + row)
        for label in screen.labels
        for column in range(label.columns)
        for row in range(2)
    }


def assert_exclusive(
    tilemap: bytes,
    pool: tuple[int, ...],
    allowed: set[tuple[int, int]],
    label: str,
) -> list[dict[str, object]]:
    references = []
    for index in range(MAP_WIDTH * MAP_HEIGHT):
        word = int.from_bytes(tilemap[index * 2:index * 2 + 2], "little")
        tile = word & TILE_MASK
        if tile not in pool:
            continue
        cell = (index % MAP_WIDTH, index // MAP_WIDTH)
        if cell not in allowed:
            raise AssertionError(
                f"{label}: tile 0x{tile:03X} is shared at map cell {cell}"
            )
        references.append({"x": cell[0], "y": cell[1], "tile": f"0x{tile:03X}"})
    return references


def canvas_tile(canvas: list[list[int]], column: int, row: int) -> bytes:
    return pack_tile(
        [canvas[row * 8 + y][column * 8 + x] for y in range(8) for x in range(8)]
    )


def draw_allocated(
    screen: Screen,
    tilemap: bytearray,
    tiles: bytearray,
) -> tuple[list[dict[str, object]], int]:
    for tile in screen.tile_pool:
        write_packed_tile(tiles, tile, bytes(TILE_BYTES))
    pattern_to_tile: dict[bytes, int] = {}
    pool_cursor = 0
    records = []
    for label in screen.labels:
        canvas = raster_label(label)
        cells = []
        for row in range(2):
            for column in range(label.columns):
                pattern = canvas_tile(canvas, column, row)
                if pattern == bytes(
                    [(label.background_colour << 4) | label.background_colour]
                ) * TILE_BYTES:
                    tile = label.background_tile
                elif pattern in pattern_to_tile:
                    tile = pattern_to_tile[pattern]
                else:
                    if pool_cursor >= len(screen.tile_pool):
                        raise AssertionError(
                            f"{screen.id}: English patterns exceed exclusive tile pool"
                        )
                    tile = screen.tile_pool[pool_cursor]
                    pool_cursor += 1
                    pattern_to_tile[pattern] = tile
                    write_packed_tile(tiles, tile, pattern)
                x, y = label.x + column, label.y + row
                old = map_word(tilemap, x, y)
                put_map_word(tilemap, x, y, (old & ~TILE_MASK) | tile)
                cells.append({"x": x, "y": y, "tile": f"0x{tile:03X}"})
        records.append(label_record(label, cells))
    return records, len(pattern_to_tile)


def draw_preserving_map(
    screen: Screen,
    source_map: bytes,
    tiles: bytearray,
) -> tuple[list[dict[str, object]], int]:
    # Each original target tile becomes exactly the pattern required by its
    # existing cell.  Repeated tile IDs are accepted only when the English
    # pattern is identical, proving that the map can stay byte-for-byte.
    for tile in screen.tile_pool:
        write_packed_tile(tiles, tile, bytes(TILE_BYTES))
    desired: dict[int, bytes] = {}
    records = []
    for label in screen.labels:
        canvas = raster_label(label)
        cells = []
        for row in range(2):
            for column in range(label.columns):
                x, y = label.x + column, label.y + row
                tile = map_word(source_map, x, y) & TILE_MASK
                if tile not in screen.tile_pool:
                    raise AssertionError(
                        f"{screen.id}: fixed cell ({x},{y}) uses non-pool tile 0x{tile:03X}"
                    )
                pattern = canvas_tile(canvas, column, row)
                if tile in desired and desired[tile] != pattern:
                    raise AssertionError(
                        f"{screen.id}: repeated tile 0x{tile:03X} needs conflicting patterns"
                    )
                desired[tile] = pattern
                cells.append({"x": x, "y": y, "tile": f"0x{tile:03X}"})
        records.append(label_record(label, cells))
    for tile, pattern in desired.items():
        write_packed_tile(tiles, tile, pattern)
    return records, len(set(desired.values()))


def label_record(label: Label, cells: list[dict[str, object]]) -> dict[str, object]:
    return {
        "id": label.id,
        "source": label.original,
        "translation": label.translation,
        "field_tiles": {"x": label.x, "y": label.y, "width": label.columns, "height": 2},
        "field_pixels": [label.columns * 8, 16],
        "render_width_pixels": text_width(label.translation),
        "font": "3x7 scaleY2, nearest-neighbour, no antialias",
        "colours": {
            "background": label.background_colour,
            "face": label.face_colour,
            "outline": label.outline_colour,
        },
        "cells": cells,
    }


def changed_indexes(before: bytes, after: bytes | bytearray) -> set[int]:
    if len(before) != len(after):
        raise ValueError("asset lengths differ")
    return {index for index, (old, new) in enumerate(zip(before, after)) if old != new}


def rgb444(value: int) -> tuple[int, int, int]:
    return ((value & 15) * 17, ((value >> 4) & 15) * 17, ((value >> 8) & 15) * 17)


def decode_palettes(payload: bytes, base: int) -> dict[int, list[tuple[int, int, int]]]:
    if len(payload) % 0x20:
        raise ValueError("palette payload is not an integer number of 16-colour banks")
    result = {}
    for bank in range(len(payload) // 0x20):
        chunk = payload[bank * 0x20:(bank + 1) * 0x20]
        result[base + bank] = [
            rgb444(int.from_bytes(chunk[i:i + 2], "little"))
            for i in range(0, 0x20, 2)
        ]
    return result


def render_screen(
    tilemap: bytes,
    tiles: bytes | bytearray,
    palettes: dict[int, list[tuple[int, int, int]]],
) -> Image.Image:
    image = Image.new("RGB", (VISIBLE_WIDTH * 8, MAP_HEIGHT * 8), (0, 0, 0))
    output = image.load()
    fallback = next(iter(palettes.values()))
    for y in range(MAP_HEIGHT * 8):
        for x in range(VISIBLE_WIDTH * 8):
            word = map_word(tilemap, x // 8, y // 8)
            tile = word & TILE_MASK
            px, py = x & 7, y & 7
            if word & 0x4000:
                px ^= 7
            if word & 0x8000:
                py ^= 7
            colour = unpack_tile(tiles, tile)[py * 8 + px]
            output[x, y] = palettes.get((word >> 9) & 15, fallback)[colour]
    return image


def comparison_preview(
    screen: Screen,
    source_map: bytes,
    source_tiles: bytes,
    patched_map: bytes,
    patched_tiles: bytes,
    palette: bytes,
    output: Path,
) -> None:
    palettes = decode_palettes(palette, screen.palette_base)
    before = render_screen(source_map, source_tiles, palettes)
    after = render_screen(patched_map, patched_tiles, palettes)
    scale = 2
    before = before.resize((before.width * scale, before.height * scale), Image.Resampling.NEAREST)
    after = after.resize((after.width * scale, after.height * scale), Image.Resampling.NEAREST)
    gap, caption = 8, 30
    canvas = Image.new("RGB", (before.width + after.width + gap, before.height + caption), (24, 24, 24))
    canvas.paste(before, (0, caption))
    canvas.paste(after, (before.width + gap, caption))
    draw = ImageDraw.Draw(canvas)
    draw.text((6, 7), f"{screen.id} SOURCE (224x144)", fill="white")
    draw.text((before.width + gap + 6, 7), f"{screen.id} ENGLISH v0.10", fill="white")
    for label in screen.labels:
        rect = (
            label.x * 8 * scale,
            caption + label.y * 8 * scale,
            (label.x + label.columns) * 8 * scale - 1,
            caption + (label.y + 2) * 8 * scale - 1,
        )
        draw.rectangle(rect, outline=(255, 64, 64), width=1)
        shifted = (rect[0] + before.width + gap, rect[1], rect[2] + before.width + gap, rect[3])
        draw.rectangle(shifted, outline=(96, 255, 96), width=1)
    canvas.save(output)


def safe_name(screen_id: str, kind: str, index: int | None = None) -> str:
    suffix = "" if index is None else f"_{index + 1}"
    return f"{screen_id}_bg0_{kind}{suffix}_v0_10.bin"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_rom", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    rom = args.source_rom.read_bytes()
    if len(rom) != ROM_SIZE or digest(rom) != SOURCE_SHA256:
        raise ValueError("unsupported source ROM; expected verified Japanese Rev 1")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    reports = []
    outputs: dict[str, str] = {}
    total_occurrences = 0
    for screen in SCREENS:
        source_maps = [
            source_region(rom, region, f"{screen.id} map {index + 1}")
            for index, region in enumerate(screen.maps)
        ]
        source_tiles = source_region(rom, screen.tiles, f"{screen.id} tiles")
        source_palette = source_region(rom, screen.palette, f"{screen.id} palette")
        guard_maps = [
            source_region(rom, region, f"{screen.id} shared guard map {index + 1}")
            for index, region in enumerate(screen.guard_maps)
        ]
        allowed_cells = label_cells(screen)
        references = [
            assert_exclusive(tilemap, screen.tile_pool, allowed_cells, screen.id)
            for tilemap in source_maps
        ]
        guard_references = [
            assert_exclusive(tilemap, screen.tile_pool, set(), f"{screen.id} guard")
            for tilemap in guard_maps
        ]
        if any(guard_references):
            raise AssertionError(f"{screen.id}: shared guard map references target tiles")

        patched_maps = [bytearray(tilemap) for tilemap in source_maps]
        patched_tiles = bytearray(source_tiles)
        if screen.preserve_map:
            labels, pattern_count = draw_preserving_map(screen, source_maps[0], patched_tiles)
            for index, tilemap in enumerate(source_maps):
                if tilemap != source_maps[0]:
                    # Header target words must match even when the remainder of
                    # the bracket maps differs.
                    for x, y in allowed_cells:
                        if map_word(tilemap, x, y) != map_word(source_maps[0], x, y):
                            raise AssertionError(
                                f"{screen.id}: map {index + 1} target cell ({x},{y}) differs"
                            )
        else:
            labels, pattern_count = draw_allocated(screen, patched_maps[0], patched_tiles)
            for index in range(1, len(patched_maps)):
                patched_maps[index][:] = patched_maps[0]

        map_change_sets = [
            changed_indexes(before, after)
            for before, after in zip(source_maps, patched_maps)
        ]
        allowed_map_bytes = {
            byte
            for x, y in allowed_cells
            for byte in ((y * MAP_WIDTH + x) * 2, (y * MAP_WIDTH + x) * 2 + 1)
        }
        if any(changes - allowed_map_bytes for changes in map_change_sets):
            raise AssertionError(f"{screen.id}: map changed outside audited label cells")
        if screen.preserve_map and any(map_change_sets):
            raise AssertionError(f"{screen.id}: preserve-map screen changed its map")

        tile_changes = changed_indexes(source_tiles, patched_tiles)
        allowed_tile_bytes = {
            byte
            for tile in screen.tile_pool
            for byte in range(tile * TILE_BYTES, (tile + 1) * TILE_BYTES)
        }
        if tile_changes - allowed_tile_bytes:
            raise AssertionError(f"{screen.id}: tile bank changed outside exclusive pool")

        map_outputs = []
        for index, (region, patched_map, changes) in enumerate(
            zip(screen.maps, patched_maps, map_change_sets)
        ):
            if not changes:
                continue
            name = safe_name(screen.id, "map", index if len(screen.maps) > 1 else None)
            path = args.output_dir / name
            path.write_bytes(patched_map)
            outputs[name] = digest(path.read_bytes())
            map_outputs.append(
                {"index": index + 1, "file": name, "sha256": outputs[name], "changed_bytes": len(changes)}
            )

        tile_name = safe_name(screen.id, "tiles")
        tile_path = args.output_dir / tile_name
        tile_path.write_bytes(patched_tiles)
        outputs[tile_name] = digest(tile_path.read_bytes())
        preview_name = f"{screen.id}_comparison_v0_10.png"
        preview_path = args.output_dir / preview_name
        comparison_preview(
            screen,
            source_maps[0],
            source_tiles,
            bytes(patched_maps[0]),
            bytes(patched_tiles),
            source_palette,
            preview_path,
        )
        outputs[preview_name] = digest(preview_path.read_bytes())

        occurrence_multiplier = len(screen.maps) if screen.id == "host_brackets" else 1
        occurrences = len(screen.labels) * occurrence_multiplier
        total_occurrences += occurrences
        reports.append(
            {
                "id": screen.id,
                "status": "PASS",
                "source_maps": [
                    {"offset": f"0x{region.offset:06X}", "length": region.length, "sha256": region.sha256}
                    for region in screen.maps
                ],
                "shared_guard_maps": [
                    {"offset": f"0x{region.offset:06X}", "length": region.length, "sha256": region.sha256}
                    for region in screen.guard_maps
                ],
                "tiles": {
                    "offset": f"0x{screen.tiles.offset:06X}",
                    "length": screen.tiles.length,
                    "source_sha256": screen.tiles.sha256,
                    "output": tile_name,
                    "output_sha256": outputs[tile_name],
                },
                "palette": {
                    "offset": f"0x{screen.palette.offset:06X}",
                    "length": screen.palette.length,
                    "sha256": screen.palette.sha256,
                    "byte_identical": True,
                },
                "labels": labels,
                "graphical_occurrences": occurrences,
                "preserve_map": screen.preserve_map,
                "map_outputs": map_outputs,
                "exclusive_tile_pool": [f"0x{tile:03X}" for tile in screen.tile_pool],
                "source_references": references,
                "shared_guard_references": guard_references,
                "unique_rendered_patterns": pattern_count,
                "changes": {
                    "map_bytes": [len(changes) for changes in map_change_sets],
                    "tile_bytes": len(tile_changes),
                    "outside_allowlist": 0,
                },
                "preview": preview_name,
            }
        )

    report = {
        "format": "n1-host-free-menu-assets-v0.10",
        "status": "PASS",
        "native_display": [224, 144],
        "visible_tile_grid": [28, 18],
        "asset_map_grid": [32, 18],
        "tile_format": "8x8 packed 4bpp",
        "source_rom_sha256": SOURCE_SHA256,
        "new_graphical_occurrences": total_occurrences,
        "screens": reports,
        "outputs": outputs,
    }
    report_path = args.output_dir / "host_free_menu_asset_report_v0_10.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
