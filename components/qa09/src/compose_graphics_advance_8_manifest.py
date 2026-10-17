#!/usr/bin/env python3
"""Compose the cumulative A8 manifest from the exact approved A7 manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


VERSION = "0.10.7-graphics-a8"
A7_VERSION = "0.10.7-graphics-a7"
A7_MANIFEST_SHA256 = "cc3e39705bfa5280567f1fc68fde7a732dbf3a55123ca72aa40704e436b4f045"
TARGET_ENTRY_ID = "pet_no_data_card_tiles"
TARGET_ASSET = "assets/pet_no_data_card_tiles_graphics_a8.bin"


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a7-manifest", required=True, type=Path)
    parser.add_argument("--asset", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    source = args.a7_manifest.read_bytes()
    if sha256(source) != A7_MANIFEST_SHA256:
        raise ValueError("A8 requires the exact approved A7 manifest")
    manifest = json.loads(source)
    if manifest.get("project_version") != A7_VERSION:
        raise ValueError("unexpected A7 project version")
    asset = args.asset.read_bytes()
    if len(asset) != 0x700:
        raise ValueError("A8 NO CHIP card asset must be the complete 0x700-byte bank")

    matches = [entry for entry in manifest.get("binary_entries", [])
               if entry.get("id") == TARGET_ENTRY_ID]
    if len(matches) != 1:
        raise ValueError("the shared NO CHIP card bank entry is not unique")
    entry = matches[0]
    if entry.get("offset") != "0x2B0A20" or int(entry.get("length", 0)) != 0x700:
        raise ValueError("unexpected NO CHIP card bank geometry")
    entry["asset"] = TARGET_ASSET
    entry["asset_sha256"] = sha256(asset)

    manifest["project_version"] = VERSION
    manifest["scope"] = (
        "Cumulative Graphics Advance 8 built on the exact approved Advance 7 ROM. "
        "It removes only the remaining Japanese pixels in the fourth 8-pixel row "
        "below the shared NO CHIP / IS / SELECTED card. The three English rows, "
        "side and lower frame, palette, maps, pointers, code, dynamic data and every "
        "other A7 resource remain unchanged."
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "PASS",
        "version": VERSION,
        "source_manifest_sha256": A7_MANIFEST_SHA256,
        "output_manifest_sha256": sha256(args.output.read_bytes()),
        "replaced_entry": TARGET_ENTRY_ID,
        "asset_sha256": sha256(asset),
        "binary_entries": len(manifest["binary_entries"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
