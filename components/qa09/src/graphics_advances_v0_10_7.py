#!/usr/bin/env python3
"""Apply graphics Advance 1 safely on top of the approved v0.10.7 RC4.

The live Program Deck atlas is copied to VRAM starting at tile ID 1, not tile
ID 0. Therefore a map entry for tile N renders asset slot N-1. The earlier
audit missed that offset and validated the neighbouring headings against the
wrong atlas slots. This corrected build restores only PROGRAM DECK, Y2 CHIP
FOLDER and its protected pictogram from the approved pixel-polished v0.10.6
reference, then replaces the two-cell marked symbol with the already-active
blank cell. All unrelated map cells, tile consumers, palettes, code, dialogue
and data remain byte-identical to RC4.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


ROM_SIZE = 0x400000
RC4_SHA256 = "129ef89f09e2fef3a6c7f1acce11f62ff0c615ca583317e5e5b106f029bbe1b8"
REFERENCE_SHA256 = "fb78269238806807616cfe622a3be9239dc5b95bbd454ee02127919dd463e3cc"
PROGRAM_MAP_OFFSET = 0x04323C
PROGRAM_MAP_PUBLIC_LENGTH = 0x0400
PROGRAM_MAP_RUNTIME_LENGTH = 0x0680
PROGRAM_TILE_OFFSET = 0x07CD20
PROGRAM_TILE_LENGTH = 0x1EF0
TILE_BYTES = 32
TILE_MASK = 0x01FF
RUNTIME_TILE_ASSET_DELTA = -1

PROGRAM_DECK_CELLS = tuple((x, y) for y in (0, 1) for x in range(11, 18))
Y2_CHIP_FOLDER_CELLS = tuple((x, y) for y in (0, 1) for x in range(20, 27))
Y2_PICTOGRAM_CELLS = ((27, 0), (27, 1))
RESTORED_HEADER_CELLS = (
    PROGRAM_DECK_CELLS + Y2_CHIP_FOLDER_CELLS + Y2_PICTOGRAM_CELLS
)
SYMBOL_CELLS = ((18, 0), (18, 1))
BLANK_SOURCE_CELLS = ((19, 0), (19, 1))


def sha256(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def map_offset(x: int, y: int) -> int:
    return PROGRAM_MAP_OFFSET + (y * 32 + x) * 2


def map_word(rom: bytes | bytearray, x: int, y: int) -> int:
    start = map_offset(x, y)
    return int.from_bytes(rom[start:start + 2], "little")


def asset_tile_offset(asset_index: int) -> int:
    return PROGRAM_TILE_OFFSET + asset_index * TILE_BYTES


def asset_tile(rom: bytes | bytearray, asset_index: int) -> bytes:
    start = asset_tile_offset(asset_index)
    payload = bytes(rom[start:start + TILE_BYTES])
    if len(payload) != TILE_BYTES:
        raise ValueError(f"asset tile 0x{asset_index:03X} is truncated")
    return payload


def runtime_asset_index(tile_id: int) -> int:
    index = tile_id + RUNTIME_TILE_ASSET_DELTA
    if index < 0:
        raise ValueError(f"runtime tile 0x{tile_id:03X} has no Program Deck asset slot")
    return index


def repair_checksum(rom: bytearray) -> int:
    checksum = sum(rom[:-2]) & 0xFFFF
    rom[-2:] = checksum.to_bytes(2, "little")
    return checksum


def tile_consumers(rom: bytes, tile_ids: set[int]) -> dict[int, list[tuple[int, int]]]:
    consumers: dict[int, list[tuple[int, int]]] = defaultdict(list)
    payload = rom[PROGRAM_MAP_OFFSET:PROGRAM_MAP_OFFSET + PROGRAM_MAP_RUNTIME_LENGTH]
    for position in range(0, len(payload), 2):
        word = int.from_bytes(payload[position:position + 2], "little")
        tile_id = word & TILE_MASK
        if tile_id in tile_ids:
            cell = position // 2
            consumers[tile_id].append((cell % 32, cell // 32))
    return dict(consumers)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-rom", type=Path, required=True)
    parser.add_argument("--reference-rom", type=Path, required=True)
    parser.add_argument("--output-rom", type=Path, required=True)
    parser.add_argument("--output-map", type=Path, required=True)
    parser.add_argument("--output-tiles", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    source = args.base_rom.read_bytes()
    reference = args.reference_rom.read_bytes()
    if len(source) != ROM_SIZE or sha256(source) != RC4_SHA256:
        raise ValueError("Advance 1 requires the exact approved v0.10.7 RC4 ROM")
    if len(reference) != ROM_SIZE or sha256(reference) != REFERENCE_SHA256:
        raise ValueError("The heading reference is not the approved pixel-polished v0.10.6")

    for source_cell in BLANK_SOURCE_CELLS:
        source_word = map_word(source, *source_cell)
        if source_word != 0x240C:
            raise ValueError(f"clean source cell {source_cell} differs from RC4")
    blank_word = map_word(source, *BLANK_SOURCE_CELLS[0])
    if any(map_word(source, *cell) != blank_word for cell in BLANK_SOURCE_CELLS):
        raise AssertionError("the two clean source cells do not match")
    if any((map_word(source, *cell) ^ blank_word) & ~TILE_MASK for cell in SYMBOL_CELLS):
        raise AssertionError("symbol and blank cells do not share map attributes")

    # Resolve the real live mapping: map tile N consumes Program Deck asset N-1.
    restored_runtime_tile_ids = {
        map_word(reference, *cell) & TILE_MASK for cell in RESTORED_HEADER_CELLS
    }
    restored_runtime_tile_ids.discard(blank_word & TILE_MASK)
    intended_asset_indices = {
        runtime_asset_index(tile_id) for tile_id in restored_runtime_tile_ids
    }
    target_cells = set(RESTORED_HEADER_CELLS) | set(SYMBOL_CELLS)

    output = bytearray(source)
    for cell in RESTORED_HEADER_CELLS:
        start = map_offset(*cell)
        reference_word = map_word(reference, *cell)
        source_word = map_word(source, *cell)
        if (reference_word ^ source_word) & ~TILE_MASK:
            raise AssertionError(f"map attributes differ at restored cell {cell}")
        output[start:start + 2] = reference_word.to_bytes(2, "little")
    for cell in SYMBOL_CELLS:
        start = map_offset(*cell)
        output[start:start + 2] = blank_word.to_bytes(2, "little")

    # Any RC4 atlas slot that differs from v0.10.6 is audited through its real
    # runtime consumer (asset slot N -> map tile ID N+1).  If such a consumer
    # survives outside the requested header, restore the slot as collateral
    # protection.  This catches the left-border corruption at asset 0x010.
    source_changed_asset_indices = {
        asset_index
        for asset_index in range(PROGRAM_TILE_LENGTH // TILE_BYTES)
        if asset_tile(source, asset_index) != asset_tile(reference, asset_index)
    }
    changed_runtime_tile_ids = {asset_index + 1 for asset_index in source_changed_asset_indices}
    output_consumers = tile_consumers(bytes(output), changed_runtime_tile_ids)
    collateral_asset_indices = {
        asset_index
        for asset_index in source_changed_asset_indices
        if any(
            cell not in target_cells
            for cell in output_consumers.get(asset_index + 1, [])
        )
    }
    restored_asset_indices = intended_asset_indices | collateral_asset_indices
    for asset_index in restored_asset_indices:
        start = asset_tile_offset(asset_index)
        output[start:start + TILE_BYTES] = asset_tile(reference, asset_index)

    unresolved_external_consumers = {
        f"0x{asset_index:03X}": output_consumers.get(asset_index + 1, [])
        for asset_index in source_changed_asset_indices - restored_asset_indices
        if any(
            cell not in target_cells
            for cell in output_consumers.get(asset_index + 1, [])
        )
    }
    if unresolved_external_consumers:
        raise AssertionError(
            f"changed Program Deck tiles still affect unrelated cells: {unresolved_external_consumers}"
        )

    checksum = repair_checksum(output)

    allowed = bytearray(ROM_SIZE)
    for cell in target_cells:
        start = map_offset(*cell)
        allowed[start:start + 2] = b"\x01\x01"
    for asset_index in restored_asset_indices:
        start = asset_tile_offset(asset_index)
        allowed[start:start + TILE_BYTES] = b"\x01" * TILE_BYTES
    allowed[-2:] = b"\x01\x01"
    changed = [index for index, (before, after) in enumerate(zip(source, output)) if before != after]
    outside = [index for index in changed if not allowed[index]]
    if outside:
        raise AssertionError(f"unexpected ROM changes: {[hex(index) for index in outside[:16]]}")

    for cell in RESTORED_HEADER_CELLS:
        if map_word(output, *cell) != map_word(reference, *cell):
            raise AssertionError(f"restored header map differs at {cell}")
    for cell in SYMBOL_CELLS:
        if map_word(output, *cell) != blank_word:
            raise AssertionError(f"symbol cell {cell} was not cleared")
    for asset_index in restored_asset_indices:
        if asset_tile(output, asset_index) != asset_tile(reference, asset_index):
            raise AssertionError(f"restored asset tile 0x{asset_index:03X} differs")
    if int.from_bytes(output[-2:], "little") != sum(output[:-2]) & 0xFFFF:
        raise AssertionError("WonderSwan checksum repair failed")

    args.output_rom.parent.mkdir(parents=True, exist_ok=True)
    args.output_map.parent.mkdir(parents=True, exist_ok=True)
    args.output_tiles.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output_rom.write_bytes(output)
    final_map = bytes(output[PROGRAM_MAP_OFFSET:PROGRAM_MAP_OFFSET + PROGRAM_MAP_PUBLIC_LENGTH])
    final_tiles = bytes(output[PROGRAM_TILE_OFFSET:PROGRAM_TILE_OFFSET + PROGRAM_TILE_LENGTH])
    args.output_map.write_bytes(final_map)
    args.output_tiles.write_bytes(final_tiles)

    changed_map = [index for index in changed if PROGRAM_MAP_OFFSET <= index < PROGRAM_MAP_OFFSET + PROGRAM_MAP_RUNTIME_LENGTH]
    changed_tiles = [index for index in changed if PROGRAM_TILE_OFFSET <= index < PROGRAM_TILE_OFFSET + PROGRAM_TILE_LENGTH]
    changed_checksum = [index for index in changed if index >= ROM_SIZE - 2]
    report = {
        "status": "PASS",
        "base": "v0.10.7 RC4 approved",
        "reference": "approved pixel-polished v0.10.6 headings",
        "advance": "1 of 6 corrected rerun",
        "scope": "restore intact adjacent headings and remove only the marked symbol",
        "runtime_tile_mapping": {
            "asset_load_cpu_base": "0x8020",
            "map_tile_id_to_asset_index": "tile_id - 1",
            "legacy_audit_offset_corrected": True,
        },
        "rom": {
            "base_sha256": sha256(source),
            "reference_sha256": sha256(reference),
            "output_sha256": sha256(output),
            "size": len(output),
            "checksum": f"0x{checksum:04X}",
            "checksum_valid": True,
        },
        "map_change": {
            "map_offset": f"0x{PROGRAM_MAP_OFFSET:06X}",
            "program_deck_cells_restored": [list(cell) for cell in PROGRAM_DECK_CELLS],
            "y2_chip_folder_cells_restored": [list(cell) for cell in Y2_CHIP_FOLDER_CELLS],
            "y2_pictogram_cells_protected": [list(cell) for cell in Y2_PICTOGRAM_CELLS],
            "symbol_cells_cleared": [list(cell) for cell in SYMBOL_CELLS],
            "blank_word": f"0x{blank_word:04X}",
            "attributes_preserved": True,
        },
        "tile_change": {
            "intended_asset_indices_restored": [f"0x{index:03X}" for index in sorted(intended_asset_indices)],
            "collateral_asset_indices_restored": [f"0x{index:03X}" for index in sorted(collateral_asset_indices)],
            "collateral_consumers": {
                f"0x{index:03X}": [list(cell) for cell in output_consumers.get(index + 1, [])]
                for index in sorted(collateral_asset_indices)
            },
            "asset_indices_restored": [f"0x{index:03X}" for index in sorted(restored_asset_indices)],
            "unresolved_external_consumers": unresolved_external_consumers,
            "unrelated_tile_consumers_changed": 0,
        },
        "rom_delta": {
            "changed_bytes": len(changed),
            "changed_map_bytes": len(changed_map),
            "changed_tile_bytes": len(changed_tiles),
            "changed_checksum_bytes": len(changed_checksum),
            "outside_allowlist": len(outside),
            "offsets": [f"0x{index:06X}" for index in changed],
        },
        "program_map_sha256": sha256(final_map),
        "program_tiles_sha256": sha256(final_tiles),
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
