#!/usr/bin/env python3
"""Validate the US GBA reference and build bounded WSC terminology assets.

The tool never writes either ROM.  It imports the official chip names,
battle-effect labels, chip descriptions, character/operator names, and Navi
attack names that have verified equivalents in Rockman EXE N1 Battle, then
emits bounded binary assets for n1tool.py.  Both input revisions are guarded
by SHA-256 before any asset is created.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path


GBA_SIZE = 0x800000
GBA_SHA256 = "e38da6e5dcdaf565ec1969ef6cbd95c4a307d87d3c853e23926ff2ce4497feb4"
GBA_TITLE = b"BATTLECHIPGP"
GBA_GAME_CODE = b"A89E"
GBA_CHIP_COUNT = 248
GBA_CHIP_NAME_TABLE = 0x22BB90
GBA_EFFECT_TABLE = 0x22BF78
GBA_CHIP_DESCRIPTION_TABLE = 0x22C35C
GBA_OPERATOR_NAME_TABLE = 0x22D69C
GBA_NAVI_ATTACK_NAME_TABLE = 0x229828
GBA_NAVI_ATTACK_SENTINEL = 0x2298EC
GBA_SCRIPT_GROUP_TABLE = 0x20B6A4
GBA_SCRIPT_POINTER_LISTS = 0x20F340
GBA_SCRIPT_POINTER_LISTS_END = 0x223CC0
GBA_SCRIPT_TEXT_START = 0x081EB8
GBA_SCRIPT_TEXT_END = 0x0E9BE4
GBA_SCRIPT_GROUP_COUNT = (GBA_SCRIPT_POINTER_LISTS - GBA_SCRIPT_GROUP_TABLE) // 4

WSC_SIZE = 0x400000
WSC_SHA256 = "4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed"
WSC_CHIP_COUNT = 249
WSC_OPERATOR_COUNT = 135
WSC_NAVI_ATTACK_COUNT = 49

# The four generic Navis appear in a different elemental order between the
# Japanese WSC game and the US GBA reference.  Import by identity, not by raw
# table index.  All other entries retain their index.
WSC_TO_GBA_OPERATOR_INDEX = tuple(range(44)) + (45, 44, 47, 46, 48) + tuple(
    range(49, WSC_OPERATOR_COUNT)
)
WSC_TO_GBA_NAVI_ATTACK_INDEX = tuple(range(44)) + (45, 44, 47, 46, 48)

SAVE_SIZE = 0x8000
SAVE_SECTOR_SIZE = 0x2000
SAVE_PAYLOAD_LENGTH = 0x1734
SAVE_MAGIC = b"INTI"


@dataclass(frozen=True)
class WscFarTable:
    name: str
    pointer_start: int
    count: int
    data_start: int
    data_end: int


CHIP_NAMES = WscFarTable(
    "chip_names", 0x367C20, WSC_CHIP_COUNT, 0x368010, 0x369160
)
EFFECT_LABELS = WscFarTable(
    "effect_labels", 0x369160, WSC_CHIP_COUNT, 0x369550, 0x36A4E0
)
OPERATOR_NAMES = WscFarTable(
    "operator_names", 0x36EA8C, WSC_OPERATOR_COUNT, 0x36E1D0, 0x36EA8C
)
NAVI_ATTACK_NAMES = WscFarTable(
    "navi_attack_names", 0x367592, WSC_NAVI_ATTACK_COUNT, 0x367170, 0x367592
)
WSC_NAVI_ATTACK_SENTINEL = 0x367656

JP_NO_DATA = (0x0048, 0x0078, 0x001A, 0x00AD, 0x00A4)

DESCRIPTION_OUTER_POINTERS = 0x36A4E0
DESCRIPTION_COUNT = 249
DESCRIPTION_BLOCK_END = 0x36E1C8
DESCRIPTION_TEXT_POOLS = (
    (0x36A8D0, 0x36B8DE),
    (0x36BB90, 0x36C7BC),
    (0x36CA30, 0x36D3FC),
    (0x36D650, 0x36DFAC),
)
DESCRIPTION_LIST_POOLS = (
    (0x36B8DE, 0x36BB8A),
    (0x36C7BC, 0x36CA28),
    (0x36D3FC, 0x36D648),
    (0x36DFAC, 0x36E1C8),
)


def die(message: str) -> "NoReturn":
    raise SystemExit(f"error: {message}")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_verified(path: Path, size: int, expected_sha256: str, label: str) -> bytes:
    data = path.read_bytes()
    if len(data) != size:
        die(f"{label} is {len(data)} bytes; expected {size}")
    actual = sha256(data)
    if actual != expected_sha256:
        die(f"unsupported {label} SHA-256 {actual}; expected {expected_sha256}")
    return data


def gba_header(data: bytes) -> dict[str, object]:
    complement_valid = (sum(data[0xA0:0xBD]) + 0x19 + data[0xBD]) & 0xFF == 0
    return {
        "title": data[0xA0:0xAC].decode("ascii", errors="replace").rstrip("\0"),
        "game_code": data[0xAC:0xB0].decode("ascii", errors="replace"),
        "maker_code": data[0xB0:0xB2].decode("ascii", errors="replace"),
        "fixed_value": f"0x{data[0xB2]:02X}",
        "software_version": data[0xBC],
        "header_complement": f"0x{data[0xBD]:02X}",
        "header_complement_valid": complement_valid,
        "sram_signature": b"SRAM_V113" in data,
    }


def validate_gba_identity(data: bytes) -> None:
    info = gba_header(data)
    if data[0xA0:0xAC] != GBA_TITLE:
        die(f"unexpected GBA title {info['title']!r}")
    if data[0xAC:0xB0] != GBA_GAME_CODE:
        die(f"unexpected GBA game code {info['game_code']!r}")
    if data[0xB2] != 0x96 or not info["header_complement_valid"]:
        die("invalid GBA cartridge header")
    if not info["sram_signature"]:
        die("the expected SRAM_V113 signature is missing")


def load_encode_table(path: Path) -> dict[str, int]:
    result: dict[str, int] = {}
    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(), 1
    ):
        if not raw or raw.lstrip().startswith(("#", ";")):
            continue
        if "=" not in raw:
            die(f"invalid table line {path}:{line_number}")
        key, value = raw.split("=", 1)
        try:
            key_bytes = bytes.fromhex(key)
        except ValueError:
            die(f"invalid table key at {path}:{line_number}")
        if len(key_bytes) != 2:
            die(f"table key must contain two bytes at {path}:{line_number}")
        value = value.replace(r"\[", "[").replace(r"\]", "]")
        if value and value not in result:
            result[value] = int.from_bytes(key_bytes, "little")
    return result


def load_decode_table(path: Path) -> dict[int, str]:
    result: dict[int, str] = {}
    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(), 1
    ):
        if not raw or raw.lstrip().startswith(("#", ";")):
            continue
        if "=" not in raw:
            die(f"invalid table line {path}:{line_number}")
        key, value = raw.split("=", 1)
        try:
            key_bytes = bytes.fromhex(key)
        except ValueError:
            die(f"invalid table key at {path}:{line_number}")
        if len(key_bytes) != 2:
            die(f"table key must contain two bytes at {path}:{line_number}")
        result[int.from_bytes(key_bytes, "little")] = value.replace(
            r"\[", "["
        ).replace(r"\]", "]")
    return result


def read_words(data: bytes, offset: int, label: str) -> list[int]:
    result: list[int] = []
    for _ in range(256):
        if offset + 2 > len(data):
            die(f"{label} runs outside its ROM")
        word = struct.unpack_from("<H", data, offset)[0]
        offset += 2
        result.append(word)
        if word & 0x8000:
            character_count = len(result) - 1
            if (word & 0xFF) != character_count:
                die(
                    f"{label} terminator says {word & 0xFF} characters; "
                    f"read {character_count}"
                )
            return result
    die(f"{label} has no terminator within 256 words")


def gba_pointer(data: bytes, table: int, index: int, label: str) -> int:
    pointer = struct.unpack_from("<I", data, table + index * 4)[0]
    if not 0x08000000 <= pointer < 0x08000000 + len(data):
        die(f"{label}[{index}] has invalid GBA pointer 0x{pointer:08X}")
    return pointer - 0x08000000


def wsc_pointer(data: bytes, table: int, index: int, label: str) -> int:
    offset, segment = struct.unpack_from("<HH", data, table + index * 4)
    physical = 0x300000 + segment * 16 + offset
    if not 0 <= physical < len(data):
        die(
            f"{label}[{index}] has invalid far pointer "
            f"{segment:04X}:{offset:04X}"
        )
    return physical


def encode_wsc_far_pointer(physical: int) -> bytes:
    logical = physical - 0x300000
    if not 0 <= logical <= 0xFFFFF:
        die(f"cannot encode WSC far pointer for file offset 0x{physical:06X}")
    segment, offset = divmod(logical, 16)
    return struct.pack("<HH", offset, segment)


def write_wsc_far_pointer(output: bytearray, entry: int, physical: int) -> None:
    output[entry : entry + 4] = encode_wsc_far_pointer(physical)


def encode_static(text: str, encode: dict[str, int], style: int = 0) -> tuple[int, ...]:
    # The US font assigns underscore to 0x0099.  On WSC that code is a
    # hiragana glyph; 0x0079 is the game's established unavailable/code mark.
    text = text.replace("_", "×")
    words: list[int] = []
    for character in text:
        if character not in encode:
            die(f"the WSC font cannot encode {character!r} in {text!r}")
        words.append(encode[character] | style)
    if len(words) > 0xFF:
        die("a static string exceeds the 255-character terminator limit")
    words.append(0x8000 | len(words))
    return tuple(words)


def pack_unique(
    output: bytearray,
    sequences: list[tuple[int, ...]],
    spans: tuple[tuple[int, int], ...],
    label: str,
) -> tuple[list[int], dict[str, object]]:
    addresses: dict[tuple[int, ...], int] = {}
    cursors = [start for start, _ in spans]
    span_index = 0
    for sequence in sequences:
        if sequence in addresses:
            continue
        payload = b"".join(struct.pack("<H", word) for word in sequence)
        while (
            span_index < len(spans)
            and cursors[span_index] + len(payload) > spans[span_index][1]
        ):
            span_index += 1
        if span_index >= len(spans):
            capacity = sum(end - start for start, end in spans)
            die(f"{label} exceeds its bounded capacity of {capacity} bytes")
        target = cursors[span_index]
        output[target : target + len(payload)] = payload
        cursors[span_index] += len(payload)
        addresses[sequence] = target
    used = sum(cursor - start for cursor, (start, _) in zip(cursors, spans))
    capacity = sum(end - start for start, end in spans)
    return [addresses[sequence] for sequence in sequences], {
        "sequence_count": len(sequences),
        "unique_sequence_count": len(addresses),
        "used_bytes": used,
        "capacity_bytes": capacity,
        "free_bytes": capacity - used,
        "spans": [f"0x{start:06X}-0x{end - 1:06X}" for start, end in spans],
        "span_cursors": [f"0x{cursor:06X}" for cursor in cursors],
    }


def merged_original_string_spans(
    source: bytes, layout: WscFarTable
) -> tuple[tuple[int, int], ...]:
    """Return the exact occupied byte spans of an existing WSC string table.

    Navi attack strings share a broader region with alignment gaps.  Those
    gaps are not assumed to be disposable: only the union of the original,
    terminated strings is made available to the English packer.
    """

    spans: list[tuple[int, int]] = []
    for index in range(layout.count):
        start = wsc_pointer(source, layout.pointer_start, index, layout.name)
        words = read_words(source, start, f"WSC {layout.name}[{index}]")
        end = start + len(words) * 2
        if not layout.data_start <= start < end <= layout.data_end:
            die(
                f"{layout.name}[{index}] occupies 0x{start:06X}-"
                f"0x{end - 1:06X}, outside its verified data region"
            )
        spans.append((start, end))

    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            previous_start, previous_end = merged[-1]
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return tuple(merged)


def pack_unique_best_fit(
    output: bytearray,
    sequences: list[tuple[int, ...]],
    spans: tuple[tuple[int, int], ...],
    label: str,
) -> tuple[list[int], dict[str, object]]:
    """Pack deduplicated strings with deterministic best-fit decreasing.

    Stable size ordering and the lowest-index tie break make the emitted
    assets reproducible while avoiding the fragmentation that a sequential
    first-fit pass creates in the Navi attack string spans.
    """

    unique_sequences = list(dict.fromkeys(sequences))
    ordered = sorted(
        enumerate(unique_sequences),
        key=lambda item: (-len(item[1]), item[0]),
    )
    cursors = [start for start, _ in spans]
    addresses: dict[tuple[int, ...], int] = {}
    for _, sequence in ordered:
        payload = b"".join(struct.pack("<H", word) for word in sequence)
        candidates = [
            index
            for index, (_, end) in enumerate(spans)
            if cursors[index] + len(payload) <= end
        ]
        if not candidates:
            capacity = sum(end - start for start, end in spans)
            die(f"{label} exceeds its bounded capacity of {capacity} bytes")
        span_index = min(
            candidates,
            key=lambda index: (
                spans[index][1] - cursors[index] - len(payload),
                index,
            ),
        )
        target = cursors[span_index]
        output[target : target + len(payload)] = payload
        cursors[span_index] += len(payload)
        addresses[sequence] = target

    used = sum(cursor - start for cursor, (start, _) in zip(cursors, spans))
    capacity = sum(end - start for start, end in spans)
    return [addresses[sequence] for sequence in sequences], {
        "algorithm": "best-fit decreasing; stable source order; lowest-span tie break",
        "sequence_count": len(sequences),
        "unique_sequence_count": len(addresses),
        "used_bytes": used,
        "capacity_bytes": capacity,
        "free_bytes": capacity - used,
        "spans": [f"0x{start:06X}-0x{end - 1:06X}" for start, end in spans],
        "span_cursors": [f"0x{cursor:06X}" for cursor in cursors],
    }


def pack_table(
    source: bytes, layout: WscFarTable, strings: list[list[int]]
) -> tuple[bytes, bytes, dict[str, object]]:
    if len(strings) != layout.count:
        die(f"{layout.name}: got {len(strings)} strings; expected {layout.count}")

    cursor = layout.data_start
    pointers = bytearray()
    packed = bytearray()
    for index, words in enumerate(strings):
        encoded = b"".join(struct.pack("<H", word) for word in words)
        if cursor + len(encoded) > layout.data_end:
            die(
                f"{layout.name}[{index}] exceeds its bounded region "
                f"ending at 0x{layout.data_end:06X}"
            )
        pointers += encode_wsc_far_pointer(cursor)
        packed += encoded
        cursor += len(encoded)

    data_asset = bytearray(source[layout.data_start : layout.data_end])
    data_asset[: len(packed)] = packed
    pointer_asset = bytes(pointers)
    expected_pointer_size = layout.count * 4
    if len(pointer_asset) != expected_pointer_size:
        die(f"{layout.name}: internal pointer-size error")
    return pointer_asset, bytes(data_asset), {
        "pointer_range": (
            f"0x{layout.pointer_start:06X}-"
            f"0x{layout.pointer_start + expected_pointer_size - 1:06X}"
        ),
        "data_range": f"0x{layout.data_start:06X}-0x{layout.data_end - 1:06X}",
        "strings": layout.count,
        "bytes_used": len(packed),
        "capacity": layout.data_end - layout.data_start,
        "bytes_free": layout.data_end - cursor,
    }


def no_data_words(encode: dict[str, int], style: int = 0) -> list[int]:
    try:
        words = [(encode[character] | style) for character in "No Data"]
    except KeyError as error:
        die(f"reference table cannot encode {error.args[0]!r}")
    words.append(0x8000 | len(words))
    return words


def gba_text(
    gba: bytes,
    pointer_table: int,
    index: int,
    label: str,
    decode: dict[int, str],
) -> str:
    pointer = gba_pointer(gba, pointer_table, index, label)
    words = read_words(gba, pointer, f"{label}[{index}]")
    text = decode_gba_words(words, decode)
    if "<0x" in text:
        die(f"{label}[{index}] contains an unknown glyph: {text}")
    return text


def gba_description_lines(
    gba: bytes, index: int, decode: dict[int, str]
) -> list[str]:
    list_offset = gba_pointer(
        gba, GBA_CHIP_DESCRIPTION_TABLE, index, "GBA chip_descriptions"
    )
    result: list[str] = []
    for line_index in range(4):
        pointer = struct.unpack_from("<I", gba, list_offset + line_index * 4)[0]
        if pointer == 0:
            if not result:
                die(f"GBA chip_descriptions[{index}] is empty")
            return result
        if not 0x08000000 <= pointer < 0x08000000 + len(gba):
            die(
                f"GBA chip_descriptions[{index}][{line_index}] has invalid "
                f"pointer 0x{pointer:08X}"
            )
        words = read_words(
            gba,
            pointer - 0x08000000,
            f"GBA chip_descriptions[{index}][{line_index}]",
        )
        text = decode_gba_words(words, decode)
        if "<0x" in text:
            die(f"GBA chip_descriptions[{index}][{line_index}] has {text}")
        result.append(text)
    die(f"GBA chip_descriptions[{index}] has no zero sentinel")


def normalize_large_card_effect(text: str) -> str:
    """Return text supported by the WSC style-0x0600 8x16 renderer."""
    return text.upper()


def build_assets(
    gba: bytes,
    wsc: bytes,
    gba_decode: dict[int, str],
    wsc_encode: dict[str, int],
) -> tuple[dict[str, bytes], dict[str, object]]:
    available: list[bool] = []
    for index in range(WSC_CHIP_COUNT):
        pointer = wsc_pointer(wsc, CHIP_NAMES.pointer_start, index, "chip_names")
        original = read_words(wsc, pointer, f"WSC chip_names[{index}]")
        available.append(index > 0 and tuple(original[:-1]) != JP_NO_DATA)
    if available[0] or sum(available) != 113:
        die("the WSC chip-presence map differs from the verified 113 slots")

    chip_names: list[tuple[int, ...]] = []
    effect_labels: list[tuple[int, ...]] = []
    for index in range(WSC_CHIP_COUNT):
        if available[index]:
            gba_index = index - 1
            name_text = gba_text(
                gba, GBA_CHIP_NAME_TABLE, gba_index, "GBA chip_names", gba_decode
            )
            effect_text = gba_text(
                gba, GBA_EFFECT_TABLE, gba_index, "GBA effect_labels", gba_decode
            )
        else:
            name_text = effect_text = "NO DATA"
        chip_names.append(encode_static(name_text, wsc_encode))
        # The WSC large-card renderer uses a dedicated 8x16 font selected by
        # style 0x0600.  That font only contains the capital Latin glyphs;
        # feeding it the mixed-case GBA labels makes the lowercase letters
        # decode as unrelated tile rows (the coloured "garbage" visible
        # between the chip code and its power).  Preserve the official words,
        # but normalize their presentation for the native WSC renderer.
        large_effect = normalize_large_card_effect(effect_text)
        if len(large_effect) > 8:
            die(
                f"effect_labels[{index}] exceeds the WSC large-card limit "
                f"of 8 glyphs: {large_effect!r}"
            )
        if (
            large_effect != "NO DATA"
            and not set(large_effect) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+~")
        ):
            die(
                f"effect_labels[{index}] has unsupported large-card glyphs: "
                f"{large_effect!r}"
            )
        effect_labels.append(
            encode_static(
                large_effect,
                wsc_encode,
                style=0x0600,
            )
        )

    description_rows: list[list[tuple[int, ...]]] = []
    for index in range(DESCRIPTION_COUNT):
        if index == 0:
            line_texts = gba_description_lines(gba, 0, gba_decode)
        elif available[index]:
            line_texts = gba_description_lines(gba, index, gba_decode)
        else:
            line_texts = ["NO DATA"]
        description_rows.append(
            [encode_static(text, wsc_encode) for text in line_texts]
        )

    if gba[GBA_NAVI_ATTACK_SENTINEL : GBA_NAVI_ATTACK_SENTINEL + 4] != b"\0" * 4:
        die("the GBA Navi attack pointer table has no zero sentinel")
    if wsc[WSC_NAVI_ATTACK_SENTINEL : WSC_NAVI_ATTACK_SENTINEL + 4] != b"\0" * 4:
        die("the WSC Navi attack pointer table has no zero sentinel")

    operator_texts = [
        gba_text(
            gba,
            GBA_OPERATOR_NAME_TABLE,
            gba_index,
            "GBA operator_names",
            gba_decode,
        )
        for gba_index in WSC_TO_GBA_OPERATOR_INDEX
    ]
    operator_names = [
        encode_static(text, wsc_encode) for text in operator_texts
    ]
    navi_attack_texts = [
        gba_text(
            gba,
            GBA_NAVI_ATTACK_NAME_TABLE,
            gba_index,
            "GBA navi_attack_names",
            gba_decode,
        )
        for gba_index in WSC_TO_GBA_NAVI_ATTACK_INDEX
    ]
    navi_attack_names = [
        encode_static(text, wsc_encode) for text in navi_attack_texts
    ]

    output = bytearray(wsc)
    name_addresses, name_report = pack_unique(
        output,
        chip_names,
        ((CHIP_NAMES.data_start, CHIP_NAMES.data_end),),
        "chip names",
    )
    effect_addresses, effect_report = pack_unique(
        output,
        effect_labels,
        ((EFFECT_LABELS.data_start, EFFECT_LABELS.data_end),),
        "effect labels",
    )
    operator_addresses, operator_report = pack_unique(
        output,
        operator_names,
        ((OPERATOR_NAMES.data_start, OPERATOR_NAMES.data_end),),
        "operator names",
    )
    navi_attack_spans = merged_original_string_spans(wsc, NAVI_ATTACK_NAMES)
    navi_attack_capacity = sum(end - start for start, end in navi_attack_spans)
    if (
        len(navi_attack_spans) != 31
        or navi_attack_capacity != 772
        or navi_attack_spans[0][0] != NAVI_ATTACK_NAMES.data_start
        or navi_attack_spans[-1][1] != NAVI_ATTACK_NAMES.data_end
    ):
        die("the WSC Navi attack string-span layout differs from the verified ROM")
    navi_attack_addresses, navi_attack_report = pack_unique_best_fit(
        output,
        navi_attack_names,
        navi_attack_spans,
        "Navi attack names",
    )
    for index, target in enumerate(name_addresses):
        write_wsc_far_pointer(output, CHIP_NAMES.pointer_start + index * 4, target)
    for index, target in enumerate(effect_addresses):
        write_wsc_far_pointer(output, EFFECT_LABELS.pointer_start + index * 4, target)
    for index, target in enumerate(operator_addresses):
        write_wsc_far_pointer(output, OPERATOR_NAMES.pointer_start + index * 4, target)
    for index, target in enumerate(navi_attack_addresses):
        write_wsc_far_pointer(
            output, NAVI_ATTACK_NAMES.pointer_start + index * 4, target
        )

    flat_descriptions = [sequence for row in description_rows for sequence in row]
    flat_addresses, description_text_report = pack_unique(
        output,
        flat_descriptions,
        DESCRIPTION_TEXT_POOLS,
        "chip-description text",
    )
    cursor = 0
    description_address_rows: list[list[int]] = []
    for row in description_rows:
        description_address_rows.append(flat_addresses[cursor : cursor + len(row)])
        cursor += len(row)

    description_lists: list[tuple[int, ...]] = []
    for address_row in description_address_rows:
        words: list[int] = []
        for target in address_row:
            offset, segment = struct.unpack("<HH", encode_wsc_far_pointer(target))
            words.extend((offset, segment))
        words.extend((0, 0))
        description_lists.append(tuple(words))
    list_addresses, description_list_report = pack_unique(
        output,
        description_lists,
        DESCRIPTION_LIST_POOLS,
        "chip-description pointer lists",
    )
    for index, target in enumerate(list_addresses):
        write_wsc_far_pointer(
            output, DESCRIPTION_OUTER_POINTERS + index * 4, target
        )

    assets: dict[str, bytes] = {
        "chip_names_pointers.bin": bytes(
            output[
                CHIP_NAMES.pointer_start : CHIP_NAMES.pointer_start
                + CHIP_NAMES.count * 4
            ]
        ),
        "chip_names_data.bin": bytes(
            output[CHIP_NAMES.data_start : CHIP_NAMES.data_end]
        ),
        "effect_labels_pointers.bin": bytes(
            output[
                EFFECT_LABELS.pointer_start : EFFECT_LABELS.pointer_start
                + EFFECT_LABELS.count * 4
            ]
        ),
        "effect_labels_data.bin": bytes(
            output[EFFECT_LABELS.data_start : EFFECT_LABELS.data_end]
        ),
        "chip_descriptions.bin": bytes(
            output[DESCRIPTION_OUTER_POINTERS:DESCRIPTION_BLOCK_END]
        ),
        "operator_names_pointers_v0_6.bin": bytes(
            output[
                OPERATOR_NAMES.pointer_start : OPERATOR_NAMES.pointer_start
                + OPERATOR_NAMES.count * 4
            ]
        ),
        "operator_names_data_v0_6.bin": bytes(
            output[OPERATOR_NAMES.data_start : OPERATOR_NAMES.data_end]
        ),
        "navi_attack_names_pointers_v0_6.bin": bytes(
            output[
                NAVI_ATTACK_NAMES.pointer_start : NAVI_ATTACK_NAMES.pointer_start
                + NAVI_ATTACK_NAMES.count * 4
            ]
        ),
        "navi_attack_names_data_v0_6.bin": bytes(
            output[NAVI_ATTACK_NAMES.data_start : NAVI_ATTACK_NAMES.data_end]
        ),
    }

    operator_remap = [
        {
            "wsc_index": wsc_index,
            "gba_index": gba_index,
            "official_name": operator_texts[wsc_index],
        }
        for wsc_index, gba_index in enumerate(WSC_TO_GBA_OPERATOR_INDEX)
        if wsc_index != gba_index
    ]
    attack_remap = [
        {
            "wsc_index": wsc_index,
            "gba_index": gba_index,
            "wsc_navi": operator_texts[wsc_index],
            "official_attack": navi_attack_texts[wsc_index],
        }
        for wsc_index, gba_index in enumerate(WSC_TO_GBA_NAVI_ATTACK_INDEX)
        if wsc_index != gba_index
    ]

    report = {
        "format": "n1battle-bcc-reference-import-v3",
        "gba_reference": {
            "sha256": sha256(gba),
            **gba_header(gba),
        },
        "wsc_source": {"sha256": sha256(wsc)},
        "mapping": {
            "wsc_chip_slots": WSC_CHIP_COUNT,
            "translated_chip_slots": sum(available),
            "no_data_slots": available.count(False),
            "gba_chip_index_rule": "gba_index = wsc_index - 1 for populated WSC slots",
            "translated_description_rows": DESCRIPTION_COUNT,
            "translated_operator_names": WSC_OPERATOR_COUNT,
            "translated_navi_attack_names": WSC_NAVI_ATTACK_COUNT,
            "underscore_adaptation": "US '_' glyph becomes WSC '×'",
            "operator_identity_remap": operator_remap,
            "navi_attack_identity_remap": attack_remap,
        },
        "pools": {
            "chip_names": name_report,
            "effect_labels": effect_report,
            "description_text": description_text_report,
            "description_pointer_lists": description_list_report,
            "operator_names": operator_report,
            "navi_attack_names": {
                **navi_attack_report,
                "far_pointer_offset_low_nibbles": sorted(
                    {
                        (address - 0x300000) & 0xF
                        for address in navi_attack_addresses
                    }
                ),
            },
        },
        "assets": {
            name: {"size": len(data), "sha256": sha256(data)}
            for name, data in sorted(assets.items())
        },
    }
    return assets, report


def decode_save_words(
    data: bytes, offset: int, table: dict[int, str], limit: int
) -> str:
    result: list[str] = []
    for index in range(limit):
        word = struct.unpack_from("<H", data, offset + index * 2)[0]
        if word & 0x8000:
            break
        glyph = word & 0x01FF
        result.append(table.get(glyph, f"<0x{glyph:03X}>"))
    return "".join(result)


def save_sector_report(data: bytes, physical_sector: int) -> dict[str, object]:
    offset = physical_sector * SAVE_SECTOR_SIZE
    block = data[offset : offset + SAVE_SECTOR_SIZE]
    logical_slot = physical_sector & 1
    if len(block) != SAVE_SECTOR_SIZE:
        return {
            "physical_sector": physical_sector,
            "offset": f"0x{offset:04X}",
            "logical_slot": logical_slot,
            "valid": False,
            "error": "sector truncated",
        }

    blank = all(value == 0xFF for value in block)
    stored_checksum = struct.unpack_from("<I", block, 0x04)[0]
    payload_length = struct.unpack_from("<I", block, 0x08)[0]
    payload_end = 0x10 + payload_length
    computed_checksum = (
        sum(block[0x10:payload_end]) & 0xFFFFFFFF
        if payload_end <= len(block)
        else None
    )
    checks = {
        "not_blank": not blank,
        "magic_INTI": block[0:4] == SAVE_MAGIC,
        "payload_length_0x1734": payload_length == SAVE_PAYLOAD_LENGTH,
        "marker_0x0C_zero": block[0x0C] == 0,
        "format_version_2": block[0x0D] == 2,
        "logical_slot_matches_sector": block[0x0E] == logical_slot,
        "committed_marker_1": block[0x0F] == 1,
        "checksum_matches": computed_checksum == stored_checksum,
    }
    return {
        "physical_sector": physical_sector,
        "offset": f"0x{offset:04X}",
        "logical_slot": logical_slot,
        "blank": blank,
        "magic": block[0:4].decode("ascii", errors="replace"),
        "stored_checksum": f"0x{stored_checksum:08X}",
        "computed_checksum": (
            f"0x{computed_checksum:08X}" if computed_checksum is not None else None
        ),
        "payload_length": f"0x{payload_length:X}",
        "format_version": block[0x0D],
        "header_slot": block[0x0E],
        "committed_marker": block[0x0F],
        "checks": checks,
        "valid": all(checks.values()),
    }


def save_metadata(
    path: Path, gba: bytes, decode: dict[int, str]
) -> tuple[dict[str, object], bool]:
    data = path.read_bytes()
    sectors = (
        [save_sector_report(data, index) for index in range(4)]
        if len(data) == SAVE_SIZE
        else []
    )
    valid_sectors = [sector for sector in sectors if sector.get("valid")]
    result: dict[str, object] = {
        "path": str(path),
        "size": len(data),
        "sha256": sha256(data),
        "expected_sram_size": SAVE_SIZE,
        "raw_32KiB_SRAM": len(data) == SAVE_SIZE,
        "non_ff_bytes": sum(byte != 0xFF for byte in data),
        "non_zero_bytes": sum(byte != 0x00 for byte in data),
        "valid_sector_count": len(valid_sectors),
        "sectors": sectors,
    }
    if len(data) == SAVE_SIZE:
        result["redundancy"] = {
            "logical_slot_0_copies_identical": (
                data[0x0000:0x2000] == data[0x4000:0x6000]
            ),
            "logical_slot_1_copies_identical": (
                data[0x2000:0x4000] == data[0x6000:0x8000]
            ),
        }

    if valid_sectors:
        first_offset = int(str(valid_sectors[0]["offset"]), 16)
        block = data[first_offset : first_offset + SAVE_SECTOR_SIZE]
        library = block[0x531 : 0x531 + GBA_CHIP_COUNT]
        navi_id = block[0x37D]
        navi_name = None
        if navi_id < GBA_CHIP_COUNT:
            name_offset = gba_pointer(gba, GBA_CHIP_NAME_TABLE, navi_id, "navi_name")
            navi_name = decode_gba_words(
                read_words(gba, name_offset, "selected_navi_name"), decode
            )
        result["progress"] = {
            "source_physical_sector": valid_sectors[0]["physical_sector"],
            "player_name": decode_save_words(block, 0x1720, decode, 4),
            "zenny": struct.unpack_from("<I", block, 0x20)[0],
            "selected_navi_chip_id": navi_id,
            "selected_navi_name": navi_name,
            "deck_memory": struct.unpack_from("<H", block, 0x38A)[0],
            "slot_in_memory": struct.unpack_from("<H", block, 0x38C)[0],
            "library_flag_records": len(library),
            "library_flags_with_collected_bit": sum(
                value & 1 == 1 for value in library
            ),
            "matches_complete_library_pattern": (
                len(library) == GBA_CHIP_COUNT
                and library[0] == 0x83
                and all(value == 0x81 for value in library[1:])
            ),
        }
    valid = len(data) == SAVE_SIZE and bool(valid_sectors)
    return result, valid


def decode_gba_words(words: list[int], table: dict[int, str]) -> str:
    return "".join(
        table.get(word & 0x01FF, f"<0x{word & 0x01FF:03X}>")
        for word in words[:-1]
    )


def dump_script(gba: bytes, decode: dict[int, str]) -> dict[str, object]:
    list_offsets = [
        gba_pointer(gba, GBA_SCRIPT_GROUP_TABLE, index, "script_groups")
        for index in range(GBA_SCRIPT_GROUP_COUNT)
    ]
    if list_offsets[0] != GBA_SCRIPT_POINTER_LISTS:
        die("the script hierarchy does not start at the expected pointer list")
    if any(current >= following for current, following in zip(list_offsets, list_offsets[1:])):
        die("script group pointer lists are not strictly increasing")

    groups: list[dict[str, object]] = []
    flat_lines: list[dict[str, object]] = []
    for group_index, list_offset in enumerate(list_offsets):
        next_list = (
            list_offsets[group_index + 1]
            if group_index + 1 < len(list_offsets)
            else GBA_SCRIPT_POINTER_LISTS_END
        )
        if (next_list - list_offset) % 4:
            die(f"script group {group_index} has an unaligned pointer list")
        raw_pointers = [
            struct.unpack_from("<I", gba, offset)[0]
            for offset in range(list_offset, next_list, 4)
        ]
        if not raw_pointers or raw_pointers[-1] != 0 or 0 in raw_pointers[:-1]:
            die(f"script group {group_index} has an invalid zero sentinel")

        lines: list[dict[str, object]] = []
        for line_index, pointer in enumerate(raw_pointers[:-1]):
            if not 0x08000000 <= pointer < 0x08000000 + len(gba):
                die(
                    f"script group {group_index}, line {line_index} has "
                    f"invalid pointer 0x{pointer:08X}"
                )
            offset = pointer - 0x08000000
            words = read_words(gba, offset, f"script[{group_index}][{line_index}]")
            line = {
                "line_index": line_index,
                "pointer": f"0x{pointer:08X}",
                "offset": offset,
                "end_offset": offset + len(words) * 2,
                "glyph_count": len(words) - 1,
                "text": decode_gba_words(words, decode),
            }
            lines.append(line)
            flat_lines.append({"group_index": group_index, **line})
        groups.append(
            {
                "group_index": group_index,
                "pointer_list_offset": list_offset,
                "line_count": len(lines),
                "lines": lines,
            }
        )

    ordered = sorted(flat_lines, key=lambda item: int(item["offset"]))
    if not ordered:
        die("the GBA script corpus is empty")
    if int(ordered[0]["offset"]) != GBA_SCRIPT_TEXT_START:
        die("the GBA script corpus starts at an unexpected offset")
    if int(ordered[-1]["end_offset"]) != GBA_SCRIPT_TEXT_END:
        die("the GBA script corpus ends at an unexpected offset")
    if len({int(line["offset"]) for line in ordered}) != len(ordered):
        die("the GBA script contains unexpected shared line pointers")
    for current, following in zip(ordered, ordered[1:]):
        if int(current["end_offset"]) != int(following["offset"]):
            die("the GBA script text is not one contiguous corpus")

    return {
        "format": "battle-chip-challenge-us-script-v1",
        "source": {
            "size": len(gba),
            "sha256": sha256(gba),
            "game_code": gba[0xAC:0xB0].decode("ascii", errors="replace"),
        },
        "layout": {
            "group_pointer_table": GBA_SCRIPT_GROUP_TABLE,
            "group_count": len(groups),
            "line_pointer_lists_start": GBA_SCRIPT_POINTER_LISTS,
            "line_pointer_lists_end": GBA_SCRIPT_POINTER_LISTS_END,
            "text_start": GBA_SCRIPT_TEXT_START,
            "text_end": GBA_SCRIPT_TEXT_END,
            "line_count": len(flat_lines),
            "glyph_count": sum(int(line["glyph_count"]) for line in flat_lines),
            "max_line_glyphs": max(int(line["glyph_count"]) for line in flat_lines),
        },
        "groups": groups,
    }


def command_info(args: argparse.Namespace) -> None:
    gba = read_verified(args.gba_rom, GBA_SIZE, GBA_SHA256, "GBA ROM")
    validate_gba_identity(gba)
    result: dict[str, object] = {
        "size": len(gba),
        "sha256": sha256(gba),
        **gba_header(gba),
    }
    save_valid = True
    if args.sav:
        decode = load_decode_table(args.table)
        result["save"], save_valid = save_metadata(args.sav, gba, decode)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not save_valid:
        raise SystemExit(1)


def command_build_assets(args: argparse.Namespace) -> None:
    gba = read_verified(args.gba_rom, GBA_SIZE, GBA_SHA256, "GBA ROM")
    validate_gba_identity(gba)
    wsc = read_verified(args.wsc_rom, WSC_SIZE, WSC_SHA256, "WSC ROM")
    gba_decode = load_decode_table(args.gba_table)
    wsc_encode = load_encode_table(args.wsc_table)
    assets, report = build_assets(gba, wsc, gba_decode, wsc_encode)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, data in assets.items():
        (args.output / name).write_bytes(data)
    report_path = args.report or args.output / "bcc_reference_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


def command_dump_script(args: argparse.Namespace) -> None:
    gba = read_verified(args.gba_rom, GBA_SIZE, GBA_SHA256, "GBA ROM")
    validate_gba_identity(gba)
    decode = load_decode_table(args.table)
    result = dump_script(gba, decode)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if args.tsv:
        args.tsv.parent.mkdir(parents=True, exist_ok=True)
        with args.tsv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(
                ["group_index", "line_index", "offset", "glyph_count", "text"]
            )
            for group in result["groups"]:
                for line in group["lines"]:
                    writer.writerow(
                        [
                            group["group_index"],
                            line["line_index"],
                            f"0x{int(line['offset']):06X}",
                            line["glyph_count"],
                            line["text"],
                        ]
                    )
    print(json.dumps(result["layout"], ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    info = subparsers.add_parser("info", help="validate and identify the US GBA ROM")
    info.add_argument("gba_rom", type=Path)
    info.add_argument("--sav", type=Path, help="also validate and summarize raw SRAM")
    info.add_argument(
        "--table",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "references" / "bcc_en.tbl",
        help="GBA decoding table used for save names",
    )
    info.set_defaults(func=command_info)

    assets = subparsers.add_parser(
        "build-assets", help="regenerate bounded WSC terminology assets"
    )
    assets.add_argument("gba_rom", type=Path)
    assets.add_argument("wsc_rom", type=Path)
    assets.add_argument("output", type=Path)
    assets.add_argument("--gba-table", type=Path, required=True)
    assets.add_argument("--wsc-table", type=Path, required=True)
    assets.add_argument("--report", type=Path)
    assets.set_defaults(func=command_build_assets)

    script = subparsers.add_parser(
        "dump-script", help="dump the complete grouped English GBA script"
    )
    script.add_argument("gba_rom", type=Path)
    script.add_argument("output", type=Path)
    script.add_argument("--table", type=Path, required=True)
    script.add_argument("--tsv", type=Path)
    script.set_defaults(func=command_dump_script)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
