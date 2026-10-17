#!/usr/bin/env python3
"""Rebuild the cleaned English title-logo layer for N1 Battle v0.10.3.

v0.10.2 correctly encoded its reviewed RGBA master, but that master had been
cut from a flat JPEG reference.  A small number of animated-background pixels
were therefore mistaken for opaque logo pixels, and the lower tail touched the
PRESS START sprite.  This generator applies an explicit, reviewed subtractive
mask to the v0.10.2 master and reuses the proven WSC encoder.  It never edits
the animated background, palettes, PRESS START, credits, or map rows 14-17.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from PIL import Image


SOURCE_ROM_SHA256 = "4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed"
BASE_V0102_SHA256 = "b6bdab3a957eac00fb9bac9aadd681d1c9495a9487cde0bef50b4eecc0125f24"
OLD_MASTER_SHA256 = "9f6a15918f5a8016aae4ddef21e71621af3dc0ec137f1adb0f1b21d88cebf83f"
MASTER_SHA256 = "bd0240a61f4ed9febefd422200920e99afaabb8d80ffa8540c333ceeb4199569"
EXPECTED_TILE_SHA256 = "df551f0e32d0d5954773568063945547bf8361b2fd47cff3c1e024ce435d8915"
EXPECTED_MAP_SHA256 = "3e8911f5e96aec73a93cab9b1a5923aab5f03b56f0ddfb279be685afd8245236"

# Inclusive horizontal runs.  These are the complete reviewed mask: 340
# background remnants and 44 lower-tail pixels, 384 pixels in total.
REMOVE_RUNS = {
    16: ((141, 142),), 17: ((142, 142),),
    24: ((16, 17), (19, 20), (150, 151), (154, 154), (156, 156)),
    25: ((16, 16), (148, 148), (150, 151), (154, 154), (158, 158)),
    26: ((16, 20), (149, 151), (154, 155)), 27: ((18, 18), (149, 150)),
    28: ((16, 18),), 38: ((14, 14), (155, 159)), 39: ((157, 160),),
    40: ((157, 157), (159, 160)), 41: ((156, 158), (162, 165)),
    42: ((157, 157), (159, 165)), 43: ((157, 166),),
    44: ((27, 28), (156, 166)), 45: ((27, 28), (156, 166)),
    46: ((27, 27), (154, 166)), 47: ((27, 27), (154, 166)),
    52: ((192, 210),), 53: ((192, 210),), 66: ((207, 207),),
    67: ((207, 207),), 69: ((207, 207),), 70: ((207, 207),),
    71: ((207, 207),), 72: ((206, 207),), 73: ((206, 206),),
    74: ((206, 207),), 75: ((206, 207),), 76: ((204, 204),),
    79: ((204, 204), (206, 207)), 80: ((204, 207),),
    81: ((204, 207),), 82: ((204, 206),),
    83: ((161, 161), (203, 207)), 84: ((161, 161), (203, 207)),
    85: ((161, 161), (203, 207)), 86: ((160, 161), (202, 207)),
    87: ((141, 207),), 88: ((152, 152), (155, 155), (157, 167)),
    89: ((152, 155), (157, 167)), 90: ((152, 154), (156, 167)),
    91: ((153, 153), (155, 167)),
    103: ((91, 93), (98, 101), (106, 113), (118, 120), (127, 130), (133, 133)),
    104: ((106, 111),), 105: ((105, 111),), 106: ((105, 111),),
    107: ((106, 106),),
}


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_encoder(root: Path):
    path = root / "src" / "title_logo_assets_v0_10_2.py"
    spec = importlib.util.spec_from_file_location("n1_title_v0102_encoder", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def cleaned_master(path: Path) -> tuple[Image.Image, Image.Image]:
    payload = path.read_bytes()
    if sha256(payload) != OLD_MASTER_SHA256:
        raise ValueError("unexpected v0.10.2 title-logo master")
    with Image.open(path) as source:
        if source.format != "PNG" or source.mode != "RGBA" or source.size != (224, 112):
            raise ValueError("base title master must be a 224x112 RGBA PNG")
        output = source.copy()
    mask = Image.new("L", output.size, 0)
    removed = 0
    for y, runs in REMOVE_RUNS.items():
        for first, last in runs:
            for x in range(first, last + 1):
                if output.getpixel((x, y))[3] != 255:
                    raise ValueError(f"cleanup run reaches transparent pixel ({x},{y})")
                output.putpixel((x, y), (0, 0, 0, 0))
                mask.putpixel((x, y), 255)
                removed += 1
    if removed != 384:
        raise AssertionError(f"cleanup mask contains {removed} pixels, expected 384")
    if sha256(output.tobytes()) == sha256(Image.open(path).tobytes()):
        raise AssertionError("cleanup did not change the master")
    # PNG serialization is part of the canonical asset identity.
    from io import BytesIO
    encoded = BytesIO()
    output.save(encoded, format="PNG")
    if sha256(encoded.getvalue()) != MASTER_SHA256:
        raise AssertionError("cleaned title master differs from the reviewed v0.10.3 PNG")
    pixels = list(output.getdata())
    if {pixel[3] for pixel in pixels} - {0, 255}:
        raise AssertionError("cleaned master alpha is not binary")
    if any(pixel[:3] != (0, 0, 0) for pixel in pixels if pixel[3] == 0):
        raise AssertionError("cleaned master has hidden RGB under transparent pixels")
    if any(channel % 17 for pixel in pixels if pixel[3] for channel in pixel[:3]):
        raise AssertionError("cleaned master contains colours outside RGB444")
    # PIL's bbox right/bottom coordinates are exclusive; the last opaque
    # pixel is therefore (208, 102).
    if output.getchannel("A").getbbox() != (14, 2, 209, 103):
        raise AssertionError("unexpected cleaned-logo alpha bounds")
    return output, mask


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-rom", required=True, type=Path)
    parser.add_argument("--base-rom", type=Path)
    parser.add_argument("--patched-rom", type=Path)
    parser.add_argument(
        "--base-master", type=Path,
        default=Path(__file__).resolve().parents[1]
        / "translation/assets/title_logo_master_v0_10_2.png",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path(__file__).resolve().parents[1] / "translation/assets",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    encoder = load_encoder(root)
    rom = args.source_rom.read_bytes()
    if len(rom) != encoder.ROM_SIZE or sha256(rom) != SOURCE_ROM_SHA256:
        raise ValueError("unsupported source ROM; expected verified Japanese Rev 1")

    source_map = encoder.source_region(rom, encoder.MAP_REGION, "title map")
    source_tiles = encoder.source_region(rom, encoder.TILE_REGION, "title tiles")
    source_palette = encoder.source_region(rom, encoder.PALETTE_REGION, "title palettes")
    master, mask = cleaned_master(args.base_master)
    palettes = encoder.decode_palettes(source_palette)
    tiles, tilemap, metrics = encoder.build_assets(master, source_map, palettes)
    if sha256(tiles) != EXPECTED_TILE_SHA256 or sha256(tilemap) != EXPECTED_MAP_SHA256:
        raise AssertionError("generated title assets differ from the reviewed v0.10.3 assets")
    if encoder.roundtrip_master(tilemap, tiles, palettes).tobytes() != master.tobytes():
        raise AssertionError("title asset round-trip differs from the clean master")

    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    master_path = output / "title_logo_master_v0_10_3.png"
    mask_path = output / "title_logo_cleanup_mask_v0_10_3.png"
    tile_path = output / "main_logo_tiles_v0_10_3.bin"
    map_path = output / "main_logo_bg0_map_v0_10_3.bin"
    preview_path = output / "title_logo_master_preview_v0_10_3.png"
    master.save(master_path)
    mask.save(mask_path)
    tile_path.write_bytes(tiles)
    map_path.write_bytes(tilemap)
    encoder.create_preview(master, preview_path)

    qa = None
    if args.base_rom or args.patched_rom:
        if not args.base_rom or not args.patched_rom:
            raise ValueError("--base-rom and --patched-rom must be supplied together")
        encoder.BASE_V0101_SHA256 = BASE_V0102_SHA256
        qa = encoder.patch_qa_rom(args.base_rom, args.patched_rom, tiles, tilemap)

    report = {
        "format": "n1-title-logo-assets-v0.10.3",
        "status": "PASS",
        "cause": "opaque animated-background remnants in the flat JPEG-derived v0.10.2 master",
        "cleanup": {
            "method": "explicit subtractive binary-alpha mask",
            "removed_pixels": 384,
            "background_remnants": 340,
            "press_start_clearance_pixels": 44,
            "mask_rows": len(REMOVE_RUNS),
            "mask_runs": sum(len(runs) for runs in REMOVE_RUNS.values()),
            "alpha_bbox_exclusive": list(master.getchannel("A").getbbox()),
            "maximum_opaque_y": 102,
        },
        "master": {
            "file": master_path.name,
            "sha256": sha256(master_path.read_bytes()),
            "opaque_pixels": sum(pixel[3] == 255 for pixel in master.getdata()),
            "transparent_rgb_zero": True,
            "rgb444_only": True,
        },
        "outputs": {
            "tiles": {"file": tile_path.name, "sha256": sha256(tiles), "length": len(tiles)},
            "map": {"file": map_path.name, "sha256": sha256(tilemap), "length": len(tilemap)},
            "mask": {"file": mask_path.name, "sha256": sha256(mask_path.read_bytes())},
            "preview": {"file": preview_path.name, "sha256": sha256(preview_path.read_bytes())},
        },
        "capacity": metrics,
        "protected": {
            "palettes_byte_identical": True,
            "map_rows_14_17_byte_identical": metrics["rows_14_17_byte_identical"],
            "hidden_columns_byte_identical": metrics["hidden_columns_28_31_byte_identical"],
            "animated_background_not_emitted": True,
            "press_start_sprite_not_emitted": True,
            "credits_not_emitted": True,
        },
        "qa_rom": qa,
    }
    report_path = output / "title_logo_asset_report_v0_10_3.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "PASS", "master_sha256": report["master"]["sha256"],
        "tiles_sha256": sha256(tiles), "map_sha256": sha256(tilemap),
        "unique_tiles": metrics["unique_tiles_used"], "spare_tiles": metrics["spare_tiles"],
        "report": report_path.as_posix(), "qa_rom": qa,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
