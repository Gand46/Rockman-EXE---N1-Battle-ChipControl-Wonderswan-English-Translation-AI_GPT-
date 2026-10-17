from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import graphics_advance_7_month_later_centering as a7  # noqa: E402


class GraphicsAdvance7Tests(unittest.TestCase):
    def test_centering_geometry_is_exact(self) -> None:
        left = a7.CENTERED_X_CELL * a7.CELL_WIDTH
        right = (a7.CENTERED_X_CELL + a7.TEXT_CELLS) * a7.CELL_WIDTH
        self.assertEqual((left, right), (48, 176))
        self.assertEqual((left + right) // 2, a7.SCREEN_WIDTH // 2)
        self.assertEqual(a7.SCREEN_WIDTH // 2, 112)
        self.assertEqual((a7.CENTERED_X_CELL - a7.ORIGINAL_X_CELL) * a7.CELL_WIDTH, -40)

    def test_call_site_changes_only_x_immediate(self) -> None:
        self.assertEqual(a7.ORIGINAL_CALL, bytes.fromhex("6A 0B"))
        self.assertEqual(a7.PATCHED_CALL, bytes.fromhex("6A 06"))
        self.assertEqual(a7.ORIGINAL_CALL[0], a7.PATCHED_CALL[0])
        self.assertEqual(hashlib.sha256(a7.PATCHED_CALL).hexdigest(), a7.CALL_ASSET_SHA256)

    def test_approved_text_record_is_unchanged(self) -> None:
        self.assertEqual(len(a7.AUX_EXPECTED_TEXT_BYTES), 34)
        self.assertTrue(a7.AUX_EXPECTED_TEXT_BYTES.endswith(bytes.fromhex("000080")))


if __name__ == "__main__":
    unittest.main()
