#!/usr/bin/env python3
"""Build and audit the uppercase large-card chip effects for v0.10.1."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import bcc_reference as bcc


OLD_ASSET_SHA256 = "631ccb14c1d57ca503e8b319cb0e882f37d4e233b63b695236a969e855c8c6fb"
NEW_ASSET_SHA256 = "46d33f0f4c1320ad754696a92f6f98ef97424acf67f3f89d9fe1829fe68acd8e"
POINTER_ASSET_SHA256 = "baf060ade9e8198c881aed504201809ea369796001993fb4a23b48086fe28460"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gba_rom", type=Path)
    parser.add_argument("wsc_rom", type=Path)
    parser.add_argument("asset_dir", type=Path)
    parser.add_argument("--gba-table", type=Path, required=True)
    parser.add_argument("--wsc-table", type=Path, required=True)
    args = parser.parse_args()

    gba = bcc.read_verified(args.gba_rom, bcc.GBA_SIZE, bcc.GBA_SHA256, "GBA ROM")
    bcc.validate_gba_identity(gba)
    wsc = bcc.read_verified(args.wsc_rom, bcc.WSC_SIZE, bcc.WSC_SHA256, "WSC ROM")
    gba_decode = bcc.load_decode_table(args.gba_table)
    wsc_encode = bcc.load_encode_table(args.wsc_table)
    assets, _full_report = bcc.build_assets(gba, wsc, gba_decode, wsc_encode)

    old_path = args.asset_dir / "effect_labels_data.bin"
    old = old_path.read_bytes()
    if digest(old) != OLD_ASSET_SHA256:
        raise ValueError("unexpected v0.10 effect-label base asset")
    pointers = assets["effect_labels_pointers.bin"]
    if digest(pointers) != POINTER_ASSET_SHA256:
        raise AssertionError("effect-label pointers changed")

    new = assets["effect_labels_data.bin"]
    if digest(new) != NEW_ASSET_SHA256:
        raise AssertionError("uppercase effect-label output is not reproducible")
    if len(new) != len(old):
        raise AssertionError("effect-label span length changed")

    effects: list[str] = []
    for index in range(bcc.WSC_CHIP_COUNT):
        pointer = bcc.wsc_pointer(wsc, bcc.CHIP_NAMES.pointer_start, index, "chip_names")
        original = bcc.read_words(wsc, pointer, f"chip_names[{index}]")
        available = index > 0 and tuple(original[:-1]) != bcc.JP_NO_DATA
        if not available:
            continue
        text = bcc.gba_text(
            gba, bcc.GBA_EFFECT_TABLE, index - 1, "GBA effect_labels", gba_decode
        )
        effects.append(text)

    nonempty = [text for text in effects if text]
    normalized = [bcc.normalize_large_card_effect(text) for text in nonempty]
    if len(effects) != 113 or len(nonempty) != 108:
        raise AssertionError("verified WSC effect inventory changed")
    if not all(text.isascii() and text == text.upper() and len(text) <= 8 for text in normalized):
        raise AssertionError("an effect cannot be represented by the WSC 8x16 font")

    output_name = "effect_labels_data_v0_10_1.bin"
    args.asset_dir.mkdir(parents=True, exist_ok=True)
    (args.asset_dir / output_name).write_bytes(new)
    changed = [index for index, pair in enumerate(zip(old, new)) if pair[0] != pair[1]]
    report = {
        "format": "n1-chip-effect-label-assets-v0.10.1",
        "status": "PASS",
        "native_display": [224, 144],
        "renderer": "WSC large-card 8x16 font, style 0x0600",
        "source_rom_sha256": bcc.WSC_SHA256,
        "official_gba_reference_sha256": bcc.GBA_SHA256,
        "rom_span": {"offset": "0x369550", "length": len(new)},
        "inventory": {
            "populated_wsc_chips": len(effects),
            "nonempty_effects": len(nonempty),
            "empty_special_effects": len(effects) - len(nonempty),
            "unique_nonempty_effects": len(set(nonempty)),
            "all_normalized_uppercase_ascii": True,
            "maximum_effect_length": max(map(len, normalized)),
        },
        "normalization": "official GBA mixed case -> uppercase for the native WSC renderer",
        "v0_10_asset_sha256": digest(old),
        "output": output_name,
        "output_sha256": digest(new),
        "pointer_asset_sha256": digest(pointers),
        "pointers_changed": 0,
        "changed_bytes": len(changed),
        "changed_words": len({index // 2 for index in changed}),
        "outside_effect_data_span_changed": 0,
    }
    report_path = args.asset_dir / "chip_effect_label_asset_report_v0_10_1.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
