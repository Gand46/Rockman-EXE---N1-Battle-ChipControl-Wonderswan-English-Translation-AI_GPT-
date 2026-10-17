from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class RedBoxFontRC3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.assets = ROOT / "translation/assets"
        cls.report = json.loads(
            (cls.assets / "redbox_font_asset_report_v0_10_7_rc3.json").read_text(encoding="utf-8")
        )
        cls.rows = [row for group in cls.report["groups"].values() for row in group["labels"]]
        cls.text_rows = [row for row in cls.rows if row["text"] is not None]

    def test_report_identity_and_base(self) -> None:
        self.assertEqual(self.report["status"], "PASS")
        self.assertEqual(self.report["version"], "0.10.7-rc3")
        self.assertEqual(
            self.report["base"]["rom_sha256"],
            "fb78269238806807616cfe622a3be9239dc5b95bbd454ee02127919dd463e3cc",
        )
        self.assertIn("RC2 excluded", self.report["base"]["description"])
        self.assertFalse(self.report["rc2_assets_reused"])
        self.assertEqual(self.report["marked_text_instances"], 17)
        self.assertEqual(self.report["harmonized_duplicate_instances"], 1)
        self.assertEqual(self.report["corrected_text_instances"], 18)
        self.assertEqual(self.report["rendered_text_segments"], 19)
        self.assertEqual(self.report["removed_non_text_symbols"], 1)

    def test_literal_uppercase_texts(self) -> None:
        expected = [
            "PROGRAM DECK", "Y2 CHIP FOLDER", "AUTO CONTROL", "DATA LIBRARY",
            "BACKPACK", "NETNAVI", "NETNAVI", "PROGRAM DECK", "NAVICHIP", "BATTLECHIP",
            "NORMAL30", "ATTACK POWER", "RETREAT", "VICTORY", "CAPACITY",
            "NAVI CHIP", "BATTLE CHIP", "BATTLE CHIP / NAVI CHIP",
        ]
        self.assertEqual(self.report["literal_text_preserved"], expected)
        for text in expected:
            self.assertEqual(text, text.upper())
        self.assertNotIn("Chip Folder", expected)
        self.assertEqual(self.report["harmonized_duplicate_ids"], ["submenu_netnavi"])

    def test_output_assets_match_report(self) -> None:
        for name, row in self.report["outputs"].items():
            path = self.assets / name
            self.assertTrue(path.is_file(), name)
            payload = path.read_bytes()
            self.assertEqual(len(payload), row["length"], name)
            self.assertEqual(sha256(payload), row["sha256"], name)

    def test_every_visible_glyph_is_manually_reviewed(self) -> None:
        manual_total = 0
        for row in self.text_rows:
            expected = sum(character != " " for character in row["text"])
            self.assertEqual(row["manual_pixel_corrected_glyph_instances"], expected, row["id"])
            manual_total += expected
        self.assertEqual(manual_total, self.report["font_policy"]["manual_glyph_instances"])
        self.assertFalse(self.report["font_policy"]["antialiasing"])
        self.assertFalse(self.report["font_policy"]["line_scaling"])
        self.assertEqual(self.report["font_policy"]["resampling"], "none")

    def test_native_fit_spacing_and_program_deck_margins(self) -> None:
        by_id = {row["id"]: row for row in self.text_rows}
        for row in self.text_rows:
            self.assertLessEqual(row["render_width_pixels"], row["field_width_pixels"], row["id"])
            self.assertLessEqual(
                row["render_height_pixels"] + row.get("shadow_pixels", 0),
                row["field_height_pixels"], row["id"],
            )
            self.assertGreaterEqual(row["minimum_interglyph_face_gap_pixels"], 1, row["id"])
        self.assertEqual(by_id["live_program_deck"]["field_width_pixels"], 48)
        self.assertEqual(by_id["live_program_deck"]["render_width_pixels"], 46)
        self.assertEqual(by_id["live_program_deck"]["offset_x_pixels"], 1)
        self.assertEqual(by_id["manual_program_deck"]["render_width_pixels"], 46)
        self.assertEqual(by_id["manual_program_deck"]["offset_x_pixels"], 1)

    def test_target_and_alias_protections(self) -> None:
        for group in self.report["groups"].values():
            self.assertEqual(group["tile_aliases_outside_targets"], 0)
            self.assertLessEqual(len(group["changed_tile_ids"]), group["modifiable_pool"])
            self.assertTrue(group["orphan_allowlist_all_unreferenced"])
            self.assertTrue(
                set(group["changed_orphan_tile_ids"]).issubset(group["orphan_allowlist"])
            )
        protections = self.report["protections"]
        self.assertFalse(protections["bottom_dialogue_boxes_modified"])
        self.assertFalse(protections["dialogue_font_or_strings_modified"])
        self.assertFalse(protections["dynamic_values_modified"])
        self.assertFalse(protections["cursors_modified"])
        self.assertFalse(protections["frames_modified"])
        self.assertFalse(protections["auto_control_icon_modified"])
        self.assertFalse(protections["program_deck_pictograms_modified"])
        self.assertFalse(protections["program_deck_tiny_unmarked_cell_modified"])
        self.assertFalse(protections["chip_folder_unmarked_screen_modified"])
        self.assertFalse(protections["netnavi_non_text_accent_pixels_modified"])
        self.assertFalse(protections["manual_overview_mixed_art_cells_modified"])
        self.assertTrue(protections["all_untargeted_visual_cells_unchanged"])
        self.assertTrue(protections["map_palette_priority_flip_bits_preserved"])

    def test_symbol_is_a_separate_pixel_exact_target(self) -> None:
        symbol = self.report["symbol_removal"]
        self.assertEqual(symbol["map_cell"], [17, 0])
        self.assertEqual(symbol["replacement_tile_pattern"], "clean grid tile 0x00D")
        self.assertTrue(symbol["pixel_exact"])
        row = next(row for row in self.rows if row["id"] == "live_unrelated_symbol")
        self.assertIsNone(row["text"])

    def test_preview_includes_active_palette_evidence(self) -> None:
        self.assertEqual(self.report["native_resolution"], [224, 144])
        self.assertIn("program_deck_stats_palette_comparison_v0_10_7_rc3.png", self.report["outputs"])

    def test_font_alternative_is_verified_but_not_selected(self) -> None:
        policy = self.report["font_policy"]
        self.assertEqual(policy["alternative_file_verified"], "SF3FontSmall")
        self.assertTrue(policy["alternative_not_selected"])
        self.assertNotIn("alternative_validated", policy)


if __name__ == "__main__":
    unittest.main()
