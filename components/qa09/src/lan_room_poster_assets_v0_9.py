#!/usr/bin/env python3
"""Translate the residual Mega Man Legends 2 poster in Lan's room.

The room loads a raw 32x18 BG0 map at CPU:0x2000 and a 0x3000-byte packed
4-bpp tile bank at CPU:0x8000.  The Japanese yellow logo is confined to six
tiles that are each referenced exactly once by this map.  This generator
hash-guards the complete source map and atlas, erases only the 46 verified
yellow logo pixels, draws the unambiguous English abbreviation ``MM / L2``
for ``Mega Man Legends 2`` in the original 8x19-pixel logo footprint, and
proves that no other tile byte or map cell changes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw


SOURCE_ROM_SHA256 = "4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed"
ROM_SIZE = 0x400000
MAP_OFFSET = 0x04DE98
MAP_LENGTH = 0x0480
MAP_SOURCE_SHA256 = "10b9f999ccf7c2271e91d972003f82a3d82174346975bb091addb398a8c5b5a9"
TILES_OFFSET = 0x0A7900
TILES_LENGTH = 0x3000
TILES_SOURCE_SHA256 = "f028469173d41f02e635fd8544a5c4d14c9622fed33378ee58e2a47c1d991c1a"
# Superseded first-pass full-title microtext, accepted only as a QA migration
# base so an already integrated v0.9 build can be rebuilt deterministically.
TILES_SUPERSEDED_SHA256 = "b63f91716f549ec6319331ea50b46e8f5f657c0e1143a4fba18fcad8ac9b28df"
MAP_WIDTH = 32
TILE_BYTES = 32
TILE_MASK = 0x01FF


# (tile ID, map x, map y, palette, yellow index, poster-background index)
TARGETS = (
    (0x031, 25, 1, 3, 4, 0xA),
    (0x032, 26, 1, 2, 7, 0x1),
    (0x046, 25, 2, 3, 4, 0xA),
    (0x047, 26, 2, 2, 7, 0x1),
    (0x05D, 25, 3, 3, 4, 0xA),
    (0x05E, 26, 3, 7, 1, 0xE),
)
TARGET_TILE_IDS = tuple(item[0] for item in TARGETS)


# Each M uses a true 5x5 diagonal glyph so it cannot be mistaken for H.  The
# final L2 line uses minimum legible 3x5 glyphs with a one-pixel gap.  All
# three rows fit the original eight-pixel-wide by 19-pixel-high yellow mark.
FONT = {
    "L": ("100", "100", "100", "100", "111"),
    "M": ("10001", "11011", "10101", "10001", "10001"),
    "2": ("110", "001", "010", "100", "111"),
}

LINES = (
    ("M", 6, 0),
    ("M", 6, 7),
    ("L2", 5, 14),
)


# Correct WonderSwan BGR444 runtime palettes from a clean Mesen capture.
PALETTES = {
    2: (
        (0, 0, 0), (51, 68, 51), (119, 85, 34), (85, 68, 17),
        (68, 119, 170), (119, 170, 204), (85, 153, 170), (255, 238, 68),
        (221, 187, 119), (102, 85, 17), (170, 102, 68), (51, 17, 85),
        (102, 102, 136), (85, 85, 119), (51, 51, 68), (204, 255, 238),
    ),
    3: (
        (0, 0, 0), (221, 238, 221), (102, 170, 204), (153, 170, 153),
        (255, 238, 68), (204, 255, 238), (255, 255, 255), (119, 102, 255),
        (136, 204, 204), (51, 68, 85), (51, 68, 51), (187, 85, 34),
        (187, 255, 255), (255, 255, 238), (119, 119, 153), (51, 68, 153),
    ),
    4: (
        (0, 0, 0), (136, 204, 204), (85, 68, 17), (119, 85, 34),
        (102, 119, 170), (204, 255, 238), (187, 204, 187), (221, 221, 187),
        (68, 68, 102), (102, 102, 136), (102, 170, 204), (170, 102, 68),
        (51, 68, 51), (119, 170, 153), (51, 68, 85), (187, 255, 255),
    ),
    7: (
        (0, 0, 0), (255, 238, 68), (153, 102, 51), (204, 153, 51),
        (221, 170, 51), (255, 221, 170), (153, 170, 153), (221, 238, 221),
        (102, 102, 136), (102, 119, 170), (102, 170, 204), (136, 204, 204),
        (255, 51, 34), (85, 102, 102), (17, 51, 51), (170, 187, 187),
    ),
}


def sha256(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def map_word(tilemap: bytes, x: int, y: int) -> int:
    position = (y * MAP_WIDTH + x) * 2
    return int.from_bytes(tilemap[position:position + 2], "little")


def get_pixel(tiles: bytes | bytearray, tile: int, x: int, y: int) -> int:
    packed = tiles[tile * TILE_BYTES + y * 4 + x // 2]
    return packed & 0x0F if x & 1 else packed >> 4


def set_pixel(tiles: bytearray, tile: int, x: int, y: int, value: int) -> None:
    position = tile * TILE_BYTES + y * 4 + x // 2
    if x & 1:
        tiles[position] = (tiles[position] & 0xF0) | value
    else:
        tiles[position] = (tiles[position] & 0x0F) | (value << 4)


def tile_at(tilemap: bytes, screen_x: int, screen_y: int) -> tuple[int, int]:
    word = map_word(tilemap, screen_x // 8, screen_y // 8)
    if word & 0xC000:
        raise AssertionError("poster target unexpectedly uses flipped map cells")
    return word & TILE_MASK, (word >> 9) & 0x0F


def screen_pixel(
    tilemap: bytes, tiles: bytes | bytearray, screen_x: int, screen_y: int
) -> tuple[int, int, int]:
    tile, palette = tile_at(tilemap, screen_x, screen_y)
    return tile, palette, get_pixel(tiles, tile, screen_x & 7, screen_y & 7)


def draw_points() -> list[tuple[int, int]]:
    result = []
    for text, origin_x, origin_y in LINES:
        for character_index, character in enumerate(text):
            for glyph_y, row in enumerate(FONT[character]):
                for glyph_x, enabled in enumerate(row):
                    if enabled == "1":
                        result.append(
                            (origin_x + character_index * 4 + glyph_x,
                             origin_y + glyph_y)
                        )
    if len(result) != len(set(result)):
        raise AssertionError("English poster raster overlaps itself")
    return result


def render_crop(tilemap: bytes, tiles: bytes | bytearray) -> Image.Image:
    origin_x, origin_y, width, height = 200, 8, 24, 24
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    for y in range(height):
        for x in range(width):
            _, palette, colour = screen_pixel(tilemap, tiles, origin_x + x, origin_y + y)
            pixels[x, y] = PALETTES[palette][colour]
    return image


def comparison_preview(
    tilemap: bytes,
    original_tiles: bytes,
    patched_tiles: bytes,
    output: Path,
) -> None:
    scale = 16
    before = render_crop(tilemap, original_tiles).resize((384, 384), Image.Resampling.NEAREST)
    after = render_crop(tilemap, patched_tiles).resize((384, 384), Image.Resampling.NEAREST)
    caption, gap = 28, 8
    image = Image.new("RGB", (before.width + after.width + gap, before.height + caption), (24, 24, 24))
    image.paste(before, (0, caption))
    image.paste(after, (before.width + gap, caption))
    draw = ImageDraw.Draw(image)
    draw.text((6, 7), "POSTER: SOURCE", fill="white")
    draw.text((before.width + gap + 6, 7), "POSTER: MM / L2 (MEGA MAN LEGENDS 2)", fill="white")
    image.save(output)


def patch_assets(source: bytes) -> tuple[bytes, bytes, dict[str, object]]:
    tilemap = source[MAP_OFFSET:MAP_OFFSET + MAP_LENGTH]
    original_tiles = source[TILES_OFFSET:TILES_OFFSET + TILES_LENGTH]
    if sha256(tilemap) != MAP_SOURCE_SHA256:
        raise ValueError("Lan room map source hash mismatch")
    if sha256(original_tiles) != TILES_SOURCE_SHA256:
        raise ValueError("Lan room tile-bank source hash mismatch")

    counts = Counter(
        int.from_bytes(tilemap[position:position + 2], "little") & TILE_MASK
        for position in range(0, len(tilemap), 2)
    )
    target_details = []
    cleared = 0
    tiles = bytearray(original_tiles)
    target_lookup = {tile: (palette, face, background) for tile, _, _, palette, face, background in TARGETS}
    for tile, x, y, palette, face, background in TARGETS:
        word = map_word(tilemap, x, y)
        if (word & TILE_MASK) != tile or ((word >> 9) & 0x0F) != palette:
            raise AssertionError(f"unexpected source map word at ({x},{y}): 0x{word:04X}")
        if counts[tile] != 1:
            raise AssertionError(f"poster tile 0x{tile:03X} has {counts[tile]} map references")
        face_count = 0
        for py in range(8):
            for px in range(8):
                if get_pixel(tiles, tile, px, py) == face:
                    set_pixel(tiles, tile, px, py, background)
                    face_count += 1
        cleared += face_count
        target_details.append({
            "tile": f"0x{tile:03X}",
            "rom_span": [f"0x{TILES_OFFSET + tile * TILE_BYTES:06X}",
                         f"0x{TILES_OFFSET + (tile + 1) * TILE_BYTES:06X}"],
            "map_cell": {"x": x, "y": y},
            "map_word": f"0x{word:04X}",
            "palette": palette,
            "cleared_yellow_pixels": face_count,
            "source_map_references": counts[tile],
        })
    if cleared != 46:
        raise AssertionError(f"expected 46 source logo pixels, found {cleared}")

    points = draw_points()
    if len(points) != 41:
        raise AssertionError(f"expected 41 English logo pixels, got {len(points)}")
    allowed_source = {
        0x031: {0xA, 4}, 0x032: {1, 7, 0xE},
        0x046: {0xA, 4}, 0x047: {1, 7, 0xE},
        0x05D: {0xA, 4}, 0x05E: {1, 0xE},
    }
    touched: Counter[int] = Counter()
    for x, y in points:
        screen_x, screen_y = 200 + x, 8 + y
        tile, palette, original_colour = screen_pixel(tilemap, original_tiles, screen_x, screen_y)
        if tile not in allowed_source or original_colour not in allowed_source[tile]:
            raise AssertionError(
                f"English pixel would overwrite poster art at ({screen_x},{screen_y})"
            )
        expected_palette, face, _ = target_lookup[tile]
        if palette != expected_palette:
            raise AssertionError("poster draw palette mismatch")
        set_pixel(tiles, tile, screen_x & 7, screen_y & 7, face)
        touched[tile] += 1

    changed = {
        index for index, (old, new) in enumerate(zip(original_tiles, tiles))
        if old != new
    }
    allowed = {
        byte
        for tile in TARGET_TILE_IDS
        for byte in range(tile * TILE_BYTES, (tile + 1) * TILE_BYTES)
    }
    if changed - allowed:
        raise AssertionError("bytes outside the six exclusive poster tiles changed")
    if tilemap != source[MAP_OFFSET:MAP_OFFSET + MAP_LENGTH]:
        raise AssertionError("Lan room map changed")

    report = {
        "source_logo": "ロックマンDASH2",
        "official_translation": "MEGA MAN LEGENDS 2",
        "rendered_abbreviation": "MM / L2",
        "rendered_lines": [line[0] for line in LINES],
        "verified_source_logo_footprint": {"width": 8, "height": 19},
        "screen_region": {"x": 200, "y": 8, "width": 24, "height": 24},
        "source_yellow_pixels_cleared": cleared,
        "english_yellow_pixels_drawn": len(points),
        "changed_bytes": len(changed),
        "changed_tile_ids": [f"0x{tile:03X}" for tile in sorted({index // TILE_BYTES for index in changed})],
        "drawn_pixels_by_tile": {f"0x{tile:03X}": count for tile, count in sorted(touched.items())},
        "tiles": target_details,
    }
    return tilemap, bytes(tiles), report


def validate_runtime_capture(
    capture_dir: Path,
    output_dir: Path,
    expected_map: bytes,
    expected_tiles: bytes,
) -> dict[str, object]:
    frame = 24924
    wram = (capture_dir / f"wram_{frame:05d}.bin").read_bytes()
    if len(wram) != 0x10000:
        raise ValueError("runtime WRAM dump is not 65536 bytes")
    ports = {}
    for line in (capture_dir / f"ports_{frame:05d}.tsv").read_text(encoding="utf-8").splitlines()[1:]:
        port, value = line.split("\t")
        ports[int(port, 16)] = int(value, 16)
    expected_ports = {0x07: 0x54, 0x10: 0, 0x11: 0, 0x12: 0, 0x13: 0, 0x60: 0xE0}
    if any(ports.get(port) != value for port, value in expected_ports.items()):
        raise AssertionError("runtime poster video ports differ from traced values")
    map_match = wram[0x2000:0x2000 + MAP_LENGTH] == expected_map
    tile_match = wram[0x8000:0x8000 + TILES_LENGTH] == expected_tiles
    if not map_match or not tile_match:
        raise AssertionError("runtime did not load the generated poster assets verbatim")
    screenshot = capture_dir / f"frame_{frame:05d}.png"
    output_name = "lan_room_poster_runtime_v0_9.png"
    output = output_dir / output_name
    output.write_bytes(screenshot.read_bytes())
    return {
        "emulator": "MesenCE 2.2.1",
        "route": "clean boot; post-manual Lan room scene",
        "save_or_state_used": False,
        "frame": frame,
        "screenshot": output_name,
        "screenshot_sha256": sha256(output.read_bytes()),
        "map_cpu_span": ["0x2000", "0x2480"],
        "tiles_cpu_span": ["0x8000", "0xB000"],
        "generated_map_matches_runtime": map_match,
        "generated_tiles_match_runtime": tile_match,
        "ports": {f"0x{port:02X}": f"0x{ports[port]:02X}" for port in expected_ports},
    }


def build(
    source_rom: Path,
    output_dir: Path,
    base_rom: Path | None,
    patched_rom: Path | None,
    runtime_capture_dir: Path | None,
) -> dict[str, object]:
    source = source_rom.read_bytes()
    if len(source) != ROM_SIZE or sha256(source) != SOURCE_ROM_SHA256:
        raise ValueError(
            f"unexpected source ROM SHA-256 {sha256(source)}; expected {SOURCE_ROM_SHA256}"
        )
    tilemap, patched_tiles, patch_report = patch_assets(source)
    original_tiles = source[TILES_OFFSET:TILES_OFFSET + TILES_LENGTH]
    output_dir.mkdir(parents=True, exist_ok=True)

    asset_name = "lan_room_poster_bg0_tiles_v0_9.bin"
    asset_path = output_dir / asset_name
    asset_path.write_bytes(patched_tiles)
    preview_name = "lan_room_poster_comparison_v0_9.png"
    preview_path = output_dir / preview_name
    comparison_preview(tilemap, original_tiles, patched_tiles, preview_path)

    qa_report = None
    if bool(base_rom) != bool(patched_rom):
        raise ValueError("--base-rom and --patched-rom must be supplied together")
    if base_rom is not None and patched_rom is not None:
        base = bytearray(base_rom.read_bytes())
        if len(base) != ROM_SIZE:
            raise ValueError("QA base ROM size mismatch")
        base_atlas_hash = sha256(base[TILES_OFFSET:TILES_OFFSET + TILES_LENGTH])
        if base_atlas_hash not in {TILES_SOURCE_SHA256, TILES_SUPERSEDED_SHA256}:
            raise ValueError("QA base poster atlas is neither the audited source nor the superseded first pass")
        base_hash = sha256(base)
        base[TILES_OFFSET:TILES_OFFSET + TILES_LENGTH] = patched_tiles
        checksum = sum(base[:-2]) & 0xFFFF
        base[-2:] = checksum.to_bytes(2, "little")
        patched_rom.parent.mkdir(parents=True, exist_ok=True)
        patched_rom.write_bytes(base)
        qa_report = {
            "base_file": base_rom.name,
            "base_sha256": base_hash,
            "base_poster_atlas_sha256": base_atlas_hash,
            "output_file": patched_rom.name,
            "output_sha256": sha256(base),
            "stored_checksum": f"0x{checksum:04X}",
            "calculated_checksum": f"0x{sum(base[:-2]) & 0xFFFF:04X}",
            "checksum_valid": int.from_bytes(base[-2:], "little") == (sum(base[:-2]) & 0xFFFF),
        }

    runtime_report = None
    if runtime_capture_dir is not None:
        runtime_report = validate_runtime_capture(
            runtime_capture_dir, output_dir, tilemap, patched_tiles
        )

    report = {
        "generator": Path(__file__).name,
        "version": "0.9",
        "source_rom": {"file": source_rom.name, "sha256": sha256(source)},
        "source_assets": {
            "lan_room_bg0_map": {
                "rom_offset": f"0x{MAP_OFFSET:06X}",
                "length": MAP_LENGTH,
                "sha256": MAP_SOURCE_SHA256,
                "runtime_cpu_span": ["0x2000", "0x2480"],
                "output_changed": False,
            },
            "lan_room_bg0_tiles": {
                "rom_offset": f"0x{TILES_OFFSET:06X}",
                "length": TILES_LENGTH,
                "sha256": TILES_SOURCE_SHA256,
                "runtime_cpu_span": ["0x8000", "0xB000"],
            },
        },
        "patch": patch_report,
        "asset": {
            "file": asset_name,
            "rom_offset": f"0x{TILES_OFFSET:06X}",
            "length": TILES_LENGTH,
            "source_sha256": TILES_SOURCE_SHA256,
            "output_sha256": sha256(patched_tiles),
        },
        "preview": {"file": preview_name, "sha256": sha256(preview_path.read_bytes())},
        "qa_rom": qa_report,
        "runtime_validation": runtime_report,
        "validation": {
            "complete_map_and_atlas_hash_guarded": True,
            "six_target_tiles_exclusive_in_source_map": True,
            "source_map_unchanged": True,
            "outside_target_tile_bytes_unchanged": True,
            "poster_art_outside_verified_logo_pixels_preserved": True,
            "official_english_title_conveyed_by_abbreviation": True,
            "full_official_title_rasterized": False,
            "encoded_text_denominator_delta": 0,
            "graphical_target_delta": 1,
            "runtime_loaded_assets_match_generated": (
                True if runtime_report is not None else None
            ),
        },
        "notes": [
            "ロックマンDASH2 is the Japanese title of Mega Man Legends 2.",
            "Capcom's official Kobun account identifies the EXE1 Lan-room poster and matching Kobun rug as Rockman DASH2: https://x.com/capkobun/status/747807756468396033",
            "MM / L2 is a documented legibility adaptation: the full official title cannot be rasterized readably inside the verified 8x19-pixel yellow-logo footprint.",
            "The three neighbouring right-column tiles 0x033/0x048/0x05F are untouched because live palette tracing proves the yellow logo never enters them.",
        ],
    }
    report_path = output_dir / "lan_room_poster_asset_report_v0_9.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "report": str(report_path),
        "asset": {asset_name: sha256(patched_tiles)},
        "preview": {preview_name: sha256(preview_path.read_bytes())},
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
    )
    parser.add_argument("--base-rom", type=Path)
    parser.add_argument("--patched-rom", type=Path)
    parser.add_argument("--runtime-capture-dir", type=Path)
    args = parser.parse_args()
    build(
        args.rom, args.output_dir, args.base_rom, args.patched_rom,
        args.runtime_capture_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
