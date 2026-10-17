from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import graphics_advance_8_no_chip_card_cleanup as a8  # noqa: E402


class GraphicsAdvance8CardCleanupTests(unittest.TestCase):
    def test_exact_card_cleanup_and_protection(self) -> None:
        base = (ROOT / "translation/assets/pet_no_data_card_tiles_v0_10.bin").read_bytes()
        output = (ROOT / "translation/assets" / a8.ASSET_NAME).read_bytes()
        self.assertEqual(a8.clean_residual_row(base), output)

        before = a8.card_pixels(base)
        after = a8.card_pixels(output)
        self.assertEqual(before[:24], after[:24])
        self.assertEqual(before[28:], after[28:])
        for y in a8.RESIDUAL_Y_RANGE:
            self.assertEqual(before[24 + y][:2], after[24 + y][:2])
            self.assertEqual(before[24 + y][62:], after[24 + y][62:])
            replacement = a8.FRAME_INDEX if y == 3 else a8.BACKGROUND_INDEX
            self.assertTrue(all(after[24 + y][x] == replacement
                                for x in a8.INNER_X_RANGE))

    def test_binary_delta_stays_in_fourth_card_row(self) -> None:
        base = (ROOT / "translation/assets/pet_no_data_card_tiles_v0_10.bin").read_bytes()
        output = (ROOT / "translation/assets" / a8.ASSET_NAME).read_bytes()
        changed = {index for index, pair in enumerate(zip(base, output, strict=True))
                   if pair[0] != pair[1]}
        self.assertTrue(changed)
        self.assertTrue(all(0x600 <= index < 0x700 for index in changed))
        self.assertEqual(base[:0x600], output[:0x600])


if __name__ == "__main__":
    unittest.main()
