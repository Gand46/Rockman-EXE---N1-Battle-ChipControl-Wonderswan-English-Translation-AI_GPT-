#!/usr/bin/env python3
"""Translate the omitted 73-entry opponent/participant name table.

The table sits between Navi attack names and chip names.  It uses the same WSC
far-pointer representation as the official-reference databases and the same
``0x80LL`` length terminator as battle messages.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import struct
import sys
from pathlib import Path
from typing import Any


SOURCE_ROM_SHA256 = "4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed"
DATA_START = 0x367660
DATA_END = 0x367AEA
POINTER_START = 0x367AEA
COUNT = 73
POINTER_LENGTH = COUNT * 4
DATA_SOURCE_SHA256 = "a611660b821386a2a38ae5b659432e588ed938bc541c9700d0dde9b1a2752a99"
POINTER_SOURCE_SHA256 = "2f9e390400a38020a528f5e687a2eb310cf10259ade1d96be7f9c19a85b3544c"
FAR_BASE = 0x300000


TRANSLATIONS = [
    "TestR", "TestR2", "TestG", "TestG2", "Test01", "Test02", "Test03",
    "Kenji", "Higsby", "Ms.Mari", "Koetsu", "Kaz", "Dex", "Mayumi", "Haru",
    "Mayl", "Micchan", "Miki", "Apple", "Mr.Match", "Tetsu", "Junko", "Millions",
    "Taka", "Froid", "Anna", "CountZap", "Gen", "Haruna", "Dave", "Miyuki", "Prof",
    "Sara", "Arashi", "Larry", "Tom", "John", "Betty", "Dark", "Ogata", "Aya",
    "Yuji", "Yahoot", "Tomoz", "Chaud", "Bass",
    *[f"GST{suffix}" for suffix in "123456789ABCDEFGHIJKLMNOPQR"],
]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_n1tool(root: Path) -> Any:
    path = root / "src" / "n1tool.py"
    spec = importlib.util.spec_from_file_location("n1tool_names_v09", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def contains_japanese(text: str) -> bool:
    return any(
        "\u3040" <= c <= "\u30ff" or "\u3400" <= c <= "\u4dbf" or "\u4e00" <= c <= "\u9fff"
        for c in text
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    if len(TRANSLATIONS) != COUNT:
        raise AssertionError(f"translation list has {len(TRANSLATIONS)} entries")
    root = Path(__file__).resolve().parents[1]
    n1tool = load_n1tool(root)
    decode, encode = n1tool.load_table(root / "tables" / "n1battle_jp.tbl")
    rom = args.rom.read_bytes()
    if len(rom) != 0x400000 or sha256(rom) != SOURCE_ROM_SHA256:
        raise ValueError("unexpected source ROM; expected verified Japanese Rev 1")
    data_source = rom[DATA_START:DATA_END]
    pointer_source = rom[POINTER_START:POINTER_START + POINTER_LENGTH]
    if sha256(data_source) != DATA_SOURCE_SHA256:
        raise ValueError("participant-name source data hash changed")
    if sha256(pointer_source) != POINTER_SOURCE_SHA256:
        raise ValueError("participant-name pointer source hash changed")

    source_rows = []
    for index in range(COUNT):
        offset, segment = struct.unpack_from("<HH", pointer_source, index * 4)
        target = FAR_BASE + segment * 16 + offset
        if not DATA_START <= target < DATA_END:
            raise ValueError(f"participant {index}: target outside data bank")
        words = []
        cursor = target
        while cursor + 1 < DATA_END:
            word = struct.unpack_from("<H", rom, cursor)[0]
            cursor += 2
            if word & 0xFF00 == 0x8000:
                if word & 0xFF != len(words):
                    raise ValueError(f"participant {index}: invalid source length byte")
                break
            words.append(word)
        else:
            raise ValueError(f"participant {index}: unterminated source name")
        text = "".join(n1tool.token_for(word, decode) for word in words)
        if not contains_japanese(text):
            raise ValueError(f"participant {index}: expected Japanese source name: {text!r}")
        source_rows.append({"target": target, "text": text})

    data_output = bytearray(DATA_END - DATA_START)
    pointer_output = bytearray(POINTER_LENGTH)
    cursor = 0
    inventory = []
    for index, (source_row, translation) in enumerate(zip(source_rows, TRANSLATIONS)):
        words = n1tool.encode_text(translation, encode)
        if len(words) > 0xFF:
            raise ValueError(f"participant {index}: name is too long")
        payload = n1tool.pack_words([*words, 0x8000 | len(words)])
        if cursor + len(payload) > len(data_output):
            raise ValueError(
                f"participant names need {cursor + len(payload)} bytes; capacity {len(data_output)}"
            )
        target = DATA_START + cursor
        data_output[cursor:cursor + len(payload)] = payload
        relative = target - FAR_BASE
        segment, offset = divmod(relative, 16)
        struct.pack_into("<HH", pointer_output, index * 4, offset, segment)
        inventory.append({
            "id": index,
            "source_target": f"0x{int(source_row['target']):06X}",
            "source_text": source_row["text"],
            "translation": translation,
            "output_target": f"0x{target:06X}",
        })
        cursor += len(payload)

    # Re-read through the output table and require English-only text.
    combined = bytearray(rom)
    combined[DATA_START:DATA_END] = data_output
    for index in range(COUNT):
        offset, segment = struct.unpack_from("<HH", pointer_output, index * 4)
        target = FAR_BASE + segment * 16 + offset
        words = []
        position = target
        while position + 1 < DATA_END:
            word = struct.unpack_from("<H", combined, position)[0]
            position += 2
            if word & 0xFF00 == 0x8000:
                if word & 0xFF != len(words):
                    raise ValueError(f"participant {index}: generated length mismatch")
                break
            words.append(word)
        text = "".join(n1tool.token_for(word, decode) for word in words)
        if contains_japanese(text):
            raise ValueError(f"participant {index}: Japanese remains: {text!r}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    data_name = "participant_names_data_v0_9.bin"
    pointer_name = "participant_names_pointers_v0_9.bin"
    (args.output_dir / data_name).write_bytes(data_output)
    (args.output_dir / pointer_name).write_bytes(pointer_output)
    report = {
        "family": "participant_names",
        "project_version": "0.9.0",
        "source_rom_sha256": SOURCE_ROM_SHA256,
        "count": COUNT,
        "translated": COUNT,
        "remaining_japanese": 0,
        "data": {
            "offset": f"0x{DATA_START:06X}", "length": len(data_output),
            "source_sha256": DATA_SOURCE_SHA256, "asset": data_name,
            "asset_sha256": sha256(data_output), "used_bytes": cursor,
            "free_bytes": len(data_output) - cursor,
        },
        "pointers": {
            "offset": f"0x{POINTER_START:06X}", "length": POINTER_LENGTH,
            "source_sha256": POINTER_SOURCE_SHA256, "asset": pointer_name,
            "asset_sha256": sha256(pointer_output),
        },
        "official_reference": {
            "title": "Mega Man Battle Chip Challenge (USA)",
            "sha256": "e38da6e5dcdaf565ec1969ef6cbd95c4a307d87d3c853e23926ff2ce4497feb4",
            "note": "Exact official USA names are used for all 72 matching entries; Haruna is a direct Latin transliteration because the USA reference omits that entry.",
        },
        "translations": inventory,
    }
    (args.output_dir / "participant_name_asset_report_v0_9.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "count": COUNT, "remaining_japanese": 0,
        "data": report["data"], "pointers": report["pointers"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
