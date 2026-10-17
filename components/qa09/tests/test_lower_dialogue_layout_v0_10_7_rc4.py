from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "src" / "lower_dialogue_layout_v0_10_7_rc4.py"
SOURCE_PATH = ROOT / "translation" / "lineage/en_v0_10_7_rc3.json"
OUTPUT_PATH = ROOT / "translation" / "lineage/en_v0_10_7_rc4_dialogue.json"
REPORT_PATH = (
    ROOT / "translation" / "assets" /
    "lower_dialogue_layout_report_v0_10_7_rc4.json"
)


def load_tool():
    spec = importlib.util.spec_from_file_location("lower_dialogue_layout_rc4_test", TOOL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {TOOL_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class LowerDialogueLayoutRC4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tool = load_tool()
        cls.source_payload = SOURCE_PATH.read_bytes()
        cls.source = json.loads(cls.source_payload)
        cls.output_payload = OUTPUT_PATH.read_bytes()
        cls.output = json.loads(cls.output_payload)
        cls.report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

        n1tool = cls.tool.load_n1tool(ROOT)
        _, cls.encode = n1tool.load_table(ROOT / "tables" / "n1battle_jp.tbl")
        cls.generated, cls.generated_report = cls.tool.transform_manifest(
            cls.source_payload, cls.encode
        )

    def test_rc3_source_is_immutable_expected_input(self) -> None:
        self.assertEqual(
            hashlib.sha256(self.source_payload).hexdigest(),
            self.tool.SOURCE_MANIFEST_SHA256,
        )
        self.assertEqual(self.source["project_version"], self.tool.SOURCE_VERSION)

    def test_generated_manifest_is_deterministic(self) -> None:
        expected_payload = self.tool.serialize_manifest(self.generated)
        self.assertEqual(self.output_payload, expected_payload)
        self.assertEqual(
            hashlib.sha256(self.output_payload).hexdigest(),
            "f82f494a2328f2d6e59bf3bdd031ff051089059092dd622c12a46a7b11537080",
        )

    def test_report_is_deterministic_and_complete(self) -> None:
        expected = json.loads(json.dumps(self.generated_report))
        expected["output_manifest"] = {
            "file": OUTPUT_PATH.name,
            "sha256": hashlib.sha256(self.output_payload).hexdigest(),
            "bytes": len(self.output_payload),
        }
        self.assertEqual(self.report, expected)
        self.assertEqual(self.report["status"], "PASS")
        self.assertEqual(self.report["source_overflow_lines"], 71)
        self.assertEqual(self.report["affected_pages"], 67)
        self.assertEqual(self.report["affected_entries"], 52)
        self.assertEqual(self.report["exact_reflow_pages"], 56)
        self.assertEqual(self.report["condensed_pages"], 11)
        self.assertEqual(self.report["remaining_literal_overflow_lines"], 0)
        self.assertEqual(self.report["remaining_vertical_overflow_pages"], 0)

    def test_every_entry_fits_narrow_box_and_original_span(self) -> None:
        for entry in self.output["entries"]:
            translation = entry["translation"]
            for page_number, page in enumerate(translation.split("[WAIT]"), 1):
                lines = self.tool.visible_lines(page)
                self.assertLessEqual(
                    len(lines), self.tool.MAX_LINES,
                    f"{entry['id']} page {page_number}",
                )
                for line_number, line in enumerate(lines, 1):
                    self.assertLessEqual(
                        len(line), self.tool.MAX_COLUMNS,
                        f"{entry['id']} page {page_number} line {line_number}: {line!r}",
                    )

            required = (len(self.tool.encode_text(translation, self.encode)) + 1) * 2
            span = int(entry["length"], 0) if isinstance(entry["length"], str) else entry["length"]
            self.assertLessEqual(required, span, entry["id"])

    def test_only_version_scope_and_52_translations_change(self) -> None:
        for key in self.source:
            if key not in {"project_version", "scope", "entries"}:
                self.assertEqual(self.output[key], self.source[key], key)
        self.assertEqual(self.output["project_version"], self.tool.OUTPUT_VERSION)

        source_entries = {entry["id"]: entry for entry in self.source["entries"]}
        output_entries = {entry["id"]: entry for entry in self.output["entries"]}
        self.assertEqual(set(source_entries), set(output_entries))
        changed = set()
        for entry_id, before in source_entries.items():
            after = output_entries[entry_id]
            for key in before:
                if key == "translation":
                    continue
                self.assertEqual(after[key], before[key], f"{entry_id}:{key}")
            if after["translation"] != before["translation"]:
                changed.add(entry_id)
        self.assertEqual(len(changed), 52)
        self.assertEqual(
            changed,
            {row["entry_id"] for row in self.report["pages"]},
        )

    def test_exact_reflows_preserve_wording(self) -> None:
        for row in self.report["pages"]:
            old_text = self.tool.normalized_page_text(row["old_lines"])
            new_text = self.tool.normalized_page_text(row["new_lines"])
            if row["mode"] == "exact_reflow":
                self.assertEqual(new_text, old_text, (row["entry_id"], row["page"]))

    def test_all_condensations_are_explicit_and_reviewed(self) -> None:
        condensed = {
            (row["entry_id"], row["page"]): tuple(row["new_lines"])
            for row in self.report["pages"]
            if row["mode"] == "condensed"
        }
        expected = {
            (item.entry_id, item.page): item.replacement_lines
            for item in self.tool.CONDENSATIONS
        }
        self.assertEqual(condensed, expected)

    def test_unexpected_source_is_rejected(self) -> None:
        mutated = self.source_payload + b"\n"
        with self.assertRaisesRegex(ValueError, "immutable RC3 manifest"):
            self.tool.transform_manifest(mutated, self.encode)


if __name__ == "__main__":
    unittest.main()
