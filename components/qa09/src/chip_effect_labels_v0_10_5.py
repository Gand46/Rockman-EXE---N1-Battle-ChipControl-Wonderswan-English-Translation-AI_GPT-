#!/usr/bin/env python3
"""Build the six-glyph large-card chip-effect labels for v0.10.5.

The v0.10.4 database is used as the guarded source.  Every label longer than
six glyphs is shortened deterministically while preserving its full numeric
value and the supported ``~``/``+`` modifiers.  Existing pointers and record
addresses remain unchanged; only the beginning of each affected terminated
string is replaced, leaving the remainder of the fixed bank byte-identical.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import bcc_reference as bcc  # noqa: E402


VERSION = "0.10.5"
BASE_ROM_SHA256 = "ba315859105dbb2acbc5c775f00ec8c9b09f612fd9d3cd00e5a49e4670c4cbb2"
BASE_ASSET_SHA256 = "46d33f0f4c1320ad754696a92f6f98ef97424acf67f3f89d9fe1829fe68acd8e"
POINTER_ASSET_SHA256 = "baf060ade9e8198c881aed504201809ea369796001993fb4a23b48086fe28460"
OUTPUT_ASSET_SHA256 = "9973bd4e3042d71189c26ea6ab852c5b86472aba0b35396e08be2cc048aea52f"

DATA_START = 0x369550
DATA_END = 0x36A4E0
DATA_LENGTH = DATA_END - DATA_START
SUPPORTED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+~")
EFFECT_PATTERN = re.compile(
    r"^(?P<prefix>~?)(?P<word>[A-Z]+)(?P<number>[0-9]+)(?P<suffix>\+?)$"
)


def sha256(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def shorten_effect(text: str) -> str:
    """Return the reviewed maximum-six-glyph representation of *text*."""
    if text == "NO DATA":
        return "NODATA"
    if len(text) <= 6:
        return text
    match = EFFECT_PATTERN.fullmatch(text)
    if match is None:
        raise ValueError(f"cannot safely abbreviate effect label: {text!r}")
    prefix = match.group("prefix")
    word = match.group("word")
    number = match.group("number")
    suffix = match.group("suffix")
    word_budget = 6 - len(prefix) - len(number) - len(suffix)
    if word_budget < 1:
        raise ValueError(f"effect has no mnemonic space at six glyphs: {text!r}")
    shortened = prefix + word[:word_budget] + number + suffix
    if len(shortened) != 6:
        raise AssertionError(f"unexpected shortened length: {text!r} -> {shortened!r}")
    return shortened


def modifier_and_number(text: str) -> tuple[str, str, str]:
    match = EFFECT_PATTERN.fullmatch(text)
    if match is None:
        return "", "", ""
    return match.group("prefix"), match.group("number"), match.group("suffix")


def load_rows(rom: bytes, decode: dict[int, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(bcc.WSC_CHIP_COUNT):
        pointer = bcc.wsc_pointer(
            rom, bcc.EFFECT_LABELS.pointer_start, index, "effect_labels"
        )
        words = bcc.read_words(rom, pointer, f"effect_labels[{index}]")
        text = bcc.decode_gba_words(words, decode)
        rows.append({
            "index": index,
            "pointer": pointer,
            "text": text,
            "record_bytes": len(words) * 2,
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-rom", type=Path,
        default=ROOT / "build/Rockman_EXE_N1_Battle_English_v0.10.4.wsc",
    )
    parser.add_argument(
        "--base-asset", type=Path,
        default=ROOT / "translation/assets/effect_labels_data_v0_10_1.bin",
    )
    parser.add_argument(
        "--pointer-asset", type=Path,
        default=ROOT / "translation/assets/effect_labels_pointers.bin",
    )
    parser.add_argument(
        "--table", type=Path, default=ROOT / "tables/n1battle_jp.tbl",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "translation/assets/effect_labels_data_v0_10_5.bin",
    )
    parser.add_argument(
        "--report", type=Path,
        default=ROOT / "translation/assets/chip_effect_label_asset_report_v0_10_5.json",
    )
    args = parser.parse_args()

    rom = args.base_rom.read_bytes()
    base_asset = args.base_asset.read_bytes()
    pointer_asset = args.pointer_asset.read_bytes()
    if len(rom) != bcc.WSC_SIZE or sha256(rom) != BASE_ROM_SHA256:
        raise ValueError("base ROM is not the canonical v0.10.4 build")
    if len(base_asset) != DATA_LENGTH or sha256(base_asset) != BASE_ASSET_SHA256:
        raise ValueError("unexpected v0.10.4 effect-label asset")
    if sha256(pointer_asset) != POINTER_ASSET_SHA256:
        raise ValueError("effect-label pointer asset changed")
    if rom[DATA_START:DATA_END] != base_asset:
        raise ValueError("base ROM and base effect-label asset differ")

    decode = bcc.load_decode_table(args.table)
    encode = bcc.load_encode_table(args.table)
    rows = load_rows(rom, decode)
    targets: dict[int, dict[str, Any]] = {}
    indices_by_pointer: dict[int, list[int]] = defaultdict(list)
    for row in rows:
        pointer = int(row["pointer"])
        indices_by_pointer[pointer].append(int(row["index"]))
        previous = targets.setdefault(pointer, row)
        if previous["text"] != row["text"] or previous["record_bytes"] != row["record_bytes"]:
            raise AssertionError("one pointer resolves to incompatible records")

    output = bytearray(base_asset)
    mappings: list[dict[str, Any]] = []
    output_texts: dict[str, list[str]] = defaultdict(list)
    changed_target_spans: list[tuple[int, int]] = []
    for pointer, row in sorted(targets.items()):
        before = str(row["text"])
        after = shorten_effect(before)
        output_texts[after].append(before)
        # Five populated special chips intentionally have an empty effect
        # field in the verified database; preserve those empty records.
        if len(after) > 6 or not set(after) <= SUPPORTED:
            raise AssertionError(f"invalid v0.10.5 effect label: {after!r}")
        if before != "NO DATA":
            old_prefix, old_number, old_suffix = modifier_and_number(before)
            new_prefix, new_number, new_suffix = modifier_and_number(after)
            if (old_prefix, old_number, old_suffix) != (new_prefix, new_number, new_suffix):
                raise AssertionError(f"number/modifier changed: {before!r} -> {after!r}")
        encoded = bcc.encode_static(after, encode, style=0x0600)
        payload = struct.pack("<" + "H" * len(encoded), *encoded)
        record_bytes = int(row["record_bytes"])
        if len(payload) > record_bytes:
            raise AssertionError(f"replacement expands record: {before!r} -> {after!r}")
        relative = pointer - DATA_START
        if not 0 <= relative <= len(output) - record_bytes:
            raise AssertionError(f"effect pointer outside guarded bank: 0x{pointer:06X}")
        if before != after:
            output[relative:relative + len(payload)] = payload
            changed_target_spans.append((relative, relative + record_bytes))
            mappings.append({
                "pointer": f"0x{pointer:06X}",
                "before": before,
                "after": after,
                "indices": indices_by_pointer[pointer],
                "occurrences": len(indices_by_pointer[pointer]),
                "record_bytes": record_bytes,
                "replacement_bytes": len(payload),
            })

    collisions = {
        output_text: sorted(set(source_texts))
        for output_text, source_texts in output_texts.items()
        if len(set(source_texts)) > 1
    }
    if collisions:
        raise AssertionError(f"six-glyph abbreviations collide: {collisions}")

    final_asset = bytes(output)
    changed_offsets = [
        index for index, (before, after) in enumerate(zip(base_asset, final_asset))
        if before != after
    ]
    outside_active_records = [
        index for index in changed_offsets
        if not any(start <= index < end for start, end in changed_target_spans)
    ]
    if outside_active_records:
        raise AssertionError("asset changed outside affected live records")
    output_hash = sha256(final_asset)
    if OUTPUT_ASSET_SHA256 and output_hash != OUTPUT_ASSET_SHA256:
        raise AssertionError("six-glyph asset is not reproducible")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(final_asset)

    final_rom = bytearray(rom)
    final_rom[DATA_START:DATA_END] = final_asset
    # This preview checksum is reported only to make the generated asset easy
    # to audit; the release composer performs the authoritative update.
    checksum = sum(final_rom[:-2]) & 0xFFFF
    final_rom[-2:] = checksum.to_bytes(2, "little")

    decoded_after: list[str] = []
    for row in rows:
        pointer = int(row["pointer"])
        decoded_after.append(shorten_effect(str(row["text"])))
    report = {
        "format": "n1-chip-effect-label-assets-v0.10.5",
        "project_version": VERSION,
        "status": "PASS",
        "native_display": [224, 144],
        "renderer": "WSC large-card 8x16 font, style 0x0600",
        "policy": {
            "maximum_visible_glyphs": 6,
            "method": "preserve prefix/suffix modifiers and complete numeric value; fill remaining capacity with the leading mnemonic letters",
            "no_data": "NO DATA -> NODATA",
        },
        "rom_span": {"offset": f"0x{DATA_START:06X}", "length": DATA_LENGTH},
        "inventory": {
            "pointer_rows": len(rows),
            "unique_targets": len(targets),
            "changed_pointer_rows": sum(
                len(indices_by_pointer[int(row["pointer"])]) for row in targets.values()
                if shorten_effect(str(row["text"])) != row["text"]
            ),
            "changed_unique_targets": len(mappings),
            "no_data_rows": sum(text == "NODATA" for text in decoded_after),
            "maximum_effect_length": max(map(len, decoded_after)),
            "all_labels_within_six_glyphs": all(len(text) <= 6 for text in decoded_after),
            "abbreviation_collisions": len(collisions),
        },
        "integrity": {
            "base_rom_sha256": sha256(rom),
            "base_asset_sha256": sha256(base_asset),
            "output_asset_sha256": output_hash,
            "pointer_asset_sha256": sha256(pointer_asset),
            "pointers_changed": 0,
            "changed_asset_bytes": len(changed_offsets),
            "outside_affected_live_records": len(outside_active_records),
            "unreferenced_bank_tail_preserved": True,
            "preview_wonderswan_checksum": f"0x{checksum:04X}",
        },
        "mappings": mappings,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    args.report.write_text(rendered, encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output),
        "output_sha256": output_hash,
        "changed_unique_targets": len(mappings),
        "changed_pointer_rows": report["inventory"]["changed_pointer_rows"],
        "maximum_effect_length": report["inventory"]["maximum_effect_length"],
        "no_data_rows": report["inventory"]["no_data_rows"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
