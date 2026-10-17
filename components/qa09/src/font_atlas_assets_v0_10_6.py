#!/usr/bin/env python3
"""Build the TTF-derived and pixel-polished UI lettering for N1 Battle v0.10.6.

The two supplied TrueType fonts establish the face assignment, size and native
metrics. FreeType first rasterizes every glyph at its final WonderSwan size;
glyphs whose small-size hinting closes counters, breaks strokes or produces
uneven diagonals then receive deterministic pixel-art masks at that same size.
No completed word or line is scaled, filtered, condensed or antialiased.
Glyphs are composed with one explicit empty face column between adjacent
characters, so fixed-width fields cannot collapse letters together.

BN5DSEU Font Thin is used for the larger PET, SHOP, SAVE and location labels;
SF3FontSmall is used where its compact forms match the keyboard controls and
the Free Battle STREAK label better.  Only the static graphical labels
explicitly identified by the user are rebuilt; dialogue strings and the lower
dialogue renderer are outside every write allowlist.

The input is the canonical v0.10.5 ROM.  Complete source spans are guarded by
SHA-256, every edited map cell and tile ID is audited, and all output assets
are full-size replacements suitable for the cumulative source-ROM manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from PIL import Image, ImageDraw, ImageFont


VERSION = "0.10.6"
ROM_SIZE = 0x400000
BASE_ROM_SHA256 = "e51d45b3a02161d20c9de136d610f9b1fc268752ca6ce29a16f308568bc082bf"
BN5_TTF_SHA256 = "8f01cacff269f66e3f4d80beae13d6f86a30d00b297da32aa0af90461662ac2d"
SF3_TTF_SHA256 = "c21fece52fb8b49f8347f60b5cf4cefc5cb5cb19aac56f4e004f4ad22bd5a220"
PET_REFERENCE_SHA256 = "1a978431df1eff538b96bf081a8c44110328add3f121237f6b47270e2f4bb786"

MAP_WIDTH = 32
TILE_BYTES = 32
TILE_MASK = 0x01FF


# Native masks repairing ambiguous small-size hinting in the supplied faces.
# They are not a third font: each mask is bound to an already selected TTF and
# point size, retains that role's proportions, and is authored at final 1:1
# WonderSwan resolution.  ``.`` is transparent and ``#`` is a face pixel.
BN5_8_PATTERNS: dict[str, tuple[str, ...]] = {
    "0": (".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."),
    "1": (".#.", "##.", ".#.", ".#.", ".#.", ".#.", "###"),
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "C": (".####", "#....", "#....", "#....", "#....", "#....", ".####"),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "G": (".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".###."),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": ("###", ".#.", ".#.", ".#.", ".#.", ".#.", "###"),
    "K": ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "M": ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "V": ("#...#", "#...#", "#...#", "#...#", ".#.#.", ".#.#.", "..#.."),
    "Y": ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    "a": (".###.", "....#", ".####", "#...#", ".####"),
    "b": ("#...", "#...", "#...", "###.", "#..#", "#..#", "#..#", "###."),
    "c": (".###", "#...", "#...", "#...", ".###"),
    "d": ("...#", "...#", "...#", ".###", "#..#", "#..#", "#..#", ".###"),
    "e": (".###.", "#...#", "#####", "#....", ".####"),
    "f": (".##", ".#.", "###", ".#.", ".#.", ".#.", ".#."),
    "g": (".###", "#..#", "#..#", ".###", "...#", "###."),
    "h": ("#...", "#...", "#...", "###.", "#..#", "#..#", "#..#", "#..#"),
    "i": ("#", ".", "#", "#", "#", "#", "#"),
    "k": ("#...", "#...", "#...", "#..#", "#.#.", "##..", "#.#.", "#..#"),
    "l": ("#", "#", "#", "#", "#", "#", "#", "#"),
    "m": ("##.##", "#.#.#", "#.#.#", "#.#.#", "#.#.#"),
    "n": ("###.", "#..#", "#..#", "#..#", "#..#"),
    "o": (".##.", "#..#", "#..#", "#..#", ".##."),
    "p": ("###.", "#..#", "#..#", "###.", "#...", "#..."),
    "r": ("###.", "#..#", "#...", "#...", "#..."),
    "s": (".###", "#...", ".##.", "...#", "###."),
    "t": (".#.", "###", ".#.", ".#.", ".#.", "..#"),
    "u": ("#..#", "#..#", "#..#", "#..#", ".###"),
    "v": ("#...#", "#...#", ".#.#.", ".#.#.", "..#.."),
    "y": ("#...#", "#...#", ".####", "....#", "#...#", ".###."),
}

SF3_13_PATTERNS = {character: BN5_8_PATTERNS[character] for character in "AEGIMNRSTY"}

SF3_15_PATTERNS: dict[str, tuple[str, ...]] = {
    "!": ("#", "#", "#", "#", "#", ".", "#", "#"),
    "A": (".####.", "##..##", "##..##", "######", "##..##", "##..##", "##..##", "##..##"),
    "B": ("#####.", "##..##", "##..##", "#####.", "##..##", "##..##", "##..##", "#####."),
    "C": (".#####", "##....", "##....", "##....", "##....", "##....", "##....", ".#####"),
    "K": ("##..##", "##.##.", "####..", "###...", "####..", "##.##.", "##..##", "##..##"),
    "L": ("##....", "##....", "##....", "##....", "##....", "##....", "##....", "######"),
    "O": (".####.", "##..##", "##..##", "##..##", "##..##", "##..##", "##..##", ".####."),
    "P": ("#####.", "##..##", "##..##", "#####.", "##....", "##....", "##....", "##...."),
    "W": ("#.....#", "#.....#", "#.....#", "#..#..#", "#..#..#", "#.###.#", ".##.##.", ".#...#."),
}

SF3_12_PATTERNS: dict[str, tuple[str, ...]] = {
    character: BN5_8_PATTERNS[character] for character in "ABCK"
}

# Condensed 4x7 capitals let STREAK retain one clear column between all six
# letters inside its immutable 30-pixel field.
SF3_11_PATTERNS: dict[str, tuple[str, ...]] = {
    "S": (".###", "#...", "#...", ".##.", "...#", "...#", "###."),
    "T": ("####", ".#..", ".#..", ".#..", ".#..", ".#..", ".#.."),
    "R": ("###.", "#..#", "#..#", "###.", "#.#.", "#..#", "#..#"),
    "E": ("####", "#...", "#...", "###.", "#...", "#...", "####"),
    "A": (".##.", "#..#", "#..#", "####", "#..#", "#..#", "#..#"),
    "K": ("#..#", "#.#.", "##..", "#...", "##..", "#.#.", "#..#"),
}

PIXEL_ART_PATTERNS: dict[tuple[str, int], dict[str, tuple[str, ...]]] = {
    ("bn5", 8): BN5_8_PATTERNS,
    ("sf3", 11): SF3_11_PATTERNS,
    ("sf3", 12): SF3_12_PATTERNS,
    ("sf3", 13): SF3_13_PATTERNS,
    ("sf3", 15): SF3_15_PATTERNS,
}

DESCENDERS = {"g", "p", "q", "y"}


@dataclass(frozen=True)
class Span:
    id: str
    offset: int
    length: int
    sha256: str
    output: str
    tile_first_id: int = 0


SPANS = {
    "keyboard_map": Span("keyboard_map", 0x0412AA, 0x0480, "85c718873c336c1d66739f97ce37408b98c0ee85b483145c1f27294df4fe8e3b", "name_keyboard_bg0_map_v0_10_6.bin"),
    "shop_map": Span("shop_map", 0x041BB2, 0x0480, "94f0d15a5419df3479e61e6dbd08bacbe5f39f3701686629c9d6bd4b21b51396", "location_shop_bg0_map_v0_10_6.bin"),
    "gp_map": Span("gp_map", 0x042034, 0x0480, "0c519fe3dec91a42b4f985e1ef5773f6fd86d5bdb972633306b33c86ef7e78c7", "location_battlechip_gp_bg0_map_v0_10_6.bin"),
    "free_map": Span("free_map", 0x0424B6, 0x0480, "5e3ffaffd778b1d894fd7194ff5ab2755d4e3717cc7b840fb55fe82a0ce99d23", "pet_carousel_free_battle_bg0_map_v0_10_6.bin"),
    "host_map": Span("host_map", 0x042938, 0x0480, "52c91b3fa6d68a7a08a65bc5c443544185f161fd9d46cc33689f1daba196520c", "pet_carousel_host_tournament_bg0_map_v0_10_6.bin"),
    "pet_map": Span("pet_map", 0x042DBA, 0x0400, "926376a47eaca5620b0fd2e58a0a9d85d01dd3cc0588d3c59acfe02f3c590c9c", "pet_labels_bg0_map_v0_10_6.bin"),
    "save_map": Span("save_map", 0x045BCA, 0x0480, "bbadd7edba1426411b699c524740889294e449332880c413b9b4ae788fe35806", "pet_submenu_save_bg0_map_v0_10_6.bin"),
    "shop_buy_map": Span("shop_buy_map", 0x04604C, 0x0480, "8898ff87ccd9d0cf50940155ec1975ed83c208dba114ccf51d075032a6563539", "shop_purchase_bg0_map_v0_10_6.bin"),
    "streak_map": Span("streak_map", 0x049AE8, 0x0480, "3606fa7a483c7b0295a070926c9f2ba1cb3871848a42214f4c55e8c6cd4fcf4b", "", 0),
    "streak_guard_1": Span("streak_guard_1", 0x049F72, 0x0480, "d47ba439dc6005cc06990cf16ca4f801a5c832e8e60de49a67f0cff7373be20a", "", 0),
    "streak_guard_2": Span("streak_guard_2", 0x04A3F4, 0x0480, "3c982fde9fa1e9e4db08ed7210bf101b6460629910766b358165b391caa50f73", "", 0),
    "keyboard_tiles": Span("keyboard_tiles", 0x074E10, 0x0760, "516f83ee3eba54416785d81d836e697bfb8036646f06377217ae6994c72a631e", "name_keyboard_tiles_v0_10_6.bin", 1),
    "shop_tiles": Span("shop_tiles", 0x0768F0, 0x1740, "b493de5939a36a61b7c1156ab2124749b6a3f19ffef1a54345c77224f33b9c10", "location_shop_bg0_tiles_v0_10_6.bin"),
    "gp_tiles": Span("gp_tiles", 0x078100, 0x1480, "4285ce7fc0be79f949a33b3eeb19682342e5c9ee9b61f32531e0652a2f8f69db", "location_battlechip_gp_bg0_tiles_v0_10_6.bin"),
    "free_tiles": Span("free_tiles", 0x079650, 0x1580, "1d575315d2e4459e9cf1ee5af1c97bdfb037838deafcb8b110762d6f50683d17", "pet_carousel_free_battle_bg0_tiles_v0_10_6.bin"),
    "host_tiles": Span("host_tiles", 0x07ACA0, 0x15C0, "2ce50fb0fc81546fe19e3c8713ce1ca25452a2f912f28514c7b6af2a687c28ba", "pet_carousel_host_tournament_bg0_tiles_v0_10_6.bin"),
    "pet_tiles": Span("pet_tiles", 0x07C330, 0x0980, "f1767e86841d884a737d0b7137be1eefa287a3849e41a2d04c6abfc18357d2a2", "pet_labels_tiles_v0_10_6.bin", 1),
    "save_tiles": Span("save_tiles", 0x081070, 0x0800, "4a2d461d734245f9650fba93373f4ba1780e4c23912c8ac91f5f92cd5527e9ad", "pet_submenu_save_tiles_v0_10_6.bin"),
    "shop_buy_tiles": Span("shop_buy_tiles", 0x0818A0, 0x0600, "1dde1b1b22c4a7441910b80a13fe8915c7b6400fa2ca23ed6879a50f912ce4d8", "shop_purchase_bg0_tiles_v0_10_6.bin"),
    "streak_tiles": Span("streak_tiles", 0x0896F0, 0x26C0, "a2bf87d95f58579e4ea4485639e3d3d3abdf5a36670c9901af2f2c1026ad28dc", "free_win_streak_bg0_tiles_v0_10_6.bin"),
}

MASK_SPANS = {
    "low": Span("keyboard_low_mask", 0x19A47E, 0x00C0, "2d4b9752c5f396dadfd2f05e5ce4182ce7a750c7909d40e841452f1b09a477eb", "name_keyboard_obj_low_mask_v0_10_6.bin"),
    "cap": Span("keyboard_cap_mask", 0x19A55C, 0x00C0, "b1388a7b66111d0f810a1d2b2611a764e4aa5f7178858cb9dc272c3c2f60d078", "name_keyboard_obj_cap_mask_v0_10_6.bin"),
    "abc": Span("keyboard_abc_mask", 0x19A63A, 0x00C0, "57ee607495b834236e0212f0bd22aa132c57a8550f4dba85f4b8cb0ad649ded9", "name_keyboard_obj_abc_mask_v0_10_6.bin"),
}


@dataclass(frozen=True)
class Label:
    id: str
    text: str
    x: int
    y: int
    columns: int
    rows: int
    background: int
    face: int
    target_width: int | None = None
    target_height: int = 12
    offset_x: int | None = None
    offset_y: int | None = None
    outline: int | None = None
    outline_mode: str = "none"
    background_tile: int | None = None
    font_id: str = "bn5"
    point_size: int = 8


def sha256(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def guarded_span(rom: bytes, spec: Span) -> bytes:
    payload = rom[spec.offset:spec.offset + spec.length]
    if len(payload) != spec.length or sha256(payload) != spec.sha256:
        raise ValueError(f"{spec.id}: unexpected canonical v0.10.5 span")
    return payload


def map_word(tilemap: bytes | bytearray, x: int, y: int) -> int:
    position = (y * MAP_WIDTH + x) * 2
    return int.from_bytes(tilemap[position:position + 2], "little")


def put_map_word(tilemap: bytearray, x: int, y: int, value: int) -> None:
    position = (y * MAP_WIDTH + x) * 2
    tilemap[position:position + 2] = value.to_bytes(2, "little")


def pack_tile(pixels: Sequence[int]) -> bytes:
    if len(pixels) != 64 or any(not 0 <= value <= 15 for value in pixels):
        raise ValueError("invalid packed 4-bpp tile")
    return bytes((pixels[index] << 4) | pixels[index + 1] for index in range(0, 64, 2))


def unpack_tile(payload: bytes | bytearray) -> tuple[int, ...]:
    if len(payload) != TILE_BYTES:
        raise ValueError("a tile must contain 32 bytes")
    return tuple(value for byte in payload for value in (byte >> 4, byte & 15))


def tile_bytes(tiles: bytes | bytearray, tile_id: int, first_id: int) -> bytes:
    start = (tile_id - first_id) * TILE_BYTES
    if start < 0 or start + TILE_BYTES > len(tiles):
        raise ValueError(f"tile 0x{tile_id:03X} is outside the bank")
    return bytes(tiles[start:start + TILE_BYTES])


def put_tile(tiles: bytearray, tile_id: int, first_id: int, pattern: bytes) -> None:
    if len(pattern) != TILE_BYTES:
        raise ValueError("invalid tile pattern")
    start = (tile_id - first_id) * TILE_BYTES
    if start < 0 or start + TILE_BYTES > len(tiles):
        raise ValueError(f"tile 0x{tile_id:03X} is outside the bank")
    tiles[start:start + TILE_BYTES] = pattern


class TTFFontSet:
    """Deterministic two-face FreeType renderer for the supplied TTF files."""

    LETTER_SPACING = 1
    SPACE_WIDTH = 3
    SOURCES = {
        "bn5": ("BN5DSEU Font Thin", BN5_TTF_SHA256),
        "sf3": ("SF3FontSmall", SF3_TTF_SHA256),
    }

    def __init__(self, bn5_path: Path, sf3_path: Path) -> None:
        self.paths = {"bn5": bn5_path, "sf3": sf3_path}
        self._fonts: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}
        self.corrected_variants: set[tuple[str, int, str]] = set()
        for font_id, path in self.paths.items():
            payload = path.read_bytes()
            expected = self.SOURCES[font_id][1]
            if sha256(payload) != expected:
                raise ValueError(f"{font_id}: TTF differs from the supplied source")
            # Loading the face here rejects corrupt or unsupported font files
            # before any output asset can be written.
            ImageFont.truetype(str(path), 8, layout_engine=ImageFont.Layout.BASIC)

    def face(self, font_id: str, point_size: int) -> ImageFont.FreeTypeFont:
        if font_id not in self.paths:
            raise ValueError(f"unknown TTF source {font_id!r}")
        if not 1 <= point_size <= 64:
            raise ValueError(f"invalid TTF point size {point_size}")
        key = (font_id, point_size)
        if key not in self._fonts:
            self._fonts[key] = ImageFont.truetype(
                str(self.paths[font_id]),
                point_size,
                layout_engine=ImageFont.Layout.BASIC,
            )
        return self._fonts[key]

    @staticmethod
    def pixel_art_glyph(
        rows: tuple[str, ...], common_height: int, baseline: int, descender: bool,
    ) -> Image.Image:
        if not rows or any(not row for row in rows):
            raise ValueError("pixel-art glyph has an empty row")
        width = len(rows[0])
        if any(len(row) != width or set(row) - {".", "#"} for row in rows):
            raise ValueError("pixel-art glyph has invalid geometry")
        image = Image.new("1", (width, common_height))
        top = baseline - len(rows) + (1 if descender else 0)
        if top < 0 or top + len(rows) > common_height:
            raise ValueError("pixel-art glyph escapes the common canvas")
        for y, row in enumerate(rows):
            for x, value in enumerate(row):
                if value == "#":
                    image.putpixel((x, top + y), 1)
        return image

    def glyphs(self, label: Label) -> tuple[list[Image.Image], int, int]:
        font = self.face(label.font_id, label.point_size)
        ascent, descent = font.getmetrics()
        baseline = ascent + 4
        common_height = ascent + descent + 8
        glyphs: list[Image.Image] = []
        corrected_instances = 0
        pattern_set = PIXEL_ART_PATTERNS.get((label.font_id, label.point_size), {})
        for character in label.text:
            if not 0x20 <= ord(character) <= 0x7E:
                raise ValueError(f"unsupported TTF glyph {character!r}")
            if character == " ":
                glyphs.append(Image.new("1", (self.SPACE_WIDTH, common_height)))
                continue
            bbox = font.getbbox(character)
            canvas = Image.new("1", (max(1, bbox[2] - bbox[0]) + 8, common_height))
            draw = ImageDraw.Draw(canvas)
            # FreeType's monochrome hinted bitmap is the final source.  The
            # line is never rendered at another size and never resampled.
            draw.fontmode = "1"
            draw.text(
                (4 - bbox[0], baseline),
                character,
                font=font,
                fill=1,
                anchor="ls",
            )
            visible = canvas.getbbox()
            if visible is None:
                raise ValueError(f"{label.id}: TTF glyph {character!r} is blank")
            source_glyph = canvas.crop((visible[0], 0, visible[2], common_height))
            rows = pattern_set.get(character)
            if rows is None:
                glyphs.append(source_glyph)
                continue
            corrected = self.pixel_art_glyph(
                rows, common_height, baseline, character in DESCENDERS,
            )
            if corrected.getbbox() is None:
                raise ValueError(f"{label.id}: corrected glyph {character!r} is blank")
            glyphs.append(corrected)
            corrected_instances += 1
            self.corrected_variants.add((label.font_id, label.point_size, character))
        return glyphs, common_height, corrected_instances

    def line(self, label: Label) -> tuple[Image.Image, dict[str, object]]:
        glyphs, common_height, corrected_instances = self.glyphs(label)
        natural_width = (
            sum(glyph.width for glyph in glyphs)
            + self.LETTER_SPACING * max(0, len(glyphs) - 1)
        )
        maximum_width = label.target_width or label.columns * 8
        if natural_width > maximum_width:
            raise ValueError(
                f"{label.id}: native TTF width {natural_width} exceeds {maximum_width}; "
                "line scaling is forbidden"
            )
        output = Image.new("1", (natural_width, common_height))
        cursor = 0
        for glyph in glyphs:
            output.paste(glyph, (cursor, 0))
            cursor += glyph.width + self.LETTER_SPACING
        visible = output.getbbox()
        if visible is None:
            raise ValueError(f"{label.id}: TTF line contains no visible pixels")
        output = output.crop((0, visible[1], output.width, visible[3]))
        return output, {
            "font_id": label.font_id,
            "font_family": self.SOURCES[label.font_id][0],
            "point_size": label.point_size,
            "source_width_pixels": natural_width,
            "render_width_pixels": natural_width,
            "source_visible_height_pixels": output.height,
            "render_height_pixels": output.height,
            "minimum_interglyph_face_gap_pixels": self.LETTER_SPACING,
            "minimum_interglyph_composite_gap_pixels": (
                self.LETTER_SPACING
                if label.outline_mode in {"none", "down"}
                else max(0, self.LETTER_SPACING - 1)
            ),
            "resampled": False,
            "rasterization": "FreeType monochrome hinting plus deterministic native pixel-art correction",
            "manual_pixel_corrected_glyph_instances": corrected_instances,
            "manual_pixel_correction": corrected_instances > 0,
        }

    def raster(self, label: Label) -> tuple[list[list[int]], dict[str, object]]:
        width = label.columns * 8
        height = label.rows * 8
        mask, line_metrics = self.line(label)
        render_width = mask.width
        render_height = mask.height
        x = label.offset_x if label.offset_x is not None else (width - render_width) // 2
        y = label.offset_y if label.offset_y is not None else (height - render_height) // 2
        if x < 0 or y < 0 or x + render_width > width or y + render_height > height:
            raise ValueError(f"{label.id}: rendered glyphs escape the field")

        face = [[False] * width for _ in range(height)]
        for glyph_y in range(render_height):
            for glyph_x in range(render_width):
                if mask.getpixel((glyph_x, glyph_y)):
                    face[y + glyph_y][x + glyph_x] = True

        canvas = [[label.background] * width for _ in range(height)]
        if label.outline is not None:
            if label.outline_mode == "four":
                deltas = ((-1, 0), (1, 0), (0, -1), (0, 1))
            elif label.outline_mode == "down":
                deltas = ((0, 1),)
            elif label.outline_mode == "shadow":
                deltas = ((1, 0), (0, 1), (1, 1))
            elif label.outline_mode == "diagonal":
                deltas = ((1, 1),)
            else:
                raise ValueError(f"{label.id}: invalid outline mode {label.outline_mode}")
            for py in range(height):
                for px in range(width):
                    if not face[py][px]:
                        continue
                    for dx, dy in deltas:
                        nx, ny = px + dx, py + dy
                        if 0 <= nx < width and 0 <= ny < height:
                            canvas[ny][nx] = label.outline
        for py in range(height):
            for px in range(width):
                if face[py][px]:
                    canvas[py][px] = label.face
        return canvas, {
            **line_metrics,
            "field_width_pixels": width,
            "field_height_pixels": height,
            "offset_x_pixels": x,
            "offset_y_pixels": y,
            "composite_height_pixels": render_height + (2 if label.outline_mode == "four" else (1 if label.outline_mode in {"down", "shadow", "diagonal"} else 0)),
        }


def canvas_patterns(canvas: list[list[int]]) -> list[bytes]:
    height = len(canvas)
    width = len(canvas[0])
    if width % 8 or height % 8 or any(len(row) != width for row in canvas):
        raise ValueError("canvas must be tile aligned")
    return [
        pack_tile([
            canvas[cell_y * 8 + y][cell_x * 8 + x]
            for y in range(8) for x in range(8)
        ])
        for cell_y in range(height // 8)
        for cell_x in range(width // 8)
    ]


def cells_for(labels: Iterable[Label]) -> set[tuple[int, int]]:
    return {
        (label.x + x, label.y + y)
        for label in labels
        for y in range(label.rows)
        for x in range(label.columns)
    }


def refs(tilemap: bytes, tile_id: int) -> list[tuple[int, int]]:
    return [
        ((position // 2) % MAP_WIDTH, (position // 2) // MAP_WIDTH)
        for position in range(0, len(tilemap), 2)
        if int.from_bytes(tilemap[position:position + 2], "little") & TILE_MASK == tile_id
    ]


def unused_ids(tilemaps: Sequence[bytes], tiles: bytes, first_id: int) -> list[int]:
    used = {
        int.from_bytes(tilemap[position:position + 2], "little") & TILE_MASK
        for tilemap in tilemaps
        for position in range(0, len(tilemap), 2)
    }
    last_id = first_id + len(tiles) // TILE_BYTES - 1
    return [tile_id for tile_id in range(first_id, last_id + 1) if tile_id not in used]


def augment_pool(
    base_pool: Sequence[int], required: int, tilemaps: Sequence[bytes],
    tiles: bytes, first_id: int, protected: set[int],
) -> tuple[int, ...]:
    pool = list(dict.fromkeys(base_pool))
    if required <= len(pool):
        return tuple(pool)
    candidates = [
        tile_id for tile_id in unused_ids(tilemaps, tiles, first_id)
        if tile_id not in pool and tile_id not in protected
    ]
    # Prefer redundant/padding patterns, then stable numeric order.
    counts: dict[bytes, int] = {}
    last_id = first_id + len(tiles) // TILE_BYTES - 1
    for tile_id in range(first_id, last_id + 1):
        pattern = tile_bytes(tiles, tile_id, first_id)
        counts[pattern] = counts.get(pattern, 0) + 1
    candidates.sort(key=lambda tile_id: (counts[tile_bytes(tiles, tile_id, first_id)] == 1, tile_id))
    pool.extend(candidates[:required - len(pool)])
    if len(pool) < required:
        raise ValueError(f"need {required} tile IDs but only {len(pool)} are safe")
    return tuple(pool)


def allocate_group(
    font: TTFFontSet,
    tilemap_source: bytes,
    tiles_source: bytes,
    labels: Sequence[Label],
    base_pool: Sequence[int],
    first_id: int,
    guard_maps: Sequence[bytes] = (),
    protected_ids: Iterable[int] = (),
) -> tuple[bytes, bytes, dict[str, object], dict[str, list[list[int]]]]:
    targets = cells_for(labels)
    protected = set(protected_ids)
    canvases: dict[str, list[list[int]]] = {}
    metrics: dict[str, dict[str, int]] = {}
    patterns_by_label: dict[str, list[bytes]] = {}
    unique_patterns: list[bytes] = []
    seen_patterns: set[bytes] = set()
    blank_patterns: dict[str, bytes] = {}
    for label in labels:
        canvas, label_metrics = font.raster(label)
        patterns = canvas_patterns(canvas)
        blank = bytes([(label.background << 4) | label.background]) * TILE_BYTES
        canvases[label.id] = canvas
        metrics[label.id] = label_metrics
        patterns_by_label[label.id] = patterns
        blank_patterns[label.id] = blank
        for pattern in patterns:
            if pattern == blank or pattern in seen_patterns:
                continue
            unique_patterns.append(pattern)
            seen_patterns.add(pattern)

    pool = augment_pool(
        base_pool, len(unique_patterns), (tilemap_source, *guard_maps),
        tiles_source, first_id, protected,
    )
    for tile_id in pool:
        for tilemap in (tilemap_source, *guard_maps):
            outside = [cell for cell in refs(tilemap, tile_id) if cell not in targets]
            if outside:
                raise AssertionError(f"tile 0x{tile_id:03X} is referenced outside targets: {outside[:4]}")

    tilemap = bytearray(tilemap_source)
    tiles = bytearray(tiles_source)
    pattern_to_tile: dict[bytes, int] = {}
    for pattern, tile_id in zip(unique_patterns, pool):
        pattern_to_tile[pattern] = tile_id
        put_tile(tiles, tile_id, first_id, pattern)

    assignments: dict[str, list[list[int]]] = {}
    records: list[dict[str, object]] = []
    for label in labels:
        if label.background_tile is None:
            raise ValueError(f"{label.id}: background tile is required")
        blank = blank_patterns[label.id]
        if tile_bytes(tiles_source, label.background_tile, first_id) != blank:
            raise AssertionError(f"{label.id}: background tile does not match colour {label.background}")
        label_assignments: list[list[int]] = []
        for index, pattern in enumerate(patterns_by_label[label.id]):
            tile_id = label.background_tile if pattern == blank else pattern_to_tile[pattern]
            cell_x = label.x + index % label.columns
            cell_y = label.y + index // label.columns
            old_word = map_word(tilemap_source, cell_x, cell_y)
            put_map_word(tilemap, cell_x, cell_y, (old_word & ~TILE_MASK) | tile_id)
            label_assignments.append([cell_x, cell_y, tile_id])
        assignments[label.id] = label_assignments
        records.append({
            "id": label.id,
            "text": label.text,
            "map_rectangle": {"x": label.x, "y": label.y, "columns": label.columns, "rows": label.rows},
            "palette_indices": {"background": label.background, "face": label.face, "outline": label.outline},
            "outline_mode": label.outline_mode,
            "background_tile": f"0x{label.background_tile:03X}",
            **metrics[label.id],
        })

    changed_cells = []
    for position in range(0, len(tilemap_source), 2):
        if tilemap_source[position:position + 2] != tilemap[position:position + 2]:
            cell = ((position // 2) % MAP_WIDTH, (position // 2) // MAP_WIDTH)
            if cell not in targets:
                raise AssertionError(f"map changed outside target at {cell}")
            changed_cells.append(list(cell))
    changed_tiles = []
    last_id = first_id + len(tiles_source) // TILE_BYTES - 1
    for tile_id in range(first_id, last_id + 1):
        if tile_bytes(tiles_source, tile_id, first_id) != tile_bytes(tiles, tile_id, first_id):
            if tile_id not in pool:
                raise AssertionError(f"tile 0x{tile_id:03X} changed outside pool")
            changed_tiles.append(tile_id)
    report = {
        "labels": records,
        "capacity": {
            "unique_nonblank_patterns": len(unique_patterns),
            "base_pool_ids": len(set(base_pool)),
            "allocation_pool_ids": len(pool),
            "additional_unreferenced_ids": [f"0x{tile_id:03X}" for tile_id in pool if tile_id not in set(base_pool)],
            "unused_pool_ids": len(pool) - len(unique_patterns),
        },
        "allowlist": {
            "target_map_cells": len(targets),
            "changed_map_cells": changed_cells,
            "allocation_pool": [f"0x{tile_id:03X}" for tile_id in pool],
            "changed_tile_ids": [f"0x{tile_id:03X}" for tile_id in changed_tiles],
            "references_outside_targets": 0,
        },
    }
    return bytes(tilemap), bytes(tiles), report, assignments


def base_pool_from_targets(tilemap: bytes, labels: Sequence[Label], excluded: set[int]) -> tuple[int, ...]:
    result: list[int] = []
    for label in labels:
        for y in range(label.y, label.y + label.rows):
            for x in range(label.x, label.x + label.columns):
                tile_id = map_word(tilemap, x, y) & TILE_MASK
                if tile_id not in excluded and tile_id not in result:
                    result.append(tile_id)
    return tuple(result)


def build_keyboard_masks(
    canvases: dict[str, list[list[int]]], source_masks: dict[str, bytes]
) -> dict[str, bytes]:
    outputs: dict[str, bytes] = {}
    order = (2, 5, 0, 1, 3, 4)
    for key in ("low", "cap", "abc"):
        canvas = canvases[key]
        patterns = canvas_patterns(canvas)
        if len(patterns) != 6:
            raise AssertionError("keyboard selector must be 3x2 tiles")
        mask_patterns = []
        for index in order:
            pixels = unpack_tile(patterns[index])
            mask_patterns.append(pack_tile([0 if value == 1 else 7 for value in pixels]))
        output = b"".join(mask_patterns)
        if len(output) != len(source_masks[key]) or len(output) != 0xC0:
            raise AssertionError("invalid selector OBJ mask")
        outputs[key] = output
    return outputs


def direct_streak(
    font: TTFFontSet, tilemap: bytes, tiles_source: bytes
) -> tuple[bytes, dict[str, object]]:
    label = Label(
        "free_streak", "STREAK", 1, 1, 4, 2,
        15, 14, 30, 12, 1, 4, 13, "down", None, "sf3", 11,
    )
    canvas, metrics = font.raster(label)
    patterns = canvas_patterns(canvas)
    target_cells = [(x, y) for y in (1, 2) for x in range(1, 5)]
    suffix_cells = [(x, y) for y in (1, 2) for x in range(7, 11)]
    target_ids = [map_word(tilemap, x, y) & TILE_MASK for x, y in target_cells]
    suffix_ids = [map_word(tilemap, x, y) & TILE_MASK for x, y in suffix_cells]
    if len(set(target_ids + suffix_ids)) != 16:
        raise AssertionError("Free Battle label pool is not 16 exclusive tiles")
    allowed_cells = set(target_cells + suffix_cells)
    for tile_id in target_ids + suffix_ids:
        outside = [cell for cell in refs(tilemap, tile_id) if cell not in allowed_cells]
        if outside:
            raise AssertionError(f"Free Battle tile 0x{tile_id:03X} escapes target")
    tiles = bytearray(tiles_source)
    for tile_id, pattern in zip(target_ids, patterns):
        put_tile(tiles, tile_id, 0, pattern)
    blank = bytes([0xFF]) * TILE_BYTES
    for tile_id in suffix_ids:
        put_tile(tiles, tile_id, 0, blank)
    changed_ids = [
        tile_id for tile_id in target_ids + suffix_ids
        if tile_bytes(tiles_source, tile_id, 0) != tile_bytes(tiles, tile_id, 0)
    ]
    return bytes(tiles), {
        "labels": [{
            "id": label.id, "text": label.text,
            "map_rectangle": {"x": 1, "y": 1, "columns": 4, "rows": 2},
            "palette_indices": {"background": 15, "face": 14, "outline": 13},
            "outline_mode": "down", **metrics,
        }],
        "dynamic_counter_cells_preserved": [[5, 1], [6, 1], [5, 2], [6, 2]],
        "cleared_legacy_suffix_cells": [list(cell) for cell in suffix_cells],
        "map_byte_identical": True,
        "changed_tile_ids": [f"0x{tile_id:03X}" for tile_id in changed_ids],
    }


def write_outputs(output_dir: Path, payloads: dict[str, bytes]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for name, payload in sorted(payloads.items()):
        path = output_dir / name
        path.write_bytes(payload)
        result[name] = {"length": len(payload), "sha256": sha256(payload)}
    return result


def colour_preview(
    font: TTFFontSet, groups: Sequence[tuple[str, Sequence[Label]]], output: Path
) -> None:
    palettes = {
        (10, 7, None): ((0, 0, 0), (238, 221, 170), None),
        (9, 1, 11): ((85, 102, 102), (238, 221, 204), (51, 51, 51)),
        (5, 8, 2): ((85, 102, 102), (238, 221, 204), (51, 51, 51)),
        (10, 1, None): ((255, 255, 204), (0, 0, 0), None),
        (2, 11, 1): ((34, 34, 34), (238, 238, 238), (0, 0, 0)),
        (10, 15, None): ((170, 170, 170), (255, 255, 255), None),
        (12, 15, None): ((204, 204, 204), (255, 255, 255), None),
        (2, 15, None): ((204, 255, 255), (0, 0, 0), None),
        (15, 14, 13): ((255, 255, 255), (238, 238, 238), (204, 204, 204)),
    }
    rows: list[tuple[str, Image.Image]] = []
    for group_name, labels in groups:
        for label in labels:
            canvas, _ = font.raster(label)
            key = (label.background, label.face, label.outline)
            bg, face, outline = palettes.get(key, ((40, 40, 40), (240, 240, 240), (90, 90, 90)))
            image = Image.new("RGB", (label.columns * 8, label.rows * 8), bg)
            for y, row in enumerate(canvas):
                for x, value in enumerate(row):
                    if value == label.face:
                        image.putpixel((x, y), face)
                    elif label.outline is not None and value == label.outline:
                        image.putpixel((x, y), outline or bg)
            rows.append((f"{group_name}: {label.text}", image))
    width = 420
    height = 12 + sum(max(30, image.height * 3 + 8) for _, image in rows)
    montage = Image.new("RGB", (width, height), (24, 24, 24))
    draw = ImageDraw.Draw(montage)
    y = 8
    for caption, preview in rows:
        draw.text((8, y + 2), caption, fill=(238, 238, 238))
        scaled = preview.resize((preview.width * 3, preview.height * 3), Image.Resampling.NEAREST)
        montage.paste(scaled, (145, y))
        y += max(30, scaled.height + 8)
    montage.save(output, format="PNG", optimize=False)


def pet_runtime_preview(
    reference: Path, tilemap: bytes, tiles: bytes, labels: Sequence[Label], output: Path
) -> None:
    payload = reference.read_bytes()
    if sha256(payload) != PET_REFERENCE_SHA256:
        raise ValueError("PET screenshot differs from the supplied 224x144 reference")
    with Image.open(reference) as source:
        preview = source.convert("RGB")
    colours = {9: (85, 102, 102), 1: (238, 221, 204), 11: (51, 51, 51)}
    for cell_x, cell_y in sorted(cells_for(labels), key=lambda cell: (cell[1], cell[0])):
        tile_id = map_word(tilemap, cell_x, cell_y) & TILE_MASK
        pixels = unpack_tile(tile_bytes(tiles, tile_id, 1))
        for y in range(8):
            for x in range(8):
                value = pixels[y * 8 + x]
                if value not in colours:
                    raise AssertionError(f"unexpected PET label palette index {value}")
                preview.putpixel((cell_x * 8 + x, cell_y * 8 + y), colours[value])
    preview.save(output, format="PNG", optimize=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--base-rom", type=Path, default=root / "build/Rockman_EXE_N1_Battle_English_v0.10.5.wsc")
    parser.add_argument("--bn5-font", required=True, type=Path)
    parser.add_argument("--sf3-font", required=True, type=Path)
    parser.add_argument("--pet-reference", type=Path, default=root / "evidence/runtime_v0_10_4/pet_root/pet_root_runtime_27000.png")
    parser.add_argument("--output-dir", type=Path, default=root / "translation/assets")
    args = parser.parse_args()

    rom = args.base_rom.read_bytes()
    if len(rom) != ROM_SIZE or sha256(rom) != BASE_ROM_SHA256:
        raise ValueError("expected the canonical v0.10.5 ROM")
    sources = {name: guarded_span(rom, spec) for name, spec in SPANS.items()}
    source_masks = {name: guarded_span(rom, spec) for name, spec in MASK_SPANS.items()}
    font = TTFFontSet(args.bn5_font, args.sf3_font)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    keyboard_labels = (
        Label("entry_name", "ENTRY NAME", 7, 0, 14, 1, 5, 8, 64, 7, None, 0, 2, "down", 1, "sf3", 13),
        Label("register", "REGISTER", 7, 1, 14, 1, 5, 8, 56, 7, None, 0, 2, "down", 1, "sf3", 13),
        Label("low", "LOW", 23, 7, 3, 2, 10, 1, 23, 12, None, None, None, "none", 0x1D, "sf3", 15),
        Label("cap", "CAP", 23, 9, 3, 2, 10, 1, 23, 12, None, None, None, "none", 0x1D, "sf3", 15),
        Label("abc", "ABC", 23, 11, 3, 2, 10, 1, 23, 12, None, None, None, "none", 0x1D, "sf3", 15),
        Label("back", "BACK", 23, 13, 3, 2, 10, 1, 23, 12, None, None, None, "none", 0x1D, "sf3", 12),
        Label("ok", "OK!", 23, 15, 3, 2, 10, 1, 18, 12, None, None, None, "none", 0x1D, "sf3", 15),
    )
    keyboard_pool = tuple(range(0x02, 0x17)) + tuple(range(0x23, 0x3B))
    keyboard_map, keyboard_tiles, keyboard_report, keyboard_assignments = allocate_group(
        font, sources["keyboard_map"], sources["keyboard_tiles"], keyboard_labels,
        keyboard_pool, 1, protected_ids={0, 1, *range(0x17, 0x23), 0x3B},
    )
    keyboard_canvases = {label.id: font.raster(label)[0] for label in keyboard_labels}
    masks = build_keyboard_masks(keyboard_canvases, source_masks)

    banner_specs = {
        "shop": (
            (Label("shop_banner", "SHOP", 1, 1, 6, 2, 10, 7, 24, 12, None, 4, None, "none", 5, "bn5", 8),),
            (0x004, 0x007, 0x008, 0x009, 0x00A, 0x00C, 0x00D, 0x00E, 0x00F),
        ),
        "gp": (
            (Label("battlechip_gp_banner", "BATTLE CHIP GP", 1, 1, 10, 2, 10, 7, 78, 12, None, 4, None, "none", 5, "bn5", 8),),
            (0x004, 0x008, 0x009, 0x00A, 0x00B, 0x007, 0x00C, 0x006, 0x00D, 0x010, 0x011, 0x012, 0x013, 0x00E, 0x00F, 0x014, 0x0A3),
        ),
        "free": (
            (Label("free_battle_banner", "FREE BATTLE", 1, 1, 9, 2, 10, 7, 64, 12, None, 4, None, "none", 5, "bn5", 8),),
            (0x004, 0x006, 0x007, 0x008, 0x009, 0x00A, 0x00B, 0x00C, 0x00F, 0x010, 0x013, 0x014, 0x0A9),
        ),
        "host": (
            (Label("host_tourney_banner", "HOST TOURNEY", 1, 1, 10, 2, 10, 7, 72, 12, None, 4, None, "none", 5, "bn5", 8),),
            (0x004, 0x006, 0x007, 0x008, 0x009, 0x00A, 0x00B, 0x00C, 0x00D, 0x00E, 0x00F, 0x010, 0x011, 0x012),
        ),
    }
    banner_outputs: dict[str, tuple[bytes, bytes]] = {}
    banner_reports: dict[str, object] = {}
    for key, (labels, pool) in banner_specs.items():
        output_map, output_tiles, group_report, _ = allocate_group(
            font, sources[f"{key}_map"], sources[f"{key}_tiles"], labels,
            pool, 0, protected_ids={5},
        )
        banner_outputs[key] = (output_map, output_tiles)
        banner_reports[key] = group_report

    pet_labels = (
        Label("program_deck", "Program Deck", 2, 2, 8, 2, 9, 1, 64, 12, 0, 3, 11, "down", 6, "bn5", 8),
        Label("chip_folder", "Chip Folder", 2, 5, 7, 2, 9, 1, 56, 12, 0, 2, 11, "down", 6, "bn5", 8),
        Label("data_library", "Data Library", 2, 8, 8, 2, 9, 1, 64, 12, 2, 3, 11, "down", 6, "bn5", 8),
        Label("netnavi", "NetNavi", 2, 11, 5, 2, 9, 1, 40, 12, 1, 2, 11, "down", 6, "bn5", 8),
        Label("save", "Save", 2, 14, 3, 2, 9, 1, 24, 12, 1, 2, 11, "down", 6, "bn5", 8),
        Label("class", "CLASS", 16, 2, 6, 2, 9, 1, 32, 12, 8, 3, 11, "down", 6, "bn5", 8),
    )
    pet_pool = base_pool_from_targets(sources["pet_map"], pet_labels, {6})
    pet_map, pet_tiles, pet_report, _ = allocate_group(
        font, sources["pet_map"], sources["pet_tiles"], pet_labels,
        pet_pool, 1, protected_ids={0x0F, 0x10, 0x2B, 0x30, 0x31, 0x45, 0x46},
    )
    if len(pet_pool) != 63:
        raise AssertionError(f"PET audited pool changed: {len(pet_pool)} != 63")

    save_labels = (
        Label("save_header", "SAVE", 12, 0, 3, 2, 2, 11, 24, 12, 0, 3, 1, "down", 1, "bn5", 8),
        Label("save_data_library", "Data Library", 3, 3, 8, 2, 10, 15, 64, 12, 0, 4, None, "none", 0x0D, "bn5", 8),
        Label("save_battle_chips", "Battle Chips", 3, 5, 7, 2, 12, 15, 56, 12, 0, 4, None, "none", 0x0C, "bn5", 8),
        Label("save_credits", "Credits", 3, 7, 5, 2, 10, 15, 40, 12, 0, 4, None, "none", 0x0D, "bn5", 8),
    )
    save_pool = (
        0x02, 0x03, 0x05, 0x06,
        *range(0x0E, 0x14), *range(0x19, 0x1F),
        0x24, 0x25, 0x26, 0x27, 0x28, 0x3A, *range(0x2A, 0x30),
        0x31, 0x32, 0x33, 0x34, 0x36, 0x37, 0x38, 0x39,
    )
    save_map, save_tiles, save_report, _ = allocate_group(
        font, sources["save_map"], sources["save_tiles"], save_labels,
        save_pool, 0, protected_ids={1, 0x0C, 0x0D, 0x29, 0x30, 0x35},
    )

    shop_buy_labels = (
        Label("shop_one_chip", "1 Chip", 2, 1, 8, 2, 2, 15, 64, 12, 21, 3, None, "none", 5, "bn5", 8),
        Label("shop_ten_chips", "10 Chips", 2, 3, 9, 2, 2, 15, 72, 12, 15, 3, None, "none", 5, "bn5", 8),
        Label("shop_information", "Info", 2, 7, 5, 2, 2, 15, 40, 12, 11, 3, None, "none", 5, "bn5", 8),
    )
    shop_buy_pool = (
        0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x1A, 0x1C,
        0x1D, 0x1E, 0x1F, 0x20, 0x21, 0x22, 0x24, 0x26,
        0x27, 0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2D,
    )
    shop_buy_map, shop_buy_tiles, shop_buy_report, _ = allocate_group(
        font, sources["shop_buy_map"], sources["shop_buy_tiles"], shop_buy_labels,
        shop_buy_pool, 0, protected_ids={5, 0x19, 0x1B, 0x23, 0x25, 0x2E, 0x2F},
    )

    streak_tiles, streak_report = direct_streak(font, sources["streak_map"], sources["streak_tiles"])
    if sources["streak_map"] != guarded_span(rom, SPANS["streak_map"]):
        raise AssertionError("Free Battle map changed unexpectedly")

    payloads = {
        SPANS["keyboard_map"].output: keyboard_map,
        SPANS["keyboard_tiles"].output: keyboard_tiles,
        **{MASK_SPANS[name].output: payload for name, payload in masks.items()},
        SPANS["shop_map"].output: banner_outputs["shop"][0],
        SPANS["shop_tiles"].output: banner_outputs["shop"][1],
        SPANS["gp_map"].output: banner_outputs["gp"][0],
        SPANS["gp_tiles"].output: banner_outputs["gp"][1],
        SPANS["free_map"].output: banner_outputs["free"][0],
        SPANS["free_tiles"].output: banner_outputs["free"][1],
        SPANS["host_map"].output: banner_outputs["host"][0],
        SPANS["host_tiles"].output: banner_outputs["host"][1],
        SPANS["pet_map"].output: pet_map,
        SPANS["pet_tiles"].output: pet_tiles,
        SPANS["save_map"].output: save_map,
        SPANS["save_tiles"].output: save_tiles,
        SPANS["shop_buy_map"].output: shop_buy_map,
        SPANS["shop_buy_tiles"].output: shop_buy_tiles,
        SPANS["streak_tiles"].output: streak_tiles,
    }
    outputs = write_outputs(args.output_dir, payloads)

    preview_groups = (
        ("KEYBOARD", keyboard_labels),
        ("BANNERS", tuple(label for labels, _ in banner_specs.values() for label in labels)),
        ("PET ROOT", pet_labels),
        ("SAVE", save_labels),
        ("SHOP", shop_buy_labels),
        ("FREE", (Label("free_streak", "STREAK", 1, 1, 4, 2, 15, 14, 30, 12, 1, 4, 13, "down", None, "sf3", 11),)),
    )
    design_preview = args.output_dir / "ttf_static_ui_preview_v0_10_6.png"
    pet_preview = args.output_dir / "pet_root_menu_font_preview_v0_10_6.png"
    colour_preview(font, preview_groups, design_preview)
    pet_runtime_preview(args.pet_reference, pet_map, pet_tiles, pet_labels, pet_preview)
    outputs[design_preview.name] = {"length": design_preview.stat().st_size, "sha256": sha256(design_preview.read_bytes()), "dimensions": list(Image.open(design_preview).size)}
    outputs[pet_preview.name] = {"length": pet_preview.stat().st_size, "sha256": sha256(pet_preview.read_bytes()), "dimensions": list(Image.open(pet_preview).size)}

    report = {
        "status": "PASS",
        "version": VERSION,
        "native_display": [224, 144],
        "tile_format": "8x8 packed 4-bpp; high nibble is left pixel",
        "base_rom_sha256": BASE_ROM_SHA256,
        "font_sources": {
            "bn5": {
                "file": args.bn5_font.name,
                "family": TTFFontSet.SOURCES["bn5"][0],
                "sha256": BN5_TTF_SHA256,
                "assignments": ["PET root", "SHOP", "SAVE", "location banners"],
            },
            "sf3": {
                "file": args.sf3_font.name,
                "family": TTFFontSet.SOURCES["sf3"][0],
                "sha256": SF3_TTF_SHA256,
                "assignments": ["keyboard headings and controls including BACK", "Free Battle STREAK"],
            },
            "rasterization": "FreeType monochrome hinting plus deterministic native pixel-art correction",
            "pixel_art_correction": "native 1:1 masks repair broken strokes, counters and diagonals",
            "corrected_glyph_variants": [
                {"font_id": font_id, "point_size": point_size, "character": character}
                for font_id, point_size, character in sorted(font.corrected_variants)
            ],
            "corrected_glyph_variant_count": len(font.corrected_variants),
            "resampling": "none",
            "antialiasing": False,
            "minimum_interglyph_face_gap_pixels": 1,
            "minimum_interglyph_composite_gap_pixels": 1,
            "outline_policy": "one-pixel lower shadow; no rightward shadow enters the separator",
            "line_fit": "none; every completed word and line remains at its native corrected glyph size",
            "ttf_files_in_public_package": False,
        },
        "scope": {
            "static_graphical_labels": 25,
            "bottom_dialogue_boxes": "not modified",
            "dialogue_font_or_strings": "not modified",
            "dynamic_rank_E_and_credits": "not modified",
            "dynamic_shop_prices": "not modified",
            "dynamic_free_streak_counter": "not modified",
        },
        "groups": {
            "keyboard": {**keyboard_report, "selector_masks": {name: {"offset": f"0x{MASK_SPANS[name].offset:06X}", "length": 192, "file": MASK_SPANS[name].output, "sha256": sha256(payload)} for name, payload in masks.items()}},
            "location_banners": banner_reports,
            "pet_root": pet_report,
            "save": save_report,
            "shop_purchase": shop_buy_report,
            "free_streak": streak_report,
        },
        "protections": {
            "map_palette_and_priority_bits_preserved": True,
            "dialogue_assets_outside_all_spans": True,
            "pet_cursor_and_frame_tiles_protected": True,
            "pet_dynamic_values_outside_target_cells": True,
            "shop_prices_and_zenny_cells_outside_target_cells": True,
            "save_dynamic_counts_and_credits_outside_target_cells": True,
            "free_streak_counter_cells_preserved": True,
        },
        "source_spans": {
            name: {"offset": f"0x{spec.offset:06X}", "length": spec.length, "sha256": spec.sha256}
            for name, spec in SPANS.items()
        },
        "outputs": outputs,
    }
    report_path = args.output_dir / "ttf_static_ui_asset_report_v0_10_6.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "PASS",
        "version": VERSION,
        "labels": 25,
        "outputs": len(outputs),
        "report": report_path.as_posix(),
        "pet_patterns": pet_report["capacity"],
        "save_patterns": save_report["capacity"],
        "shop_patterns": shop_buy_report["capacity"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
