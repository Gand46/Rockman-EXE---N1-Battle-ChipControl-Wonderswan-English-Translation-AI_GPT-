#!/usr/bin/env python3
"""Trim the unchanged tail of the v0.8 Program Deck atlas.

The final 0x110 bytes of the original 0x2000-byte manifest span overlap the
Chip Folder/Data Library tile bank.  They were byte-identical to the Japanese
ROM in v0.8, so v0.9 publishes only the non-overlapping prefix.  This prevents
manifest order from restoring Japanese Chip Folder tiles.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SOURCE_ROM_SHA256 = "4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed"
SOURCE_START = 0x07CD20
SOURCE_LENGTH = 0x2000
PREFIX_LENGTH = 0x1EF0
OVERLAP_START = SOURCE_START + PREFIX_LENGTH
OVERLAP_LENGTH = SOURCE_LENGTH - PREFIX_LENGTH
SOURCE_PREFIX_SHA256 = "ef6d011c4d289338ecbd8c3bdf93da37b271295b442c066e3963ea0d1421bd97"
V08_ASSET = "program_deck_live_ui_tiles_v0_8.bin"
V08_ASSET_SHA256 = "39b85f75f1020e7ebed792969ba6aad026492ed03c3d8e60d2af3c4bd273d73b"
V09_ASSET = "program_deck_live_ui_tiles_v0_9.bin"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    rom = args.rom.read_bytes()
    if len(rom) != 0x400000 or sha256(rom) != SOURCE_ROM_SHA256:
        raise ValueError("unexpected source ROM; expected verified Japanese Rev 1")
    source_span = rom[SOURCE_START:SOURCE_START + SOURCE_LENGTH]
    if sha256(source_span[:PREFIX_LENGTH]) != SOURCE_PREFIX_SHA256:
        raise ValueError("Program Deck prefix source hash changed")

    old_path = root / "translation" / "assets" / V08_ASSET
    old = old_path.read_bytes()
    if len(old) != SOURCE_LENGTH or sha256(old) != V08_ASSET_SHA256:
        raise ValueError("unexpected v0.8 Program Deck live atlas")
    if old[PREFIX_LENGTH:] != source_span[PREFIX_LENGTH:]:
        raise ValueError("overlapping v0.8 tail is not source-identical")

    asset = old[:PREFIX_LENGTH]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / V09_ASSET).write_bytes(asset)
    report = {
        "family": "program_deck_live_overlap_guard",
        "project_version": "0.9.0",
        "source_rom_sha256": SOURCE_ROM_SHA256,
        "asset": {
            "offset": f"0x{SOURCE_START:06X}",
            "length": len(asset),
            "source_sha256": SOURCE_PREFIX_SHA256,
            "file": V09_ASSET,
            "sha256": sha256(asset),
        },
        "excluded_source_identical_overlap": {
            "start": f"0x{OVERLAP_START:06X}",
            "length": OVERLAP_LENGTH,
            "owner": "pet_submenu_chip_library_tiles_v0_9.bin",
            "v0_8_bytes_equal_source": True,
        },
    }
    (args.output_dir / "program_deck_overlap_asset_report_v0_9.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
