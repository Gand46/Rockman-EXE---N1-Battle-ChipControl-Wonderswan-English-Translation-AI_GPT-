#!/usr/bin/env python3
"""Build the runtime graphics corrections requested for N1 Battle v0.10.3.

The fixes are deliberately narrow:

* replace the three Japanese ENTRY NAME selector OBJ masks with masks derived
  from the already-reviewed English LOW/CAP/ABC BG labels;
* repair the six wrong-palette CAPACITY cells in Program Deck;
* redraw the cramped Program Deck order and help labels in a native 5x7 font.

Original Program Deck direction arrows and chip-type pictograms are protected;
they are functional artwork, not untranslated characters or patch artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw


SOURCE_ROM_SHA256 = "4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed"
ROM_SIZE = 0x400000
TILE_BYTES = 32
MAP_WIDTH = 32

KEYBOARD_TILES_SHA256 = "516f83ee3eba54416785d81d836e697bfb8036646f06377217ae6994c72a631e"
KEYBOARD_MASKS = {
    "low": {
        "offset": 0x19A47E,
        "source_sha256": "696d5b34e81db76ce71bc7ab0ce254488c519f9371c0b7eac8a53dec7d7a9a9b",
        "output_sha256": "2d4b9752c5f396dadfd2f05e5ce4182ce7a750c7909d40e841452f1b09a477eb",
        "top": (0x23, 0x24, 0x25), "bottom": (0x26, 0x27, 0x28),
    },
    "cap": {
        "offset": 0x19A55C,
        "source_sha256": "0b8bbe3b8ae8002ccb22f0a43c4c143fefcb2c25b847028c77eec944251ea36e",
        "output_sha256": "b1388a7b66111d0f810a1d2b2611a764e4aa5f7178858cb9dc272c3c2f60d078",
        "top": (0x10, 0x11, 0x12), "bottom": (0x13, 0x14, 0x15),
    },
    "abc": {
        "offset": 0x19A63A,
        "source_sha256": "b51f428801747eb8baefa7423113abad51ef9e4d23bb42a5ce57562ebe56a3ec",
        "output_sha256": "57ee607495b834236e0212f0bd22aa132c57a8550f4dba85f4b8cb0ad649ded9",
        "top": (0x2B, 0x2C, 0x1D), "bottom": (0x2D, 0x2E, 0x1D),
    },
}

BASE_ASSETS = {
    "stats_map": ("program_deck_manual_stats_bg0_map_v0_8.bin", "e2fa65ba7ad1ea563579c74327bfe1699f206ee300449a4e8101e9cc13e289f0"),
    "order_map": ("program_deck_manual_order_bg0_map_v0_8.bin", "2c92e8bdd95173beb73dac3176fd804978b9cc66f97b7e3fcf450c65b6e1d28e"),
    "tool_map": ("program_deck_manual_tool_bg0_map_v0_8.bin", "f9548d24d175f3ec997ba93bc5e951c264adf5f895221c6a8539fcb4942d96e0"),
    "manual_tiles": ("program_deck_manual_internal_tiles_v0_9.bin", "a31d6fbc83aa517c661bb96f8f3e2bab210faa2e5f6fe59c891deb05d5377a8a"),
}

OUTPUT_HASHES = {
    "stats_map": "3dee6f7defb7d4b76c9223660140d861a4c2b0bdb1fffeaa7c9062d327eb4996",
    "order_map": "f5c00161868770672e34e8daa3eedd38c3ac8c05403ba8c962b19a91dd4a6057",
    "tool_map": "de316b72749a1c08d787adcdcf35f0b8fb1ab2e5fa09ebcafd142687d0df5740",
    "manual_tiles": "e73fb7e716cafeea1f5c5c707621cf6749694ea982a446b5a4e1ddea8d83df11",
}

OUTPUT_FILES = {
    "stats_map": "program_deck_manual_stats_bg0_map_v0_10_3.bin",
    "order_map": "program_deck_manual_order_bg0_map_v0_10_3.bin",
    "tool_map": "program_deck_manual_tool_bg0_map_v0_10_3.bin",
    "manual_tiles": "program_deck_manual_internal_tiles_v0_10_3.bin",
}

# Relative to the 0x0ACA20 Program Deck manual atlas.
PAGE_BASES = {"stats": 0x1150, "order": 0x3990, "tool": 0x4BE0}

# Clear 5x7 capitals, one native pixel per source pixel.
FONT = {
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
}


def sha256(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def unpack_tile(payload: bytes | bytearray) -> list[int]:
    if len(payload) != TILE_BYTES:
        raise ValueError("a tile must contain 32 bytes")
    return [value for byte in payload for value in (byte >> 4, byte & 15)]


def pack_tile(pixels: list[int]) -> bytes:
    if len(pixels) != 64 or any(not 0 <= value <= 15 for value in pixels):
        raise ValueError("invalid 8x8 4-bpp tile")
    return bytes((pixels[i] << 4) | pixels[i + 1] for i in range(0, 64, 2))


def map_word(tilemap: bytes | bytearray, x: int, y: int) -> int:
    offset = (y * MAP_WIDTH + x) * 2
    return int.from_bytes(tilemap[offset:offset + 2], "little")


def put_map_word(tilemap: bytearray, x: int, y: int, word: int) -> None:
    offset = (y * MAP_WIDTH + x) * 2
    tilemap[offset:offset + 2] = word.to_bytes(2, "little")


def set_palette(tilemap: bytearray, x: int, y: int, palette: int) -> None:
    word = map_word(tilemap, x, y)
    put_map_word(tilemap, x, y, (word & ~0x1E00) | (palette << 9))


def text_width(text: str) -> int:
    return sum(4 if character == " " else 6 for character in text) - 1


def draw_text(canvas: list[int], width: int, x: int, y: int, text: str, ink: int) -> None:
    cursor = x
    for character in text:
        if character != " ":
            if character not in FONT:
                raise ValueError(f"missing 5x7 glyph {character!r}")
            for glyph_y, row in enumerate(FONT[character]):
                for glyph_x, value in enumerate(row):
                    if value == "1":
                        canvas[(y + glyph_y) * width + cursor + glyph_x] = ink
        cursor += 4 if character == " " else 6


def label_canvas(width: int, height: int, lines: tuple[tuple[str, int], ...], background: int, ink: int) -> list[int]:
    canvas = [background] * (width * height)
    for text, y in lines:
        x = (width - text_width(text)) // 2
        draw_text(canvas, width, x, y, text, ink)
    return canvas


def tile_patterns(canvas: list[int], width: int, height: int) -> list[bytes]:
    if width % 8 or height % 8 or len(canvas) != width * height:
        raise ValueError("label canvas is not tile-aligned")
    patterns = []
    for cell_y in range(height // 8):
        for cell_x in range(width // 8):
            patterns.append(pack_tile([
                canvas[(cell_y * 8 + y) * width + cell_x * 8 + x]
                for y in range(8) for x in range(8)
            ]))
    return patterns


def write_direct(
    atlas: bytearray, page_base: int, tilemap: bytearray,
    cell_x: int, cell_y: int, columns: int, rows: int,
    patterns: list[bytes], tile_ids: tuple[int, ...], palette: int,
) -> None:
    if len(patterns) != columns * rows or len(tile_ids) != len(patterns):
        raise ValueError("direct label pool does not match its rectangle")
    for index, (pattern, tile) in enumerate(zip(patterns, tile_ids)):
        start = page_base + tile * TILE_BYTES
        atlas[start:start + TILE_BYTES] = pattern
        x = cell_x + index % columns
        y = cell_y + index // columns
        word = map_word(tilemap, x, y)
        put_map_word(tilemap, x, y, (word & ~0x1FFF) | (palette << 9) | tile)


def build_keyboard_masks(rom: bytes, keyboard_tiles: bytes) -> dict[str, bytes]:
    outputs: dict[str, bytes] = {}
    for name, spec in KEYBOARD_MASKS.items():
        offset = int(spec["offset"])
        source = rom[offset:offset + 0xC0]
        if sha256(source) != spec["source_sha256"]:
            raise ValueError(f"{name}: unexpected source OBJ mask")
        top = tuple(spec["top"])
        bottom = tuple(spec["bottom"])
        # The game's six-sprite DMA order is right column, then left/centre.
        order = (top[2], bottom[2], top[0], top[1], bottom[0], bottom[1])
        tiles = []
        for tile_id in order:
            start = (tile_id - 1) * TILE_BYTES
            bg_pixels = unpack_tile(keyboard_tiles[start:start + TILE_BYTES])
            # OBJ colour 0 is transparent; colour 7 is the cyan highlight.
            tiles.append(pack_tile([0 if pixel == 1 else 7 for pixel in bg_pixels]))
        output = b"".join(tiles)
        if len(output) != 0xC0 or sha256(output) != spec["output_sha256"]:
            raise AssertionError(f"{name}: generated selector differs from reviewed mask")
        outputs[name] = output
    return outputs


def build_program_assets(base: dict[str, bytes]) -> dict[str, bytes]:
    stats = bytearray(base["stats_map"])
    order = bytearray(base["order_map"])
    tool = bytearray(base["tool_map"])
    atlas = bytearray(base["manual_tiles"])

    for y in (6, 7):
        for x in (12, 13, 14):
            set_palette(stats, x, y, 2)

    top = label_canvas(48, 24, (("LIKELY", 3), ("CHIPS", 14)), 2, 15)
    write_direct(
        atlas, PAGE_BASES["order"], order, 3, 0, 6, 3,
        tile_patterns(top, 48, 24),
        tuple(range(0x04, 0x08)) + tuple(range(0x10, 0x1B)) + tuple(range(0x23, 0x26)),
        3,
    )

    left_full = label_canvas(56, 16, (("2 CHIPS", 0), ("LEFT", 9)), 2, 13)
    left = [left_full[y * 56 + x] for y in range(16) for x in range(8, 48)]
    write_direct(
        atlas, PAGE_BASES["order"], order, 3, 5, 5, 2,
        tile_patterns(left, 40, 16),
        tuple(range(0x26, 0x2D)) + (0x2E, 0x4F, 0x50), 3,
    )

    right = label_canvas(48, 16, (("MIDDLE", 0), ("1 CHIP", 9)), 2, 13)
    right_patterns = tile_patterns(right, 48, 16)
    right_tiles = (0x51, 0x52, 0x53, 0x54, 0x55, 0x56, 0x03, 0x62, 0x63, 0x64, 0x65, 0x03)
    write_direct(
        atlas, PAGE_BASES["order"], order, 22, 4, 6, 2,
        right_patterns, right_tiles, 3,
    )
    # Tile 003 is the page's shared uniform background and must stay intact.
    blank = pack_tile([2] * 64)
    if right_patterns[6] != blank or right_patterns[11] != blank:
        raise AssertionError("right label no longer has the two protected blank cells")

    prompt = label_canvas(64, 16, (("PRESS START", 0), ("DECK INFO", 9)), 14, 15)
    prompt_tiles = tuple(range(0x34, 0x3C)) + tuple(range(0x3D, 0x45))
    write_direct(
        atlas, PAGE_BASES["tool"], tool, 4, 4, 8, 2,
        tile_patterns(prompt, 64, 16), prompt_tiles, 3,
    )
    for y in (3, 6):
        for x in range(4, 12):
            word = map_word(tool, x, y)
            put_map_word(tool, x, y, (word & ~0x1FFF) | (3 << 9) | 0x33)

    outputs = {
        "stats_map": bytes(stats), "order_map": bytes(order),
        "tool_map": bytes(tool), "manual_tiles": bytes(atlas),
    }
    for name, payload in outputs.items():
        if sha256(payload) != OUTPUT_HASHES[name]:
            raise AssertionError(f"{name}: output differs from reviewed Mesen prototype")
    return outputs


PROGRAM_PALETTES = {
    "stats": {
        0: ("000", "ddd", "ffc", "000", "edc", "000", "ffe", "000", "ffe", "00f", "ffe", "f00", "fff", "5f2", "aba", "788"),
        2: ("000", "222", "333", "545", "566", "858", "c50", "788", "4c6", "f80", "aba", "fb0", "edc", "ff8", "ffd", "000"),
        3: ("000", "545", "333", "143", "263", "840", "566", "3a5", "a71", "788", "4d6", "db1", "7f9", "ed3", "87a", "858"),
        4: ("000", "545", "445", "566", "566", "667", "c50", "f80", "fb0", "ed8", "fec", "333", "000", "000", "000", "000"),
    },
    "order": {
        0: ("000", "ddd", "ffc", "000", "edc", "000", "ffe", "000", "ffe", "00f", "ffe", "f00", "fff", "5f2", "aba", "788"),
        2: ("000", "545", "545", "647", "566", "858", "87a", "888", "baa", "ed8", "edc", "fec", "121", "ff8", "000", "000"),
        3: ("000", "ec0", "121", "445", "667", "872", "c50", "886", "f80", "aaa", "fb0", "ed8", "ff0", "ff8", "fed", "ffd"),
    },
    "tool": {
        0: ("000", "ddd", "ffc", "000", "edc", "000", "ffe", "000", "ffe", "00f", "ffe", "f00", "fff", "5f2", "aba", "788"),
        2: ("000", "545", "647", "858", "87a", "fc0", "ff8", "ffe", "000", "000", "000", "000", "000", "000", "000", "000"),
        3: ("000", "333", "143", "263", "566", "a50", "3a4", "788", "f80", "5e3", "aba", "ec2", "ddd", "edc", "ffd", "000"),
    },
}


def rgb444(text: str) -> tuple[int, int, int]:
    return tuple(int(character, 16) * 17 for character in text)  # type: ignore[return-value]


def render_program_page(tilemap: bytes, atlas: bytes, page: str) -> Image.Image:
    image = Image.new("RGB", (224, 80))
    pixels = image.load()
    base = PAGE_BASES[page]
    for y in range(80):
        for x in range(224):
            word = map_word(tilemap, x // 8, y // 8)
            tile = word & 0x1FF
            palette = (word >> 9) & 0x0F
            tile_x = 7 - (x & 7) if word & 0x4000 else x & 7
            tile_y = 7 - (y & 7) if word & 0x8000 else y & 7
            start = base + tile * TILE_BYTES
            # The final tool-border tile is supplied by the following ROM
            # resource at runtime and is outside this atlas span.  It is not
            # part of any edited label, so the asset-only preview may render
            # that protected cell as transparent colour 0.
            if start + TILE_BYTES > len(atlas):
                value = 0
            else:
                value = unpack_tile(atlas[start:start + TILE_BYTES])[tile_y * 8 + tile_x]
            pixels[x, y] = rgb444(PROGRAM_PALETTES[page][palette][value])
    return image


def create_program_preview(outputs: dict[str, bytes], path: Path) -> None:
    pages = [
        render_program_page(outputs["stats_map"], outputs["manual_tiles"], "stats"),
        render_program_page(outputs["order_map"], outputs["manual_tiles"], "order"),
        render_program_page(outputs["tool_map"], outputs["manual_tiles"], "tool"),
    ]
    canvas = Image.new("RGB", (448, 480), (24, 24, 24))
    for index, page in enumerate(pages):
        canvas.paste(page.resize((448, 160), Image.Resampling.NEAREST), (0, index * 160))
    canvas.save(path)


def create_keyboard_preview(masks: dict[str, bytes], path: Path) -> None:
    labels = []
    for name in ("low", "cap", "abc"):
        payload = masks[name]
        order = [unpack_tile(payload[index * 32:(index + 1) * 32]) for index in range(6)]
        # Undo DMA order into the 3x2 on-screen sprite rectangle.
        grid = ((order[2], order[3], order[0]), (order[4], order[5], order[1]))
        image = Image.new("RGB", (24, 16), (170, 255, 255))
        pixels = image.load()
        for cell_y in range(2):
            for cell_x in range(3):
                tile = grid[cell_y][cell_x]
                for y in range(8):
                    for x in range(8):
                        pixels[cell_x * 8 + x, cell_y * 8 + y] = (
                            (0, 0, 0) if tile[y * 8 + x] == 0 else (170, 255, 255)
                        )
        labels.append(image.resize((96, 64), Image.Resampling.NEAREST))
    canvas = Image.new("RGB", (304, 80), (20, 28, 28))
    draw = ImageDraw.Draw(canvas)
    for index, (name, image) in enumerate(zip(("LOW", "CAP", "ABC"), labels)):
        x = index * 104
        canvas.paste(image, (x, 0))
        draw.text((x + 36, 66), name, fill=(255, 255, 255))
    canvas.save(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-rom", required=True, type=Path)
    parser.add_argument(
        "--asset-dir", type=Path,
        default=Path(__file__).resolve().parents[1] / "translation/assets",
    )
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir or args.asset_dir
    rom = args.source_rom.read_bytes()
    if len(rom) != ROM_SIZE or sha256(rom) != SOURCE_ROM_SHA256:
        raise ValueError("unsupported source ROM; expected verified Japanese Rev 1")

    keyboard_tiles = (args.asset_dir / "name_keyboard_tiles_v0_9.bin").read_bytes()
    if sha256(keyboard_tiles) != KEYBOARD_TILES_SHA256:
        raise ValueError("unexpected reviewed keyboard BG tile asset")
    base: dict[str, bytes] = {}
    for name, (filename, expected_hash) in BASE_ASSETS.items():
        payload = (args.asset_dir / filename).read_bytes()
        if sha256(payload) != expected_hash:
            raise ValueError(f"unexpected base asset {filename}")
        base[name] = payload

    masks = build_keyboard_masks(rom, keyboard_tiles)
    program = build_program_assets(base)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in masks.items():
        (output_dir / f"name_keyboard_obj_{name}_mask_v0_10_3.bin").write_bytes(payload)
    for name, payload in program.items():
        (output_dir / OUTPUT_FILES[name]).write_bytes(payload)

    keyboard_preview = output_dir / "name_keyboard_selector_preview_v0_10_3.png"
    program_preview = output_dir / "program_deck_design_preview_v0_10_3.png"
    create_keyboard_preview(masks, keyboard_preview)
    create_program_preview(program, program_preview)

    arrow = rom[0x07CE80:0x07CEA0] + rom[0x07D080:0x07D0A0]
    card_icon = b"".join(
        rom[0x07CD20 + tile * 32:0x07CD20 + (tile + 1) * 32]
        for tile in (0x50, 0x51, 0x58, 0x59, 0x5E, 0x5F)
    )
    report = {
        "format": "n1-quality-graphics-assets-v0.10.3",
        "status": "PASS",
        "keyboard": {
            "cause": "Japanese dynamic OBJ selector masks over correct English BG labels",
            "initial_page": "source byte 0x00 retained: LOW lowercase",
            "bg_map_and_tiles_changed": False,
            "masks": {
                name: {
                    "offset": f"0x{int(spec['offset']):06X}", "length": 192,
                    "file": f"name_keyboard_obj_{name}_mask_v0_10_3.bin",
                    "sha256": sha256(masks[name]),
                }
                for name, spec in KEYBOARD_MASKS.items()
            },
            "preview": keyboard_preview.name,
        },
        "program_deck": {
            "native_font": "5x7, 1:1 pixels, 6-pixel advance / 4-pixel space advance",
            "labels": ["LIKELY / CHIPS", "2 CHIPS / LEFT", "MIDDLE / 1 CHIP", "PRESS START / DECK INFO"],
            "capacity_palette_cells": [[x, y] for y in (6, 7) for x in (12, 13, 14)],
            "outputs": {
                name: {"file": OUTPUT_FILES[name], "sha256": sha256(payload), "length": len(payload)}
                for name, payload in program.items()
            },
            "preview": program_preview.name,
            "protected_original_art": {
                "direction_arrow_sha256": sha256(arrow),
                "chip_type_pictogram_sha256": sha256(card_icon),
                "byte_identical_to_japanese_source": True,
            },
        },
    }
    report_path = output_dir / "quality_graphics_asset_report_v0_10_3.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "PASS",
        "keyboard_masks": {name: sha256(payload) for name, payload in masks.items()},
        "program_assets": {name: sha256(payload) for name, payload in program.items()},
        "report": report_path.as_posix(),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
