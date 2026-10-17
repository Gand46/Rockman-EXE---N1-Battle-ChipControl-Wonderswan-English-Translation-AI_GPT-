#!/usr/bin/env python3
"""Repack the omitted auxiliary text pool as an English v0.9 asset.

The pool is referenced by 208 little-endian word offsets at 0x34AB10.  It
contains the entry-name keyboard rows, tournament labels, deck advice and the
credits.  Earlier project inventories started at 0x34B850 and therefore did
not include this independently referenced block.

The generator reads only the verified Japanese Rev 1 ROM, guards both source
spans by SHA-256, preserves aliases and opaque control strings, overwrites all
unused pool bytes with END words, and proves that no Japanese glyph remains in
any generated pointer target.
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
POINTER_START = 0x34AB10
POINTER_COUNT = 208
POINTER_LENGTH = POINTER_COUNT * 2
POINTER_SOURCE_SHA256 = "2ecc503144cc5245736e8b49b7d69ebf7b32a025ec7cf46a2bafca713d84f70f"
POOL_START = 0x34ACB0
POOL_END = 0x34B75E
POOL_LENGTH = POOL_END - POOL_START
POOL_SOURCE_SHA256 = "600926c8e902301f668b2b376a90220dda678700a7e5a32745b0643f01228f0d"

ASSET_POINTERS = "aux_text_pointers_v0_9.bin"
ASSET_POOL = "aux_text_pool_v0_9.bin"
REPORT_NAME = "auxiliary_text_asset_report_v0_9.json"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_n1tool(root: Path) -> Any:
    path = root / "src" / "n1tool.py"
    spec = importlib.util.spec_from_file_location("n1tool_aux_v09", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def keyboard_row(characters: str) -> str:
    """Return the game's ten-cell row: a glyph and separator per cell."""
    if len(characters) != 10:
        raise ValueError(f"keyboard row needs ten cells: {characters!r}")
    return " ".join(characters)


def credit(text: str, width: int = 22) -> str:
    """Keep one safe left inset while fitting the fixed auxiliary pool."""
    if len(text) > width:
        raise ValueError(f"credit line is wider than {width}: {text!r}")
    return " " + text


# Keys are representative pointer indices.  Every pointer aliasing the same
# Japanese source target receives the same translation automatically.
TRANSLATIONS: dict[int, str] = {
    # Page 0: lowercase; page 1: capitals.  Page 2 (0B-0F) was already 0-9/A-Z.
    0x01: keyboard_row("abcdefghij"),
    0x02: keyboard_row("klmnopqrst"),
    0x03: keyboard_row("uvwxyz.,!?"),
    0x04: keyboard_row("-'\"/()@&+="),
    0x05: keyboard_row("0123456789"),
    0x06: keyboard_row("ABCDEFGHIJ"),
    0x07: keyboard_row("KLMNOPQRST"),
    0x08: keyboard_row("UVWXYZ.,!?"),
    0x09: keyboard_row("-'\"/()@&+="),
    0x0A: keyboard_row("0123456789"),

    0x10: "1 MONTH LATER...",
    0x1F: "A CLASS",
    0x20: "B CLASS",
    0x21: "C CLASS",
    0x22: "D CLASS",
    0x23: "E CLASS",
    0x24: "NOVICE",
    0x25: "GUTS",
    0x26: "HEALING",
    0x27: "MATCH",
    0x28: "SAPLING",
    0x29: "DROPLET",
    0x2A: "BATTERY",
    0x2B: "QUICK",
    0x2C: "BLOCK",
    0x2D: "CLIFF",
    0x2E: "EAST",
    0x2F: "WEST",
    0x30: "MASTER",
    0x31: "NO RECORD",
    0x32: "UNRANKED",
    0x33: "BEST 8",
    0x34: "BEST 4",
    0x35: "RUNNER-UP",
    0x36: "WINNER",

    0x40: "[RAW:0E2D]Hmm... At this rate",
    0x47: "This may be tough.",
    0x48: "[RAW:0E2D]Their Navi is still",
    0x49: "a little stronger.",
    0x4A: "[RAW:0E2D]About as strong as",
    0x4B: "the other Navi.",
    0x4C: "[RAW:0E2D]Yes! This deck can",
    0x4D: "beat their Navi!",
    0x4E: "[RAW:0E2D]Great work, Lan!",
    0x4F: "We can't lose now!",
    0x50: "No rival to assess...",
    0x51: "Load your Folder first.",
    0x52: "Just a moment...",
    0x64: "ENTER",
    0x7F: "WINNER",
    0x80: "RUNNER-UP",
    0x81: " PLACE",

    # Official capitalizations match the supplied USA GBA reference wherever
    # that version credits the same person or entity.
    0x82: credit("STAFF"),
    0x9C: credit("DIRECTOR"),
    0x9D: credit("YOSHIHISA TSUDA"),
    0x9E: credit("YOSHINORI KAWANO"),
    0xA0: credit("GRAPHIC STAFF"),
    0xA1: credit("NOBORU HONDA"),
    0xA3: credit("IPPEI MASUDA"),
    0xA4: credit("RIE ONISHI"),
    0xA5: credit("YUKIMASA TAMURA"),
    0xA6: credit("TORU NAKAYAMA"),
    0xA7: credit("MAKOTO YABE"),
    0xA9: credit("PROGRAMMER"),
    0xAA: credit("AKIHIRO SHISHIDO"),
    0xAB: credit("KAZUTAKA YANAGISAWA"),
    0xAD: credit("KOUJI OKURA"),
    0xAE: credit("HIROKATSU KAWANISHI"),
    0xAF: credit("TOYOHIRO SERITA"),
    0xB1: credit("SOUND STAFF"),
    0xB2: credit("STUDIO CLICHE"),
    0xB3: credit("YUSUKE BEPPU"),
    0xB5: credit("PACKAGE DESIGN"),
    0xB6: credit("AKEMI IWASAKI"),
    0xB8: credit("SPECIAL THANKS"),
    0xB9: credit("KUNIHITO TAKASHIMA"),
    0xBA: credit("SATOSHI UKAI"),
    0xBB: credit("TAKAYUKI SANO"),
    0xBC: credit("SHIGEYOSHI KOBAYASHI"),
    0xBD: credit("ASUKA HAYASHI"),
    0xBE: credit("TAKESHI HORINOUCHI"),
    0xBF: credit("HIROKO NAKAMURA"),
    0xC0: credit("POLE TO WIN"),
    0xC4: credit("PRODUCER"),
    0xC5: credit("KEIJI INAFUNE"),
    0xC6: credit("TAKUYA AIZU"),
    0xC8: credit("PRODUCTION/COPYRIGHT"),
    0xCF: credit("THANKS FOR PLAYING!"),
}


def contains_japanese(text: str) -> bool:
    return any(
        "\u3040" <= character <= "\u30ff"
        or "\u3400" <= character <= "\u4dbf"
        or "\u4e00" <= character <= "\u9fff"
        for character in text
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path, help="verified Japanese Rev 1 ROM")
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    n1tool = load_n1tool(root)
    decode, encode = n1tool.load_table(root / "tables" / "n1battle_jp.tbl")
    rom = args.rom.read_bytes()
    if len(rom) != 0x400000 or sha256(rom) != SOURCE_ROM_SHA256:
        raise ValueError("unexpected source ROM; expected verified Japanese Rev 1")

    source_pointer_bytes = rom[POINTER_START:POINTER_START + POINTER_LENGTH]
    source_pool = rom[POOL_START:POOL_END]
    if sha256(source_pointer_bytes) != POINTER_SOURCE_SHA256:
        raise ValueError("auxiliary pointer table source hash changed")
    if sha256(source_pool) != POOL_SOURCE_SHA256:
        raise ValueError("auxiliary text pool source hash changed")

    source_targets: list[int] = []
    source_sequences: dict[int, bytes] = {}
    source_text: dict[int, str] = {}
    ids_by_target: dict[int, list[int]] = {}
    for index in range(POINTER_COUNT):
        relative_words = struct.unpack_from("<H", source_pointer_bytes, index * 2)[0]
        target = POOL_START + relative_words * 2
        if not POOL_START <= target < POOL_END or target % 2:
            raise ValueError(f"invalid source pointer {index:02X}: 0x{target:06X}")
        sequence = n1tool.words_at(rom, target, POOL_END)
        if not sequence or sequence[-1][1] != n1tool.CONTROL_WORDS["END"]:
            raise ValueError(f"unterminated source target 0x{target:06X}")
        payload = rom[target:sequence[-1][0] + 2]
        text = "".join(n1tool.token_for(word, decode) for _, word in sequence)
        source_targets.append(target)
        source_sequences[target] = payload
        source_text[target] = text
        ids_by_target.setdefault(target, []).append(index)

    translation_by_target: dict[int, str] = {}
    for representative, translation in TRANSLATIONS.items():
        target = source_targets[representative]
        previous = translation_by_target.setdefault(target, translation)
        if previous != translation:
            raise ValueError(f"conflicting translations for target 0x{target:06X}")

    japanese_targets = {
        target for target, text in source_text.items() if contains_japanese(text)
    }
    missing = japanese_targets - set(translation_by_target)
    extra = set(translation_by_target) - japanese_targets
    if missing or extra:
        raise ValueError(
            "translation inventory mismatch: "
            f"missing={[f'0x{x:06X}' for x in sorted(missing)]}, "
            f"extra={[f'0x{x:06X}' for x in sorted(extra)]}"
        )
    if len(japanese_targets) != 88:
        raise ValueError(f"expected 88 Japanese source targets, found {len(japanese_targets)}")

    pointer_output = bytearray(POINTER_LENGTH)
    pool_output = bytearray(struct.pack("<H", n1tool.CONTROL_WORDS["END"]) * (POOL_LENGTH // 2))
    packed_offsets: dict[bytes, int] = {}
    output_target_for_source: dict[int, int] = {}
    cursor = 0
    inventory: list[dict[str, object]] = []

    for source_target in sorted(source_sequences, key=lambda value: min(ids_by_target[value])):
        translation = translation_by_target.get(source_target)
        if translation is None:
            # Several entries are nothing but layout spaces followed by END.
            # They are semantically the same empty string; canonicalizing them
            # is what makes the longer official English credit names fit while
            # preserving every non-blank opaque/control sequence byte-for-byte.
            visible_source = source_text[source_target].removesuffix("[END]")
            if visible_source.strip() == "":
                payload = n1tool.pack_words([n1tool.CONTROL_WORDS["END"]])
            else:
                payload = source_sequences[source_target]
        else:
            words = n1tool.encode_text(translation, encode)
            payload = n1tool.pack_words([*words, n1tool.CONTROL_WORDS["END"]])
        if payload not in packed_offsets:
            if cursor + len(payload) > POOL_LENGTH:
                raise ValueError(
                    f"translated pool needs {cursor + len(payload)} bytes; capacity is {POOL_LENGTH}"
                )
            packed_offsets[payload] = cursor
            pool_output[cursor:cursor + len(payload)] = payload
            cursor += len(payload)
        output_offset = packed_offsets[payload]
        output_target_for_source[source_target] = POOL_START + output_offset
        if translation is not None:
            inventory.append({
                "pointer_ids": [f"05:{index:02X}" for index in ids_by_target[source_target]],
                "source_target": f"0x{source_target:06X}",
                "source_text": source_text[source_target].removesuffix("[END]"),
                "translation": translation,
                "output_target": f"0x{POOL_START + output_offset:06X}",
                "output_bytes": len(payload),
            })

    for index, source_target in enumerate(source_targets):
        relative = output_target_for_source[source_target] - POOL_START
        if relative % 2:
            raise AssertionError("generated target is not word aligned")
        struct.pack_into("<H", pointer_output, index * 2, relative // 2)

    # Decode every generated target through the final pointers.  This verifies
    # termination, bounds and the absence of Japanese rather than merely
    # trusting the translation dictionary.
    generated_blob = bytes(pool_output)
    remaining: list[dict[str, object]] = []
    unique_output_targets: set[int] = set()
    for index in range(POINTER_COUNT):
        relative_words = struct.unpack_from("<H", pointer_output, index * 2)[0]
        relative = relative_words * 2
        unique_output_targets.add(relative)
        words: list[int] = []
        for offset in range(relative, POOL_LENGTH, 2):
            word = struct.unpack_from("<H", generated_blob, offset)[0]
            words.append(word)
            if word == n1tool.CONTROL_WORDS["END"]:
                break
        if not words or words[-1] != n1tool.CONTROL_WORDS["END"]:
            raise ValueError(f"generated pointer 05:{index:02X} is unterminated")
        text = "".join(n1tool.token_for(word, decode) for word in words)
        if contains_japanese(text):
            remaining.append({"pointer_id": f"05:{index:02X}", "text": text})
    if remaining:
        raise ValueError(f"Japanese remains in generated auxiliary pool: {remaining[:5]}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    pointer_path = args.output_dir / ASSET_POINTERS
    pool_path = args.output_dir / ASSET_POOL
    pointer_path.write_bytes(pointer_output)
    pool_path.write_bytes(pool_output)

    report = {
        "family": "auxiliary_text_pool",
        "project_version": "0.9.0",
        "source_rom_sha256": SOURCE_ROM_SHA256,
        "layout": {
            "pointer_start": f"0x{POINTER_START:06X}",
            "pointer_count": POINTER_COUNT,
            "pointer_unit_bytes": 2,
            "pool_start": f"0x{POOL_START:06X}",
            "pool_end_exclusive": f"0x{POOL_END:06X}",
            "pool_capacity_bytes": POOL_LENGTH,
        },
        "source": {
            "unique_pointer_targets": len(source_sequences),
            "japanese_unique_targets": len(japanese_targets),
            "pointer_sha256": POINTER_SOURCE_SHA256,
            "pool_sha256": POOL_SOURCE_SHA256,
        },
        "output": {
            "unique_pointer_targets": len(unique_output_targets),
            "translated_unique_targets": len(inventory),
            "remaining_japanese_targets": 0,
            "used_pool_bytes": cursor,
            "free_pool_bytes": POOL_LENGTH - cursor,
            "pointer_asset": ASSET_POINTERS,
            "pointer_asset_sha256": sha256(pointer_output),
            "pool_asset": ASSET_POOL,
            "pool_asset_sha256": sha256(pool_output),
            "unused_bytes_filled_with": "0x8000 END words",
        },
        "official_reference": {
            "title": "Mega Man Battle Chip Challenge (USA)",
            "sha256": "e38da6e5dcdaf565ec1969ef6cbd95c4a307d87d3c853e23926ff2ce4497feb4",
            "credits_ascii_table_offset": "0x234D6C",
        },
        "translations": inventory,
    }
    report_path = args.output_dir / REPORT_NAME
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
