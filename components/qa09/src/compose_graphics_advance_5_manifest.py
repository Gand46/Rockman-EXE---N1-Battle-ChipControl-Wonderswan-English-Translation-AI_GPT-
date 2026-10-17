#!/usr/bin/env python3
"""Compose the cumulative Advance 5 manifest from the verified Advance 3 manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


VERSION = "0.10.7-graphics-a5"
UPDATES = {
    "program_deck_manual_stats_bg0_map": (
        "assets/program_deck_manual_stats_bg0_map_graphics_a4.bin",
        "ed8ae281f04b285ce93c5ad92411ce2643fd1ece8600a0042f7a10ec1b2d1cad",
    ),
    "program_deck_manual_internal_tiles": (
        "assets/program_deck_manual_internal_tiles_graphics_a4.bin",
        "f465f7ecb14960d06156a34970dc4d98db1f19b101bd68b16ddacd4358a88218",
    ),
    "pet_submenu_chip_folder_bg0_map": (
        "assets/pet_submenu_chip_folder_bg0_map_graphics_a5.bin",
        "23172a777fb2f55434e275171a8dbe60868300977469690107cd4864e8b5eb85",
    ),
}


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.base_manifest.read_text(encoding="utf-8"))
    if manifest.get("project_version") != "0.10.7-graphics-a3":
        raise ValueError("expected the exact cumulative A3 manifest")
    manifest["project_version"] = VERSION
    manifest["scope"] = (
        "Cumulative Graphics Advance 5 built on the exact approved Advance 4 ROM. "
        "It preserves Advances 1-4 and changes only twelve BG0 map references in the "
        "main Chip Folder screen, reusing without modification the twelve CHIP FOLDER "
        "patterns approved in Advance 3. Tile banks, palettes, code, dialogue, dynamic "
        "values, icons, list contents, frames and all non-target map cells remain unchanged."
    )
    seen = set()
    for entry in manifest.get("binary_entries", []):
        entry_id = entry.get("id")
        if entry_id not in UPDATES:
            continue
        asset, expected_hash = UPDATES[entry_id]
        path = args.output.parent / asset
        payload = path.read_bytes()
        if len(payload) != int(entry["length"]) or sha256(payload) != expected_hash:
            raise ValueError(f"generated asset differs: {path}")
        entry["asset"] = asset
        entry["asset_sha256"] = expected_hash
        seen.add(entry_id)
    if seen != set(UPDATES):
        raise ValueError(f"manifest update targets missing: {sorted(set(UPDATES) - seen)}")
    if len(manifest.get("entries", [])) != 271 or len(manifest.get("binary_entries", [])) != 80:
        raise ValueError("cumulative manifest inventory differs")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "output": str(args.output), "sha256": sha256(args.output.read_bytes())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
