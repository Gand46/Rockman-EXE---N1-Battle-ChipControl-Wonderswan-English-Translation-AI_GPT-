#!/usr/bin/env python3
"""Repack the battle/result message banks with RC4-safe line widths.

Each non-null far-pointer row normally contributes one 8x16 text line.  A
runtime probe established that ``0x0800`` (``[LINE]``) may add one physical
line *inside the final record of a group*.  The null pointer after a group is
still its dispatch separator: consuming it makes the renderer continue into
the following message.  RC4 therefore preserves the null bitmap exactly,
allows ``[LINE]`` only in a group's final record, and caps every group at three
physical rows.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import struct
import sys
from pathlib import Path
from typing import Any


VERSION = "0.10.7-rc4"
SOURCE_ROM_SHA256 = "4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed"
FAR_BASE = 0x300000
PORTRAIT_LINE_COLUMNS = 19
RESULT_LINE_COLUMNS = 26
PAUSE_OPTION_COLUMNS = 8
DEFAULT_RAW_COLUMNS = 8

OUTPUT_FILES = {
    "b1": (
        "battle_messages_b1_data_v0_10_7_rc4.bin",
        "battle_messages_b1_pointers_v0_10_7_rc4.bin",
    ),
    "b2": (
        "battle_messages_b2_data_v0_10_7_rc4.bin",
        "battle_messages_b2_pointers_v0_10_7_rc4.bin",
    ),
}
REPORT_NAME = "battle_message_asset_report_v0_10_7_rc4.json"

# Pinned after deterministic generation from the verified Japanese Rev 1 ROM.
OUTPUT_SHA256: dict[str, str] = {
    "b1_data": "cf8c3375d9b151f9f4d2229788be56613d313962abae8a340b171da46e691f0f",
    "b1_pointers": "ac7abb10e37781e42fb863a0d3475cc4182bb11e6cd539167bca7358cfb3e931",
    "b2_data": "9bde45dc60d5b4ca84068a423c18cc1f648546ffdd4ed74a3490e491b9d09d83",
    "b2_pointers": "7b8e48eeab3078c0bb6640793936306a1bd760d1216da56a753f08400d5b8ea2",
}


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ROOT = Path(__file__).resolve().parents[1]
legacy = load_module(ROOT / "src/battle_message_assets_v0_9.py", "battle_messages_v09_for_rc4")
n1tool = load_module(ROOT / "src/n1tool.py", "n1tool_for_battle_rc4")
BANKS = legacy.BANKS


B1 = dict(legacy.B1)
B1.update({
    13: "deleted from[LINE]the deck!",
    30: "has no chip set;",
    60: "used [RAW:0201] to",
    61: "cast a barrier!",
    64: "fired a[LINE]Charge Shot!",
    74: "destroyed in 1 hit!",
    92: "a hole blocked it;",
    93: "couldn't get close!",
    137: "[RAW:0200] was[LINE]paralyzed",
    140: "is numb and cannot[LINE]move!",
    143: "barely endured[LINE]the hit!",
    145: "Fire burst from[LINE]the panel!",
    147: "Absorbed earth",
    148: "energy from the[LINE]panel!",
    150: "Poison gas filled[LINE]the panel!",
    155: "[RAW:0200] changed",
    156: "damage into Attack[LINE]power!",
    162: "[RAW:0200] activated!",
    167: "stole [RAW:0201]'s[LINE]panel",
    170: "became harder[LINE]to move!",
    172: "Navi and chip match",
    173: "type! Chip Attack[LINE]increased!",
    179: "boosted Elec chip[LINE]Attack!",
})

B2 = dict(legacy.B2)
B2.update({
    55: "DECK",
})

TRANSLATIONS = {"b1": B1, "b2": B2}
CHANGED_IDS = {
    "b1": tuple(sorted(index for index in B1 if B1[index] != legacy.B1[index])),
    "b2": tuple(sorted(index for index in B2 if B2[index] != legacy.B2[index])),
}

# Runtime substitution contracts.  Names and chip labels use the database-wide
# maximum of eight glyphs; HP/damage values use four columns and hit counts use
# two.  The explicit numeric overrides avoid rejecting correct legacy lines as
# if every ``RAW`` placeholder were a name.
B1_RAW_COLUMNS: dict[int, dict[int, int]] = {
    3: {0x0201: 4},
    6: {0x0201: 4},
    19: {0x0201: 4},
    27: {0x0202: 4},
    37: {0x0201: 4},
    112: {0x0200: 2},
    114: {0x0202: 4},
    129: {0x0202: 4},
    181: {0x0200: 2},
    183: {0x0202: 4},
}

B2_RAW_COLUMNS: dict[int, dict[int, int]] = {
    7: {0x0200: 2},
    23: {0x0200: 8, 0x0201: 3},
    24: {0x0202: 8, 0x0203: 3},
    27: {0x0200: 8, 0x0201: 4},
    28: {0x0202: 8, 0x0203: 4},
    42: {0x0200: 2},
    44: {0x0200: 5},
}

RAW_RE = re.compile(r"\[RAW:([0-9A-Fa-f]{4})\]")
LINE_TOKEN = "[LINE]"
FORBIDDEN_CONTROL_TOKENS = ("[WAIT]", "[END]")

# Runtime-tested line breaks.  Every listed record is the last non-null pointer
# before a separator.  Keeping this explicit prevents a future copy edit from
# introducing a control word into an untested position.
APPROVED_LINE_IDS = frozenset({13, 64, 137, 140, 143, 145, 148, 150, 156, 167, 170, 173, 179})


def sha256(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def visible_columns(bank: str, index: int, text: str) -> int:
    """Return worst-case rendered columns for one physical text line."""

    widths_by_bank = B1_RAW_COLUMNS if bank == "b1" else B2_RAW_COLUMNS
    widths = widths_by_bank.get(index, {})
    result = 0
    cursor = 0
    for match in RAW_RE.finditer(text):
        result += len(text[cursor:match.start()])
        result += widths.get(int(match.group(1), 16), DEFAULT_RAW_COLUMNS)
        cursor = match.end()
    result += len(text[cursor:])
    return result


def physical_line_widths(bank: str, index: int, text: str) -> tuple[int, ...]:
    return tuple(visible_columns(bank, index, line) for line in text.split(LINE_TOKEN))


def groups_from_pointer_source(pointer_source: bytes, pointer_count: int) -> list[list[int]]:
    """Return contiguous non-null pointer runs separated by dispatch NULLs."""

    groups: list[list[int]] = []
    current: list[int] = []
    for index in range(pointer_count):
        is_null = struct.unpack_from("<I", pointer_source, index * 4)[0] == 0
        if is_null:
            if current:
                groups.append(current)
                current = []
        else:
            current.append(index)
    if current:
        groups.append(current)
    return groups


def line_limit(bank: str, index: int) -> int:
    if bank == "b1":
        return PORTRAIT_LINE_COLUMNS
    if index == 55:
        return PAUSE_OPTION_COLUMNS
    return RESULT_LINE_COLUMNS


def validate_bank_translations(
    bank: Any, pointer_source: bytes
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Validate widths and runtime-tested line-control placement."""

    rows: list[dict[str, object]] = []
    groups = groups_from_pointer_source(pointer_source, bank.pointer_count)
    group_by_id = {index: group for group in groups for index in group}
    translations = TRANSLATIONS[bank.name]
    seen_line_ids: set[int] = set()
    group_rows: list[dict[str, object]] = []

    for index, text in sorted(translations.items()):
        widths = physical_line_widths(bank.name, index, text)
        limit = line_limit(bank.name, index)
        if any(columns > limit for columns in widths):
            raise ValueError(
                f"{bank.name}:{index:03} has physical widths {list(widths)}; "
                f"limit is {limit}: {text!r}"
            )
        if any(token in text for token in FORBIDDEN_CONTROL_TOKENS):
            raise ValueError(f"{bank.name}:{index:03}: forbidden control in battle bank")
        line_count = text.count(LINE_TOKEN)
        if line_count:
            seen_line_ids.add(index)
            if bank.name != "b1" or index not in APPROVED_LINE_IDS:
                raise ValueError(
                    f"{bank.name}:{index:03}: unapproved [LINE] placement"
                )
            group = group_by_id[index]
            if index != group[-1]:
                raise ValueError(
                    f"{bank.name}:{index:03}: [LINE] is not in final group record"
                )
        rows.append({
            "id": f"{bank.name.upper()}:{index:03}",
            "text": text,
            "physical_line_widths_worst_case": list(widths),
            "maximum_visible_columns": max(widths),
            "line_limit": limit,
            "line_controls": line_count,
            "changed_from_v0_9": index in CHANGED_IDS[bank.name],
        })

    if bank.name == "b1" and seen_line_ids != set(APPROVED_LINE_IDS):
        raise ValueError(
            "b1: approved [LINE] inventory mismatch; "
            f"missing={sorted(APPROVED_LINE_IDS - seen_line_ids)}, "
            f"extra={sorted(seen_line_ids - APPROVED_LINE_IDS)}"
        )

    for group in groups:
        added_rows = sum(
            translations.get(index, "").count(LINE_TOKEN) for index in group
        )
        physical_rows = len(group) + added_rows
        if bank.name == "b1" and physical_rows > 3:
            raise ValueError(
                f"b1 group {group[0]:03}-{group[-1]:03} would use "
                f"{physical_rows} physical rows"
            )
        if added_rows:
            group_rows.append({
                "pointer_ids": group,
                "pointer_rows": len(group),
                "line_controls": added_rows,
                "physical_rows": physical_rows,
                "line_control_id": group[-1],
            })
    return rows, group_rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    decode, encode = n1tool.load_table(ROOT / "tables/n1battle_jp.tbl")
    rom = args.rom.read_bytes()
    if len(rom) != 0x400000 or sha256(rom) != SOURCE_ROM_SHA256:
        raise ValueError("unexpected source ROM; expected verified Japanese Rev 1")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    report_banks: list[dict[str, object]] = []
    width_rows: list[dict[str, object]] = []
    line_control_groups: list[dict[str, object]] = []
    total_translated = 0
    for bank in BANKS:
        data_source = rom[bank.data_start:bank.data_end]
        pointer_length = bank.pointer_count * 4
        pointer_source = rom[bank.pointer_start:bank.pointer_start + pointer_length]
        if sha256(data_source) != bank.data_sha256:
            raise ValueError(f"{bank.name}: data source hash changed")
        if sha256(pointer_source) != bank.pointer_sha256:
            raise ValueError(f"{bank.name}: pointer source hash changed")
        bank_width_rows, bank_line_groups = validate_bank_translations(
            bank, pointer_source
        )
        width_rows.extend(bank_width_rows)
        line_control_groups.extend(
            {"bank": bank.name, **item} for item in bank_line_groups
        )

        source_by_id: dict[int, dict[str, object]] = {}
        targets: list[int] = []
        null_ids: list[int] = []
        for index in range(bank.pointer_count):
            offset, segment = struct.unpack_from("<HH", pointer_source, index * 4)
            if offset == segment == 0:
                null_ids.append(index)
                continue
            target = FAR_BASE + segment * 16 + offset
            if not bank.data_start <= target < bank.data_end:
                raise ValueError(f"{bank.name}:{index:03}: target out of bank")
            targets.append(target)
            source_by_id[index] = {"target": target}
        if len(targets) != len(set(targets)):
            raise ValueError(f"{bank.name}: expected unique non-null targets")

        ordered = sorted(targets)
        next_target = {
            target: ordered[pos + 1] if pos + 1 < len(ordered) else bank.data_end
            for pos, target in enumerate(ordered)
        }
        japanese_ids: set[int] = set()
        for index, item in source_by_id.items():
            target = int(item["target"])
            words, terminator, used_end = legacy.read_target(
                rom, target, next_target[target]
            )
            text = "".join(n1tool.token_for(word, decode) for word in words)
            item.update({
                "words": words,
                "terminator": terminator,
                "used_end": used_end,
                "source_text": text,
            })
            if legacy.contains_japanese(text):
                japanese_ids.add(index)

        translations = TRANSLATIONS[bank.name]
        if set(translations) != japanese_ids:
            raise ValueError(
                f"{bank.name}: translation IDs mismatch; "
                f"missing={sorted(japanese_ids - set(translations))}, "
                f"extra={sorted(set(translations) - japanese_ids)}"
            )

        data_output = bytearray(bank.data_end - bank.data_start)
        pointer_output = bytearray(pointer_source)
        cursor = 0
        output_targets: dict[int, int] = {}
        inventory: list[dict[str, object]] = []
        for index in sorted(source_by_id):
            item = source_by_id[index]
            translation = translations.get(index)
            words = (
                n1tool.encode_text(translation, encode)
                if translation is not None
                else list(item["words"])
            )
            if len(words) > 0xFF:
                raise ValueError(f"{bank.name}:{index:03}: record exceeds 255 words")
            high = int(item["terminator"]) & 0xFF00
            payload = n1tool.pack_words([*words, high | len(words)])
            if cursor + len(payload) > len(data_output):
                raise ValueError(f"{bank.name}: translated records exceed bank capacity")
            target = bank.data_start + cursor
            data_output[cursor:cursor + len(payload)] = payload
            output_targets[index] = target
            cursor += len(payload)
            if translation is not None:
                inventory.append({
                    "id": f"{bank.name.upper()}:{index:03}",
                    "source_text": item["source_text"],
                    "translation": translation,
                    "output_target": f"0x{target:06X}",
                    "terminator_high": f"0x{high:04X}",
                    "physical_line_widths_worst_case": list(
                        physical_line_widths(bank.name, index, translation)
                    ),
                    "changed_from_v0_9": index in CHANGED_IDS[bank.name],
                })

        for index, target in output_targets.items():
            relative = target - FAR_BASE
            segment, offset = divmod(relative, 16)
            struct.pack_into("<HH", pointer_output, index * 4, offset, segment)

        output_null_ids = [
            index for index in range(bank.pointer_count)
            if struct.unpack_from("<I", pointer_output, index * 4)[0] == 0
        ]
        if output_null_ids != null_ids:
            raise AssertionError(f"{bank.name}: null-pointer topology changed")

        combined = bytearray(rom)
        combined[bank.data_start:bank.data_end] = data_output
        combined[bank.pointer_start:bank.pointer_start + pointer_length] = pointer_output
        for index, target in output_targets.items():
            words, terminator, _ = legacy.read_target(combined, target, bank.data_end)
            expected_high = int(source_by_id[index]["terminator"]) & 0xFF00
            if terminator & 0xFF00 != expected_high:
                raise AssertionError(f"{bank.name}:{index:03}: terminator flag changed")
            forbidden_words = {
                n1tool.CONTROL_WORDS["WAIT"], n1tool.CONTROL_WORDS["END"]
            }
            if any(word in forbidden_words for word in words):
                raise AssertionError(f"{bank.name}:{index:03}: forbidden control leaked in")
            expected_lines = (
                translations[index].count(LINE_TOKEN) if index in translations else 0
            )
            actual_lines = words.count(n1tool.CONTROL_WORDS["LINE"])
            if actual_lines != expected_lines:
                raise AssertionError(
                    f"{bank.name}:{index:03}: [LINE] count {actual_lines} != "
                    f"{expected_lines}"
                )

        data_name, pointer_name = OUTPUT_FILES[bank.name]
        actual_hashes = {
            f"{bank.name}_data": sha256(data_output),
            f"{bank.name}_pointers": sha256(pointer_output),
        }
        for key, actual in actual_hashes.items():
            if actual != OUTPUT_SHA256[key]:
                raise AssertionError(
                    f"{key}: deterministic hash {actual} != {OUTPUT_SHA256[key]}"
                )
        (args.output_dir / data_name).write_bytes(data_output)
        (args.output_dir / pointer_name).write_bytes(pointer_output)
        report_banks.append({
            "id": bank.name,
            "layout": {
                "default_line_limit": (
                    PORTRAIT_LINE_COLUMNS if bank.name == "b1" else RESULT_LINE_COLUMNS
                ),
                "special_line_limits": (
                    {} if bank.name == "b1" else {"55": PAUSE_OPTION_COLUMNS}
                ),
                "maximum_visible_columns": max(
                    int(row["maximum_visible_columns"]) for row in bank_width_rows
                ),
            },
            "data": {
                "offset": f"0x{bank.data_start:06X}",
                "length": len(data_output),
                "asset": data_name,
                "sha256": sha256(data_output),
                "used_bytes": cursor,
                "free_bytes": len(data_output) - cursor,
            },
            "pointers": {
                "offset": f"0x{bank.pointer_start:06X}",
                "count": bank.pointer_count,
                "non_null": len(source_by_id),
                "null": len(null_ids),
                "null_ids": null_ids,
                "null_topology_preserved": True,
                "asset": pointer_name,
                "sha256": sha256(pointer_output),
            },
            "changed_ids": list(CHANGED_IDS[bank.name]),
            "translations": inventory,
        })
        total_translated += len(inventory)

    report = {
        "status": "PASS",
        "family": "battle_and_result_messages",
        "project_version": VERSION,
        "source_rom_sha256": SOURCE_ROM_SHA256,
        "format": (
            "one dispatched record per non-null far pointer; 8x16 glyph rows; optional "
            "runtime-tested 0x0800 line break; 0x80LL/0xC0LL length terminator"
        ),
        "geometry": {
            "native_screen": [224, 144],
            "bottom_box": [224, 64],
            "portrait": [64, 64],
            "glyph": [8, 16],
            "safe_columns_with_portrait": PORTRAIT_LINE_COLUMNS,
            "safe_columns_without_portrait": RESULT_LINE_COLUMNS,
            "pause_option_columns": PAUSE_OPTION_COLUMNS,
            "physical_line_positions": 3,
        },
        "dispatch_safety": {
            "null_pointer_topology_preserved": True,
            "new_pointer_rows": 0,
            "line_control_words_added": len(APPROVED_LINE_IDS),
            "line_control_ids": sorted(APPROVED_LINE_IDS),
            "line_control_groups": line_control_groups,
            "third_line_policy": (
                "0x0800 is allowed only in the final record of a group whose total remains "
                "at most three physical rows; null dispatch separators are never consumed"
            ),
        },
        "translated_targets": total_translated,
        "changed_targets": sum(len(ids) for ids in CHANGED_IDS.values()),
        "maximum_visible_columns": max(
            int(row["maximum_visible_columns"]) for row in width_rows
        ),
        "maximum_visible_columns_by_bank": {
            bank["id"]: bank["layout"]["maximum_visible_columns"]
            for bank in report_banks
        },
        "width_audit": width_rows,
        "banks": report_banks,
    }
    (args.output_dir / REPORT_NAME).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": "PASS",
        "changed_targets": report["changed_targets"],
        "maximum_visible_columns": report["maximum_visible_columns"],
        "banks": [
            {"id": row["id"], "data": row["data"], "pointers": row["pointers"]}
            for row in report_banks
        ],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
