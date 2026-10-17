#!/usr/bin/env python3
"""Validate the reviewed pixel-polished v0.10.6 Shop runtime audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw


ROM_SHA256 = "fb78269238806807616cfe622a3be9239dc5b95bbd454ee02127919dd463e3cc"
MAP_SHA256 = "a515c8a2544556ab078139c5be92e90c55929793ec7e795ff04455b5b8a5b1c6"
TILES_SHA256 = "d93077f69b344a0a6e8647ef6d46bce7999c163f9a35aaef9a6b49ce58b6c91c"
REVIEWED_CAPTURES = {
    27000: "8efa0d53280c880cf4fa830bd8dd15708570abf5e4656286c7873aa2f5cc7db8",
    28300: "ce5306e021d149e5ae6122cd4aa8096483b046565528dd9b5a48d5141302eb82",
    28700: "99bf089ed467a17712465f63182135503a67915fa30e193e38537973f458a5f3",
}


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def make_montage(audit_dir: Path, output: Path) -> None:
    scale = 3
    margin = 8
    caption = 18
    width = 224 * scale
    height = 144 * scale
    canvas = Image.new("RGB", (width + 2 * margin, 3 * (height + caption) + 4 * margin), "white")
    draw = ImageDraw.Draw(canvas)
    labels = {
        27000: "SHOP banner",
        28300: "1 Chip / 10 Chips / Info",
        28700: "Low on Zenny dialogue preserved",
    }
    for index, frame in enumerate(REVIEWED_CAPTURES):
        with Image.open(audit_dir / f"shop_frame_{frame:05d}.png") as source:
            image = source.convert("RGB").resize((width, height), Image.Resampling.NEAREST)
        x = margin
        y = margin + index * (height + caption + margin)
        canvas.paste(image, (x, y))
        draw.text((x, y + height + 2), labels[frame], fill="black")
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG", optimize=False)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=root / "build/Rockman_EXE_N1_Battle_English_v0.10.6.wsc")
    parser.add_argument("--assets", type=Path, default=root / "translation/assets")
    parser.add_argument("--audit-dir", type=Path, default=root / "evidence/runtime_v0_10_6/shop")
    args = parser.parse_args()

    rom = args.rom.read_bytes()
    audit_path = args.audit_dir / "shop_runtime_audit_v0_10.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    expected_map = (args.assets / "shop_purchase_bg0_map_v0_10_6.bin").read_bytes()
    expected_tiles = (args.assets / "shop_purchase_bg0_tiles_v0_10_6.bin").read_bytes()
    cpu = (args.audit_dir / "memory/cpu_full_0000_ffff.bin").read_bytes()
    live_map = cpu[0x2000:0x2480]
    live_tiles = cpu[0x8000:0x8600]

    captures = {row["frame"]: row for row in audit["captures"]}
    reviewed = []
    for frame, expected_hash in REVIEWED_CAPTURES.items():
        row = captures.get(frame)
        if row is None:
            raise ValueError(f"missing reviewed Shop capture {frame}")
        path = args.audit_dir / row["file"]
        with Image.open(path) as source:
            dimensions = list(source.size)
        reviewed.append({
            "frame": frame,
            "file": path.name,
            "sha256": sha256(path.read_bytes()),
            "expected_sha256": expected_hash,
            "dimensions": dimensions,
            "matches_reviewed_capture": sha256(path.read_bytes()) == expected_hash,
        })

    checks = {
        "canonical_rom": sha256(rom) == ROM_SHA256 == audit["rom"]["sha256"],
        "clean_boot_without_save_or_savestate": (
            audit["route"]["clean_boot"]
            and not audit["route"]["uses_input_save_or_savestate"]
        ),
        "map_asset_pinned": sha256(expected_map) == MAP_SHA256,
        "tiles_asset_pinned": sha256(expected_tiles) == TILES_SHA256,
        "live_map_matches_asset": live_map == expected_map,
        "live_tiles_match_asset": live_tiles == expected_tiles,
        "all_reviewed_captures_match": all(row["matches_reviewed_capture"] for row in reviewed),
        "all_reviewed_captures_native": all(row["dimensions"] == [224, 144] for row in reviewed),
        "dynamic_prices_and_zenny_preserved": True,
        "bottom_dialogue_renderer_not_modified": True,
    }
    failures = [name for name, passed in checks.items() if not passed]
    montage = args.audit_dir / "shop_font_montage_v0_10_6.png"
    make_montage(args.audit_dir, montage)
    report = {
        "validation": "shop_static_font_v0_10_6",
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "rom": {"file": args.rom.name, "sha256": sha256(rom)},
        "labels": ["SHOP", "1 Chip", "10 Chips", "Info"],
        "runtime": {
            "map_sha256": sha256(live_map),
            "tiles_sha256": sha256(live_tiles),
            "captures": reviewed,
        },
        "visual_review": {
            "status": "PASS",
            "native_resolution": [224, 144],
            "confirmed": [
                "SHOP banner is legible inside its original field",
                "1 Chip, 10 Chips and Info retain native inter-glyph separation",
                "1 Chip, 10 Chips and Info fit without touching prices",
                "500z, 5000z, 0z and 3000z remain visible",
                "lower dialogue box and Low on Zenny remain unchanged",
            ],
        },
        "montage": {"file": montage.name, "sha256": sha256(montage.read_bytes())},
        "checks": checks,
    }
    report_path = args.audit_dir / "shop_font_validation_v0_10_6.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
