#!/usr/bin/env python3
"""Compose the cumulative A9 manifest from the exact approved A8 manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


VERSION = "0.10.7-graphics-a9"
A8_VERSION = "0.10.7-graphics-a8"
A8_MANIFEST_SHA256 = "aef62af89624e73f8b9bc5cab7521477fdae683c4202c6c3188419268843ad59"
TARGET_ENTRY_ID = "program_deck_live_ui_tiles"
TARGET_ASSET = "assets/program_deck_live_ui_tiles_graphics_a9.bin"


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a8-manifest", required=True, type=Path)
    parser.add_argument("--asset", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source = args.a8_manifest.read_bytes()
    if sha256(source) != A8_MANIFEST_SHA256:
        raise ValueError("A9 requires the exact approved A8 manifest")
    manifest = json.loads(source)
    if manifest.get("project_version") != A8_VERSION:
        raise ValueError("unexpected A8 project version")
    asset = args.asset.read_bytes()
    if len(asset) != 0x1EF0:
        raise ValueError("A9 Program Deck asset must be the complete 0x1EF0-byte bank")
    matches = [entry for entry in manifest.get("binary_entries", []) if entry.get("id") == TARGET_ENTRY_ID]
    if len(matches) != 1:
        raise ValueError("the Program Deck tile-bank entry is not unique")
    entry = matches[0]
    if entry.get("offset") != "0x07CD20" or int(entry.get("length", 0)) != 0x1EF0:
        raise ValueError("unexpected Program Deck tile-bank geometry")
    entry["asset"] = TARGET_ASSET
    entry["asset_sha256"] = sha256(asset)
    manifest["project_version"] = VERSION
    manifest["scope"] = (
        "Cumulative Graphics Advance 9 built on the exact approved Advance 8 ROM. "
        "It restores only the original lower-left 8x8 quadrant of the first MegaMan "
        "chip beside OK in PROGRAM DECK. The English toolbar labels, maps, palettes, "
        "code, pointers, text and every other A8 resource remain unchanged."
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "PASS", "version": VERSION,
        "source_manifest_sha256": A8_MANIFEST_SHA256,
        "output_manifest_sha256": sha256(args.output.read_bytes()),
        "replaced_entry": TARGET_ENTRY_ID,
        "asset_sha256": sha256(asset),
        "binary_entries": len(manifest["binary_entries"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
