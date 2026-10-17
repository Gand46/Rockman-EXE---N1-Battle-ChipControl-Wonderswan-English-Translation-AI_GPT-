#!/usr/bin/env python3
"""Build the remaining Program Deck transfer and tournament header assets.

The source graphics are raw WonderSwan Color packed 4-bpp tiles.  This tool
accepts only the verified Rev 1 Japanese ROM, rewrites five guarded spans in
memory, proves that no byte outside those spans changed, and emits the five
complete replacement assets plus visual previews and a JSON report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


SOURCE_ROM_SHA256 = "4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed"


@dataclass(frozen=True)
class AssetSpec:
    asset_id: str
    offset: int
    length: int
    source_sha256: str
    filename: str


ASSETS = (
    AssetSpec(
        "program_deck_transfer_text",
        0x2E9EE0,
        0x300,
        "526049c4368e60a6be09130afcab7a536fcb5a758184883e80bb2b77a0ab6f19",
        "program_deck_transfer_text_tiles_v0_9.bin",
    ),
    AssetSpec(
        "tournament_header_top",
        0x08C2F0,
        0x0E0,
        "94392a0f57f43ba1c722451cd873d126dd7ef18dbd441c7d74a09d115ae95dd1",
        "tournament_header_top_tiles_v0_9.bin",
    ),
    AssetSpec(
        "tournament_header_bottom",
        0x08C430,
        0x0E0,
        "188d7ef4dee5d29e08fe7e82c69f2fdf6bb38f02422de560f2f05446d3e44a26",
        "tournament_header_bottom_tiles_v0_9.bin",
    ),
    AssetSpec(
        "tournament_phase_renderer",
        0x328F10,
        0x070,
        "d2d2414673d9a6348792821130a41277baed4a156cdc4f4308b6d61fc7151179",
        "tournament_phase_renderer_v0_9.bin",
    ),
    AssetSpec(
        "tournament_phase_text_pool",
        0x344688,
        0x034,
        "7955cb2de90dd9efc6df9fdbf5f5d10c114f4135a9a6b52db1003be749e32f7a",
        "tournament_phase_text_pool_v0_9.bin",
    ),
)

# Compact 3x5 alphabet used by the validated Mesen prototype.  Tournament
# letters are doubled vertically so TOURNAMENT remains legible in 56x16 px.
FONT = {
    "A": ("010", "101", "111", "101", "101"),
    "B": ("110", "101", "110", "101", "110"),
    "C": ("011", "100", "100", "100", "011"),
    "D": ("110", "101", "101", "101", "110"),
    "E": ("111", "100", "110", "100", "111"),
    "F": ("111", "100", "110", "100", "100"),
    "G": ("011", "100", "101", "101", "011"),
    "I": ("111", "010", "010", "010", "111"),
    "K": ("101", "101", "110", "101", "101"),
    "L": ("100", "100", "100", "100", "111"),
    "M": ("101", "111", "111", "101", "101"),
    "N": ("101", "111", "111", "111", "101"),
    "O": ("010", "101", "101", "101", "010"),
    "R": ("110", "101", "110", "101", "101"),
    "S": ("011", "100", "010", "001", "110"),
    "T": ("111", "010", "010", "010", "010"),
    "U": ("101", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("110", "001", "010", "100", "111"),
    "3": ("110", "001", "010", "001", "110"),
    " ": ("000", "000", "000", "000", "000"),
}

TRANSFER_PALETTE = {
    1: (68, 68, 136),
    2: (187, 170, 170),
    3: (255, 238, 204),
    14: (85, 85, 153),
}
TOURNAMENT_PALETTE = {
    2: (51, 51, 51),
    6: (85, 102, 102),
    13: (238, 221, 204),
}

# Static-text word values consumed by the game's native 8x16 text renderer.
# The renderer increments the supplied pointer before reading, so every string
# below starts with a sentinel word and ends with 0x8000.
NATIVE_TEXT = {
    " ": 0x0000,
    "A": 0x005E,
    "D": 0x0061,
    "E": 0x0062,
    "F": 0x0063,
    "I": 0x0066,
    "L": 0x0069,
    "M": 0x006A,
    "N": 0x006B,
    "O": 0x006C,
    "R": 0x006F,
    "S": 0x0070,
    "U": 0x0072,
}

PHASE_POOL_SEGMENT = 0x4400
PHASE_POOL_FILE_OFFSET = 0x344688
PHASE_SENTINEL_OFFSETS = {
    "ROUND": 0x0688,
    "FINAL": 0x0698,
    "SEMIFINAL": 0x06A6,
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encode_native_string(text: str) -> bytes:
    unsupported = sorted(set(text) - NATIVE_TEXT.keys())
    if unsupported:
        raise ValueError(f"unsupported native text characters: {unsupported}")
    words = [NATIVE_TEXT[character] for character in text] + [0x8000]
    return b"".join(word.to_bytes(2, "little") for word in words)


def unpack_tile(data: bytes | bytearray, offset: int) -> list[int]:
    payload = data[offset : offset + 32]
    if len(payload) != 32:
        raise ValueError(f"truncated tile at 0x{offset:06X}")
    return [value for byte in payload for value in (byte >> 4, byte & 0x0F)]


def pack_tile(pixels: list[int]) -> bytes:
    if len(pixels) != 64 or any(not 0 <= value <= 15 for value in pixels):
        raise ValueError("invalid packed 4-bpp tile")
    return bytes(
        (pixels[index] << 4) | pixels[index + 1]
        for index in range(0, 64, 2)
    )


def read_canvas(
    data: bytes | bytearray,
    offsets: list[int],
    tile_columns: int,
    tile_rows: int,
) -> list[int]:
    if len(offsets) != tile_columns * tile_rows:
        raise ValueError("offset count does not match canvas dimensions")
    width = tile_columns * 8
    canvas = [0] * (width * tile_rows * 8)
    for tile_index, offset in enumerate(offsets):
        tile = unpack_tile(data, offset)
        tile_x, tile_y = tile_index % tile_columns, tile_index // tile_columns
        for y in range(8):
            for x in range(8):
                canvas[(tile_y * 8 + y) * width + tile_x * 8 + x] = tile[y * 8 + x]
    return canvas


def write_canvas(
    data: bytearray,
    offsets: list[int],
    tile_columns: int,
    tile_rows: int,
    canvas: list[int],
) -> None:
    width, height = tile_columns * 8, tile_rows * 8
    if len(canvas) != width * height:
        raise ValueError("canvas size does not match tile dimensions")
    for tile_index, offset in enumerate(offsets):
        tile_x, tile_y = tile_index % tile_columns, tile_index // tile_columns
        tile = [
            canvas[(tile_y * 8 + y) * width + tile_x * 8 + x]
            for y in range(8)
            for x in range(8)
        ]
        data[offset : offset + 32] = pack_tile(tile)


def text_width(text: str) -> int:
    return len(text) * 4 - 1


def draw_text(
    canvas: list[int],
    width: int,
    height: int,
    text: str,
    x: int,
    y: int,
    ink: int,
    shadow: int,
    vertical_scale: int = 1,
) -> None:
    unsupported = sorted(set(text) - FONT.keys())
    if unsupported:
        raise ValueError(f"unsupported characters: {unsupported}")
    points: list[tuple[int, int]] = []
    for character_index, character in enumerate(text):
        for glyph_y, row in enumerate(FONT[character]):
            for glyph_x, bit in enumerate(row):
                if bit == "1":
                    for scale_y in range(vertical_scale):
                        points.append(
                            (
                                x + character_index * 4 + glyph_x,
                                y + glyph_y * vertical_scale + scale_y,
                            )
                        )
    if any(not (0 <= px < width and 0 <= py < height) for px, py in points):
        raise ValueError(f"text does not fit canvas: {text!r}")
    if any(not (0 <= px + 1 < width and 0 <= py + 1 < height) for px, py in points):
        raise ValueError(f"text shadow does not fit canvas: {text!r}")
    for px, py in points:
        canvas[(py + 1) * width + px + 1] = shadow
    for px, py in points:
        canvas[py * width + px] = ink


def render_preview(
    canvas: list[int],
    width: int,
    height: int,
    palette: dict[int, tuple[int, int, int]],
    output: Path,
    scale: int = 8,
) -> None:
    unknown = sorted(set(canvas) - palette.keys())
    if unknown:
        raise ValueError(f"preview palette lacks nibbles: {unknown}")
    image = Image.new("RGB", (width, height))
    image.putdata([palette[value] for value in canvas])
    image.resize((width * scale, height * scale), Image.Resampling.NEAREST).save(output)


def build_assets(source: bytes, output_dir: Path) -> dict[str, object]:
    if sha256(source) != SOURCE_ROM_SHA256:
        raise ValueError(
            "unexpected source ROM SHA-256: "
            f"{sha256(source)}; expected {SOURCE_ROM_SHA256}"
        )
    for spec in ASSETS:
        actual = sha256(source[spec.offset : spec.offset + spec.length])
        if actual != spec.source_sha256:
            raise ValueError(
                f"unexpected source span for {spec.asset_id}: {actual}; "
                f"expected {spec.source_sha256}"
            )

    output = bytearray(source)

    transfer = ASSETS[0]
    transfer_offsets = [transfer.offset + index * 32 for index in range(24)]
    transfer_canvas = read_canvas(output, transfer_offsets, 8, 3)
    transfer_canvas = [1 if value in (2, 3) else value for value in transfer_canvas]
    for label, y in (("SENDING", 3), ("DECK DATA", 14)):
        draw_text(
            transfer_canvas,
            64,
            24,
            label,
            (64 - text_width(label)) // 2,
            y,
            ink=3,
            shadow=2,
        )
    write_canvas(output, transfer_offsets, 8, 3, transfer_canvas)

    top, bottom = ASSETS[1], ASSETS[2]
    tournament_offsets = (
        [top.offset + index * 32 for index in range(7)]
        + [bottom.offset + index * 32 for index in range(7)]
    )
    tournament_canvas = read_canvas(output, tournament_offsets, 7, 2)
    tournament_canvas = [
        6 if value in (2, 13) else value for value in tournament_canvas
    ]
    tournament_label = "TOURNAMENT"
    draw_text(
        tournament_canvas,
        56,
        16,
        tournament_label,
        (56 - text_width(tournament_label)) // 2,
        2,
        ink=13,
        shadow=2,
        vertical_scale=2,
    )
    write_canvas(output, tournament_offsets, 7, 2, tournament_canvas)

    # Tournament phase header.  The original routine has three exclusive
    # branches: SEMIFINAL, FINAL, and a generic N + Japanese suffix.  Point all
    # three branches at an unused fixed-bank pool and put the English prefix
    # first.  The number formatter is right-aligned: width 0 suppresses its
    # leading-space fill and column 24 leaves both digits of 10-13 to the right
    # of the native string terminator at column 22.  This covers every numeric
    # phase (the game uses 1-13) without patching shared digit/kanji glyphs or
    # overlapping the v0.9 auxiliary-text pool.
    renderer = ASSETS[3]
    pool = ASSETS[4]
    if pool.offset != PHASE_POOL_FILE_OFFSET:
        raise AssertionError("phase pool spec disagrees with fixed-bank address")

    def replace_renderer(address: int, expected: bytes, replacement: bytes) -> None:
        if len(expected) != len(replacement):
            raise AssertionError("renderer replacement must be length-preserving")
        actual = bytes(output[address : address + len(expected)])
        if actual != expected:
            raise AssertionError(
                f"unexpected renderer bytes at 0x{address:06X}: {actual.hex()}"
            )
        output[address : address + len(replacement)] = replacement

    # Replace the three auxiliary pointer-table reads with fixed word indices
    # into the new segment.  The native renderer doubles each index.
    direct_loads = {
        0x328F16: PHASE_SENTINEL_OFFSETS["FINAL"] // 2,
        0x328F3E: PHASE_SENTINEL_OFFSETS["SEMIFINAL"] // 2,
        0x328F67: PHASE_SENTINEL_OFFSETS["ROUND"] // 2,
    }
    for address, word_index in direct_loads.items():
        expected = bytes(output[address : address + 9])
        if expected[:3] != b"\xB8\xB1\x4A" or expected[3:6] != b"\x8E\xC0\x26":
            raise AssertionError(f"unexpected phase pointer load at 0x{address:06X}")
        replace_renderer(
            address,
            expected,
            b"\xB8" + word_index.to_bytes(2, "little") + b"\x90" * 6,
        )
    replace_renderer(0x328F49, b"\x6A\x02", b"\x6A\x00")
    replace_renderer(0x328F4D, b"\x6A\x11", b"\x6A\x18")
    replace_renderer(0x328F65, b"\x6A\x12", b"\x6A\x11")
    replace_renderer(
        0x328F75,
        b"\x68\xCB\x4A",
        b"\x68" + PHASE_POOL_SEGMENT.to_bytes(2, "little"),
    )

    if any(output[pool.offset : pool.offset + pool.length]):
        raise AssertionError("phase text pool is not the verified zero-filled cave")
    phase_layout = {
        "ROUND": 0x00,
        "FINAL": 0x10,
        "SEMIFINAL": 0x1E,
    }
    for label, relative_sentinel in phase_layout.items():
        cpu_physical = 0x40000 + (pool.offset - 0x340000)
        cpu_offset = cpu_physical - (PHASE_POOL_SEGMENT << 4) + relative_sentinel
        if cpu_offset != PHASE_SENTINEL_OFFSETS[label]:
            raise AssertionError(f"phase pool address mismatch for {label!r}")
        payload = encode_native_string(label)
        start = pool.offset + relative_sentinel + 2
        end = start + len(payload)
        if end > pool.offset + pool.length:
            raise AssertionError(f"phase text does not fit pool: {label!r}")
        output[start:end] = payload

    allowed = tuple((spec.offset, spec.offset + spec.length) for spec in ASSETS)
    escaped = [
        index
        for index, (before, after) in enumerate(zip(source, output))
        if before != after
        and not any(start <= index < end for start, end in allowed)
    ]
    if escaped:
        raise AssertionError(
            f"{len(escaped)} bytes changed outside guarded spans; "
            f"first=0x{escaped[0]:06X}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    asset_rows = []
    for spec in ASSETS:
        asset = bytes(output[spec.offset : spec.offset + spec.length])
        if len(asset) != spec.length:
            raise AssertionError(f"wrong asset length for {spec.asset_id}")
        path = output_dir / spec.filename
        path.write_bytes(asset)
        asset_rows.append(
            {
                "id": spec.asset_id,
                "offset": f"0x{spec.offset:06X}",
                "length": spec.length,
                "expected_source_sha256": spec.source_sha256,
                "asset": spec.filename,
                "asset_sha256": sha256(asset),
                "changed_byte_count": sum(
                    before != after
                    for before, after in zip(
                        source[spec.offset : spec.offset + spec.length], asset
                    )
                ),
            }
        )

    transfer_preview = output_dir / "program_deck_transfer_text_preview_v0_9.png"
    tournament_preview = output_dir / "tournament_header_preview_v0_9.png"
    phase_preview = output_dir / "tournament_phase_text_preview_v0_9.png"
    render_preview(transfer_canvas, 64, 24, TRANSFER_PALETTE, transfer_preview)
    render_preview(tournament_canvas, 56, 16, TOURNAMENT_PALETTE, tournament_preview)
    phase_canvas = [6] * (96 * 48)
    for label, y in (("ROUND 1", 2), ("ROUND 13", 14), ("SEMIFINAL", 26), ("FINAL", 38)):
        draw_text(
            phase_canvas,
            96,
            48,
            label,
            (96 - text_width(label)) // 2,
            y,
            ink=13,
            shadow=2,
        )
    render_preview(phase_canvas, 96, 48, TOURNAMENT_PALETTE, phase_preview, scale=4)

    changed_offsets = [
        index for index, (before, after) in enumerate(zip(source, output)) if before != after
    ]
    report: dict[str, object] = {
        "family": "program_transfer_and_tournament_header",
        "version": "0.9",
        "source_rom_sha256": SOURCE_ROM_SHA256,
        "format": "WonderSwan Color packed 4-bpp; 8x8 tiles; high nibble is left pixel",
        "labels": [
            {
                "source": "デッキデータを送信します",
                "replacement": ["SENDING", "DECK DATA"],
                "canvas": [64, 24],
                "palette_nibbles": {"background": 1, "ink": 3, "shadow": 2},
            },
            {
                "source": "トーナメント",
                "replacement": "TOURNAMENT",
                "canvas": [56, 16],
                "palette_nibbles": {"background": 6, "ink": 13, "shadow": 2},
            },
            {
                "source": ["1回戦-13回戦", "準決勝戦", "決勝戦"],
                "replacement": ["ROUND 1-ROUND 13", "SEMIFINAL", "FINAL"],
                "renderer_rom_span": ["0x328F10", "0x328F80"],
                "native_map_wram": ["0xC022-0xC027", "0xC062-0xC067"],
                "map_aliases": [
                    "0x2822-0x2827 / 0x2862-0x2867",
                    "0x3022-0x3027 / 0x3062-0x3067",
                ],
                "shared_japanese_glyph_tiles_modified": False,
            },
        ],
        "assets": asset_rows,
        "previews": [
            {
                "file": transfer_preview.name,
                "sha256": sha256(transfer_preview.read_bytes()),
            },
            {
                "file": tournament_preview.name,
                "sha256": sha256(tournament_preview.read_bytes()),
            },
            {
                "file": phase_preview.name,
                "sha256": sha256(phase_preview.read_bytes()),
            },
        ],
        "safety": {
            "guarded_spans": [
                [f"0x{start:06X}", f"0x{end:06X}"] for start, end in allowed
            ],
            "changed_byte_count": len(changed_offsets),
            "outside_guarded_spans_unchanged": True,
        },
    }
    report_path = output_dir / "program_tournament_assets_report_v0_9.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path, help="verified Japanese Rev 1 WSC ROM")
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    report = build_assets(args.rom.read_bytes(), args.output_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
