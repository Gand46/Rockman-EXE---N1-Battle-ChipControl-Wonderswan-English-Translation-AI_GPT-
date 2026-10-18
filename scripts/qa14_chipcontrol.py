#!/usr/bin/env python3
"""Carry the pinned RC6 binary delta onto a newer English localization safely.

The existing component supplies the historical IPS parser and hash-checked
reference reconstruction. This module verifies every functional preimage before
writing any bytes, preserves all unrelated candidate edits, and recalculates the
WonderSwan checksum. It does not rebuild the missing original RC6 assembly.
The release builder creates the cumulative Japanese-to-variant BPS separately.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
CC = ROOT / "components/chip-control"
ROM_SIZE = 0x400000
CHECKSUM_START = ROM_SIZE - 2
FUNCTIONAL_BYTES = 1959
IPS_RECORDS = 167
QA09_RC6_SHA256 = "1fec1a21d486fe30931053181810e2d9f82d573c5ece5dae23e1416b060de57e"
MANT04_ENGLISH_SHA256 = "e9fcfec134135c2f129da79d20b8f42ec4e7b7051e4b3b927036731041418800"
MANT04_CHIP_CONTROL_SHA256 = "3937167ede996dcb3ae59a3fa0e0a00fc720783aece66efdd059294792ff2c62"
RESERVED_REGIONS = (
    (0x073400, 0x073540, "RC6 title glyph tiles"),
    (0x35C8A0, 0x35CFBD, "RC6 payload allocation"),
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def adapter():
    path = CC / "src/verify_and_build_experimental.py"
    spec = importlib.util.spec_from_file_location("qa14_rc6_legacy_adapter", path)
    ensure(spec is not None and spec.loader is not None, f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_checksum(data: bytes, label: str) -> int:
    ensure(len(data) == ROM_SIZE, f"{label}: expected a 4 MiB WonderSwan ROM")
    stored = int.from_bytes(data[-2:], "little")
    calculated = sum(data[:-2]) & 0xFFFF
    ensure(stored == calculated,
           f"{label}: checksum 0x{stored:04X} does not match 0x{calculated:04X}")
    return stored


def references(original: bytes) -> tuple[bytes, bytes, bytes, list[tuple[int, bytes]], dict]:
    """Reconstruct the frozen QA09 and RC6 references using the existing adapter."""
    legacy = adapter()
    patch = (ROOT / "maintenance/baseline-patches/Rockman_N1_English_QA09.bps").read_bytes()
    a9_ips = (CC / "vendor/Rockman_EXE_N1_Battle_English_v0.10.7-graphics-a9.ips").read_bytes()
    rc6_ips = (CC / "vendor/ChipControl_v0.5.8_RC6_for_English_v0.10.7-graphics-a9.ips").read_bytes()
    # This also verifies the Japanese ROM, all three patch hashes, the A9 ROM,
    # the historical RC6-A9 output, all IPS writes and their original preimages.
    rc6_qa09, audit = legacy.analyse(original, patch, a9_ips, rc6_ips)
    ensure(digest(rc6_qa09) == QA09_RC6_SHA256, "Pinned QA09 + RC6 reference mismatch")
    qa09 = legacy.apply_bps(original, patch)
    a9 = legacy.apply_ips(original, legacy.parse_ips(a9_ips))
    return qa09, a9, rc6_qa09, legacy.parse_ips(rc6_ips), audit


def _carry_delta(english: bytes, qa09: bytes, a9: bytes,
                 records: list[tuple[int, bytes]], *, reference_label: str = "QA09") -> tuple[bytes, dict]:
    """Internal integration after the caller has authenticated the references."""
    original_checksum = valid_checksum(english, "English input")
    ensure(len(qa09) == len(a9) == ROM_SIZE, "Invalid reference size")
    ensure(len(records) == IPS_RECORDS, "RC6 IPS record count changed")
    writes: dict[int, int] = {}
    checksum_writes = []
    for start, values in records:
        ensure(start >= 0 and start + len(values) <= ROM_SIZE, "RC6 write exceeds ROM")
        for offset, target in enumerate(values, start):
            ensure(offset not in writes and offset not in checksum_writes,
                   f"Overlapping RC6 record at 0x{offset:06X}")
            if offset >= CHECKSUM_START:
                checksum_writes.append(offset)
            else:
                writes[offset] = target
    ensure(len(writes) == FUNCTIONAL_BYTES, "RC6 functional write count changed")
    ensure(sorted(checksum_writes) == [CHECKSUM_START, CHECKSUM_START + 1],
           "Unexpected RC6 checksum write domain")

    # Validate the complete write set BEFORE allocating/modifying the output.
    conflicts = []
    for offset, target in writes.items():
        ensure(qa09[offset] == a9[offset],
               f"Historical A9/QA09 preimages differ at 0x{offset:06X}")
        ensure(target != qa09[offset], f"Unexpected RC6 no-op at 0x{offset:06X}")
        if english[offset] != qa09[offset]:
            conflicts.append({"offset": f"0x{offset:06X}",
                              "expected_a9_qa09": qa09[offset],
                              "current_english": english[offset], "rc6": target})
    ensure(not conflicts,
           f"RC6 functional conflict ({len(conflicts)} bytes): {json.dumps(conflicts[:12])}")
    # IPS omits bytes that already matched the base. Those holes are still
    # part of the consumed payload/tiles and must not receive unrelated edits.
    for start, end, label in RESERVED_REGIONS:
        ensure(qa09[start:end] == a9[start:end], f"Historical reserved-region preimages differ: {label}")
        ensure(english[start:end] == qa09[start:end],
               f"RC6 reserved-region conflict in {label} (0x{start:06X}..0x{end - 1:06X})")

    candidate = bytearray(english)
    for offset, value in writes.items():
        candidate[offset] = value
    checksum = sum(candidate[:-2]) & 0xFFFF
    candidate[-2:] = checksum.to_bytes(2, "little")
    result = bytes(candidate)
    valid_checksum(result, "Chip Control output")

    changed = {i for i, (before, after) in enumerate(zip(english, result)) if before != after}
    functional_changed = {i for i in changed if i < CHECKSUM_START}
    ensure(functional_changed == set(writes), "Actual RC6 changes differ from the verified write set")
    base_delta = {i for i, (before, after) in enumerate(zip(qa09, english))
                  if i < CHECKSUM_START and before != after}
    ensure(not base_delta.intersection(writes), "Candidate changes overlap RC6")
    ensure(all(result[i] == english[i] for i in base_delta), "Candidate edits were not preserved")
    banks = Counter(offset >> 16 for offset in writes)
    report = {
        "status": "PASS_STATIC_RC6_DELTA_PRESERVED",
        "english_rom_sha256": digest(english),
        "chip_control_rom_sha256": digest(result),
        "english_checksum": f"0x{original_checksum:04X}",
        "chip_control_checksum": f"0x{checksum:04X}",
        "functional_bytes_validated": len(writes),
        "functional_bytes_changed": len(functional_changed),
        "functional_conflicts": 0,
        "checksum_bytes_changed": len(changed - functional_changed),
        "unexpected_changed_bytes": 0,
        "english_delta_reference": reference_label,
        "english_changes_relative_to_reference_nonchecksum": len(base_delta),
        "english_changes_preserved": len(base_delta),
        "ips_records": len(records),
        "functional_bytes_by_64k_bank": {f"0x{bank:02X}": count for bank, count in sorted(banks.items())},
        "reserved_regions_validated": [{"start": f"0x{start:06X}", "end_exclusive": f"0x{end:06X}",
                                         "bytes": end - start, "label": label}
                                        for start, end, label in RESERVED_REGIONS],
        "original_rc6_code_reassembled": False,
        "original_rc6_assembly_available": False,
        "runtime_validated_by_this_module": False,
    }
    return result, report


def apply_from_original(original: bytes, english: bytes, *, expected_english_sha256: str | None = None) -> tuple[bytes, dict]:
    """Apply unchanged RC6 to a caller-produced English ROM; return bytes/report.

    Authentication of a new English release belongs to its source builder. The
    optional expected hash lets the CLI pin that identity. This module certifies
    RC6's byte-level compatibility, not every other edit in that English input.
    """
    if expected_english_sha256 is not None:
        ensure(digest(english) == expected_english_sha256, "English input SHA-256 mismatch")
    qa09, a9, reference, records, inherited = references(original)
    result, report = _carry_delta(english, qa09, a9, records)
    report.update({"original_japanese_sha256": digest(original),
                   "qa09_reference_sha256": digest(qa09),
                   "a9_reference_sha256": digest(a9),
                   "qa09_rc6_reference_sha256": digest(reference),
                   "rc6_ips_sha256": inherited["rc6_ips_sha256"],
                   "scope": "Unchanged pinned RC6 delta onto the nominated English input; no global gameplay claim"})
    return result, report


def apply(mant04_english: bytes, mant04_chip_control: bytes, english: bytes) -> tuple[bytes, dict]:
    """Preserve the exact MANT04 RC6 delta while carrying new English edits.

    Both nominated parent ROMs must match their published identities. The
    existing IPS must explain every functional difference between those parents,
    and the newer English ROM must retain all of those verified preimages.
    """
    ensure(digest(mant04_english) == MANT04_ENGLISH_SHA256, "MANT04 English reference SHA-256 mismatch")
    ensure(digest(mant04_chip_control) == MANT04_CHIP_CONTROL_SHA256,
           "MANT04 Chip Control reference SHA-256 mismatch")
    legacy = adapter()
    ips = (CC / "vendor/ChipControl_v0.5.8_RC6_for_English_v0.10.7-graphics-a9.ips").read_bytes()
    legacy.require_equal(digest(ips), legacy.RC6_IPS_SHA, "ChipControl RC6 IPS")
    records = legacy.parse_ips(ips)
    reproduced, _ = _carry_delta(mant04_english, mant04_english, mant04_english,
                                 records, reference_label="QA09_MANT04")
    ensure(reproduced == mant04_chip_control, "MANT04 pair differs from the pinned RC6 delta")
    result, report = _carry_delta(english, mant04_english, mant04_english, records,
                                 reference_label="QA09_MANT04")
    report.update({"mant04_english_sha256": MANT04_ENGLISH_SHA256,
                   "mant04_chip_control_sha256": MANT04_CHIP_CONTROL_SHA256,
                   "rc6_ips_sha256": legacy.RC6_IPS_SHA,
                   "parent_pair_equals_pinned_rc6_delta": True,
                   "scope": "Unchanged pinned MANT04 RC6 delta onto the newer English ROM; no global gameplay claim"})
    return result, report


def verify_pair(mant04_english: bytes, mant04_chip_control: bytes,
                english: bytes, chip_control: bytes) -> dict:
    expected, report = apply(mant04_english, mant04_chip_control, english)
    ensure(chip_control == expected, "Supplied Chip Control ROM differs from the safe RC6 integration")
    report["supplied_variant_equals_safe_integration"] = True
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Original Japanese ROM")
    parser.add_argument("--english", type=Path, required=True, help="New English ROM produced from sources")
    parser.add_argument("--expected-english-sha256", required=True, help="Identity from the current build report")
    parser.add_argument("--check-variant", type=Path, help="Compare an existing Chip Control ROM")
    parser.add_argument("--output", type=Path, help="Write a private emulator ROM; BPS is generated by release builder")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    inputs = {p.resolve() for p in (args.source, args.english, args.check_variant) if p is not None}
    outputs = [p.resolve() for p in (args.output, args.report) if p is not None]
    ensure(not inputs.intersection(outputs) and len(outputs) == len(set(outputs)),
           "Output paths must not overwrite input files or each other")
    output, report = apply_from_original(args.source.read_bytes(), args.english.read_bytes(),
                                         expected_english_sha256=args.expected_english_sha256)
    if args.check_variant is not None:
        ensure(args.check_variant.read_bytes() == output, "Chip Control variant identity mismatch")
        report["supplied_variant_equals_safe_integration"] = True
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(output)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
