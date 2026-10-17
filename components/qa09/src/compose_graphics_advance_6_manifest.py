#!/usr/bin/env python3
"""Compose the cumulative A6 manifest from the exact approved A5 manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


VERSION = "0.10.7-graphics-a6"
A5_VERSION = "0.10.7-graphics-a5"
A5_MANIFEST_SHA256 = "10beb8737f57fcf42655069222da28d708bb765fa928579b0211666203156308"
B1_OUTPUT_SHA256 = "edf6f689f8142ef02d11e473f33a2c84b65442db19f090b16a12e0f5246ff7af"
CALL_SOURCE_SHA256 = "3eac881e4c04ec4d115240e6b04bf95aece3f8c1813d57817ed931cdb4eac45d"
CALL_ASSET_SHA256 = "63c4dfd5c3f4b7a5f8535b6eddfe053f7109e535c1160e05f0be5e19cd7276b0"


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a5-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    source = args.a5_manifest.read_bytes()
    if sha256(source) != A5_MANIFEST_SHA256:
        raise ValueError("A6 requires the exact approved A5 manifest")
    manifest = json.loads(source)
    if manifest.get("project_version") != A5_VERSION:
        raise ValueError("unexpected A5 project version")

    manifest["project_version"] = VERSION
    manifest["scope"] = (
        "Cumulative Graphics Advance 6 built on the exact approved Advance 5 ROM. "
        "It changes only the Backpack quantity-renderer far call and hosts a compact "
        "3x5 digit wrapper in the verified unreferenced tail of the existing B1 data "
        "allocation. Each visible quantity is reassigned to one exclusive runtime tile "
        "pair selected only after a complete ROM-map and live cross-layer consumer audit; "
        "the shared large numeric font, digits inside chip names, "
        "capacities, MB labels, icons, card statistics, maps, palettes, dialogue and all "
        "other A5 content remain unchanged."
    )

    b1_rows = [entry for entry in manifest["binary_entries"] if entry["id"] == "battle_messages_b1_data"]
    if len(b1_rows) != 1:
        raise AssertionError("A5 B1 data entry is not unique")
    b1_rows[0]["asset"] = "assets/battle_messages_b1_data_graphics_a6.bin"
    b1_rows[0]["asset_sha256"] = B1_OUTPUT_SHA256

    manifest["binary_entries"].append({
        "id": "graphics_a6_backpack_quantity_call",
        "offset": "0x33835C",
        "length": 5,
        "expected_sha256": CALL_SOURCE_SHA256,
        "asset": "assets/backpack_quantity_callsite_graphics_a6.bin",
        "asset_sha256": CALL_ASSET_SHA256,
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "PASS",
        "version": VERSION,
        "source_manifest_sha256": A5_MANIFEST_SHA256,
        "output_manifest_sha256": sha256(args.output.read_bytes()),
        "binary_entries": len(manifest["binary_entries"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
