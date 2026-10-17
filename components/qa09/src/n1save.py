#!/usr/bin/env python3
"""Inspect and safely transform Rockman EXE N1 Battle SRAM saves.

The tool accepts either a 32 KiB raw cartridge SRAM image or the 33 KiB
BizHawk/Cygne SaveRAM container used by this game (1 KiB iEEPROM followed by
32 KiB cartridge SRAM).  Mutating commands always require a distinct, new
output path; input files are never modified in place.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


TOOL_VERSION = "0.4.0"

SRAM_SIZE = 0x8000
BIZHAWK_IEEPROM_SIZE = 0x0400
BIZHAWK_CONTAINER_SIZE = BIZHAWK_IEEPROM_SIZE + SRAM_SIZE

BLOCK_SIZE = 0x1000
MAIN_BLOCK_OFFSET = 0x1000
COPY_BLOCK_OFFSET = 0x2000
CHECKSUM_OFFSET = 0x04
CHECKSUM_SIZE = 0x02
PAYLOAD_LENGTH_OFFSET = 0x06
SAVE_HEADER_SIZE = 0x0C
EXPECTED_PAYLOAD_LENGTH = 0x0466
SAVE_SIGNATURE = b"INTI"

FORMAT_RAW = "n1battle-raw-sram"
FORMAT_BIZHAWK = "bizhawk-cygne-ieeprom+sram"


class SaveToolError(Exception):
    """An expected input, format, or output safety error."""


@dataclass(frozen=True)
class BlockStatus:
    name: str
    sram_offset: int
    signature: bytes
    stored_checksum: int
    calculated_checksum: int | None
    payload_length: int
    sha256: str

    @property
    def initialized(self) -> bool:
        return self.signature == SAVE_SIGNATURE

    @property
    def checksum_valid(self) -> bool:
        return (
            self.calculated_checksum is not None
            and self.stored_checksum == self.calculated_checksum
        )

    @property
    def payload_length_valid(self) -> bool:
        return self.payload_length == EXPECTED_PAYLOAD_LENGTH

    @property
    def valid(self) -> bool:
        return self.initialized and self.payload_length_valid and self.checksum_valid

    def as_dict(self, source_offset: int) -> dict[str, object]:
        return {
            "name": self.name,
            "sram_offset": f"0x{self.sram_offset:04X}",
            "source_offset": f"0x{source_offset + self.sram_offset:04X}",
            "signature_hex": self.signature.hex().upper(),
            "signature_ascii": printable_ascii(self.signature),
            "initialized": self.initialized,
            "payload_length": self.payload_length,
            "payload_length_hex": f"0x{self.payload_length:04X}",
            "payload_length_valid": self.payload_length_valid,
            "stored_checksum": f"0x{self.stored_checksum:04X}",
            "calculated_checksum": (
                None
                if self.calculated_checksum is None
                else f"0x{self.calculated_checksum:04X}"
            ),
            "checksum_valid": self.checksum_valid,
            "valid": self.valid,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class SaveImage:
    path: Path
    data: bytes
    format_name: str
    sram_offset: int

    @property
    def sram(self) -> bytes:
        return self.data[self.sram_offset : self.sram_offset + SRAM_SIZE]

    @property
    def main(self) -> BlockStatus:
        return inspect_block(self.sram, "main", MAIN_BLOCK_OFFSET)

    @property
    def copy(self) -> BlockStatus:
        return inspect_block(self.sram, "copy", COPY_BLOCK_OFFSET)

    @property
    def copies_identical(self) -> bool:
        sram = self.sram
        return (
            sram[MAIN_BLOCK_OFFSET : MAIN_BLOCK_OFFSET + BLOCK_SIZE]
            == sram[COPY_BLOCK_OFFSET : COPY_BLOCK_OFFSET + BLOCK_SIZE]
        )

    @property
    def valid(self) -> bool:
        return self.main.valid and self.copy.valid and self.copies_identical

    def validation_issues(self) -> list[str]:
        issues: list[str] = []
        for status in (self.main, self.copy):
            label = "main block" if status.name == "main" else "copy block"
            if not status.initialized:
                issues.append(
                    f"{label} at 0x{status.sram_offset:04X} has no INTI signature"
                )
            elif not status.checksum_valid:
                if not status.payload_length_valid:
                    issues.append(
                        f"{label} payload length is 0x{status.payload_length:04X}; "
                        f"expected 0x{EXPECTED_PAYLOAD_LENGTH:04X}"
                    )
                else:
                    assert status.calculated_checksum is not None
                    issues.append(
                        f"{label} checksum is 0x{status.stored_checksum:04X}; "
                        f"expected 0x{status.calculated_checksum:04X}"
                    )
        if not self.copies_identical:
            issues.append("main and copy blocks are not byte-identical")
        return issues

    def replace_sram(self, sram: bytes | bytearray) -> bytes:
        if len(sram) != SRAM_SIZE:
            raise SaveToolError(
                f"internal error: replacement SRAM is {len(sram)} bytes, "
                f"expected {SRAM_SIZE}"
            )
        result = bytearray(self.data)
        result[self.sram_offset : self.sram_offset + SRAM_SIZE] = sram
        return bytes(result)

    def as_dict(self) -> dict[str, object]:
        return {
            "format": self.format_name,
            "path": str(self.path),
            "container_size": len(self.data),
            "sram_offset": f"0x{self.sram_offset:04X}",
            "sram_size": SRAM_SIZE,
            "ieeprom_size": self.sram_offset,
            "sha256": hashlib.sha256(self.data).hexdigest(),
            "sram_sha256": hashlib.sha256(self.sram).hexdigest(),
            "checksum_formula": (
                "uint16_le[block+0x04] = "
                "sum(block[0x0C:0x0C+0x0466]) & 0xFFFF"
            ),
            "main": self.main.as_dict(self.sram_offset),
            "copy": self.copy.as_dict(self.sram_offset),
            "copies_identical": self.copies_identical,
            "valid": self.valid,
            "issues": self.validation_issues(),
        }


def printable_ascii(data: bytes) -> str:
    return "".join(chr(value) if 0x20 <= value <= 0x7E else "." for value in data)


def read_payload_length(block: bytes | bytearray) -> int:
    """Return the little-endian payload length stored in a save-block header."""

    if len(block) != BLOCK_SIZE:
        raise ValueError(f"save block must be {BLOCK_SIZE} bytes")
    return int.from_bytes(
        block[PAYLOAD_LENGTH_OFFSET : PAYLOAD_LENGTH_OFFSET + 2], "little"
    )


def calculate_block_checksum(block: bytes | bytearray) -> int:
    """Return the 16-bit checksum used by N1 Battle for one save block.

    The ROM sums exactly the declared payload after the 0x0C-byte header.  N1
    Battle's save routine always declares 0x0466 bytes; refusing other lengths
    prevents a damaged header from selecting an unintended checksum region.
    """

    payload_length = read_payload_length(block)
    if payload_length != EXPECTED_PAYLOAD_LENGTH:
        raise ValueError(
            f"N1 payload length must be 0x{EXPECTED_PAYLOAD_LENGTH:04X}, "
            f"got 0x{payload_length:04X}"
        )
    payload_end = SAVE_HEADER_SIZE + payload_length
    if payload_end > len(block):
        raise ValueError("declared payload extends beyond the save block")
    return sum(block[SAVE_HEADER_SIZE:payload_end]) & 0xFFFF


def inspect_block(sram: bytes, name: str, offset: int) -> BlockStatus:
    block = sram[offset : offset + BLOCK_SIZE]
    if len(block) != BLOCK_SIZE:
        raise SaveToolError(
            f"internal error: {name} block at 0x{offset:04X} is truncated"
        )
    payload_length = read_payload_length(block)
    try:
        calculated_checksum = calculate_block_checksum(block)
    except ValueError:
        calculated_checksum = None
    return BlockStatus(
        name=name,
        sram_offset=offset,
        signature=block[: len(SAVE_SIGNATURE)],
        stored_checksum=int.from_bytes(
            block[CHECKSUM_OFFSET : CHECKSUM_OFFSET + CHECKSUM_SIZE], "little"
        ),
        calculated_checksum=calculated_checksum,
        payload_length=payload_length,
        sha256=hashlib.sha256(block).hexdigest(),
    )


def format_is_confident(sram: bytes) -> bool:
    """Require enough structure to distinguish N1 SRAM from another 32 KiB save."""

    main = inspect_block(sram, "main", MAIN_BLOCK_OFFSET)
    copy = inspect_block(sram, "copy", COPY_BLOCK_OFFSET)
    # Two signatures remain a confident identification even when both checksum
    # bytes need repair.  With only one signature, require a valid checksum to
    # avoid accepting an unrelated file containing a coincidental ASCII token.
    return (main.initialized and copy.initialized) or main.valid or copy.valid


def load_save(path: Path) -> SaveImage:
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise SaveToolError(f"input file does not exist: {path}") from exc
    except OSError as exc:
        raise SaveToolError(f"cannot read {path}: {exc}") from exc

    if len(data) == SRAM_SIZE:
        format_name = FORMAT_RAW
        sram_offset = 0
    elif len(data) == BIZHAWK_CONTAINER_SIZE:
        format_name = FORMAT_BIZHAWK
        sram_offset = BIZHAWK_IEEPROM_SIZE
    else:
        raise SaveToolError(
            f"unsupported or ambiguous size {len(data)} bytes for {path}; "
            f"expected exactly {SRAM_SIZE} (raw SRAM) or "
            f"{BIZHAWK_CONTAINER_SIZE} (BizHawk 0x400-byte iEEPROM + SRAM)"
        )

    sram = data[sram_offset : sram_offset + SRAM_SIZE]
    if not format_is_confident(sram):
        raise SaveToolError(
            f"{path} has a supported size but cannot be identified safely as "
            "an N1 Battle save (need INTI in both save blocks, or one INTI "
            "block with a valid checksum); refusing an ambiguous format"
        )
    return SaveImage(path=path, data=data, format_name=format_name, sram_offset=sram_offset)


def ensure_new_output(input_path: Path, output_path: Path) -> None:
    try:
        same_path = input_path.resolve(strict=False) == output_path.resolve(strict=False)
    except OSError as exc:
        raise SaveToolError(f"cannot resolve output path {output_path}: {exc}") from exc
    if same_path:
        raise SaveToolError("input and output paths must be different; in-place writes are forbidden")
    if output_path.exists():
        raise SaveToolError(f"output already exists; refusing to overwrite it: {output_path}")
    if not output_path.parent.is_dir():
        raise SaveToolError(f"output directory does not exist: {output_path.parent}")


def write_new_output(input_path: Path, output_path: Path, data: bytes) -> None:
    ensure_new_output(input_path, output_path)
    created = False
    try:
        with output_path.open("xb") as handle:
            created = True
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise SaveToolError(f"output already exists; refusing to overwrite it: {output_path}") from exc
    except OSError as exc:
        if created:
            try:
                output_path.unlink()
            except OSError:
                pass
        raise SaveToolError(f"cannot write {output_path}: {exc}") from exc


def repair_save(image: SaveImage, block_names: Sequence[str]) -> tuple[bytes, list[dict[str, object]]]:
    offsets = {"main": MAIN_BLOCK_OFFSET, "copy": COPY_BLOCK_OFFSET}
    requested = [(name, offsets[name]) for name in block_names]
    sram = bytearray(image.sram)

    # Validate every target before changing any byte.
    for name, offset in requested:
        if sram[offset : offset + len(SAVE_SIGNATURE)] != SAVE_SIGNATURE:
            raise SaveToolError(
                f"cannot repair {name} block at 0x{offset:04X}: INTI signature is missing"
            )
        payload_length = int.from_bytes(
            sram[
                offset + PAYLOAD_LENGTH_OFFSET : offset + PAYLOAD_LENGTH_OFFSET + 2
            ],
            "little",
        )
        if payload_length != EXPECTED_PAYLOAD_LENGTH:
            raise SaveToolError(
                f"cannot repair {name} block at 0x{offset:04X}: payload length "
                f"is 0x{payload_length:04X}, expected 0x{EXPECTED_PAYLOAD_LENGTH:04X}"
            )

    changes: list[dict[str, object]] = []
    for name, offset in requested:
        block = sram[offset : offset + BLOCK_SIZE]
        old = int.from_bytes(
            block[CHECKSUM_OFFSET : CHECKSUM_OFFSET + CHECKSUM_SIZE], "little"
        )
        new = calculate_block_checksum(block)
        sram[
            offset + CHECKSUM_OFFSET : offset + CHECKSUM_OFFSET + CHECKSUM_SIZE
        ] = new.to_bytes(CHECKSUM_SIZE, "little")
        changes.append(
            {
                "block": name,
                "sram_range": (
                    f"0x{offset + CHECKSUM_OFFSET:04X}-"
                    f"0x{offset + CHECKSUM_OFFSET + CHECKSUM_SIZE - 1:04X}"
                ),
                "source_range": (
                    f"0x{image.sram_offset + offset + CHECKSUM_OFFSET:04X}-"
                    f"0x{image.sram_offset + offset + CHECKSUM_OFFSET + CHECKSUM_SIZE - 1:04X}"
                ),
                "old": f"0x{old:04X}",
                "new": f"0x{new:04X}",
                "changed": old != new,
            }
        )
    return image.replace_sram(sram), changes


def clone_main_block(image: SaveImage) -> bytes:
    main = image.main
    if not main.initialized:
        raise SaveToolError("cannot clone: main block has no INTI signature")
    if not main.checksum_valid:
        raise SaveToolError(
            "cannot clone an invalid main block; run repair to a new file first"
        )
    sram = bytearray(image.sram)
    sram[COPY_BLOCK_OFFSET : COPY_BLOCK_OFFSET + BLOCK_SIZE] = sram[
        MAIN_BLOCK_OFFSET : MAIN_BLOCK_OFFSET + BLOCK_SIZE
    ]
    return image.replace_sram(sram)


def contiguous_ranges(offsets: Iterable[int]) -> list[tuple[int, int]]:
    values = iter(offsets)
    try:
        start = previous = next(values)
    except StopIteration:
        return []
    result: list[tuple[int, int]] = []
    for value in values:
        if value != previous + 1:
            result.append((start, previous + 1))
            start = value
        previous = value
    result.append((start, previous + 1))
    return result


def make_diff_report(
    first: SaveImage,
    second: SaveImage,
    max_details: int = 64,
    max_ranges: int = 64,
) -> dict[str, object]:
    if max_details < 0 or max_ranges < 0:
        raise SaveToolError("diff limits cannot be negative")
    differences = [
        offset
        for offset, (left, right) in enumerate(zip(first.sram, second.sram))
        if left != right
    ]
    ranges = contiguous_ranges(differences)
    by_block = []
    for block_index in range(SRAM_SIZE // BLOCK_SIZE):
        start = block_index * BLOCK_SIZE
        end = start + BLOCK_SIZE
        count = sum(1 for offset in differences if start <= offset < end)
        if count:
            by_block.append(
                {
                    "block": block_index,
                    "range": f"0x{start:04X}-0x{end - 1:04X}",
                    "different_bytes": count,
                }
            )
    return {
        "first": str(first.path),
        "second": str(second.path),
        "first_format": first.format_name,
        "second_format": second.format_name,
        "compared_region": "32 KiB cartridge SRAM",
        "identical": not differences,
        "different_bytes": len(differences),
        "different_ranges": len(ranges),
        "ranges": [
            {
                "start": f"0x{start:04X}",
                "end_exclusive": f"0x{end:04X}",
                "length": end - start,
            }
            for start, end in ranges[:max_ranges]
        ],
        "ranges_truncated": len(ranges) > max_ranges,
        "by_0x1000_block": by_block,
        "details": [
            {
                "offset": f"0x{offset:04X}",
                "first": f"0x{first.sram[offset]:02X}",
                "second": f"0x{second.sram[offset]:02X}",
            }
            for offset in differences[:max_details]
        ],
        "details_truncated": len(differences) > max_details,
    }


def print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def print_block(status: BlockStatus) -> None:
    calculated = (
        "n/a"
        if status.calculated_checksum is None
        else f"0x{status.calculated_checksum:04X}"
    )
    print(
        f"{status.name:>4}  offset=0x{status.sram_offset:04X}  "
        f"signature={printable_ascii(status.signature)!r}  "
        f"length=0x{status.payload_length:04X}  "
        f"stored=0x{status.stored_checksum:04X}  "
        f"calculated={calculated}  "
        f"valid={'yes' if status.valid else 'no'}"
    )


def command_info(args: argparse.Namespace) -> int:
    image = load_save(args.input)
    if args.json:
        print_json(image.as_dict())
        return 0
    print(f"File: {image.path}")
    print(f"Format: {image.format_name}")
    print(f"Container size: {len(image.data)} bytes")
    print(f"SRAM: offset=0x{image.sram_offset:04X}, size={SRAM_SIZE} bytes")
    print(f"SHA-256: {hashlib.sha256(image.data).hexdigest()}")
    print_block(image.main)
    print_block(image.copy)
    print(f"Copies identical: {'yes' if image.copies_identical else 'no'}")
    print(f"Strict validation: {'VALID' if image.valid else 'INVALID'}")
    return 0


def command_checksum(args: argparse.Namespace) -> int:
    image = load_save(args.input)
    payload = {
        "path": str(image.path),
        "format": image.format_name,
        "formula": (
            "uint16_le@+0x04 = sum(bytes[+0x0C:+0x0C+0x0466]) & 0xFFFF"
        ),
        "main": image.main.as_dict(image.sram_offset),
        "copy": image.copy.as_dict(image.sram_offset),
    }
    if args.json:
        print_json(payload)
    else:
        print(payload["formula"])
        print_block(image.main)
        print_block(image.copy)
    return 0


def command_validate(args: argparse.Namespace) -> int:
    image = load_save(args.input)
    payload = image.as_dict()
    if args.json:
        print_json(payload)
    elif image.valid:
        print(f"VALID: {image.path}")
        print("Both INTI blocks have valid checksums and are byte-identical.")
    else:
        print(f"INVALID: {image.path}")
        for issue in image.validation_issues():
            print(f"- {issue}")
    return 0 if image.valid else 1


def command_repair(args: argparse.Namespace) -> int:
    image = load_save(args.input)
    names = ("main", "copy") if args.block == "both" else (args.block,)
    output_data, changes = repair_save(image, names)
    write_new_output(args.input, args.output, output_data)
    if args.json:
        print_json(
            {
                "input": str(args.input),
                "output": str(args.output),
                "format": image.format_name,
                "changes": changes,
            }
        )
    else:
        for change in changes:
            print(
                f"Repaired {change['block']} checksum: "
                f"{change['old']} -> {change['new']}"
            )
        print(f"Wrote new file: {args.output}")
    return 0


def command_clone(args: argparse.Namespace) -> int:
    image = load_save(args.input)
    output_data = clone_main_block(image)
    write_new_output(args.input, args.output, output_data)
    payload = {
        "input": str(args.input),
        "output": str(args.output),
        "format": image.format_name,
        "source_range": "0x1000-0x1FFF",
        "destination_range": "0x2000-0x2FFF",
        "bytes_copied": BLOCK_SIZE,
    }
    if args.json:
        print_json(payload)
    else:
        print("Cloned SRAM 0x1000-0x1FFF to 0x2000-0x2FFF (4096 bytes).")
        print(f"Wrote new file: {args.output}")
    return 0


def command_export_bizhawk(args: argparse.Namespace) -> int:
    image = load_save(args.input)
    if image.format_name != FORMAT_BIZHAWK:
        raise SaveToolError(
            f"export-bizhawk requires an exact {BIZHAWK_CONTAINER_SIZE}-byte "
            "BizHawk/Cygne container with 0x400-byte iEEPROM prefix"
        )
    write_new_output(args.input, args.output, image.sram)
    payload = {
        "input": str(args.input),
        "output": str(args.output),
        "input_size": len(image.data),
        "skipped_ieeprom_bytes": BIZHAWK_IEEPROM_SIZE,
        "exported_sram_bytes": SRAM_SIZE,
        "sram_sha256": hashlib.sha256(image.sram).hexdigest(),
    }
    if args.json:
        print_json(payload)
    else:
        print(
            f"Skipped BizHawk iEEPROM prefix ({BIZHAWK_IEEPROM_SIZE} bytes) "
            f"and exported {SRAM_SIZE} bytes of cartridge SRAM."
        )
        print(f"Wrote new file: {args.output}")
    return 0


def command_diff(args: argparse.Namespace) -> int:
    first = load_save(args.first)
    second = load_save(args.second)
    report = make_diff_report(first, second, args.max_details, args.max_ranges)
    if args.json:
        print_json(report)
    else:
        if report["identical"]:
            print("SRAM images are identical (32768 bytes compared).")
        else:
            print(
                f"SRAM images differ in {report['different_bytes']} byte(s) "
                f"across {report['different_ranges']} contiguous range(s)."
            )
            for region in report["by_0x1000_block"]:
                print(
                    f"- block {region['block']} {region['range']}: "
                    f"{region['different_bytes']} byte(s)"
                )
            for detail in report["details"]:
                print(
                    f"  {detail['offset']}: {detail['first']} -> {detail['second']}"
                )
            if report["details_truncated"]:
                print(f"  ... detail limited to {args.max_details} byte(s)")
            if report["ranges_truncated"]:
                print(f"  ... ranges limited to {args.max_ranges}")
    # Match conventional diff: 0 means identical, 1 means different.
    return 0 if report["identical"] else 1


def add_json_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect, validate, repair, compare, and convert Rockman EXE "
            "N1 Battle SRAM saves without overwriting originals."
        )
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {TOOL_VERSION}"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    info = subparsers.add_parser("info", help="show format and save-block metadata")
    info.add_argument("input", type=Path)
    add_json_argument(info)
    info.set_defaults(handler=command_info)

    validate = subparsers.add_parser(
        "validate", help="strictly validate both checksums and redundant copies"
    )
    validate.add_argument("input", type=Path)
    add_json_argument(validate)
    validate.set_defaults(handler=command_validate)

    checksum = subparsers.add_parser(
        "checksum", help="calculate and display both block checksums"
    )
    checksum.add_argument("input", type=Path)
    add_json_argument(checksum)
    checksum.set_defaults(handler=command_checksum)

    repair = subparsers.add_parser(
        "repair", help="repair 16-bit checksum(s) and write a distinct new file"
    )
    repair.add_argument("input", type=Path)
    repair.add_argument("output", type=Path)
    repair.add_argument(
        "--block",
        choices=("main", "copy", "both"),
        default="main",
        help="block(s) to repair (default: main)",
    )
    add_json_argument(repair)
    repair.set_defaults(handler=command_repair)

    clone = subparsers.add_parser(
        "clone", help="copy main block 0x1000-0x1FFF over 0x2000-0x2FFF"
    )
    clone.add_argument("input", type=Path)
    clone.add_argument("output", type=Path)
    add_json_argument(clone)
    clone.set_defaults(handler=command_clone)

    export = subparsers.add_parser(
        "export-bizhawk",
        help="export 32768-byte SRAM from a BizHawk container containing iEEPROM",
    )
    export.add_argument("input", type=Path)
    export.add_argument("output", type=Path)
    add_json_argument(export)
    export.set_defaults(handler=command_export_bizhawk)

    diff = subparsers.add_parser("diff", help="compare the 32 KiB SRAM in two saves")
    diff.add_argument("first", type=Path)
    diff.add_argument("second", type=Path)
    diff.add_argument(
        "--max-details",
        type=int,
        default=64,
        help="maximum differing bytes to print/store (default: 64)",
    )
    diff.add_argument(
        "--max-ranges",
        type=int,
        default=64,
        help="maximum contiguous ranges to store (default: 64)",
    )
    add_json_argument(diff)
    diff.set_defaults(handler=command_diff)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except SaveToolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
