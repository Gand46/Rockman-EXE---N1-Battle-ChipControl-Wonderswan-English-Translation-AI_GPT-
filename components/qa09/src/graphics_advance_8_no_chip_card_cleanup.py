#!/usr/bin/env python3
"""Remove the residual Japanese row below the shared NO CHIP SELECTED card."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw


ROM_SIZE = 0x400000
BASE_A7_SHA256 = "e049ce549ddbbe695995cc7c76863a201e22199e064daaa24f2e542dcedaf9fa"
BANK_OFFSET = 0x2B0A20
BANK_LENGTH = 0x0700
BASE_BANK_SHA256 = "74c01244813b89716255ac44afb13b8370dc254264a1bc73404303ee2882a26f"
TILE_BYTES = 32
FIRST_RESIDUAL_TILE = 0x30
RESIDUAL_TILE_COUNT = 8
BACKGROUND_INDEX = 1
FRAME_INDEX = 14
INNER_X_RANGE = range(2, 62)
RESIDUAL_Y_RANGE = range(0, 4)
ASSET_NAME = "pet_no_data_card_tiles_graphics_a8.bin"
REPORT_NAME = "graphics_advance_8_no_chip_card_cleanup_report.json"
PREVIEW_NAME = "graphics_advance_8_no_chip_card_cleanup_preview.png"


PALETTE = (
    (0, 0, 0), (68, 68, 136), (170, 170, 187), (204, 238, 255),
    (34, 255, 255), (255, 0, 255), (255, 0, 255), (255, 0, 255),
    (255, 0, 255), (255, 0, 238), (255, 0, 255), (255, 0, 255),
    (255, 0, 238), (255, 0, 255), (85, 85, 153), (68, 68, 136),
)


def sha256(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def unpack_tile(bank: bytes | bytearray, tile_id: int) -> list[int]:
    payload = bank[tile_id * TILE_BYTES:(tile_id + 1) * TILE_BYTES]
    if len(payload) != TILE_BYTES:
        raise ValueError(f"tile 0x{tile_id:03X} is outside the card bank")
    return [value for byte in payload for value in (byte >> 4, byte & 0x0F)]


def pack_tile(pixels: list[int]) -> bytes:
    if len(pixels) != 64 or any(not 0 <= value <= 15 for value in pixels):
        raise ValueError("invalid 4-bpp tile")
    return bytes((pixels[index] << 4) | pixels[index + 1] for index in range(0, 64, 2))


def card_pixels(bank: bytes | bytearray) -> list[list[int]]:
    canvas = [[BACKGROUND_INDEX] * 64 for _ in range(32)]
    for y in range(32):
        for x in range(64):
            tile_id = 0x18 + (y // 8) * 8 + x // 8
            tile = unpack_tile(bank, tile_id)
            canvas[y][x] = tile[(y & 7) * 8 + (x & 7)]
    return canvas


def clean_residual_row(base_bank: bytes) -> bytes:
    if len(base_bank) != BANK_LENGTH or sha256(base_bank) != BASE_BANK_SHA256:
        raise ValueError("Graphics Advance 8 requires the exact approved A7 card bank")

    output = bytearray(base_bank)
    tiles = {tile_id: unpack_tile(base_bank, tile_id)
             for tile_id in range(FIRST_RESIDUAL_TILE, FIRST_RESIDUAL_TILE + RESIDUAL_TILE_COUNT)}
    for y in RESIDUAL_Y_RANGE:
        for x in INNER_X_RANGE:
            tile_id = FIRST_RESIDUAL_TILE + x // 8
            replacement = FRAME_INDEX if y == 3 else BACKGROUND_INDEX
            tiles[tile_id][y * 8 + (x & 7)] = replacement
    for tile_id, pixels in tiles.items():
        start = tile_id * TILE_BYTES
        output[start:start + TILE_BYTES] = pack_tile(pixels)

    before = card_pixels(base_bank)
    after = card_pixels(output)
    if not any(before[24 + y][x] != BACKGROUND_INDEX
               for y in RESIDUAL_Y_RANGE for x in INNER_X_RANGE):
        raise AssertionError("the A7 residual row was not present")
    if any(after[24 + y][x] != (FRAME_INDEX if y == 3 else BACKGROUND_INDEX)
           for y in RESIDUAL_Y_RANGE for x in INNER_X_RANGE):
        raise AssertionError("Japanese residual pixels remain in the interior cleanup field")
    for y in RESIDUAL_Y_RANGE:
        if before[24 + y][:2] != after[24 + y][:2] or before[24 + y][62:] != after[24 + y][62:]:
            raise AssertionError("the card side frame changed")
    if before[:24] != after[:24]:
        raise AssertionError("NO CHIP / IS / SELECTED changed")
    if before[28:] != after[28:]:
        raise AssertionError("the lower frame changed")
    return bytes(output)


def render_card(bank: bytes) -> Image.Image:
    pixels = card_pixels(bank)
    image = Image.new("RGB", (64, 32))
    for y in range(32):
        for x in range(64):
            image.putpixel((x, y), PALETTE[pixels[y][x]])
    return image


def write_preview(before: bytes, after: bytes, path: Path) -> None:
    scale = 8
    left = render_card(before).resize((64 * scale, 32 * scale), Image.Resampling.NEAREST)
    right = render_card(after).resize(left.size, Image.Resampling.NEAREST)
    gap, caption = 12, 30
    image = Image.new("RGB", (left.width * 2 + gap, left.height + caption), (20, 20, 20))
    image.paste(left, (0, caption))
    image.paste(right, (left.width + gap, caption))
    draw = ImageDraw.Draw(image)
    draw.text((8, 8), "A7: residual Japanese row", fill="white")
    draw.text((left.width + gap + 8, 8), "A8: clean card interior", fill="white")
    image.save(path)


def changed_runs(before: bytes, after: bytes) -> list[list[str]]:
    changed = [index for index, pair in enumerate(zip(before, after, strict=True)) if pair[0] != pair[1]]
    if not changed:
        return []
    runs: list[list[str]] = []
    start = previous = changed[0]
    for value in changed[1:]:
        if value != previous + 1:
            runs.append([f"0x{BANK_OFFSET + start:06X}", f"0x{BANK_OFFSET + previous + 1:06X}"])
            start = value
        previous = value
    runs.append([f"0x{BANK_OFFSET + start:06X}", f"0x{BANK_OFFSET + previous + 1:06X}"])
    return runs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a7-rom", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    rom = args.a7_rom.read_bytes()
    if len(rom) != ROM_SIZE or sha256(rom) != BASE_A7_SHA256:
        raise ValueError("Graphics Advance 8 requires the exact approved A7 ROM")
    base_bank = rom[BANK_OFFSET:BANK_OFFSET + BANK_LENGTH]
    output_bank = clean_residual_row(base_bank)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    asset_path = args.output_dir / ASSET_NAME
    preview_path = args.output_dir / PREVIEW_NAME
    asset_path.write_bytes(output_bank)
    write_preview(base_bank, output_bank, preview_path)

    differences = [index for index, pair in enumerate(zip(base_bank, output_bank, strict=True))
                   if pair[0] != pair[1]]
    changed_tiles = sorted({index // TILE_BYTES for index in differences})
    allowed_tiles = list(range(FIRST_RESIDUAL_TILE, FIRST_RESIDUAL_TILE + RESIDUAL_TILE_COUNT))
    if any(tile not in allowed_tiles for tile in changed_tiles):
        raise AssertionError("cleanup escaped the fourth card row")

    report = {
        "status": "PASS",
        "project_version": "0.10.7-graphics-a8",
        "base_advance_7_sha256": BASE_A7_SHA256,
        "bank_offset": f"0x{BANK_OFFSET:06X}",
        "bank_length": BANK_LENGTH,
        "base_bank_sha256": BASE_BANK_SHA256,
        "output_bank_sha256": sha256(output_bank),
        "asset": ASSET_NAME,
        "asset_sha256": sha256(asset_path.read_bytes()),
        "card_dimensions": [64, 32],
        "english_text_rectangle": [0, 0, 64, 24],
        "residual_cleanup_rectangle_inside_card": [2, 24, 62, 28],
        "protected_side_frame_rectangles": [[0, 24, 2, 28], [62, 24, 64, 28]],
        "reconstructed_uniform_frame_row": [0, 27, 64, 28],
        "protected_lower_frame_rectangle": [0, 28, 64, 32],
        "changed_tiles": [f"0x{tile:03X}" for tile in changed_tiles],
        "changed_bytes_vs_advance_7": len(differences),
        "changed_runs": changed_runs(base_bank, output_bank),
        "english_text_changed_bytes": 0,
        "lower_and_side_frame_changed_pixels": 0,
        "residual_japanese_glyph_pixels_after": 0,
        "shared_dynamic_consumers": 3,
        "maps_palettes_code_pointers_changed_bytes": 0,
        "preview": PREVIEW_NAME,
        "preview_sha256": sha256(preview_path.read_bytes()),
    }
    report_path = args.output_dir / REPORT_NAME
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
