#!/usr/bin/env python3
"""Shorten the five class labels without moving the auxiliary text pool.

The translated ``A CLASS`` ... ``E CLASS`` strings occupy seven BG character
cells.  On the Battle Chip GP class screen, the final two cells have priority
over and hide the first (green) tournament icon.  This generator replaces the
five labels with ``A CLS`` ... ``E CLS`` inside their existing 16-byte slots.
Pointers, targets, every other auxiliary string and all unused bytes remain
byte-identical; the unused tail of each slot is filled with END words.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

import n1tool


VERSION = "0.10.6"
POOL_START = 0x34ACB0
POOL_LENGTH = 0x0AAE
POINTER_COUNT = 208
SLOT_LENGTH = 16
BASE_POOL_SHA256 = "40de4032c9e02e40eb776ade4a58881b0a6144d4492ff2566a93bb116968e749"
POINTERS_SHA256 = "d962913d3b8efb61d9017e5cc1105b8c033c70dfa0db36d7882704075426ce6d"
OUTPUT_ASSET = "aux_text_pool_v0_10_6.bin"
REPORT_NAME = "class_selection_labels_report_v0_10_6.json"
LABELS = {index: f"{letter} CLS" for index, letter in zip(range(0x1F, 0x24), "ABCDE")}


def sha256(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def words_until_end(payload: bytes, start: int) -> list[int]:
    words: list[int] = []
    for offset in range(start, len(payload), 2):
        word = struct.unpack_from("<H", payload, offset)[0]
        words.append(word)
        if word == n1tool.CONTROL_WORDS["END"]:
            return words
    raise ValueError(f"unterminated auxiliary string at relative 0x{start:04X}")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-pool", type=Path,
        default=root / "translation/assets/aux_text_pool_v0_9.bin",
    )
    parser.add_argument(
        "--pointers", type=Path,
        default=root / "translation/assets/aux_text_pointers_v0_9.bin",
    )
    parser.add_argument("--table", type=Path, default=root / "tables/n1battle_jp.tbl")
    parser.add_argument("--output-dir", type=Path, default=root / "translation/assets")
    args = parser.parse_args()

    base = args.base_pool.read_bytes()
    pointers = args.pointers.read_bytes()
    if len(base) != POOL_LENGTH or sha256(base) != BASE_POOL_SHA256:
        raise ValueError("unexpected canonical auxiliary text pool")
    if len(pointers) != POINTER_COUNT * 2 or sha256(pointers) != POINTERS_SHA256:
        raise ValueError("unexpected canonical auxiliary pointer table")
    decode, encode = n1tool.load_table(args.table)

    output = bytearray(base)
    allowed = bytearray(len(base))
    records: list[dict[str, object]] = []
    end_word = struct.pack("<H", n1tool.CONTROL_WORDS["END"])
    for index, replacement in LABELS.items():
        relative = struct.unpack_from("<H", pointers, index * 2)[0] * 2
        expected_original = f"{replacement[0]} CLASS"
        original_words = words_until_end(base, relative)
        original = "".join(n1tool.token_for(word, decode) for word in original_words).removesuffix("[END]")
        if original != expected_original:
            raise ValueError(
                f"05:{index:02X}: expected {expected_original!r}, found {original!r}"
            )
        original_payload = n1tool.pack_words(original_words)
        if len(original_payload) != SLOT_LENGTH:
            raise ValueError(f"05:{index:02X}: expected an isolated 16-byte slot")
        replacement_words = [
            *n1tool.encode_text(replacement, encode), n1tool.CONTROL_WORDS["END"],
        ]
        replacement_payload = n1tool.pack_words(replacement_words)
        if len(replacement_payload) > SLOT_LENGTH:
            raise ValueError(f"05:{index:02X}: replacement does not fit its slot")
        padded = replacement_payload + end_word * ((SLOT_LENGTH - len(replacement_payload)) // 2)
        output[relative:relative + SLOT_LENGTH] = padded
        allowed[relative:relative + SLOT_LENGTH] = b"\x01" * SLOT_LENGTH
        decoded = "".join(
            n1tool.token_for(word, decode) for word in words_until_end(bytes(output), relative)
        ).removesuffix("[END]")
        if decoded != replacement:
            raise AssertionError(f"05:{index:02X}: generated label failed round-trip")
        records.append({
            "pointer_id": f"05:{index:02X}",
            "pointer_table_offset": f"0x{0x34AB10 + index * 2:06X}",
            "target": f"0x{POOL_START + relative:06X}",
            "slot_length": SLOT_LENGTH,
            "before": original,
            "after": replacement,
            "bg_character_cells_before": len(original),
            "bg_character_cells_after": len(replacement),
            "freed_screen_columns": [8, 9],
        })

    changed = [index for index, (old, new) in enumerate(zip(base, output)) if old != new]
    outside = [index for index in changed if not allowed[index]]
    if outside:
        raise AssertionError(f"auxiliary pool changed outside the five slots: {outside[:8]}")
    if pointers != args.pointers.read_bytes():
        raise AssertionError("pointer table changed during generation")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / OUTPUT_ASSET
    output_path.write_bytes(output)
    report = {
        "status": "PASS",
        "version": VERSION,
        "cause": "two trailing CLASS cells covered the green tournament icon through BG priority",
        "solution": "five in-place A CLS through E CLS labels with early END and END padding",
        "pool": {
            "offset": f"0x{POOL_START:06X}",
            "length": POOL_LENGTH,
            "base_sha256": BASE_POOL_SHA256,
            "output_file": OUTPUT_ASSET,
            "output_sha256": sha256(output),
            "changed_bytes": len(changed),
            "outside_allowlist": len(outside),
        },
        "pointers": {
            "count": POINTER_COUNT,
            "sha256": POINTERS_SHA256,
            "modified": False,
        },
        "labels": records,
        "runtime_expectation": {
            "released_bg_columns": [8, 9],
            "released_pixel_range_x": [64, 79],
            "green_icon_obj_tiles": ["0x0C", "0x0D", "0x0E", "0x0F"],
            "cursor_and_yellow_pink_icons": "preserved",
        },
        "outputs": {
            OUTPUT_ASSET: {"length": len(output), "sha256": sha256(output)},
        },
    }
    report_path = args.output_dir / REPORT_NAME
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
