#!/usr/bin/env python3
"""Compose the cumulative A7 manifest from the exact approved A6 manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


VERSION = "0.10.7-graphics-a7"
A6_VERSION = "0.10.7-graphics-a6"
A6_MANIFEST_SHA256 = "094c7c6e544ad8a23a99f5d262502e12b5ff25e6ea2554970b919cb20c4270fe"
CALL_SOURCE_SHA256 = "fd7051a9b39dc1dac575afd8cb708c29b36fd7fcca29bf24be8a2dc1a3f07c04"
CALL_ASSET_SHA256 = "8fb92af601334ca5905b034f643e675e81f5eb7c13eff845d3a0085d19aad419"


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a6-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    source = args.a6_manifest.read_bytes()
    if sha256(source) != A6_MANIFEST_SHA256:
        raise ValueError("A7 requires the exact approved A6 manifest")
    manifest = json.loads(source)
    if manifest.get("project_version") != A6_VERSION:
        raise ValueError("unexpected A6 project version")

    manifest["project_version"] = VERSION
    manifest["scope"] = (
        "Cumulative Graphics Advance 7 built on the exact approved Advance 6 ROM. "
        "It centers only the 16-cell auxiliary intertitle 1 MONTH LATER... by changing "
        "the scene-state 0x0D x-coordinate argument from column 11 to column 6. The text "
        "record, pointer, shared renderer, font, palettes, y coordinate, backgrounds and "
        "all other A6 content remain unchanged."
    )
    manifest["binary_entries"].append({
        "id": "graphics_a7_month_later_x_call",
        "offset": "0x32A6F7",
        "length": 2,
        "expected_sha256": CALL_SOURCE_SHA256,
        "asset": "assets/month_later_x_callsite_graphics_a7.bin",
        "asset_sha256": CALL_ASSET_SHA256,
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "PASS",
        "version": VERSION,
        "source_manifest_sha256": A6_MANIFEST_SHA256,
        "output_manifest_sha256": sha256(args.output.read_bytes()),
        "binary_entries": len(manifest["binary_entries"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
