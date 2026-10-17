#!/usr/bin/env python3
"""Regression tests for the isolated Graphics Advance 6 quantity renderer."""

from __future__ import annotations

import hashlib
import json
import struct
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import graphics_advance_6_backpack_quantity as a6  # noqa: E402


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class GraphicsAdvance6QuantityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.assets = ROOT / "translation/assets"
        cls.code = (cls.assets / a6.CODE_ASSET).read_bytes()

    def test_renderer_identity_and_tables(self) -> None:
        self.assertEqual(len(self.code), 282)
        self.assertEqual(sha256(self.code), a6.CODE_SHA256)
        digits = self.code[a6.DIGIT_TABLE_OFFSET:a6.DIGIT_TABLE_OFFSET + a6.DIGIT_TABLE_LENGTH]
        self.assertEqual(len(digits), 50)
        self.assertTrue(all(0 <= value <= 7 for value in digits))
        self.assertTrue(all(any(digits[digit * 5:digit * 5 + 5]) for digit in range(10)))
        row_masks = struct.unpack_from("<8H", self.code, a6.ROW_MASKS_OFFSET)
        self.assertEqual(row_masks, (0x0000, 0x1000, 0x0001, 0x1001,
                                     0x0010, 0x1010, 0x0011, 0x1011))
        top_tiles = struct.unpack_from("<7H", self.code, a6.QUANTITY_TILE_TABLE_OFFSET)
        self.assertEqual(tuple(value for tile in top_tiles for value in (tile, tile + 1)),
                         a6.QUANTITY_TILE_IDS)

    def test_call_and_hosted_b1_asset(self) -> None:
        call = (self.assets / a6.CALL_ASSET).read_bytes()
        self.assertEqual(call, a6.PATCHED_CALL)
        b1 = (self.assets / a6.B1_OUTPUT_ASSET).read_bytes()
        self.assertEqual(len(b1), a6.B1_DATA_LENGTH)
        host = a6.HOST_OFFSET - a6.B1_DATA_OFFSET
        self.assertEqual(b1[host:host + len(self.code)], self.code)

    def test_tiles_have_no_static_consumers(self) -> None:
        tile_ids = set(a6.QUANTITY_TILE_IDS)
        self.assertEqual(len(tile_ids), 14)
        self.assertGreater(min(tile_ids), 75)
        maps = (
            "program_deck_chip_folder_bg0_map_graphics_a3.bin",
            "pet_submenu_chip_folder_bg0_map_graphics_a5.bin",
            "pet_submenu_backpack_bg0_map_v0_10_7_rc3.bin",
            "pet_submenu_data_library_bg0_map_v0_10_7_rc3.bin",
        )
        for filename in maps:
            payload = (self.assets / filename).read_bytes()
            used = {struct.unpack_from("<H", payload, index)[0] & 0x1FF
                    for index in range(0, len(payload) - 1, 2)}
            self.assertTrue(tile_ids.isdisjoint(used), filename)

    def test_manifest_ranges_do_not_overlap(self) -> None:
        manifest = json.loads((ROOT / "translation/lineage/en_v0_10_7_graphics_a6.json").read_text(encoding="utf-8"))
        rows = []
        for entry in manifest["binary_entries"]:
            start = int(entry["offset"], 0)
            rows.append((start, start + int(entry["length"]), entry["id"]))
        rows.sort()
        for left, right in zip(rows, rows[1:]):
            self.assertLessEqual(left[1], right[0], f"overlap: {left[2]} / {right[2]}")
        call = [entry for entry in manifest["binary_entries"]
                if entry["id"] == "graphics_a6_backpack_quantity_call"]
        self.assertEqual(len(call), 1)

    def test_rule_and_runtime_closure(self) -> None:
        rules = json.loads((ROOT / "translation/graphics_advance_rules.json").read_text(encoding="utf-8"))
        advance = int(rules["project_version"].rsplit("a", 1)[1])
        self.assertGreaterEqual(advance, 6)
        self.assertGreaterEqual(len(rules["rules"]), 26)
        self.assertIn("isolated_dynamic_quantity_renderer",
                      {row["name"] for row in rules["rules"]})
        self.assertEqual(rules["advance_6"]["status"], "PASS")
        runtime = json.loads((ROOT / "evidence/runtime_graphics_advances/advance_6_gate_final/graphics_advance_6_runtime_validation.json").read_text(encoding="utf-8"))
        self.assertEqual(runtime["status"], "PASS")
        self.assertEqual(len(runtime["live_consumer_graph"]["quantity_layer_consumers"]), 14)
        self.assertEqual(runtime["live_consumer_graph"]["other_layer_consumers"], [])
        self.assertTrue(runtime["empty_backpack_pixel_exact_vs_a5"])
        self.assertTrue(runtime["main_chip_folder_pixel_exact_vs_a5"])


if __name__ == "__main__":
    unittest.main()
