#!/usr/bin/env python3
"""Build the v0.10.4 title layer from the exact user-supplied PNG.

The indexed 224x144 PNG is the only art reference. Its alpha support is
cropped, scaled uniformly to 196x99 with nearest-neighbour sampling and placed
at (14,4) in the safe 224x112 logo layer. Each 8x8 cell is then mapped to the
closest of the game's five original title palettes. The animated background,
palettes, PRESS START, legal text, hidden columns and map rows 14-17 are never
emitted by this generator.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image


SOURCE_ROM_SHA256 = "4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed"
BASE_V0103_SHA256 = "eb53372aa5e7e3b202dab7959669d6787c4776c487f9860951012ffb6d8f08dc"
REFERENCE_SHA256 = "f1394a24454413e44933fb5981825dd97daa93647b05ece03ecb0fbf91b9973e"

# Locked after deterministic generation and visual review.
MASTER_SHA256 = "7773d34d168c7206b7aafa2e12ed03060392af77fe783e5511d6298f9545754d"
EXPECTED_TILE_SHA256 = "7a4556ddef397cf1a20d0cd8ab6552efa589b23a7b561c6145a12bcc5cb214a8"
EXPECTED_MAP_SHA256 = "be3a4b84dfed1ff9d51585d4aa71f0148b60f6bea15a96829def8a30294bebf3"

REFERENCE_SIZE = (224, 144)
REFERENCE_ALPHA_BBOX = (4, 17, 220, 126)
REFERENCE_OPAQUE_PIXELS = 12989
TARGET_SIZE = (196, 99)
TARGET_ORIGIN = (14, 4)
TARGET_BBOX = (14, 4, 210, 103)
V0103_MAP_SHA256 = "3e8911f5e96aec73a93cab9b1a5923aab5f03b56f0ddfb279be685afd8245236"
V0103_TILES_SHA256 = "df551f0e32d0d5954773568063945547bf8361b2fd47cff3c1e024ce435d8915"


def sha256(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_encoder(root: Path):
    path = root / "src/title_logo_assets_v0_10_2.py"
    spec = importlib.util.spec_from_file_location("n1_title_v0102_encoder", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_reference(path: Path) -> tuple[Image.Image, dict[str, object]]:
    payload = path.read_bytes()
    if sha256(payload) != REFERENCE_SHA256:
        raise ValueError("use the exact PNG member supplied in the v0.10.4 ZIP")
    with Image.open(path) as source:
        if source.format != "PNG" or source.mode != "P" or source.size != REFERENCE_SIZE:
            raise ValueError("reference must be the exact 224x144 indexed PNG")
        transparency = source.info.get("transparency")
        palette_entries = len(source.getpalette() or []) // 3
        reference = source.convert("RGBA")
    pixels = list(reference.get_flattened_data())
    opaque_colours = {pixel[:3] for pixel in pixels if pixel[3] == 255}
    if {pixel[3] for pixel in pixels} != {0, 255}:
        raise ValueError("reference alpha must be binary")
    if reference.getchannel("A").getbbox() != REFERENCE_ALPHA_BBOX:
        raise ValueError("reference alpha bounds differ from the supplied PNG")
    if len(set(pixels)) != 62 or len(opaque_colours) != 61:
        raise ValueError("reference must use 62 RGBA entries / 61 visible colours")
    if sum(pixel[3] == 255 for pixel in pixels) != REFERENCE_OPAQUE_PIXELS:
        raise ValueError("reference opaque-pixel count differs from the supplied PNG")
    if any(channel % 17 for colour in opaque_colours for channel in colour):
        raise ValueError("reference contains colours outside RGB444")
    if any(pixel[:3] != (0, 0, 0) for pixel in pixels if pixel[3] == 0):
        raise ValueError("transparent reference pixels contain hidden RGB")
    return reference, {
        "container": "PNG",
        "mode": "indexed with binary transparency",
        "dimensions": list(reference.size),
        "palette_entries": palette_entries,
        "transparent_palette_index": transparency,
        "rgba_entries_used": 62,
        "visible_rgb444_colours": 61,
        "opaque_pixels": REFERENCE_OPAQUE_PIXELS,
        "alpha_bbox_exclusive": list(REFERENCE_ALPHA_BBOX),
    }


def place_reference(reference: Image.Image) -> tuple[Image.Image, dict[str, object]]:
    crop = reference.crop(REFERENCE_ALPHA_BBOX)
    if crop.size != (216, 109):
        raise AssertionError("unexpected alpha-cropped reference size")
    resized = crop.resize(TARGET_SIZE, Image.Resampling.NEAREST)
    layer = Image.new("RGBA", (224, 112), (0, 0, 0, 0))
    layer.paste(resized, TARGET_ORIGIN, resized.getchannel("A"))
    if layer.getchannel("A").getbbox() != TARGET_BBOX:
        raise AssertionError("nearest-neighbour placement has unexpected bounds")
    return layer, {
        "operation": "alpha crop + uniform nearest-neighbour scale + centred placement",
        "source_crop_exclusive": list(REFERENCE_ALPHA_BBOX),
        "source_crop_size": list(crop.size),
        "target_size": list(TARGET_SIZE),
        "target_origin": list(TARGET_ORIGIN),
        "target_bbox_exclusive": list(TARGET_BBOX),
        "scale_x": TARGET_SIZE[0] / crop.width,
        "scale_y": TARGET_SIZE[1] / crop.height,
        "maximum_opaque_y": 102,
        "press_start_clearance_pixels": 1,
        "resampling": "nearest-neighbour",
    }


def usable_colours(palette: list[tuple[int, int, int]]) -> tuple[tuple[int, int, int], ...]:
    result: list[tuple[int, int, int]] = []
    for index, colour in enumerate(palette[1:], start=1):
        if palette.index(colour) == index and colour not in result:
            result.append(colour)
    if not result:
        raise ValueError("title palette contains no opaque colours")
    return tuple(result)


def quantize_master(
    placed: Image.Image,
    palettes: dict[int, list[tuple[int, int, int]]],
) -> tuple[Image.Image, dict[str, object]]:
    master = Image.new("RGBA", placed.size, (0, 0, 0, 0))
    source = placed.load()
    output = master.load()
    candidates = {palette: usable_colours(palettes[palette]) for palette in range(2, 7)}
    palette_cells = {str(palette): 0 for palette in range(2, 7)}
    squared_error = 0
    opaque_pixels = 0
    for cell_y in range(14):
        for cell_x in range(28):
            coordinates = [
                (cell_x * 8 + x, cell_y * 8 + y)
                for y in range(8) for x in range(8)
                if source[cell_x * 8 + x, cell_y * 8 + y][3] == 255
            ]
            if not coordinates:
                continue
            samples = [source[x, y][:3] for x, y in coordinates]
            choices = []
            for palette in range(2, 7):
                error = sum(min(
                    (sample[0] - colour[0]) ** 2
                    + (sample[1] - colour[1]) ** 2
                    + (sample[2] - colour[2]) ** 2
                    for colour in candidates[palette]
                ) for sample in samples)
                choices.append((error, palette))
            cell_error, palette = min(choices)
            squared_error += cell_error
            opaque_pixels += len(samples)
            palette_cells[str(palette)] += 1
            for (x, y), sample in zip(coordinates, samples):
                colour = min(candidates[palette], key=lambda value: (
                    (sample[0] - value[0]) ** 2
                    + (sample[1] - value[1]) ** 2
                    + (sample[2] - value[2]) ** 2,
                    candidates[palette].index(value),
                ))
                output[x, y] = (*colour, 255)
    pixels = list(master.get_flattened_data())
    if {pixel[3] for pixel in pixels} != {0, 255}:
        raise AssertionError("quantized master alpha is not binary")
    if master.getchannel("A").getbbox() != TARGET_BBOX:
        raise AssertionError("quantization changed the reference silhouette")
    if any(channel % 17 for pixel in pixels if pixel[3] for channel in pixel[:3]):
        raise AssertionError("quantized master contains colours outside RGB444")
    rmse = math.sqrt(squared_error / (opaque_pixels * 3))
    return master, {
        "opaque_pixels": opaque_pixels,
        "unique_opaque_rgb_colours": len({pixel[:3] for pixel in pixels if pixel[3]}),
        "palette_cells": palette_cells,
        "rgb_quantization_rmse_0_255": round(rmse, 6),
        "rgb_quantization_psnr_db": round(20 * math.log10(255 / rmse), 6),
        "alpha_preserved": True,
        "opaque_black_canvas_introduced": False,
    }


def read_regions(rom: bytes, encoder) -> tuple[bytes, bytes, bytes, str]:
    digest = sha256(rom)
    if len(rom) != encoder.ROM_SIZE:
        raise ValueError("title input ROM must be exactly 4 MiB")
    if digest == SOURCE_ROM_SHA256:
        return (
            encoder.source_region(rom, encoder.MAP_REGION, "title map"),
            encoder.source_region(rom, encoder.TILE_REGION, "title tiles"),
            encoder.source_region(rom, encoder.PALETTE_REGION, "title palettes"),
            "verified Japanese Rev 1",
        )
    if digest == BASE_V0103_SHA256:
        regions = []
        for region in (encoder.MAP_REGION, encoder.TILE_REGION, encoder.PALETTE_REGION):
            regions.append(rom[region.offset:region.offset + region.length])
        source_map, source_tiles, source_palette = regions
        if sha256(source_map) != V0103_MAP_SHA256 or sha256(source_tiles) != V0103_TILES_SHA256:
            raise ValueError("unexpected v0.10.3 title assets")
        if sha256(source_palette) != encoder.PALETTE_REGION.source_sha256:
            raise ValueError("v0.10.3 title palettes differ from the Japanese source")
        return source_map, source_tiles, source_palette, "verified v0.10.3 QA base"
    raise ValueError("expected Japanese Rev 1 or the canonical v0.10.3 QA base")


def difference(path: Path, payload: bytes) -> dict[str, object] | None:
    if not path.is_file():
        return None
    previous = path.read_bytes()
    return {
        "file": path.name,
        "previous_sha256": sha256(previous),
        "length_equal": len(previous) == len(payload),
        "changed_bytes": sum(a != b for a, b in zip(previous, payload))
        + abs(len(previous) - len(payload)),
    }


def enforce(label: str, payload: bytes, expected: str) -> None:
    if expected and sha256(payload) != expected:
        raise AssertionError(f"{label} differs from the reviewed v0.10.4 output")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-rom", required=True, type=Path)
    parser.add_argument(
        "--reference", type=Path,
        default=Path(__file__).resolve().parents[1]
        / "translation/assets/title_logo_reference_v0_10_4.png",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path(__file__).resolve().parents[1] / "translation/assets",
    )
    parser.add_argument("--base-rom", type=Path)
    parser.add_argument("--patched-rom", type=Path)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    encoder = load_encoder(root)
    rom = args.source_rom.read_bytes()
    source_map, source_tiles, source_palette, input_kind = read_regions(rom, encoder)
    palettes = encoder.decode_palettes(source_palette)
    reference, reference_metrics = load_reference(args.reference)
    placed, transform_metrics = place_reference(reference)
    master, quantization_metrics = quantize_master(placed, palettes)
    tiles, tilemap, capacity = encoder.build_assets(master, source_map, palettes)

    serialized = BytesIO()
    master.save(serialized, format="PNG")
    enforce("master", serialized.getvalue(), MASTER_SHA256)
    enforce("tiles", tiles, EXPECTED_TILE_SHA256)
    enforce("map", tilemap, EXPECTED_MAP_SHA256)
    if encoder.roundtrip_master(tilemap, tiles, palettes).tobytes() != master.tobytes():
        raise AssertionError("title asset round-trip differs from the quantized master")
    if capacity["spare_tiles"] < 1:
        raise AssertionError("title conversion leaves no spare tile")

    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    master_path = output / "title_logo_master_v0_10_4.png"
    tile_path = output / "main_logo_tiles_v0_10_4.bin"
    map_path = output / "main_logo_bg0_map_v0_10_4.bin"
    preview_path = output / "title_logo_master_preview_v0_10_4.png"
    report_path = output / "title_logo_asset_report_v0_10_4.json"
    master.save(master_path, format="PNG")
    tile_path.write_bytes(tiles)
    map_path.write_bytes(tilemap)
    encoder.create_preview(master, preview_path)

    qa = None
    if args.base_rom or args.patched_rom:
        if not args.base_rom or not args.patched_rom:
            raise ValueError("--base-rom and --patched-rom must be supplied together")
        encoder.BASE_V0101_SHA256 = BASE_V0103_SHA256
        qa = encoder.patch_qa_rom(args.base_rom, args.patched_rom, tiles, tilemap)

    report = {
        "format": "n1-title-logo-assets-v0.10.4",
        "status": "PASS",
        "reference": {
            "file": args.reference.name,
            "sha256": sha256(args.reference.read_bytes()),
            "sole_art_reference": True,
            **reference_metrics,
        },
        "transform": transform_metrics,
        "master": {
            "file": master_path.name,
            "sha256": sha256(master_path.read_bytes()),
            "dimensions": list(master.size),
            **quantization_metrics,
        },
        "input_rom": {
            "kind": input_kind,
            "sha256": sha256(rom),
            "map_sha256": sha256(source_map),
            "tiles_sha256": sha256(source_tiles),
            "palettes_sha256": sha256(source_palette),
        },
        "canonical_source_guards": {
            "rom_sha256": SOURCE_ROM_SHA256,
            "map_sha256": encoder.MAP_REGION.source_sha256,
            "tiles_sha256": encoder.TILE_REGION.source_sha256,
            "palettes_sha256": encoder.PALETTE_REGION.source_sha256,
        },
        "outputs": {
            "tiles": {
                "file": tile_path.name, "length": len(tiles), "sha256": sha256(tiles),
                "difference_vs_v0_10_3": difference(
                    output / "main_logo_tiles_v0_10_3.bin", tiles
                ),
            },
            "map": {
                "file": map_path.name, "length": len(tilemap), "sha256": sha256(tilemap),
                "difference_vs_v0_10_3": difference(
                    output / "main_logo_bg0_map_v0_10_3.bin", tilemap
                ),
            },
            "preview": {
                "file": preview_path.name,
                "sha256": sha256(preview_path.read_bytes()),
                "scale": "3x nearest-neighbour",
            },
        },
        "capacity": capacity,
        "protected": {
            "palettes_byte_identical": True,
            "map_rows_14_17_byte_identical": capacity["rows_14_17_byte_identical"],
            "hidden_columns_28_31_byte_identical": capacity[
                "hidden_columns_28_31_byte_identical"
            ],
            "animated_background_not_emitted": True,
            "press_start_sprite_not_emitted": True,
            "credits_not_emitted": True,
            "maximum_logo_y": 102,
        },
        "qa_rom": qa,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": "PASS",
        "reference_sha256": REFERENCE_SHA256,
        "master_sha256": sha256(master_path.read_bytes()),
        "tiles_sha256": sha256(tiles),
        "map_sha256": sha256(tilemap),
        "unique_tiles": capacity["unique_tiles_used"],
        "spare_tiles": capacity["spare_tiles"],
        "final_colours": quantization_metrics["unique_opaque_rgb_colours"],
        "rmse": quantization_metrics["rgb_quantization_rmse_0_255"],
        "maximum_opaque_y": 102,
        "report": report_path.as_posix(),
        "qa_rom": qa,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
