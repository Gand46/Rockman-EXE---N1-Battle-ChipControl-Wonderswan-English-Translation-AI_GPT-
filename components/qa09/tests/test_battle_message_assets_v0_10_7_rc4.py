from __future__ import annotations

import hashlib
import importlib.util
import json
import struct
import sys
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "src" / "battle_message_assets_v0_10_7_rc4.py"
ASSET_DIR = ROOT / "translation" / "assets"
REPORT_PATH = ASSET_DIR / "battle_message_asset_report_v0_10_7_rc4.json"
REPORT_SHA256 = "246532da99bc34f45f7e27d41bb3f5ed697564fd4fd37f8b301ca4ff5f06c677"

EXPECTED_CHANGED_IDS = {
    "b1": {
        13, 30, 60, 61, 64, 74, 92, 93, 137, 140, 143, 145,
        147, 148, 150, 155, 156, 162, 167, 170, 172, 173, 179,
    },
    "b2": {55},
}

EXPECTED_CRITICAL_TEXT = {
    ("b1", 13): "deleted from[LINE]the deck!",
    ("b1", 30): "has no chip set;",
    ("b1", 60): "used [RAW:0201] to",
    ("b1", 61): "cast a barrier!",
    ("b1", 64): "fired a[LINE]Charge Shot!",
    ("b1", 74): "destroyed in 1 hit!",
    ("b1", 92): "a hole blocked it;",
    ("b1", 93): "couldn't get close!",
    ("b1", 137): "[RAW:0200] was[LINE]paralyzed",
    ("b1", 140): "is numb and cannot[LINE]move!",
    ("b1", 143): "barely endured[LINE]the hit!",
    ("b1", 145): "Fire burst from[LINE]the panel!",
    ("b1", 147): "Absorbed earth",
    ("b1", 148): "energy from the[LINE]panel!",
    ("b1", 150): "Poison gas filled[LINE]the panel!",
    ("b1", 155): "[RAW:0200] changed",
    ("b1", 156): "damage into Attack[LINE]power!",
    ("b1", 162): "[RAW:0200] activated!",
    ("b1", 167): "stole [RAW:0201]'s[LINE]panel",
    ("b1", 170): "became harder[LINE]to move!",
    ("b1", 172): "Navi and chip match",
    ("b1", 173): "type! Chip Attack[LINE]increased!",
    ("b1", 179): "boosted Elec chip[LINE]Attack!",
    ("b2", 55): "DECK",
}


def load_tool() -> Any:
    spec = importlib.util.spec_from_file_location("battle_messages_rc4_test", TOOL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {TOOL_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_records(tool: Any, bank: Any, data: bytes, pointers: bytes) -> dict[int, dict[str, Any]]:
    targets: dict[int, int] = {}
    for index in range(bank.pointer_count):
        offset, segment = struct.unpack_from("<HH", pointers, index * 4)
        if offset == segment == 0:
            continue
        target = tool.FAR_BASE + segment * 16 + offset
        if not bank.data_start <= target < bank.data_end:
            raise AssertionError(f"{bank.name}:{index:03}: target 0x{target:06X}")
        targets[index] = target
    if len(targets.values()) != len(set(targets.values())):
        raise AssertionError(f"{bank.name}: duplicate target")

    ordered = sorted(targets.values())
    next_target = {
        target: ordered[pos + 1] if pos + 1 < len(ordered) else bank.data_end
        for pos, target in enumerate(ordered)
    }
    result: dict[int, dict[str, Any]] = {}
    for index, target in targets.items():
        relative = target - bank.data_start
        limit = next_target[target] - bank.data_start
        words, terminator, used_end = tool.legacy.read_target(data, relative, limit)
        result[index] = {
            "target": target,
            "words": words,
            "terminator": terminator,
            "used_end": used_end,
        }
    return result


class BattleMessageAssetsRC4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tool = load_tool()
        cls.n1tool = cls.tool.n1tool
        cls.decode, cls.encode = cls.n1tool.load_table(ROOT / "tables" / "n1battle_jp.tbl")
        cls.report_payload = REPORT_PATH.read_bytes()
        cls.report = json.loads(cls.report_payload)
        cls.generated: dict[str, dict[str, Any]] = {}
        cls.legacy_assets: dict[str, dict[str, Any]] = {}

        for bank in cls.tool.BANKS:
            data_name, pointer_name = cls.tool.OUTPUT_FILES[bank.name]
            data = (ASSET_DIR / data_name).read_bytes()
            pointers = (ASSET_DIR / pointer_name).read_bytes()
            legacy_data = (ASSET_DIR / f"battle_messages_{bank.name}_data_v0_9.bin").read_bytes()
            legacy_pointers = (
                ASSET_DIR / f"battle_messages_{bank.name}_pointers_v0_9.bin"
            ).read_bytes()
            cls.generated[bank.name] = {
                "bank": bank,
                "data": data,
                "pointers": pointers,
                "records": load_records(cls.tool, bank, data, pointers),
            }
            cls.legacy_assets[bank.name] = {
                "data": legacy_data,
                "pointers": legacy_pointers,
                "records": load_records(cls.tool, bank, legacy_data, legacy_pointers),
            }

    def decoded(self, words: list[int]) -> str:
        return "".join(self.n1tool.token_for(word, self.decode) for word in words)

    def test_assets_have_pinned_hashes_and_exact_bank_sizes(self) -> None:
        for bank in self.tool.BANKS:
            row = self.generated[bank.name]
            self.assertEqual(len(row["data"]), bank.data_end - bank.data_start)
            self.assertEqual(len(row["pointers"]), bank.pointer_count * 4)
            self.assertEqual(
                digest(row["data"]), self.tool.OUTPUT_SHA256[f"{bank.name}_data"]
            )
            self.assertEqual(
                digest(row["pointers"]),
                self.tool.OUTPUT_SHA256[f"{bank.name}_pointers"],
            )
        self.assertEqual(digest(self.report_payload), REPORT_SHA256)

    def test_null_dispatch_topology_is_byte_exact(self) -> None:
        for bank in self.tool.BANKS:
            new = self.generated[bank.name]["pointers"]
            old = self.legacy_assets[bank.name]["pointers"]
            new_nulls = {
                index for index in range(bank.pointer_count)
                if struct.unpack_from("<I", new, index * 4)[0] == 0
            }
            old_nulls = {
                index for index in range(bank.pointer_count)
                if struct.unpack_from("<I", old, index * 4)[0] == 0
            }
            self.assertEqual(new_nulls, old_nulls, bank.name)
        self.assertTrue({138, 141, 174}.issubset({
            index for index in range(187)
            if struct.unpack_from(
                "<I", self.generated["b1"]["pointers"], index * 4
            )[0] == 0
        }))

    def test_every_record_matches_translation_or_preserved_native_words(self) -> None:
        for bank in self.tool.BANKS:
            current = self.generated[bank.name]["records"]
            baseline = self.legacy_assets[bank.name]["records"]
            self.assertEqual(set(current), set(baseline))
            for index, row in current.items():
                if index in self.tool.TRANSLATIONS[bank.name]:
                    expected = self.n1tool.encode_text(
                        self.tool.TRANSLATIONS[bank.name][index], self.encode
                    )
                else:
                    expected = baseline[index]["words"]
                self.assertEqual(row["words"], expected, f"{bank.name}:{index:03}")
                self.assertEqual(
                    row["terminator"] & 0xFF00,
                    baseline[index]["terminator"] & 0xFF00,
                    f"{bank.name}:{index:03}",
                )
                self.assertEqual(row["terminator"] & 0xFF, len(row["words"]))

    def test_semantic_delta_is_exactly_the_reviewed_24_records(self) -> None:
        self.assertEqual(
            {name: set(ids) for name, ids in self.tool.CHANGED_IDS.items()},
            EXPECTED_CHANGED_IDS,
        )
        for bank in self.tool.BANKS:
            changed = {
                index
                for index, row in self.generated[bank.name]["records"].items()
                if row["words"] != self.legacy_assets[bank.name]["records"][index]["words"]
            }
            self.assertEqual(changed, EXPECTED_CHANGED_IDS[bank.name])
        for key, expected in EXPECTED_CRITICAL_TEXT.items():
            self.assertEqual(self.tool.TRANSLATIONS[key[0]][key[1]], expected)

    def test_line_control_only_uses_runtime_proven_positions(self) -> None:
        line_word = self.n1tool.CONTROL_WORDS["LINE"]
        wait_word = self.n1tool.CONTROL_WORDS["WAIT"]
        end_word = self.n1tool.CONTROL_WORDS["END"]
        found: set[int] = set()
        for bank in self.tool.BANKS:
            for index, row in self.generated[bank.name]["records"].items():
                self.assertNotIn(wait_word, row["words"], f"{bank.name}:{index:03}")
                self.assertNotIn(end_word, row["words"], f"{bank.name}:{index:03}")
                count = row["words"].count(line_word)
                if count:
                    self.assertEqual(bank.name, "b1")
                    self.assertEqual(count, 1)
                    found.add(index)
        self.assertEqual(found, set(self.tool.APPROVED_LINE_IDS))

        groups = self.tool.groups_from_pointer_source(
            self.generated["b1"]["pointers"], 187
        )
        for group in groups:
            line_ids = [
                index for index in group
                if line_word in self.generated["b1"]["records"][index]["words"]
            ]
            if line_ids:
                self.assertEqual(line_ids, [group[-1]])
            added = sum(
                self.generated["b1"]["records"][index]["words"].count(line_word)
                for index in group
            )
            self.assertLessEqual(len(group) + added, 3, group)

    def test_all_physical_lines_fit_their_runtime_geometry(self) -> None:
        for bank in self.tool.BANKS:
            width_rows, group_rows = self.tool.validate_bank_translations(
                bank, self.generated[bank.name]["pointers"]
            )
            for row in width_rows:
                self.assertLessEqual(
                    max(row["physical_line_widths_worst_case"]), row["line_limit"], row
                )
            if bank.name == "b1":
                self.assertEqual(max(row["maximum_visible_columns"] for row in width_rows), 19)
                self.assertEqual(len(group_rows), 13)
            else:
                self.assertEqual(max(row["maximum_visible_columns"] for row in width_rows), 25)
                self.assertEqual(group_rows, [])
        self.assertEqual(self.tool.physical_line_widths("b2", 55, "DECK"), (4,))
        self.assertEqual(self.tool.line_limit("b2", 55), 8)

    def test_pause_neighbors_and_numeric_width_contracts_are_preserved(self) -> None:
        self.assertEqual(self.tool.B2[53], "PAUSE")
        self.assertEqual(self.tool.B2[55], "DECK")
        self.assertEqual(self.tool.B2[56], "RETRY")
        self.assertEqual(self.tool.B2[57], "GIVE UP")
        for index in (19, 27, 37, 112, 114):
            self.assertEqual(self.tool.B1[index], self.tool.legacy.B1[index])
            self.assertLessEqual(
                max(self.tool.physical_line_widths("b1", index, self.tool.B1[index])),
                self.tool.PORTRAIT_LINE_COLUMNS,
            )

    def test_report_accounts_for_assets_topology_controls_and_slack(self) -> None:
        self.assertEqual(self.report["status"], "PASS")
        self.assertEqual(self.report["project_version"], self.tool.VERSION)
        self.assertEqual(self.report["changed_targets"], 24)
        self.assertEqual(self.report["maximum_visible_columns"], 25)
        self.assertEqual(
            self.report["maximum_visible_columns_by_bank"], {"b1": 19, "b2": 25}
        )
        safety = self.report["dispatch_safety"]
        self.assertTrue(safety["null_pointer_topology_preserved"])
        self.assertEqual(safety["new_pointer_rows"], 0)
        self.assertEqual(safety["line_control_words_added"], 13)
        self.assertEqual(set(safety["line_control_ids"]), set(self.tool.APPROVED_LINE_IDS))
        by_bank = {row["id"]: row for row in self.report["banks"]}
        self.assertEqual(by_bank["b1"]["layout"]["default_line_limit"], 19)
        self.assertEqual(by_bank["b1"]["layout"]["maximum_visible_columns"], 19)
        self.assertEqual(by_bank["b2"]["layout"]["default_line_limit"], 26)
        self.assertEqual(by_bank["b2"]["layout"]["special_line_limits"], {"55": 8})
        self.assertEqual(by_bank["b2"]["layout"]["maximum_visible_columns"], 25)
        self.assertEqual(by_bank["b1"]["data"]["free_bytes"], 284)
        self.assertEqual(by_bank["b2"]["data"]["free_bytes"], 84)
        for bank in self.tool.BANKS:
            used = by_bank[bank.name]["data"]["used_bytes"]
            self.assertFalse(any(self.generated[bank.name]["data"][used:]))
            self.assertTrue(by_bank[bank.name]["pointers"]["null_topology_preserved"])


if __name__ == "__main__":
    unittest.main()
