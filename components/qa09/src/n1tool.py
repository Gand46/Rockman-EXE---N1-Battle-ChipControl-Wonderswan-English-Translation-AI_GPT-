#!/usr/bin/env python3
"""Rockman EXE N1 Battle (WonderSwan Color) text/patch utility.

The utility intentionally targets the verified Rev 1 Japanese ROM only.  It can
dump the six verified pointer groups, apply bounded in-place translations, repair
the WonderSwan checksum, and create/apply an IPS patch without redistributing a
ROM image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROM_SIZE = 0x400000
SOURCE_SHA256 = "4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed"
SOURCE_SHA1 = "9b4786adca7b83fe66a9d4b9fd4ffaf32abe7656"
SOURCE_MD5 = "d902afdadf17b452621c50a1ffda2fa9"
SOURCE_CRC32 = "1F10CA75"


@dataclass(frozen=True)
class TextGroup:
    index: int
    pointer_table: int
    pointer_count: int
    base: int
    end: int


TEXT_GROUPS = (
    TextGroup(0, 0x34B850, 40, 0x34B8A0, 0x34CFDA),
    TextGroup(1, 0x34CFE0, 112, 0x34D0C0, 0x3540B8),
    TextGroup(2, 0x3540C0, 80, 0x354160, 0x3574CE),
    TextGroup(3, 0x3574D0, 32, 0x357510, 0x357D38),
    TextGroup(4, 0x357D40, 32, 0x357D80, 0x358732),
    # Auxiliary UI/credits pool omitted from inventories before v0.9.  Its
    # table precedes the five story groups and uses the same relative-word
    # pointer format.
    TextGroup(5, 0x34AB10, 208, 0x34ACB0, 0x34B75E),
)

CONTROL_WORDS = {
    "LINE": 0x0800,
    "WAIT": 0x4000,
    "END": 0x8000,
}


def die(message: str) -> "NoReturn":
    raise SystemExit(f"error: {message}")


def parse_number(value: str | int) -> int:
    if isinstance(value, int):
        return value
    return int(value, 0)


def digest(data: bytes, algorithm: str = "sha256") -> str:
    return hashlib.new(algorithm, data).hexdigest()


def read_rom(path: Path, require_source: bool = False) -> bytes:
    data = path.read_bytes()
    if len(data) != ROM_SIZE:
        die(f"{path} is {len(data)} bytes; expected {ROM_SIZE}")
    if require_source:
        actual = digest(data)
        if actual != SOURCE_SHA256:
            die(
                "unsupported source ROM (SHA-256 "
                f"{actual}); expected Rev 1 {SOURCE_SHA256}"
            )
    return data


def load_table(path: Path) -> tuple[dict[int, str], dict[str, int]]:
    decode: dict[int, str] = {}
    encode: dict[str, int] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip("\r\n")
        if not line or line.lstrip().startswith(('#', ';')):
            continue
        if "=" not in line:
            die(f"invalid table line {path}:{line_number}")
        key, value = line.split("=", 1)
        try:
            key_bytes = bytes.fromhex(key)
        except ValueError:
            die(f"invalid hex key at {path}:{line_number}")
        if len(key_bytes) != 2:
            die(f"table key must contain two bytes at {path}:{line_number}")
        word = int.from_bytes(key_bytes, "little")
        decode[word] = value
        if value and value not in encode:
            encode[value] = word
    for name, word in CONTROL_WORDS.items():
        decode[word] = f"[{name}]"
        encode[f"[{name}]"] = word
    return decode, encode


def token_for(word: int, table: dict[int, str]) -> str:
    if word in table and table[word] != "":
        return table[word]
    if 0x0900 <= word <= 0x09FF:
        return f"[PORTRAIT:{word & 0xFF:02X}]"
    style = word >> 12
    base = word & 0x0FFF
    if style and base in table and table[base]:
        return f"[STYLE{style}:{table[base]}]"
    return f"[RAW:{word:04X}]"


def words_at(data: bytes, start: int, limit: int) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    cursor = start
    while cursor + 1 < limit:
        word = struct.unpack_from("<H", data, cursor)[0]
        result.append((cursor, word))
        cursor += 2
        if word == CONTROL_WORDS["END"]:
            break
    return result


def checksum(data: bytes) -> tuple[int, int]:
    return int.from_bytes(data[-2:], "little"), sum(data[:-2]) & 0xFFFF


def repair_checksum(data: bytearray) -> int:
    value = sum(data[:-2]) & 0xFFFF
    data[-2:] = value.to_bytes(2, "little")
    return value


def rom_metadata(data: bytes) -> dict[str, object]:
    stored, calculated = checksum(data)
    return {
        "size": len(data),
        "sha256": digest(data),
        "sha1": digest(data, "sha1"),
        "md5": digest(data, "md5"),
        "footer_hex": data[-10:].hex().upper(),
        "stored_checksum": f"0x{stored:04X}",
        "calculated_checksum": f"0x{calculated:04X}",
        "checksum_valid": stored == calculated,
    }


def dump_scripts(data: bytes, table: dict[int, str]) -> dict[str, object]:
    groups: list[dict[str, object]] = []
    valid_total = 0
    unique_targets: set[int] = set()
    for group in TEXT_GROUPS:
        pointers: list[dict[str, object]] = []
        for index in range(group.pointer_count):
            pointer_address = group.pointer_table + index * 2
            relative_words = struct.unpack_from("<H", data, pointer_address)[0]
            target = group.base + relative_words * 2
            valid = group.base <= target < group.end and target % 2 == 0
            item: dict[str, object] = {
                "id": f"{group.index:02X}:{index:02X}",
                "pointer_address": f"0x{pointer_address:06X}",
                "relative_words": f"0x{relative_words:04X}",
                "target": f"0x{target:06X}",
                "valid": valid,
            }
            if valid:
                valid_total += 1
                unique_targets.add(target)
                sequence = words_at(data, target, group.end)
                item["byte_length"] = len(sequence) * 2
                item["words"] = [f"0x{word:04X}" for _, word in sequence]
                item["text"] = "".join(token_for(word, table) for _, word in sequence)
                item["terminated"] = bool(sequence and sequence[-1][1] == CONTROL_WORDS["END"])
            pointers.append(item)
        groups.append(
            {
                "group": group.index,
                "pointer_table": f"0x{group.pointer_table:06X}",
                "pointer_count": group.pointer_count,
                "text_base": f"0x{group.base:06X}",
                "text_end_exclusive": f"0x{group.end:06X}",
                "region_bytes": group.end - group.base,
                "pointers": pointers,
            }
        )
    return {
        "format": "n1battle-script-dump-v1",
        "source": rom_metadata(data),
        "layout": {
            "word_endian": "little",
            "pointer_unit_bytes": 2,
            "line_word": "0x0800",
            "wait_word": "0x4000",
            "end_word": "0x8000",
            "valid_pointer_count": valid_total,
            "unique_pointer_targets": len(unique_targets),
        },
        "groups": groups,
    }


def encode_text(text: str, encode: dict[str, int]) -> list[int]:
    words: list[int] = []
    cursor = 0
    while cursor < len(text):
        if text[cursor] == "[":
            close = text.find("]", cursor + 1)
            if close < 0:
                die(f"unclosed tag in translation: {text!r}")
            tag = text[cursor + 1 : close]
            upper = tag.upper()
            if upper in CONTROL_WORDS:
                words.append(CONTROL_WORDS[upper])
            elif upper.startswith("RAW:"):
                words.append(int(tag.split(":", 1)[1], 16))
            elif upper.startswith("PORTRAIT:"):
                words.append(0x0900 | int(tag.split(":", 1)[1], 16))
            else:
                die(f"unsupported translation tag [{tag}]")
            cursor = close + 1
            continue
        character = text[cursor]
        if character not in encode:
            die(f"character {character!r} is not present in the table")
        words.append(encode[character])
        cursor += 1
    return words


def pack_words(words: Iterable[int]) -> bytes:
    return b"".join(struct.pack("<H", word) for word in words)


def patch_entries(
    source: bytes,
    manifest: dict[str, object],
    encode: dict[str, int],
    asset_root: Path,
) -> tuple[bytes, list[dict[str, object]]]:
    expected_source = str(manifest.get("source_sha256", "")).lower()
    if expected_source != SOURCE_SHA256:
        die("manifest does not target the supported source SHA-256")
    if digest(source) != expected_source:
        die("source ROM does not match the manifest")

    output = bytearray(source)
    report: list[dict[str, object]] = []
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        die("manifest has no translation entries")

    occupied: list[tuple[int, int, str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            die("manifest entry is not an object")
        entry_id = str(entry.get("id", "unnamed"))
        offset = parse_number(entry["offset"])
        length = parse_number(entry["length"])
        if length <= 0 or length % 2:
            die(f"{entry_id}: length must be a positive even number")
        end = offset + length
        if offset < 0 or end > len(source) - 2:
            die(f"{entry_id}: span is outside the ROM")
        for used_start, used_end, used_id in occupied:
            if max(offset, used_start) < min(end, used_end):
                die(f"{entry_id}: span overlaps {used_id}")
        occupied.append((offset, end, entry_id))

        expected_hex = str(entry.get("expected_hex", "")).replace(" ", "")
        expected_sha256 = str(entry.get("expected_sha256", "")).lower()
        if expected_hex:
            expected = bytes.fromhex(expected_hex)
            if len(expected) != length or source[offset:end] != expected:
                die(f"{entry_id}: source bytes do not match expected_hex")
        elif expected_sha256:
            if digest(source[offset:end]) != expected_sha256:
                die(f"{entry_id}: source span does not match expected_sha256")
        else:
            die(f"{entry_id}: expected_hex or expected_sha256 is required")

        translation = str(entry.get("translation", ""))
        words = encode_text(translation, encode)
        terminator_name = str(entry.get("terminator", "END")).upper()
        if terminator_name == "NONE":
            terminator: list[int] = []
        elif terminator_name in CONTROL_WORDS:
            terminator = [CONTROL_WORDS[terminator_name]]
        else:
            die(f"{entry_id}: unsupported terminator {terminator_name}")

        capacity_words = length // 2
        padding_count = capacity_words - len(words) - len(terminator)
        if padding_count < 0:
            die(
                f"{entry_id}: translation uses {len(words) + len(terminator)} words; "
                f"capacity is {capacity_words}"
            )
        pad_character = str(entry.get("pad_character", " "))
        if pad_character not in encode:
            die(f"{entry_id}: padding character is not in the table")
        pad_after_terminator = bool(entry.get("pad_after_terminator", False))
        if pad_after_terminator:
            final_words = words + terminator + [encode[pad_character]] * padding_count
        else:
            final_words = words + [encode[pad_character]] * padding_count + terminator
        replacement = pack_words(final_words)
        output[offset:end] = replacement
        report.append(
            {
                "id": entry_id,
                "offset": f"0x{offset:06X}",
                "length": length,
                "translation": translation,
                "padding_words": padding_count,
                "padding_after_terminator": pad_after_terminator,
                "terminator": terminator_name,
            }
        )

    binary_entries = manifest.get("binary_entries", [])
    if not isinstance(binary_entries, list):
        die("manifest binary_entries is not a list")
    for entry in binary_entries:
        if not isinstance(entry, dict):
            die("binary manifest entry is not an object")
        entry_id = str(entry.get("id", "unnamed_binary"))
        offset = parse_number(entry["offset"])
        length = parse_number(entry["length"])
        end = offset + length
        if length <= 0 or offset < 0 or end > len(source) - 2:
            die(f"{entry_id}: binary span is outside the ROM")
        for used_start, used_end, used_id in occupied:
            if max(offset, used_start) < min(end, used_end):
                die(f"{entry_id}: span overlaps {used_id}")
        occupied.append((offset, end, entry_id))

        expected_sha256 = str(entry.get("expected_sha256", "")).lower()
        if not expected_sha256 or digest(source[offset:end]) != expected_sha256:
            die(f"{entry_id}: source span does not match expected_sha256")

        asset_name = str(entry.get("asset", ""))
        if not asset_name:
            die(f"{entry_id}: asset is required")
        asset_path = (asset_root / asset_name).resolve()
        try:
            asset_path.relative_to(asset_root.resolve())
        except ValueError:
            die(f"{entry_id}: asset path escapes the manifest directory")
        replacement = asset_path.read_bytes()
        if len(replacement) != length:
            die(
                f"{entry_id}: asset is {len(replacement)} bytes; "
                f"expected {length}"
            )
        output[offset:end] = replacement
        report.append(
            {
                "id": entry_id,
                "offset": f"0x{offset:06X}",
                "length": length,
                "asset": asset_name,
            }
        )

    new_checksum = repair_checksum(output)
    return bytes(output), report + [{"wonder_swan_checksum": f"0x{new_checksum:04X}"}]


def changed_runs(source: bytes, target: bytes) -> Iterable[tuple[int, bytes]]:
    if len(source) != len(target):
        die("IPS creation currently requires equal-sized files")
    cursor = 0
    while cursor < len(source):
        if source[cursor] == target[cursor]:
            cursor += 1
            continue
        start = cursor
        while cursor < len(source) and source[cursor] != target[cursor]:
            cursor += 1
        data = target[start:cursor]
        while data:
            chunk, data = data[:0xFFFF], data[0xFFFF:]
            yield start, chunk
            start += len(chunk)


def make_ips(source: bytes, target: bytes) -> bytes:
    result = bytearray(b"PATCH")
    for offset, data in changed_runs(source, target):
        if offset > 0xFFFFFF:
            die("IPS offset exceeds 24-bit range")
        result += offset.to_bytes(3, "big")
        result += len(data).to_bytes(2, "big")
        result += data
    result += b"EOF"
    return bytes(result)


def apply_ips(source: bytes, patch: bytes) -> bytes:
    if not patch.startswith(b"PATCH"):
        die("not an IPS patch")
    output = bytearray(source)
    cursor = 5
    while True:
        if patch[cursor : cursor + 3] == b"EOF":
            cursor += 3
            break
        if cursor + 5 > len(patch):
            die("truncated IPS record")
        offset = int.from_bytes(patch[cursor : cursor + 3], "big")
        size = int.from_bytes(patch[cursor + 3 : cursor + 5], "big")
        cursor += 5
        if size:
            if cursor + size > len(patch):
                die("truncated IPS data")
            record = patch[cursor : cursor + size]
            cursor += size
        else:
            if cursor + 3 > len(patch):
                die("truncated IPS RLE record")
            run_size = int.from_bytes(patch[cursor : cursor + 2], "big")
            record = patch[cursor + 2 : cursor + 3] * run_size
            cursor += 3
        needed = offset + len(record)
        if needed > len(output):
            output.extend(b"\x00" * (needed - len(output)))
        output[offset:needed] = record
    if cursor + 3 == len(patch):
        output = output[: int.from_bytes(patch[cursor : cursor + 3], "big")]
    elif cursor != len(patch):
        die("unexpected bytes after IPS EOF")
    return bytes(output)


def write_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def command_info(args: argparse.Namespace) -> None:
    data = read_rom(args.rom, require_source=args.require_source)
    print(json.dumps(rom_metadata(data), ensure_ascii=False, indent=2))


def command_dump(args: argparse.Namespace) -> None:
    data = read_rom(args.rom, require_source=args.require_source)
    table, _ = load_table(args.table)
    result = dump_scripts(data, table)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"dumped {result['layout']['valid_pointer_count']} valid pointers "
        f"({result['layout']['unique_pointer_targets']} unique targets) to {args.output}"
    )


def command_build(args: argparse.Namespace) -> None:
    source = read_rom(args.rom, require_source=True)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    _, encode = load_table(args.table)
    target, report = patch_entries(source, manifest, encode, args.asset_root or args.manifest.parent)
    write_file(args.output, target)
    if args.ips:
        write_file(args.ips, make_ips(source, target))
    result = {
        "output": str(args.output),
        "output_sha256": digest(target),
        "checksum": rom_metadata(target),
        "entries": report,
    }
    if args.report:
        write_json(args.report, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_apply(args: argparse.Namespace) -> None:
    source = read_rom(args.rom, require_source=True)
    target = apply_ips(source, args.patch.read_bytes())
    stored, calculated = checksum(target)
    if stored != calculated:
        die(
            f"patched checksum is invalid (stored 0x{stored:04X}, "
            f"calculated 0x{calculated:04X})"
        )
    write_file(args.output, target)
    print(json.dumps(rom_metadata(target), ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    info = subparsers.add_parser("info", help="show ROM hashes and checksum")
    info.add_argument("rom", type=Path)
    info.add_argument(
        "--require-source",
        action="store_true",
        help="reject anything except the supported Japanese Rev 1 ROM",
    )
    info.set_defaults(func=command_info)

    dump = subparsers.add_parser("dump", help="dump the six verified text groups")
    dump.add_argument("rom", type=Path)
    dump.add_argument("output", type=Path)
    dump.add_argument("--table", type=Path, required=True)
    dump.add_argument("--require-source", action="store_true")
    dump.set_defaults(func=command_dump)

    build = subparsers.add_parser("build", help="build an in-place translated ROM and IPS")
    build.add_argument("rom", type=Path)
    build.add_argument("manifest", type=Path)
    build.add_argument("output", type=Path)
    build.add_argument("--table", type=Path, required=True)
    build.add_argument("--ips", type=Path)
    build.add_argument("--asset-root", type=Path, help="Explicit resource root for a lineage manifest; default is its directory")
    build.add_argument(
        "--report",
        type=Path,
        help="also save the reproducible build report as JSON",
    )
    build.set_defaults(func=command_build)

    apply = subparsers.add_parser("apply", help="apply an IPS to the verified source ROM")
    apply.add_argument("rom", type=Path)
    apply.add_argument("patch", type=Path)
    apply.add_argument("output", type=Path)
    apply.set_defaults(func=command_apply)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
