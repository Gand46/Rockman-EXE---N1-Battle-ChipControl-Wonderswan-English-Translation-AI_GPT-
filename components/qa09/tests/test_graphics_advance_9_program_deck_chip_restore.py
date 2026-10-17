from __future__ import annotations

import sys
import os
import unittest
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import graphics_advance_9_program_deck_chip_restore as a9  # noqa: E402
import n1tool  # noqa: E402


class GraphicsAdvance9Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source_path = os.environ.get("CONTINUITY_INPUT_JP")
        if not source_path:
            raise unittest.SkipTest("CONTINUITY_INPUT_JP missing: supply verified original JP .wsc")
        cls.source = Path(source_path).read_bytes()
        if hashlib.sha256(cls.source).hexdigest() != a9.SOURCE_SHA256:
            raise AssertionError("Unexpected Japanese source hash")
        # A8 source is reconstructed from its cumulative, archived IPS, not an
        # obsolete developer-only build/ file or an external /mnt/upload path.
        patch = (ROOT / "tests/fixtures/patches/Rockman_EXE_N1_Battle_English_v0.10.7-graphics-a8.ips").read_bytes()
        cls.a8 = n1tool.apply_ips(cls.source, patch)
        if hashlib.sha256(cls.a8).hexdigest() != a9.BASE_A8_SHA256:
            raise AssertionError("Reconstructed A8 does not match approved hash")
        cls.output = a9.restore_tile(cls.source, cls.a8)

    def test_complete_bank_and_single_tile_allowlist(self) -> None:
        self.assertEqual(len(self.output), a9.BANK_LENGTH)
        before = self.a8[a9.BANK_OFFSET:a9.BANK_OFFSET + a9.BANK_LENGTH]
        changed = [i for i, pair in enumerate(zip(before, self.output, strict=True)) if pair[0] != pair[1]]
        self.assertEqual(len(changed), 29)
        self.assertTrue(all(a9.ASSET_INDEX * 32 <= i < (a9.ASSET_INDEX + 1) * 32 for i in changed))

    def test_restored_pattern_is_exact_original(self) -> None:
        start = a9.ASSET_INDEX * 32
        source_bank = self.source[a9.BANK_OFFSET:a9.BANK_OFFSET + a9.BANK_LENGTH]
        self.assertEqual(self.output[start:start + 32], source_bank[start:start + 32])
        self.assertEqual(a9.sha256(self.output[start:start + 32]), a9.SOURCE_TILE_SHA256)

    def test_runtime_consumer_is_exclusive(self) -> None:
        tilemap = self.a8[a9.MAP_OFFSET:a9.MAP_OFFSET + a9.MAP_LENGTH]
        self.assertEqual(a9.consumers(tilemap, a9.RUNTIME_TILE_ID), [list(a9.TARGET_CELL)])

    def test_toolbar_pool_does_not_include_runtime_tile_e9(self) -> None:
        self.assertNotIn(a9.RUNTIME_TILE_ID, set(range(0x0E2, 0x0E9)))


if __name__ == "__main__":
    unittest.main()
