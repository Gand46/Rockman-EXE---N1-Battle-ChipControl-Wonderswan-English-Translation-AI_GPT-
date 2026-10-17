#!/usr/bin/env python3
"""Patch PET states that the v0.9 route/crop did not catalogue.

The omissions live below the initial 18-row viewport, in alternate PET maps,
and in a shared BG1 card atlas.  This generator layers the new edits on the
hash-verified v0.9 banks, keeps every map word unchanged, and restricts writes
to glyph tile IDs proven exclusive across every consumer map.
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
TILE_BYTES = 32
TILE_MASK = 0x01FF


@dataclass(frozen=True)
class Region:
    offset: int
    length: int
    sha256: str


MAPS = {
    "program": Region(0x04323C, 0x0680, "1036a349ed72da5461a5cbf0f48f6787f9fce0841be862a90001fa1c50a5f2e1"),
    "program_alt": Region(0x0438BE, 0x0680, "d9e6f17908ad2da229bdf53a339e20a4e78a2641e447dd700d852d14485ef2cf"),
    "chip": Region(0x043F40, 0x0680, "20f8cc49ceec3ca227a9f3d7f1b1882b05fb51458afdab5fa0c5abe6fa4ee2c4"),
    "backpack": Region(0x0445C2, 0x0680, "782e352204c6e53684b8579668a3f1a8d6cdf9487247387bc5cb5334adec4c59"),
    "data": Region(0x044C44, 0x0680, "07ebe88de45c645949f644ff211d3b2333e02d332122d493abe0bd129d50699e"),
    "netnavi": Region(0x0452C6, 0x0480, "a9c6a387067b6b0f062e03e22f78aeb7f75f3939534b4bb0119045ddcc4278b2"),
    "netnavi_stats": Region(0x045748, 0x0480, "51d99c5d476ad281e3e454a81c24723bdd0ac4863ef36e7c0b5038d3f1b1940f"),
}

TILE_BANKS = {
    "program": Region(0x07CD20, 0x1EF0, "ef6d011c4d289338ecbd8c3bdf93da37b271295b442c066e3963ea0d1421bd97"),
    "chip": Region(0x07EC10, 0x16C0, "848239b8a63279baf5f7e2c243d97f677fa810fc6f1699f8b5aa3920fb1a707c"),
    "netnavi": Region(0x080300, 0x0D40, "48d4c0245741ce07669fc476817f6d440dbde161c0b5ce1788ce030942c2a539"),
    "no_data": Region(0x2B0A20, 0x0700, "eca42490b022105dfcb1dc761e34b933f2923f57a6439cdf22b9f2cd003f9962"),
}

V09_BASES = {
    "program": ("program_deck_live_ui_tiles_v0_9.bin", "f70420a7a48d058640bba8db6aab49ac33a8be42f5ac1c29ac6c6307c0179187"),
    "chip": ("pet_submenu_chip_library_tiles_v0_9.bin", "cedc648b7098547cbe3bbe38b96c455969144fdbb98569b8e46c84779829d45c"),
    "netnavi": ("pet_submenu_netnavi_tiles_v0_9.bin", "927a2a8c64e27e0f6f74da4a86cb67dcded3be7ea33daeed12acd7ab7be60321"),
}

OUTPUTS = {
    "program": "program_deck_live_ui_tiles_v0_10.bin",
    "chip": "pet_submenu_chip_library_tiles_v0_10.bin",
    "netnavi": "pet_submenu_netnavi_tiles_v0_10.bin",
    "no_data": "pet_no_data_card_tiles_v0_10.bin",
}

NO_DATA_TEMPLATE_A = Region(0x358790, 0x30, "c54b4554036ef509c2e28fe342d572441b783090a76b348fcbd7f02a9bdeb155")
NO_DATA_TEMPLATE_B = Region(0x358810, 0x30, "c54b4554036ef509c2e28fe342d572441b783090a76b348fcbd7f02a9bdeb155")
NO_DATA_PALETTE = Region(0x2B1128, 0x20, "2ba8381ddfa44902ad14839dd886c64d017ac05e9b68f66090b196f77df46cc0")


FONT_3X5 = {
    "A": ("010", "101", "111", "101", "101"),
    "B": ("110", "101", "110", "101", "110"),
    "C": ("011", "100", "100", "100", "011"),
    "D": ("110", "101", "101", "101", "110"),
    "E": ("111", "100", "110", "100", "111"),
    "F": ("111", "100", "110", "100", "100"),
    "G": ("011", "100", "101", "101", "011"),
    "H": ("101", "101", "111", "101", "101"),
    "I": ("111", "010", "010", "010", "111"),
    "K": ("101", "101", "110", "101", "101"),
    "L": ("100", "100", "100", "100", "111"),
    "M": ("101", "111", "111", "101", "101"),
    "N": ("101", "111", "111", "111", "101"),
    "O": ("010", "101", "101", "101", "010"),
    "P": ("110", "101", "110", "100", "100"),
    "R": ("110", "101", "110", "101", "101"),
    "S": ("011", "100", "010", "001", "110"),
    "T": ("111", "010", "010", "010", "010"),
    "U": ("101", "101", "101", "101", "111"),
    "V": ("101", "101", "101", "101", "010"),
    "Y": ("101", "101", "010", "010", "010"),
    "4": ("101", "101", "111", "001", "001"),
}

FONT_3X7 = {
    "A": ("010", "101", "101", "111", "101", "101", "101"),
    "B": ("110", "101", "101", "110", "101", "101", "110"),
    "C": ("011", "100", "100", "100", "100", "100", "011"),
    "D": ("110", "101", "101", "101", "101", "101", "110"),
    "E": ("111", "100", "100", "110", "100", "100", "111"),
    "I": ("111", "010", "010", "010", "010", "010", "111"),
    "K": ("101", "101", "110", "100", "110", "101", "101"),
    "L": ("100", "100", "100", "100", "100", "100", "111"),
    "N": ("101", "111", "111", "111", "111", "111", "101"),
    "P": ("110", "101", "101", "110", "100", "100", "100"),
    "W": ("101", "101", "101", "101", "111", "111", "101"),
}


def digest(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def source_span(rom: bytes, region: Region, label: str) -> bytes:
    payload = rom[region.offset:region.offset + region.length]
    if len(payload) != region.length or digest(payload) != region.sha256:
        raise ValueError(f"{label}: unexpected source at 0x{region.offset:06X}")
    return payload


def unpack_tile(data: bytes | bytearray, tile: int) -> list[int]:
    payload = data[tile * TILE_BYTES:(tile + 1) * TILE_BYTES]
    if len(payload) != TILE_BYTES:
        raise ValueError(f"tile 0x{tile:03X} is outside its bank")
    return [value for byte in payload for value in (byte >> 4, byte & 15)]


def pack_tile(pixels: list[int]) -> bytes:
    if len(pixels) != 64:
        raise ValueError("tile must contain 64 pixels")
    return bytes((pixels[i] << 4) | pixels[i + 1] for i in range(0, 64, 2))


def write_tile(data: bytearray, tile: int, pixels: list[int]) -> None:
    data[tile * TILE_BYTES:(tile + 1) * TILE_BYTES] = pack_tile(pixels)


def map_tile(tilemap: bytes, x: int, y: int) -> int:
    position = (y * MAP_WIDTH + x) * 2
    return int.from_bytes(tilemap[position:position + 2], "little") & TILE_MASK


def text_width(text: str, space: int) -> int:
    return sum(space if character == " " else 4 for character in text) - 1


def points(text: str, font: dict[str, tuple[str, ...]], space: int) -> tuple[list[tuple[int, int]], int]:
    unsupported = sorted(set(text.replace(" ", "")) - font.keys())
    if unsupported:
        raise ValueError(f"unsupported glyphs {unsupported} in {text!r}")
    result = []
    cursor = 0
    for character in text:
        if character == " ":
            cursor += space
            continue
        for y, row in enumerate(font[character]):
            for x, enabled in enumerate(row):
                if enabled == "1":
                    result.append((cursor + x, y))
        cursor += 4
    return result, cursor - 1


def pixels_to_tiles(bank: bytearray, tile_ids: tuple[int, ...], canvas: list[list[int]]) -> None:
    if len(canvas) != 8 or len(canvas[0]) != len(tile_ids) * 8:
        raise ValueError("one-row canvas geometry does not match tile allocation")
    for column, tile in enumerate(tile_ids):
        write_tile(
            bank,
            tile,
            [canvas[y][column * 8 + x] for y in range(8) for x in range(8)],
        )


def draw_flat_3x5(
    bank: bytearray,
    tile_ids: tuple[int, ...],
    text: str,
    background: int,
    face: int,
    *,
    space: int = 2,
) -> dict[str, object]:
    width = len(tile_ids) * 8
    glyphs, rendered_width = points(text, FONT_3X5, space)
    if rendered_width > width:
        raise ValueError(f"{text!r} needs {rendered_width}px, field has {width}px")
    canvas = [[background] * width for _ in range(8)]
    ox, oy = (width - rendered_width) // 2, 1
    for x, y in glyphs:
        canvas[oy + y][ox + x] = face
    pixels_to_tiles(bank, tile_ids, canvas)
    return {"translation": text, "width_pixels": rendered_width, "field_pixels": [width, 8]}


def draw_arrow_3x5(
    bank: bytearray,
    tile_ids: tuple[int, ...],
    text: str,
    fill: int,
    face: int,
    erase: set[int],
) -> dict[str, object]:
    width = len(tile_ids) * 8
    canvas = []
    for y in range(8):
        row = []
        for tile in tile_ids:
            source = unpack_tile(bank, tile)
            row.extend(source[y * 8:(y + 1) * 8])
        canvas.append([fill if value in erase else value for value in row])
    glyphs, rendered_width = points(text, FONT_3X5, 2)
    if rendered_width > width:
        raise ValueError(f"{text!r} needs {rendered_width}px, arrow has {width}px")
    ox, oy = (width - rendered_width) // 2, 1
    for x, y in glyphs:
        canvas[oy + y][ox + x] = face
    pixels_to_tiles(bank, tile_ids, canvas)
    return {"translation": text, "width_pixels": rendered_width, "field_pixels": [width, 8]}


def draw_backpack(bank: bytearray) -> dict[str, object]:
    top = tuple(range(0x2A, 0x31))
    bottom = tuple(range(0x37, 0x3E))
    width = 56
    glyphs, rendered_width = points("BACKPACK", FONT_3X7, 2)
    canvas = [[3] * width for _ in range(16)]
    ox = (width - rendered_width) // 2
    face_points = []
    for x, y in glyphs:
        for dy in (0, 1):
            px, py = ox + x, 1 + y * 2 + dy
            canvas[py][px] = 15
            face_points.append((px, py))
    for x, y in face_points:
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < 16 and canvas[ny][nx] == 3:
                canvas[ny][nx] = 9
    for row, ids in enumerate((top, bottom)):
        for column, tile in enumerate(ids):
            write_tile(
                bank,
                tile,
                [canvas[row * 8 + y][column * 8 + x] for y in range(8) for x in range(8)],
            )
    return {"translation": "BACKPACK", "width_pixels": rendered_width, "field_pixels": [56, 16]}


def draw_stat_letter(bank: bytearray, top: int, bottom: int, text: str) -> dict[str, object]:
    ids = (top, bottom)
    canvas = []
    for row, tile in enumerate(ids):
        source = unpack_tile(bank, tile)
        for y in range(8):
            canvas.append([8 if value == 6 else value for value in source[y * 8:(y + 1) * 8]])
    glyphs, rendered_width = points(text, FONT_3X7, 2)
    ox = (8 - rendered_width) // 2
    for x, y in glyphs:
        for dy in (0, 1):
            py = 1 + y * 2 + dy
            if canvas[py][ox + x] == 8:
                canvas[py][ox + x] = 6
    for row, tile in enumerate(ids):
        write_tile(bank, tile, [canvas[row * 8 + y][x] for y in range(8) for x in range(8)])
    return {"translation": text, "width_pixels": rendered_width, "field_pixels": [8, 16]}


def draw_no_data_card(bank: bytearray) -> dict[str, object]:
    width, height = 64, 24
    canvas = [[1] * width for _ in range(height)]
    records = []
    for text, face_y in (("NO CHIP", 1), ("IS", 9), ("SELECTED", 17)):
        glyphs, rendered_width = points(text, FONT_3X5, 2)
        ox = (width - rendered_width) // 2
        face_points = [(ox + x, face_y + y) for x, y in glyphs]
        for x, y in face_points:
            if x + 1 < width and y + 1 < height and canvas[y + 1][x + 1] == 1:
                canvas[y + 1][x + 1] = 2
        for x, y in face_points:
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < width and 0 <= ny < height and canvas[ny][nx] == 1:
                    canvas[ny][nx] = 14
        for x, y in face_points:
            canvas[y][x] = 3
        records.append({"text": text, "width_pixels": rendered_width, "face_y": face_y})
    for row in range(3):
        for column in range(8):
            # This raw atlas begins at hardware tile ID 0x140, so the
            # visible 0x158..0x16F card occupies local indices 0x18..0x2F.
            tile = 0x18 + row * 8 + column
            write_tile(
                bank,
                tile,
                [canvas[row * 8 + y][column * 8 + x] for y in range(8) for x in range(8)],
            )
    return {"translation_lines": records, "field_pixels": [64, 24], "dynamic_consumers": 3}


def expected_cells(tilemap: bytes, cells: dict[tuple[int, int], int], label: str) -> None:
    for cell, tile in cells.items():
        actual = map_tile(tilemap, *cell)
        if actual != tile:
            raise AssertionError(f"{label}: cell {cell} uses 0x{actual:03X}, expected 0x{tile:03X}")


def assert_pool_aliases(
    maps: dict[str, bytes],
    pool: set[int],
    allowed: dict[str, set[tuple[int, int]]],
    label: str,
) -> list[dict[str, object]]:
    refs = []
    for name, tilemap in maps.items():
        for position in range(0, len(tilemap), 2):
            tile = int.from_bytes(tilemap[position:position + 2], "little") & TILE_MASK
            if tile not in pool:
                continue
            word = position // 2
            cell = (word % MAP_WIDTH, word // MAP_WIDTH)
            if cell not in allowed.get(name, set()):
                raise AssertionError(f"{label}: tile 0x{tile:03X} aliases {name} cell {cell}")
            refs.append({"map": name, "x": cell[0], "y": cell[1], "tile": f"0x{tile:03X}"})
    return refs


def changed(before: bytes, after: bytes | bytearray) -> set[int]:
    return {index for index, (old, new) in enumerate(zip(before, after)) if old != new}


def render_crop(tilemap: bytes, tiles: bytes | bytearray, crop: tuple[int, int, int, int]) -> Image.Image:
    x0, y0, columns, rows = crop
    image = Image.new("RGB", (columns * 8, rows * 8), "black")
    output = image.load()
    for py in range(rows * 8):
        for px in range(columns * 8):
            tile = map_tile(tilemap, x0 + px // 8, y0 + py // 8)
            value = unpack_tile(tiles, tile)[(py & 7) * 8 + (px & 7)]
            shade = value * 17
            output[px, py] = (shade, shade, shade)
    return image


def comparison(
    title: str,
    tilemap: bytes,
    before_tiles: bytes,
    after_tiles: bytes,
    crop: tuple[int, int, int, int],
    output: Path,
) -> None:
    before = render_crop(tilemap, before_tiles, crop)
    after = render_crop(tilemap, after_tiles, crop)
    scale = 3
    before = before.resize((before.width * scale, before.height * scale), Image.Resampling.NEAREST)
    after = after.resize(before.size, Image.Resampling.NEAREST)
    gap, caption = 8, 28
    canvas = Image.new("RGB", (before.width * 2 + gap, before.height + caption), (24, 24, 24))
    canvas.paste(before, (0, caption))
    canvas.paste(after, (before.width + gap, caption))
    draw = ImageDraw.Draw(canvas)
    draw.text((7, 7), f"{title}: v0.9", fill="white")
    draw.text((before.width + gap + 7, 7), f"{title}: ENGLISH v0.10", fill="white")
    canvas.save(output)


def card_preview(before: bytes, after: bytes, output: Path) -> None:
    def render(bank: bytes) -> Image.Image:
        image = Image.new("RGB", (64, 24), "black")
        palette = [
            (0, 0, 0), (68, 68, 136), (170, 170, 187), (204, 238, 255),
            (34, 255, 255), (255, 0, 255), (255, 0, 255), (255, 0, 255),
            (255, 0, 255), (255, 0, 238), (255, 0, 255), (255, 0, 255),
            (255, 0, 238), (255, 0, 255), (85, 85, 153), (68, 68, 136),
        ]
        pixels = image.load()
        for y in range(24):
            for x in range(64):
                tile = 0x18 + (y // 8) * 8 + x // 8
                value = unpack_tile(bank, tile)[(y & 7) * 8 + (x & 7)]
                pixels[x, y] = palette[value]
        return image
    left, right = render(before), render(after)
    scale = 5
    left = left.resize((320, 120), Image.Resampling.NEAREST)
    right = right.resize((320, 120), Image.Resampling.NEAREST)
    canvas = Image.new("RGB", (648, 148), (24, 24, 24))
    canvas.paste(left, (0, 28)); canvas.paste(right, (328, 28))
    draw = ImageDraw.Draw(canvas)
    draw.text((7, 7), "NO DATA CARD: v0.9", fill="white")
    draw.text((335, 7), "NO DATA CARD: ENGLISH v0.10", fill="white")
    canvas.save(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_rom", type=Path)
    parser.add_argument("asset_dir", type=Path, help="v0.9 input assets and v0.10 output directory")
    args = parser.parse_args()
    rom = args.source_rom.read_bytes()
    if len(rom) != ROM_SIZE or digest(rom) != SOURCE_SHA256:
        raise ValueError("unsupported source ROM; expected verified Japanese Rev 1")
    args.asset_dir.mkdir(parents=True, exist_ok=True)

    maps = {name: source_span(rom, region, f"map {name}") for name, region in MAPS.items()}
    source_banks = {name: source_span(rom, region, f"tiles {name}") for name, region in TILE_BANKS.items()}
    source_span(rom, NO_DATA_TEMPLATE_A, "NO DATA template A")
    source_span(rom, NO_DATA_TEMPLATE_B, "NO DATA template B")
    source_span(rom, NO_DATA_PALETTE, "NO DATA palette")

    bases: dict[str, bytes] = {}
    for bank, (filename, expected) in V09_BASES.items():
        payload = (args.asset_dir / filename).read_bytes()
        if len(payload) != TILE_BANKS[bank].length or digest(payload) != expected:
            raise ValueError(f"{bank}: unexpected v0.9 base asset")
        bases[bank] = payload
    bases["no_data"] = source_banks["no_data"]
    patched = {name: bytearray(payload) for name, payload in bases.items()}

    # Exact source map orders; maps are deliberately never rewritten.
    expected_cells(maps["program"], {(x, 24): tile for x, tile in zip(range(2, 9), range(0xE2, 0xE9))}, "DECK FILE")
    expected_cells(maps["program"], {(x, 24): tile for x, tile in zip(range(11, 18), (0xCE, 0xCF, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8))}, "NAVIGATION")
    expected_cells(maps["program"], {(x, 24): tile for x, tile in zip(range(20, 28), range(0xEB, 0xF3))}, "NAVI CODE")
    expected_cells(maps["program_alt"], {(x, 1): tile for x, tile in zip(range(1, 8), range(0x10, 0x17))}, "PROGRAM DECK Y4")
    expected_cells(maps["backpack"], {(x, 1): tile for x, tile in zip(range(1, 8), (0x69, 0x47, 0x48, 0x49, 0x4A, 0x6A, 0x6B))}, "CHIP FOLDER Y4")
    expected_cells(maps["backpack"], {(x, y): tile for y, row in ((0, range(0x2A, 0x31)), (1, range(0x37, 0x3E))) for x, tile in zip(range(11, 18), row)}, "BACKPACK")
    expected_cells(maps["netnavi_stats"], {(x, 1): tile for x, tile in zip(range(1, 6), range(0x0F, 0x14))}, "MENU Y4")
    expected_cells(maps["netnavi_stats"], {(17, 7): 0x65, (17, 8): 0x67, (22, 7): 0x66, (22, 8): 0x68}, "W/L")

    sort_cells = {(x, 24): tile for x, tile in zip(range(4, 13), range(0x97, 0xA0))}
    sort_cells.update({(x, 24): tile for x, tile in zip(range(23, 27), range(0xB1, 0xB5))})
    expected_cells(maps["chip"], sort_cells, "chip sort")
    expected_cells(maps["backpack"], sort_cells, "backpack sort")

    alias_reports = {}
    alias_reports["program_toolbar"] = assert_pool_aliases(
        {"program": maps["program"]},
        set(range(0xE2, 0xE9)) | {0xCE, 0xCF, *range(0xD4, 0xD9), *range(0xEB, 0xF3)},
        {"program": {(x, 24) for x in (*range(2, 9), *range(11, 18), *range(20, 28))}},
        "program toolbar",
    )
    shared_chip_maps = {name: maps[name] for name in ("program_alt", "chip", "backpack", "data")}
    program_arrow = set(range(0x10, 0x17))
    backpack_arrow = {0x69, 0x47, 0x48, 0x49, 0x4A, 0x6A, 0x6B}
    backpack_header = set(range(0x2A, 0x31)) | set(range(0x37, 0x3E))
    sort_pool = set(range(0x97, 0xA0)) | set(range(0xB1, 0xB5))
    alias_reports["program_arrow"] = assert_pool_aliases(shared_chip_maps, program_arrow, {"program_alt": {(x, 1) for x in range(1, 8)}}, "program arrow")
    alias_reports["backpack_arrow"] = assert_pool_aliases(shared_chip_maps, backpack_arrow, {"backpack": {(x, 1) for x in range(1, 8)}}, "backpack arrow")
    alias_reports["backpack_header"] = assert_pool_aliases(shared_chip_maps, backpack_header, {"backpack": {(x, y) for y in (0, 1) for x in range(11, 18)}}, "backpack header")
    alias_reports["sort_bar"] = assert_pool_aliases(shared_chip_maps, sort_pool, {name: {(x, 24) for x in (*range(4, 13), *range(23, 27))} for name in ("program_alt", "chip", "backpack")}, "sort bar")
    net_pool = set(range(0x0F, 0x14)) | {0x65, 0x66, 0x67, 0x68}
    alias_reports["netnavi_stats"] = assert_pool_aliases(
        {name: maps[name] for name in ("netnavi", "netnavi_stats")},
        net_pool,
        {"netnavi_stats": {(x, 1) for x in range(1, 6)} | {(17, 7), (17, 8), (22, 7), (22, 8)}},
        "NetNavi stats",
    )

    labels = []
    labels.append({"id": "program_deck_file", **draw_flat_3x5(patched["program"], tuple(range(0xE2, 0xE9)), "DECK FILE", 3, 9)})
    labels.append({"id": "program_navigation", **draw_flat_3x5(patched["program"], (0xCE, 0xCF, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8), "NAVIGATION", 3, 9)})
    # Preserve the source-zero outer cell F2; it is a boundary, not a glyph.
    labels.append({"id": "program_navicode", **draw_flat_3x5(patched["program"], tuple(range(0xEB, 0xF2)), "NAVI CODE", 3, 9)})
    labels.append({"id": "program_alt_button", **draw_arrow_3x5(patched["chip"], tuple(range(0x10, 0x17)), "PROGRAM DECK Y4", 6, 2, {2, 4})})
    labels.append({"id": "chip_sort_name_attack", **draw_flat_3x5(patched["chip"], tuple(range(0x97, 0xA0)), "NAME ATK", 3, 9)})
    labels.append({"id": "chip_sort_type", **draw_flat_3x5(patched["chip"], tuple(range(0xB1, 0xB5)), "TYPE", 3, 9)})
    labels.append({"id": "backpack_alt_button", **draw_arrow_3x5(patched["chip"], (0x69, 0x47, 0x48, 0x49, 0x4A, 0x6A, 0x6B), "CHIP FOLDER Y4", 6, 2, {2, 4})})
    labels.append({"id": "backpack_header", **draw_backpack(patched["chip"])})
    labels.append({"id": "netnavi_menu_button", **draw_arrow_3x5(patched["netnavi"], tuple(range(0x0F, 0x14)), "MENU Y4", 12, 9, {9, 14})})
    labels.append({"id": "netnavi_wins", **draw_stat_letter(patched["netnavi"], 0x65, 0x67, "W")})
    labels.append({"id": "netnavi_losses", **draw_stat_letter(patched["netnavi"], 0x66, 0x68, "L")})
    no_data = draw_no_data_card(patched["no_data"])
    labels.append({"id": "no_chip_selected_card", **no_data})

    allowed = {
        "program": set(range(0xE2, 0xE9)) | {0xCE, 0xCF, *range(0xD4, 0xD9), *range(0xEB, 0xF2)},
        "chip": program_arrow | backpack_arrow | backpack_header | sort_pool,
        "netnavi": net_pool,
        "no_data": set(range(0x18, 0x30)),
    }
    change_reports = {}
    output_hashes = {}
    for bank, payload in patched.items():
        differences = changed(bases[bank], payload)
        allowed_bytes = {byte for tile in allowed[bank] for byte in range(tile * TILE_BYTES, (tile + 1) * TILE_BYTES)}
        if differences - allowed_bytes:
            raise AssertionError(f"{bank}: changed outside audited v0.10 tile pool")
        output = args.asset_dir / OUTPUTS[bank]
        output.write_bytes(payload)
        output_hashes[output.name] = digest(output.read_bytes())
        change_reports[bank] = {
            "changed_bytes_from_v0_9": len(differences),
            "changed_tile_ids": [f"0x{tile:03X}" for tile in sorted({index // TILE_BYTES for index in differences})],
            "outside_allowlist": 0,
            "output": output.name,
            "output_sha256": output_hashes[output.name],
        }

    preview_specs = (
        ("pet_program_toolbar", maps["program"], bases["program"], bytes(patched["program"]), (0, 23, 28, 3)),
        ("pet_program_alt", maps["program_alt"], bases["chip"], bytes(patched["chip"]), (0, 0, 28, 18)),
        ("pet_chip_sort", maps["chip"], bases["chip"], bytes(patched["chip"]), (0, 23, 28, 3)),
        ("pet_backpack", maps["backpack"], bases["chip"], bytes(patched["chip"]), (0, 0, 28, 18)),
        ("pet_netnavi_stats", maps["netnavi_stats"], bases["netnavi"], bytes(patched["netnavi"]), (0, 0, 28, 18)),
    )
    previews = []
    for title, tilemap, before, after, crop in preview_specs:
        filename = f"{title}_comparison_v0_10.png"
        path = args.asset_dir / filename
        comparison(title, tilemap, before, after, crop, path)
        output_hashes[filename] = digest(path.read_bytes())
        previews.append(filename)
    card_name = "pet_no_data_card_comparison_v0_10.png"
    card_path = args.asset_dir / card_name
    card_preview(bases["no_data"], bytes(patched["no_data"]), card_path)
    output_hashes[card_name] = digest(card_path.read_bytes())
    previews.append(card_name)

    report = {
        "format": "n1-pet-runtime-remaining-assets-v0.10",
        "status": "PASS",
        "native_display": [224, 144],
        "scroll_map_rows": 26,
        "source_rom_sha256": SOURCE_SHA256,
        "maps_hash_guarded_and_byte_identical": {
            name: {"offset": f"0x{region.offset:06X}", "length": region.length, "sha256": region.sha256}
            for name, region in MAPS.items()
        },
        "tile_banks": {
            name: {
                "offset": f"0x{region.offset:06X}",
                "length": region.length,
                "source_sha256": region.sha256,
                **change_reports[name],
            }
            for name, region in TILE_BANKS.items()
        },
        "no_data_templates_byte_identical": [
            {"offset": f"0x{region.offset:06X}", "length": region.length, "sha256": region.sha256}
            for region in (NO_DATA_TEMPLATE_A, NO_DATA_TEMPLATE_B)
        ],
        "no_data_palette_byte_identical": {
            "offset": f"0x{NO_DATA_PALETTE.offset:06X}",
            "length": NO_DATA_PALETTE.length,
            "sha256": NO_DATA_PALETTE.sha256,
        },
        "labels": labels,
        "graphical_occurrences": 18,
        "occurrence_note": "13 fixed UI occurrences, two sort labels reused in three maps, and one shared NO CHIP card visible in three PET consumers",
        "alias_checks": {name: {"references": refs, "outside_targets": 0} for name, refs in alias_reports.items()},
        "maps_changed": 0,
        "outputs": output_hashes,
        "previews": previews,
    }
    report_path = args.asset_dir / "pet_runtime_remaining_asset_report_v0_10.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
