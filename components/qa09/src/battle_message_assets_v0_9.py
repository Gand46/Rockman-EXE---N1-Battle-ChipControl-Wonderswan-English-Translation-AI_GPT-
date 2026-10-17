#!/usr/bin/env python3
"""Repack the two omitted battle/result message banks in English.

Each bank has a far-pointer table of ``<offset:u16, segment:u16>`` records.
Physical addresses are ``0x300000 + segment * 16 + offset``.  Text records are
16-bit words followed by ``0x80LL`` or ``0xC0LL``; ``LL`` is the number of
preceding words.  Repacking removes stale Japanese bytes, preserves null table
slots and terminator high bytes, and recalculates every length byte.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SOURCE_ROM_SHA256 = "4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed"
FAR_BASE = 0x300000


@dataclass(frozen=True)
class Bank:
    name: str
    data_start: int
    data_end: int
    pointer_start: int
    pointer_count: int
    data_sha256: str
    pointer_sha256: str


BANKS = (
    Bank("b1", 0x37CC30, 0x37D7F4, 0x37D7F4, 187,
         "a3e586701f5ccb8f165dff1e0a4ca7e8e322301d14692deff7d4ae70adc8c578",
         "ba5c8533a43908ce23fd552f3962a6ab0c5313569d21f0c2291eb2f450d43c12"),
    Bank("b2", 0x37DAE0, 0x37E0CC, 0x37E0CC, 92,
         "f92001a5d80e860ddbd261742198a7d1ee883f54397bf16df8b46f4696feb1aa",
         "499067c64f7bb216b6b609f670a21866db28631f16b18854dd958198aad27f60"),
)


B1: dict[int, str] = {
    0: "[RAW:0200]'s action!", 2: "[RAW:0200]", 3: "Attack: [RAW:0201]!",
    5: "[RAW:0200]", 6: "[RAW:0201] damage!!", 8: "CRITICAL DAMAGE!!",
    9: "[RAW:0200]", 10: "logged out!", 12: "[RAW:0200] chip",
    13: "deleted from the deck!", 15: "[RAW:0200]", 16: "used [RAW:0201]!",
    18: "[RAW:0200]", 19: "recovered [RAW:0201] HP!", 21: "[RAW:0200]'s",
    22: "[RAW:0201]", 23: "attacked the deck!", 25: "[RAW:0200]'s",
    26: "[RAW:0201] chip", 27: "dealt [RAW:0202] damage!", 29: "[RAW:0200]",
    30: "has no BattleChip set", 31: "attacked a panel", 33: "[RAW:0200] guarded",
    34: "with [RAW:0201]", 36: "[RAW:0200]", 37: "took [RAW:0201] damage!",
    39: "But [RAW:0200]", 40: "blocked [RAW:0201]", 41: "Perfect guard!",
    43: "[RAW:0200]", 44: "took no damage!!", 46: "[RAW:0201] chip's",
    47: "counterattack!!", 49: "[RAW:0200]", 50: "fired [RAW:0201]!",
    52: "[RAW:0200]", 53: "threw [RAW:0201]!", 55: "[RAW:0200]",
    56: "used [RAW:0201] to", 57: "slash!", 59: "[RAW:0200]",
    60: "used [RAW:0201] to cast", 61: "a barrier!", 63: "[RAW:0200]",
    64: "fired a Charge Shot!", 66: "[RAW:0200]", 67: "swung GutsHammer!",
    69: "[RAW:0200]", 70: "dodged [RAW:0201]!", 72: "Amazing! [RAW:0200]",
    73: "[RAW:0201]", 74: "destroyed it in one hit!!", 76: "[RAW:0200]",
    77: "on [RAW:0201] chip", 78: "had no effect", 80: "[RAW:0200]'s",
    81: "Slot-In Panel(L)", 82: "was disabled!", 84: "[RAW:0200]'s",
    85: "Slot-In Panel(R)", 86: "was disabled!", 88: "[RAW:0200] chip",
    89: "confused [RAW:0201]!", 91: "But [RAW:0200]", 92: "was blocked by a hole",
    93: "and could not get close!", 95: "[RAW:0200]", 96: "with [RAW:0201]",
    97: "punched!", 99: "[RAW:0200]", 100: "[RAW:0201]",
    101: "struck down!", 103: "[RAW:0200]", 104: "set [RAW:0201]!",
    106: "[RAW:0200]'s", 109: "[RAW:0200]", 110: "cannot use it here",
    112: "Hit [RAW:0200] times!!", 113: "[RAW:0201] chip",
    114: "dealt [RAW:0202] damage!!", 116: "[RAW:0200]", 117: "rolled the dice",
    118: "...([RAW:0201])!", 120: "[RAW:0200]", 121: "pierced [RAW:0201]!",
    123: "[RAW:0200]'s trap!", 124: "[RAW:0201] chip", 125: "reacted!",
    127: "[RAW:0200]", 128: "[RAW:0201] chip's", 129: "Attack +[RAW:0202]",
    131: "[RAW:0200]", 132: "had no effect", 134: "[RAW:0200]'s",
    135: "effect wore off", 137: "[RAW:0200] was paralyzed", 139: "[RAW:0200]",
    140: "is numb and cannot move!", 142: "[RAW:0200]",
    143: "barely endured the hit!", 145: "Fire burst from the panel!",
    147: "Absorbed earth energy", 148: "from the panel!",
    150: "Poison gas filled the panel!", 152: "[RAW:0200]", 153: "used AirShoes",
    155: "[RAW:0200] changed damage", 156: "into Attack power!",
    158: "[RAW:0200]", 159: "was hit by [RAW:0201]", 160: "and broke!",
    162: "[RAW:0200] activated!!", 163: "[RAW:0201] hit a trap",
    164: "and was caught!!", 166: "[RAW:0200]", 167: "stole [RAW:0201]'s panel",
    169: "[RAW:0200]", 170: "became harder to move!",
    172: "Navi and chip match type!", 173: "Chip Attack increased!",
    175: "Weakness hit!", 176: "Super effective!!", 178: "Aluminum panel",
    179: "boosted Elec chip Attack!", 181: "Hit [RAW:0200] times!",
    182: "to [RAW:0201]", 183: "[RAW:0202] damage", 185: "GUARD BREAK!!",
}


B2: dict[int, str] = {
    0: "BATTLE START!", 2: "[RAW:0200] switched Navis!", 4: "[RAW:0200]",
    5: "touched [RAW:0201]", 7: "TURN [RAW:0200]!! FIGHT!",
    9: "Let's go, [RAW:0200]!", 10: "BATTLECHIP SLOT IN!",
    12: "In [RAW:0200]'s deck", 13: "[RAW:0201] chip", 14: "was installed!",
    16: "[RAW:0200]", 17: "won the battle!", 19: "BATTLE OVER!",
    20: "Calculating results", 22: "Deleted BattleChips",
    23: "[RAW:0200]: [RAW:0201] chips", 24: "[RAW:0202]: [RAW:0203] chips",
    26: "Navi damage", 27: "[RAW:0200]: [RAW:0201]", 28: "[RAW:0202]: [RAW:0203]",
    30: "Result is a draw", 31: "Drawing a winner", 33: "Result",
    34: "[RAW:0200] wins!", 36: "Yes!", 38: "Go!", 40: "Attack!",
    42: "BUSTING LEVEL [RAW:0200]", 44: "Won [RAW:0200]z", 45: "Got it!!",
    47: "From the rival deck", 48: "got [RAW:0200] chip", 49: "Got it!!",
    53: "PAUSE", 55: "VIEW DECK", 56: "RETRY", 57: "GIVE UP",
    59: "Retry the battle?", 61: "TRY AGAIN", 62: "Let's rethink strategy!",
    64: "End the battle?", 66: "Review the Chip Folder",
    67: "and challenge again!", 69: "YES", 70: "NO",
    72: "Program Deck's", 73: "Catch Machine", 74: "raised BUSTING LEVEL!",
    76: "BATTLE OVER! We did it!", 78: "Great! Keep it up!",
    80: "Whew, that was close...", 82: "Pant... Tough opponent...",
    85: "Good luck!", 87: "Challenge again?", 89: "RETRY", 90: "GIVE UP",
}

TRANSLATIONS = {"b1": B1, "b2": B2}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def contains_japanese(text: str) -> bool:
    return any(
        "\u3040" <= c <= "\u30ff" or "\u3400" <= c <= "\u4dbf" or "\u4e00" <= c <= "\u9fff"
        for c in text
    )


def load_n1tool(root: Path) -> Any:
    path = root / "src" / "n1tool.py"
    spec = importlib.util.spec_from_file_location("n1tool_battle_v09", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_target(rom: bytes, target: int, limit: int) -> tuple[list[int], int, int]:
    words: list[int] = []
    cursor = target
    while cursor + 1 < limit:
        word = struct.unpack_from("<H", rom, cursor)[0]
        cursor += 2
        if word & 0xFF00 in (0x8000, 0xC000):
            if word & 0xFF != len(words):
                raise ValueError(
                    f"length byte mismatch at 0x{target:06X}: {word & 0xFF} != {len(words)}"
                )
            return words, word, cursor
        words.append(word)
    raise ValueError(f"unterminated battle record at 0x{target:06X}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    n1tool = load_n1tool(root)
    decode, encode = n1tool.load_table(root / "tables" / "n1battle_jp.tbl")
    rom = args.rom.read_bytes()
    if len(rom) != 0x400000 or sha256(rom) != SOURCE_ROM_SHA256:
        raise ValueError("unexpected source ROM; expected verified Japanese Rev 1")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_banks = []
    total_japanese = 0
    total_translated = 0

    for bank in BANKS:
        data_source = rom[bank.data_start:bank.data_end]
        pointer_length = bank.pointer_count * 4
        pointer_source = rom[bank.pointer_start:bank.pointer_start + pointer_length]
        if sha256(data_source) != bank.data_sha256:
            raise ValueError(f"{bank.name}: data source hash changed")
        if sha256(pointer_source) != bank.pointer_sha256:
            raise ValueError(f"{bank.name}: pointer source hash changed")

        source_by_id: dict[int, dict[str, object]] = {}
        targets: list[int] = []
        for index in range(bank.pointer_count):
            offset, segment = struct.unpack_from("<HH", pointer_source, index * 4)
            if offset == segment == 0:
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
            words, terminator, used_end = read_target(rom, target, next_target[target])
            text = "".join(n1tool.token_for(word, decode) for word in words)
            item.update({
                "words": words,
                "terminator": terminator,
                "used_end": used_end,
                "source_text": text,
                "source_slot_bytes": next_target[target] - target,
            })
            if contains_japanese(text):
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
        inventory = []
        output_targets: dict[int, int] = {}
        for index in sorted(source_by_id):
            item = source_by_id[index]
            translation = translations.get(index)
            if translation is None:
                words = list(item["words"])
            else:
                words = n1tool.encode_text(translation, encode)
            if len(words) > 0xFF:
                raise ValueError(f"{bank.name}:{index:03}: record exceeds 255 words")
            high = int(item["terminator"]) & 0xFF00
            payload = n1tool.pack_words([*words, high | len(words)])
            if cursor + len(payload) > len(data_output):
                raise ValueError(
                    f"{bank.name}: translated records need {cursor + len(payload)} bytes; "
                    f"capacity is {len(data_output)}"
                )
            target = bank.data_start + cursor
            data_output[cursor:cursor + len(payload)] = payload
            output_targets[index] = target
            cursor += len(payload)
            if translation is not None:
                inventory.append({
                    "id": f"{bank.name.upper()}:{index:03}",
                    "source_target": f"0x{int(item['target']):06X}",
                    "source_text": item["source_text"],
                    "translation": translation,
                    "output_target": f"0x{target:06X}",
                    "terminator_high": f"0x{high:04X}",
                })

        for index, target in output_targets.items():
            relative = target - FAR_BASE
            segment, offset = divmod(relative, 16)
            if segment > 0xFFFF or offset > 0xFFFF:
                raise ValueError(f"{bank.name}:{index:03}: far pointer cannot represent target")
            struct.pack_into("<HH", pointer_output, index * 4, offset, segment)

        # Re-read the generated records through their generated far pointers.
        combined = bytearray(rom)
        combined[bank.data_start:bank.data_end] = data_output
        remaining = []
        for index in source_by_id:
            offset, segment = struct.unpack_from("<HH", pointer_output, index * 4)
            target = FAR_BASE + segment * 16 + offset
            words, _, _ = read_target(combined, target, bank.data_end)
            text = "".join(n1tool.token_for(word, decode) for word in words)
            if contains_japanese(text):
                remaining.append({"id": index, "text": text})
        if remaining:
            raise ValueError(f"{bank.name}: Japanese remains: {remaining[:3]}")

        data_name = f"battle_messages_{bank.name}_data_v0_9.bin"
        pointer_name = f"battle_messages_{bank.name}_pointers_v0_9.bin"
        (args.output_dir / data_name).write_bytes(data_output)
        (args.output_dir / pointer_name).write_bytes(pointer_output)
        report_banks.append({
            "id": bank.name,
            "data": {
                "offset": f"0x{bank.data_start:06X}", "length": len(data_output),
                "source_sha256": bank.data_sha256, "asset": data_name,
                "asset_sha256": sha256(data_output), "used_bytes": cursor,
                "free_bytes": len(data_output) - cursor,
            },
            "pointers": {
                "offset": f"0x{bank.pointer_start:06X}", "count": bank.pointer_count,
                "non_null": len(source_by_id), "source_sha256": bank.pointer_sha256,
                "asset": pointer_name, "asset_sha256": sha256(pointer_output),
            },
            "japanese_source_targets": len(japanese_ids),
            "translated_targets": len(inventory),
            "remaining_japanese_targets": 0,
            "translations": inventory,
        })
        total_japanese += len(japanese_ids)
        total_translated += len(inventory)

    if total_japanese != 185 or total_translated != 185:
        raise ValueError(f"expected 185 translated targets, got {total_translated}")
    report = {
        "family": "battle_and_result_messages",
        "project_version": "0.9.0",
        "source_rom_sha256": SOURCE_ROM_SHA256,
        "format": "16-bit text; far pointers <offset,segment>; 0x80LL/0xC0LL terminators",
        "source_targets": 188,
        "japanese_source_targets": total_japanese,
        "translated_targets": total_translated,
        "remaining_japanese_targets": 0,
        "banks": report_banks,
    }
    (args.output_dir / "battle_message_asset_report_v0_9.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "source_targets": 188,
        "translated_targets": total_translated,
        "remaining_japanese_targets": 0,
        "banks": [{"id": x["id"], "data": x["data"], "pointers": x["pointers"]} for x in report_banks],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
