#!/usr/bin/env python3
"""Patch four residual Japanese location graphics in N1 Battle v0.9.

The Shop and BattleChipGP location screens load raw 32x18 BG0 maps at
CPU:0x2000 and packed 4-bpp tiles at CPU:0x8000.  This generator accepts only
the verified Rev 1 Japanese ROM, hash-guards each complete source asset, and
changes only map cells and tile IDs proven exclusive to the four labels:

* ・ショップ・       -> SHOP
* ・バトルチップGP・ -> BATTLE CHIP GP
* ヒグレヤ           -> HIGSBY
* 会場               -> VENUE

It emits complete replacement maps/tile banks, four before/after previews, a
machine-readable report, and optionally a checksum-correct QA ROM built on top
of the current English ROM.
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
ROM_SIZE = 0x400000
MAP_WIDTH = 32
TILE_BYTES = 32
TILE_MASK = 0x01FF


@dataclass(frozen=True)
class Region:
    offset: int
    length: int
    source_sha256: str


@dataclass(frozen=True)
class Screen:
    name: str
    map_region: Region
    tile_region: Region


SCREENS = {
    "shop": Screen(
        "shop",
        Region(0x041BB2, 0x0480, "c865ab0fed96a66bc02494d72411bd965b38168a010a6fa118696ec7970bbe36"),
        Region(0x0768F0, 0x1740, "d40c25251dd92512fb4fd47b6d10be9acbfff0a7031f69aa3ed0dea0b376a611"),
    ),
    "battlechip_gp": Screen(
        "battlechip_gp",
        Region(0x042034, 0x0480, "b5f0188ed5f4671193e892107d5799683ed3788604f228199ed293bbefa79cb1"),
        Region(0x078100, 0x1480, "1c100a2e11fb98b8fc046557e3dbeb1a23677537219d31d02fcfa98338b6cce8"),
    ),
}


# Compact 3x5 capitals.  Banners double rows; SHOP also doubles columns.
FONT = {
    "A": ("010", "101", "111", "101", "101"),
    "B": ("110", "101", "110", "101", "110"),
    "C": ("011", "100", "100", "100", "011"),
    "E": ("111", "100", "110", "100", "111"),
    "G": ("011", "100", "101", "101", "011"),
    "H": ("101", "101", "111", "101", "101"),
    "I": ("111", "010", "010", "010", "111"),
    "L": ("100", "100", "100", "100", "111"),
    "N": ("101", "111", "111", "111", "101"),
    "O": ("010", "101", "101", "101", "010"),
    "P": ("110", "101", "110", "100", "100"),
    "S": ("011", "100", "010", "001", "110"),
    "T": ("111", "010", "010", "010", "010"),
    "U": ("101", "101", "101", "101", "111"),
    "V": ("101", "101", "101", "101", "010"),
    "Y": ("101", "101", "010", "010", "010"),
}


# RGB444 palettes observed in clean Mesen captures at the exact location route.
PALETTES = {
    ("shop", 2): [
        (0, 255, 0), (51, 51, 51), (102, 85, 68), (102, 102, 85),
        (136, 136, 119), (170, 187, 170), (204, 221, 221), (170, 221, 238),
        (238, 255, 255), (255, 255, 255), (0, 0, 0), (170, 136, 68),
        (221, 170, 102), (255, 221, 170), (0, 255, 0), (0, 255, 0),
    ],
    ("shop", 6): [
        (0, 255, 0), (255, 255, 255), (136, 153, 153), (170, 136, 102),
        (204, 170, 136), (221, 238, 238), (17, 68, 204), (119, 136, 238),
        (204, 221, 238), (85, 68, 85), (187, 204, 187), (136, 102, 51),
        (51, 34, 153), (136, 187, 255), (119, 136, 238), (17, 170, 221),
    ],
    ("battlechip_gp", 2): [
        (0, 255, 0), (51, 51, 51), (102, 85, 68), (102, 102, 85),
        (136, 136, 119), (170, 187, 170), (204, 221, 221), (170, 221, 238),
        (238, 255, 255), (255, 255, 255), (0, 0, 0), (170, 136, 68),
        (221, 170, 102), (255, 221, 170), (0, 255, 0), (0, 255, 0),
    ],
    ("battlechip_gp", 6): [
        (0, 255, 0), (68, 85, 119), (68, 51, 51), (0, 68, 102),
        (0, 187, 221), (0, 221, 255), (17, 34, 170), (0, 119, 153),
        (17, 34, 187), (170, 221, 238), (102, 102, 153), (170, 187, 153),
        (51, 170, 68), (51, 204, 85), (51, 221, 102), (68, 255, 153),
    ],
}


SHOP_BANNER_POOL = (0x004, 0x007, 0x008, 0x009, 0x00A, 0x00C, 0x00D, 0x00E, 0x00F)
GP_BANNER_POOL = (
    0x004, 0x008, 0x009, 0x00A, 0x00B, 0x007, 0x00C, 0x006,
    0x00D, 0x010, 0x011, 0x012, 0x013, 0x00E, 0x00F, 0x014, 0x0A3,
)
HIGSBY_TILES = (0x05E, 0x05F, 0x060, 0x06A, 0x06B, 0x06C, 0x06D, 0x06E)
VENUE_TILES = (0x040, 0x041, 0x042, 0x043)


def sha256(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def region_bytes(rom: bytes, region: Region, name: str) -> bytes:
    payload = rom[region.offset:region.offset + region.length]
    if len(payload) != region.length:
        raise ValueError(f"{name}: truncated source region")
    actual = sha256(payload)
    if actual != region.source_sha256:
        raise ValueError(
            f"{name}: unexpected source SHA-256 {actual}; expected {region.source_sha256}"
        )
    return payload


def map_word(tilemap: bytes | bytearray, x: int, y: int) -> int:
    position = (y * MAP_WIDTH + x) * 2
    return int.from_bytes(tilemap[position:position + 2], "little")


def put_map_word(tilemap: bytearray, x: int, y: int, word: int) -> None:
    position = (y * MAP_WIDTH + x) * 2
    tilemap[position:position + 2] = word.to_bytes(2, "little")


def unpack_tile(tiles: bytes | bytearray, tile: int) -> list[int]:
    start = tile * TILE_BYTES
    payload = tiles[start:start + TILE_BYTES]
    if len(payload) != TILE_BYTES:
        raise ValueError(f"tile 0x{tile:03X} is outside the asset")
    return [nibble for byte in payload for nibble in (byte >> 4, byte & 0x0F)]


def pack_tile(pixels: list[int]) -> bytes:
    if len(pixels) != 64 or any(not 0 <= value <= 15 for value in pixels):
        raise ValueError("invalid 8x8 4-bpp tile")
    return bytes(
        (pixels[index] << 4) | pixels[index + 1]
        for index in range(0, 64, 2)
    )


def write_tile(tiles: bytearray, tile: int, pixels: list[int]) -> None:
    start = tile * TILE_BYTES
    tiles[start:start + TILE_BYTES] = pack_tile(pixels)


def get_tile_pixel(tiles: bytes | bytearray, tile: int, x: int, y: int) -> int:
    position = tile * TILE_BYTES + y * 4 + x // 2
    packed = tiles[position]
    return packed & 0x0F if x & 1 else packed >> 4


def set_tile_pixel(tiles: bytearray, tile: int, x: int, y: int, colour: int) -> None:
    position = tile * TILE_BYTES + y * 4 + x // 2
    if x & 1:
        tiles[position] = (tiles[position] & 0xF0) | colour
    else:
        tiles[position] = (tiles[position] & 0x0F) | (colour << 4)


def changed_indexes(before: bytes, after: bytes | bytearray) -> set[int]:
    if len(before) != len(after):
        raise ValueError("asset lengths differ")
    return {index for index, (old, new) in enumerate(zip(before, after)) if old != new}


def text_points(
    text: str,
    scale_x: int = 1,
    scale_y: int = 1,
    step_y_per_character: int = 0,
) -> tuple[list[tuple[int, int]], int, int]:
    unsupported = sorted(set(text.replace(" ", "")) - FONT.keys())
    if unsupported:
        raise ValueError(f"unsupported glyphs: {unsupported}")
    points: list[tuple[int, int]] = []
    cursor = 0
    character_index = 0
    for character in text:
        if character == " ":
            cursor += 3 * scale_x
            continue
        for gy, row in enumerate(FONT[character]):
            for gx, enabled in enumerate(row):
                if enabled != "1":
                    continue
                for dy in range(scale_y):
                    for dx in range(scale_x):
                        points.append(
                            (
                                cursor + gx * scale_x + dx,
                                gy * scale_y + dy
                                + character_index * step_y_per_character,
                            )
                        )
        cursor += 4 * scale_x
        character_index += 1
    width = cursor - scale_x
    ys = [point[1] for point in points]
    return points, width, max(ys) - min(ys) + 1


def source_tile_counts(tilemap: bytes) -> Counter[int]:
    return Counter(
        int.from_bytes(tilemap[position:position + 2], "little") & TILE_MASK
        for position in range(0, len(tilemap), 2)
    )


def assert_exclusive(
    tilemap: bytes,
    tile_ids: tuple[int, ...],
    allowed_cells: set[tuple[int, int]],
    label: str,
) -> list[dict[str, object]]:
    references: list[dict[str, object]] = []
    for position in range(0, len(tilemap), 2):
        word = int.from_bytes(tilemap[position:position + 2], "little")
        tile = word & TILE_MASK
        if tile not in tile_ids:
            continue
        index = position // 2
        x, y = index % MAP_WIDTH, index // MAP_WIDTH
        if (x, y) not in allowed_cells:
            raise AssertionError(
                f"{label}: tile 0x{tile:03X} is also referenced at ({x},{y})"
            )
        references.append({"x": x, "y": y, "tile": f"0x{tile:03X}"})
    return references


def draw_banner(
    tilemap: bytearray,
    tiles: bytearray,
    *,
    label_id: str,
    text: str,
    x: int,
    y: int,
    columns: int,
    pool: tuple[int, ...],
    background_tile: int,
    background_colour: int,
    face_colour: int,
    scale_x: int,
    scale_y: int,
) -> dict[str, object]:
    width, height = columns * 8, 16
    points, text_width, text_height = text_points(text, scale_x, scale_y)
    origin_x = (width - text_width) // 2
    origin_y = (height - text_height) // 2
    canvas = [background_colour] * (width * height)
    for px, py in points:
        canvas[(origin_y + py) * width + origin_x + px] = face_colour

    # Scrub all source Japanese glyphs in the exclusive pool first.
    for tile in pool:
        write_tile(tiles, tile, [background_colour] * 64)

    pattern_to_tile: dict[bytes, int] = {}
    pool_cursor = 0
    cell_records = []
    for tile_y in range(2):
        for tile_x in range(columns):
            pixels = [
                canvas[(tile_y * 8 + py) * width + tile_x * 8 + px]
                for py in range(8)
                for px in range(8)
            ]
            packed = pack_tile(pixels)
            if set(pixels) == {background_colour}:
                tile = background_tile
            elif packed in pattern_to_tile:
                tile = pattern_to_tile[packed]
            else:
                if pool_cursor >= len(pool):
                    raise AssertionError(
                        f"{label_id}: {len(pattern_to_tile) + 1} patterns exceed "
                        f"the {len(pool)} exclusive tiles"
                    )
                tile = pool[pool_cursor]
                pool_cursor += 1
                pattern_to_tile[packed] = tile
                write_tile(tiles, tile, pixels)
            old = map_word(tilemap, x + tile_x, y + tile_y)
            put_map_word(tilemap, x + tile_x, y + tile_y, (old & ~TILE_MASK) | tile)
            cell_records.append(
                {"x": x + tile_x, "y": y + tile_y, "tile": f"0x{tile:03X}"}
            )

    return {
        "id": label_id,
        "original": "・ショップ・" if label_id == "shop_banner" else "・バトルチップGP・",
        "translation": text,
        "kind": "packed_4bpp_bg_banner",
        "map_rectangle": {"x": x, "y": y, "width": columns, "height": 2},
        "render_pixels": {"width": width, "height": height},
        "font_scale": {"x": scale_x, "y": scale_y},
        "exclusive_tile_pool": [f"0x{tile:03X}" for tile in pool],
        "unique_rendered_patterns": len(pattern_to_tile),
        "background_tile": f"0x{background_tile:03X}",
        "final_cells": cell_records,
    }


def cell_tile(tilemap: bytes | bytearray, x: int, y: int) -> int:
    word = map_word(tilemap, x, y)
    if word & 0xC000:
        raise AssertionError(f"flipped target tile at ({x},{y}) is unsupported")
    return word & TILE_MASK


def screen_pixel(
    tilemap: bytes | bytearray, tiles: bytes | bytearray, x: int, y: int
) -> int:
    return get_tile_pixel(tiles, cell_tile(tilemap, x // 8, y // 8), x & 7, y & 7)


def set_screen_pixel(
    tilemap: bytes | bytearray,
    tiles: bytearray,
    x: int,
    y: int,
    colour: int,
    allowed_tiles: set[int],
) -> None:
    tile = cell_tile(tilemap, x // 8, y // 8)
    if tile not in allowed_tiles:
        raise AssertionError(
            f"attempt to draw through non-exclusive tile 0x{tile:03X} at ({x},{y})"
        )
    set_tile_pixel(tiles, tile, x & 7, y & 7, colour)


def patch_higsby(tilemap: bytearray, tiles: bytearray) -> dict[str, object]:
    allowed = set(HIGSBY_TILES)
    cleared = 0
    for tile in HIGSBY_TILES:
        pixels = unpack_tile(tiles, tile)
        cleared += sum(value == 5 for value in pixels)
        write_tile(tiles, tile, [12 if value == 5 else value for value in pixels])

    # The source plaque is a diagonal 40x16 strip.  Six upright 3x5 glyphs,
    # stepped upward two pixels per character, fit entirely on its purple face.
    points, width, height = text_points("HIGSBY", step_y_per_character=-2)
    origin_x, origin_y = 120 + 9, 24 + 10
    source_before_draw = bytes(tiles)
    for px, py in points:
        for dx, dy in ((0, 0), (1, 1)):
            sx, sy = origin_x + px + dx, origin_y + py + dy
            value = screen_pixel(tilemap, source_before_draw, sx, sy)
            if value != 12:
                raise AssertionError(
                    f"HIGSBY placement left plaque face at ({sx},{sy}), colour {value:X}"
                )
    for px, py in points:
        set_screen_pixel(tilemap, tiles, origin_x + px + 1, origin_y + py + 1, 2, allowed)
    for px, py in points:
        set_screen_pixel(tilemap, tiles, origin_x + px, origin_y + py, 5, allowed)
    return {
        "id": "shop_higsby_sign",
        "original": "ヒグレヤ",
        "translation": "HIGSBY",
        "kind": "diagonal_packed_4bpp_bg_sign",
        "official_name_note": "HIGSBY chosen because HIGSBY'S cannot fit the diagonal 40x16 plaque safely.",
        "screen_pixel_region": {"x": 120, "y": 24, "width": 40, "height": 16},
        "text_origin": {"x": origin_x, "y": origin_y},
        "character_step_y": -2,
        "render_size": {"width": width, "height": height},
        "face_colour_index": 5,
        "shadow_colour_index": 2,
        "cleared_source_face_pixels": cleared,
        "exclusive_tiles": [f"0x{tile:03X}" for tile in HIGSBY_TILES],
    }


def patch_venue(tilemap: bytearray, tiles: bytearray) -> dict[str, object]:
    allowed = set(VENUE_TILES)
    cleared = 0
    # x=88..89 is the cyan vertical edge of the plaque, not Japanese text.
    for sy in range(8):
        for sx in range(90, 120):
            value = screen_pixel(tilemap, tiles, sx, sy)
            if value in (4, 7):
                set_screen_pixel(tilemap, tiles, sx, sy, 8, allowed)
                cleared += 1
    points, width, height = text_points("VENUE")
    origin_x, origin_y = 88 + (32 - width) // 2, 0
    for px, py in points:
        set_screen_pixel(tilemap, tiles, origin_x + px + 1, origin_y + py + 1, 7, allowed)
    for px, py in points:
        set_screen_pixel(tilemap, tiles, origin_x + px, origin_y + py, 4, allowed)
    return {
        "id": "battlechip_gp_venue_sign",
        "original": "会場",
        "translation": "VENUE",
        "kind": "packed_4bpp_bg_sign",
        "screen_pixel_region": {"x": 88, "y": 0, "width": 32, "height": 8},
        "text_origin": {"x": origin_x, "y": origin_y},
        "render_size": {"width": width, "height": height},
        "face_colour_index": 4,
        "shadow_colour_index": 7,
        "preserved_left_plaque_edge_pixels": 16,
        "cleared_source_glyph_pixels": cleared,
        "exclusive_tiles": [f"0x{tile:03X}" for tile in VENUE_TILES],
    }


def render_region(
    screen: str,
    tilemap: bytes | bytearray,
    tiles: bytes | bytearray,
    x: int,
    y: int,
    width: int,
    height: int,
) -> Image.Image:
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    for py in range(height):
        for px in range(width):
            sx, sy = x + px, y + py
            word = map_word(tilemap, sx // 8, sy // 8)
            palette_index = (word >> 9) & 0x0F
            palette = PALETTES[(screen, palette_index)]
            colour = screen_pixel(tilemap, tiles, sx, sy)
            pixels[px, py] = palette[colour]
    return image


def comparison_preview(
    screen: str,
    original_map: bytes,
    original_tiles: bytes,
    patched_map: bytes | bytearray,
    patched_tiles: bytes | bytearray,
    rect: tuple[int, int, int, int],
    title: str,
    output: Path,
) -> None:
    before = render_region(screen, original_map, original_tiles, *rect)
    after = render_region(screen, patched_map, patched_tiles, *rect)
    scale = 8
    before = before.resize((before.width * scale, before.height * scale), Image.Resampling.NEAREST)
    after = after.resize((after.width * scale, after.height * scale), Image.Resampling.NEAREST)
    caption, gap = 28, 8
    montage = Image.new("RGB", (before.width + after.width + gap, before.height + caption), (24, 24, 24))
    montage.paste(before, (0, caption))
    montage.paste(after, (before.width + gap, caption))
    draw = ImageDraw.Draw(montage)
    draw.text((6, 7), f"{title}: SOURCE", fill="white")
    draw.text((before.width + gap + 6, 7), f"{title}: ENGLISH", fill="white")
    montage.save(output)


def allowed_tile_bytes(tile_ids: set[int]) -> set[int]:
    return {
        byte
        for tile in tile_ids
        for byte in range(tile * TILE_BYTES, (tile + 1) * TILE_BYTES)
    }


def allowed_map_bytes(cells: set[tuple[int, int]]) -> set[int]:
    result = set()
    for x, y in cells:
        position = (y * MAP_WIDTH + x) * 2
        result.update((position, position + 1))
    return result


def validate_runtime_capture(
    capture_dir: Path,
    output_dir: Path,
    maps: dict[str, bytearray],
    tiles: dict[str, bytearray],
) -> dict[str, object]:
    """Prove Mesen loaded the exact generated assets and preserve two frames."""
    evidence: dict[str, object] = {}
    for screen, frame, output_name in (
        ("shop", 26930, "location_shop_runtime_v0_9.png"),
        ("battlechip_gp", 27050, "location_battlechip_gp_runtime_v0_9.png"),
    ):
        wram_path = capture_dir / f"wram_{frame:05d}.bin"
        ports_path = capture_dir / f"ports_{frame:05d}.tsv"
        frame_path = capture_dir / f"frame_{frame:05d}.png"
        wram = wram_path.read_bytes()
        if len(wram) != 0x10000:
            raise ValueError(f"runtime {screen}: expected 65536-byte WRAM dump")
        ports = {}
        for line in ports_path.read_text(encoding="utf-8").splitlines()[1:]:
            port, value = line.split("\t")
            ports[int(port, 16)] = int(value, 16)
        expected_ports = {0x07: 0x64, 0x10: 0, 0x11: 0, 0x12: 0, 0x13: 0, 0x60: 0xE0}
        if any(ports.get(port) != value for port, value in expected_ports.items()):
            raise AssertionError(f"runtime {screen}: unexpected video ports")
        map_match = wram[0x2000:0x2000 + len(maps[screen])] == bytes(maps[screen])
        tile_match = wram[0x8000:0x8000 + len(tiles[screen])] == bytes(tiles[screen])
        if not map_match or not tile_match:
            raise AssertionError(f"runtime {screen}: generated map/tile bank was not loaded verbatim")
        output_path = output_dir / output_name
        output_path.write_bytes(frame_path.read_bytes())
        evidence[screen] = {
            "frame": frame,
            "screenshot": output_name,
            "screenshot_sha256": sha256(output_path.read_bytes()),
            "work_ram_map_cpu_span": ["0x2000", f"0x{0x2000 + len(maps[screen]):04X}"],
            "work_ram_tiles_cpu_span": ["0x8000", f"0x{0x8000 + len(tiles[screen]):04X}"],
            "generated_map_matches_runtime": map_match,
            "generated_tiles_match_runtime": tile_match,
            "ports": {f"0x{port:02X}": f"0x{ports[port]:02X}" for port in expected_ports},
        }
    return {
        "emulator": "MesenCE 2.2.1",
        "route": "clean boot; first tournament; Shop then BattleChipGP",
        "save_or_state_used": False,
        "screens": evidence,
        "all_generated_assets_loaded_verbatim": True,
    }


def build(
    source_rom: Path,
    output_dir: Path,
    base_rom: Path | None = None,
    patched_rom: Path | None = None,
    runtime_capture_dir: Path | None = None,
) -> dict[str, object]:
    source = source_rom.read_bytes()
    if len(source) != ROM_SIZE or sha256(source) != SOURCE_ROM_SHA256:
        raise ValueError(
            f"unexpected source ROM SHA-256 {sha256(source)}; expected {SOURCE_ROM_SHA256}"
        )

    original_maps = {
        name: region_bytes(source, spec.map_region, f"{name}_map")
        for name, spec in SCREENS.items()
    }
    original_tiles = {
        name: region_bytes(source, spec.tile_region, f"{name}_tiles")
        for name, spec in SCREENS.items()
    }
    maps = {name: bytearray(payload) for name, payload in original_maps.items()}
    tiles = {name: bytearray(payload) for name, payload in original_tiles.items()}

    shop_banner_cells = {(x, y) for y in (1, 2) for x in range(1, 7)}
    gp_banner_cells = {(x, y) for y in (1, 2) for x in range(1, 11)}
    higsby_cells = {(x, 3) for x in range(17, 20)} | {(x, 4) for x in range(15, 20)}
    venue_cells = {(x, 0) for x in range(11, 15)}
    alias_validation = {
        "shop_banner": assert_exclusive(original_maps["shop"], SHOP_BANNER_POOL, shop_banner_cells, "shop_banner"),
        "shop_higsby_sign": assert_exclusive(original_maps["shop"], HIGSBY_TILES, higsby_cells, "shop_higsby_sign"),
        "battlechip_gp_banner": assert_exclusive(original_maps["battlechip_gp"], GP_BANNER_POOL, gp_banner_cells, "battlechip_gp_banner"),
        "battlechip_gp_venue_sign": assert_exclusive(original_maps["battlechip_gp"], VENUE_TILES, venue_cells, "battlechip_gp_venue_sign"),
    }

    if unpack_tile(original_tiles["shop"], 0x005) != [10] * 64:
        raise AssertionError("shop banner background tile 0x005 is not solid black")
    if unpack_tile(original_tiles["battlechip_gp"], 0x005) != [10] * 64:
        raise AssertionError("GP banner background tile 0x005 is not solid black")

    labels = [
        draw_banner(
            maps["shop"], tiles["shop"], label_id="shop_banner", text="SHOP",
            x=1, y=1, columns=6, pool=SHOP_BANNER_POOL, background_tile=0x005,
            background_colour=10, face_colour=7, scale_x=2, scale_y=2,
        ),
        patch_higsby(maps["shop"], tiles["shop"]),
        draw_banner(
            maps["battlechip_gp"], tiles["battlechip_gp"],
            label_id="battlechip_gp_banner", text="BATTLE CHIP GP",
            x=1, y=1, columns=10, pool=GP_BANNER_POOL, background_tile=0x005,
            background_colour=10, face_colour=7, scale_x=1, scale_y=2,
        ),
        patch_venue(maps["battlechip_gp"], tiles["battlechip_gp"]),
    ]

    target_tiles = {
        "shop": set(SHOP_BANNER_POOL) | set(HIGSBY_TILES),
        "battlechip_gp": set(GP_BANNER_POOL) | set(VENUE_TILES),
    }
    target_cells = {
        "shop": shop_banner_cells,
        "battlechip_gp": gp_banner_cells,
    }
    changed = {"tile_banks": {}, "maps": {}}
    for name in SCREENS:
        tile_changes = changed_indexes(original_tiles[name], tiles[name])
        unexpected_tiles = tile_changes - allowed_tile_bytes(target_tiles[name])
        if unexpected_tiles:
            raise AssertionError(f"{name}: changed {len(unexpected_tiles)} bytes outside exclusive tiles")
        map_changes = changed_indexes(original_maps[name], maps[name])
        unexpected_maps = map_changes - allowed_map_bytes(target_cells[name])
        if unexpected_maps:
            raise AssertionError(f"{name}: changed {len(unexpected_maps)} bytes outside audited map cells")
        changed["tile_banks"][name] = {
            "changed_bytes": len(tile_changes),
            "changed_tiles": [f"0x{tile:03X}" for tile in sorted({index // TILE_BYTES for index in tile_changes})],
            "allowed_exclusive_tiles": [f"0x{tile:03X}" for tile in sorted(target_tiles[name])],
        }
        changed["maps"][name] = {
            "changed_bytes": len(map_changes),
            "changed_cells": [
                {"x": index // 2 % MAP_WIDTH, "y": index // 2 // MAP_WIDTH}
                for index in sorted({position // 2 * 2 for position in map_changes})
            ],
            "allowed_cells": [{"x": x, "y": y} for x, y in sorted(target_cells[name], key=lambda item: (item[1], item[0]))],
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    assets: dict[str, dict[str, object]] = {}
    for name, spec in SCREENS.items():
        for kind, payload, region, filename in (
            ("bg0_tilemap", maps[name], spec.map_region, f"location_{name}_bg0_map_v0_9.bin"),
            ("packed_4bpp_tiles", tiles[name], spec.tile_region, f"location_{name}_bg0_tiles_v0_9.bin"),
        ):
            path = output_dir / filename
            path.write_bytes(payload)
            assets[filename] = {
                "kind": kind,
                "rom_offset": f"0x{region.offset:06X}",
                "length": region.length,
                "source_sha256": region.source_sha256,
                "output_sha256": sha256(payload),
            }

    preview_specs = (
        ("shop", (8, 8, 48, 16), "SHOP", "location_shop_banner_comparison_v0_9.png"),
        ("shop", (120, 24, 40, 16), "HIGSBY", "location_shop_higsby_comparison_v0_9.png"),
        ("battlechip_gp", (8, 8, 80, 16), "BATTLE CHIP GP", "location_battlechip_gp_banner_comparison_v0_9.png"),
        ("battlechip_gp", (88, 0, 32, 8), "VENUE", "location_battlechip_gp_venue_comparison_v0_9.png"),
    )
    previews = {}
    for screen, rect, title, filename in preview_specs:
        path = output_dir / filename
        comparison_preview(
            screen, original_maps[screen], original_tiles[screen],
            maps[screen], tiles[screen], rect, title, path,
        )
        previews[filename] = {"sha256": sha256(path.read_bytes()), "rectangle": list(rect)}

    qa_report = None
    if bool(base_rom) != bool(patched_rom):
        raise ValueError("--base-rom and --patched-rom must be supplied together")
    if base_rom is not None and patched_rom is not None:
        base = bytearray(base_rom.read_bytes())
        if len(base) != ROM_SIZE:
            raise ValueError(f"QA base ROM has {len(base)} bytes; expected {ROM_SIZE}")
        base_hash = sha256(base)
        for name, spec in SCREENS.items():
            for payload, region, kind in (
                (maps[name], spec.map_region, "map"),
                (tiles[name], spec.tile_region, "tiles"),
            ):
                current = bytes(base[region.offset:region.offset + region.length])
                if sha256(current) != region.source_sha256:
                    raise ValueError(f"QA base {name} {kind} is not the audited source asset")
                base[region.offset:region.offset + region.length] = payload
        checksum = sum(base[:-2]) & 0xFFFF
        base[-2:] = checksum.to_bytes(2, "little")
        patched_rom.parent.mkdir(parents=True, exist_ok=True)
        patched_rom.write_bytes(base)
        qa_report = {
            "base_file": base_rom.name,
            "base_sha256": base_hash,
            "output_file": patched_rom.name,
            "output_sha256": sha256(base),
            "stored_checksum": f"0x{checksum:04X}",
            "calculated_checksum": f"0x{sum(base[:-2]) & 0xFFFF:04X}",
            "checksum_valid": int.from_bytes(base[-2:], "little") == (sum(base[:-2]) & 0xFFFF),
        }

    runtime_report = None
    if runtime_capture_dir is not None:
        runtime_report = validate_runtime_capture(
            runtime_capture_dir, output_dir, maps, tiles
        )

    report = {
        "generator": Path(__file__).name,
        "version": "0.9",
        "source_rom": {"path": str(source_rom), "sha256": sha256(source)},
        "format": {
            "tiles": "8x8 packed 4bpp, high nibble first, 32 bytes per tile",
            "map": "32 columns, little-endian 16-bit BG0 words; tile=word&0x1FF",
            "runtime": {
                "map_cpu_base": "0x2000",
                "tile_cpu_base": "0x8000",
                "video_mode_port_0x60": "0xE0",
                "screen_address_port_0x07": "0x64",
                "scroll": [0, 0],
            },
        },
        "labels": labels,
        "assets": assets,
        "previews": previews,
        "changed": changed,
        "source_alias_validation": {
            key: {
                "exclusive": True,
                "source_references_in_audited_cells": value,
                "references_outside_audited_cells": 0,
            }
            for key, value in alias_validation.items()
        },
        "qa_rom": qa_report,
        "runtime_validation": runtime_report,
        "validation": {
            "complete_source_assets_hash_guarded": True,
            "allocated_tiles_exclusive_to_audited_cells": True,
            "outside_target_tile_bytes_unchanged": True,
            "outside_banner_map_cells_unchanged": True,
            "higsby_and_venue_maps_unchanged": True,
            "uppercase_ascii_outputs": True,
            "labels_patched": 4,
            "encoded_text_denominator_delta": 0,
            "graphical_target_delta": 4,
            "runtime_loaded_assets_match_generated": (
                True if runtime_report is not None else None
            ),
        },
        "notes": [
            "The four labels are BG graphics, not encoded text; they add zero items to the 1552 text denominator.",
            "HIGSBY'S cannot fit the diagonal plaque without touching shared roof tiles, so the official short form HIGSBY is used.",
            "Unused Japanese banner tile records are scrubbed to the verified black background and no longer referenced.",
            "Runtime palettes are included only for deterministic previews; binary patches operate on palette indexes.",
        ],
    }
    report_path = output_dir / "location_graphics_asset_report_v0_9.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "report": str(report_path),
        "assets": {name: item["output_sha256"] for name, item in assets.items()},
        "previews": list(previews),
        "qa_rom": qa_report,
        "runtime_validation": runtime_report,
        "validation": report["validation"],
    }, indent=2))
    return report


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True, help="verified Rev 1 Japanese ROM")
    parser.add_argument(
        "--output-dir", type=Path,
        default=project_root / "translation" / "assets",
        help="asset/report/preview output directory",
    )
    parser.add_argument("--base-rom", type=Path, help="optional current English ROM for QA overlay")
    parser.add_argument("--patched-rom", type=Path, help="optional checksum-correct QA ROM output")
    parser.add_argument(
        "--runtime-capture-dir", type=Path,
        help="optional Mesen capture directory containing frames, WRAM and ports",
    )
    args = parser.parse_args()
    build(
        args.rom, args.output_dir, args.base_rom, args.patched_rom,
        args.runtime_capture_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
