"""Portability and evidence invariants for QA09 maintenance (no ROM changes)."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import n1tool  # noqa: E402
from qa09_paths import QA08_SHA256, qa08_rom  # noqa: E402

QA09_SHA256 = "d729823bbe6cf9132e6345ed734eb2dbe51885c13d5a17a44a9f7cfae086c326"
BPS_SHA256 = "4fbfce1dcf2d0da714b936874167219e05076ad8ac40db0e43bb214eb063b0f2"
JP_SHA256 = "4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed"


def h(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class QA09MaintenanceChecks(unittest.TestCase):
    def test_baseline_artifacts_are_shipped_with_no_mutations(self):
        bps = ROOT / "../../maintenance/baseline-patches/Rockman_N1_English_QA09.bps"
        self.assertTrue(bps.is_file())
        self.assertEqual(h(bps.read_bytes()), BPS_SHA256)
        self.assertEqual(len(bps.read_bytes()), 151492)
        report = json.loads((ROOT / "evidence/qa09/validation.json").read_text())
        self.assertEqual(report["rom_sha256"], QA09_SHA256)
        self.assertEqual(report["base_rom_sha256"], QA08_SHA256)
        self.assertEqual(report["changed_bytes"], 72)
        self.assertEqual(report["required_pending"], [])

    def test_archived_replay_states_exist_and_match_provenance(self):
        routes = json.loads((ROOT / "evidence/qa09/replay_index.json").read_text())
        self.assertEqual(len(routes), 30)
        # Public GitHub excludes private savestates containing ROM/RAM bytes.
        # The routes and provenance remain inspectable, but do not convert a
        # missing private runtime fixture into a successful replay.
        if any(not (ROOT / item["state"]).is_file() for item in routes):
            for item in routes:
                self.assertTrue((ROOT / item["route"]).is_file(), item["route"])
                self.assertEqual(len(item["state_sha256"]), 64)
            self.skipTest("PRIVATE_FIXTURE_NOT_DISTRIBUTED: 30 historical runtime savestates intentionally excluded from GitHub")
        for item in routes:
            with self.subTest(case=item["case"]):
                state = ROOT / item["state"]
                route = ROOT / item["route"]
                self.assertTrue(state.is_file(), str(state))
                self.assertTrue(route.is_file(), str(route))
                self.assertEqual(h(state.read_bytes()), item["state_sha256"])
                self.assertIsInstance(json.loads(route.read_text()), list)

    def test_qa08_parent_is_locatable_after_one_qa09_build(self):
        if not (ROOT / "build/qa09/qa08_base/Rockman_N1_English_QA08.wsc").is_file():
            self.skipTest("Run tools/build_qa09.py --source original.wsc first")
        self.assertEqual(h(qa08_rom(ROOT).read_bytes()), QA08_SHA256)

    def test_exact_qa09_bps_rebuild_roundtrip(self):
        source = os.environ.get("CONTINUITY_INPUT_JP")
        target = ROOT / "build/qa09/Rockman_N1_English_QA09.wsc"
        rebuilt = ROOT / "build/qa09/Rockman_N1_English_QA09.bps"
        if not source or not (target.is_file() and rebuilt.is_file()):
            self.skipTest("Run build and set CONTINUITY_INPUT_JP to verified original ROM")
        original = Path(source).read_bytes()
        self.assertEqual(h(original), JP_SHA256)
        self.assertEqual(h(target.read_bytes()), QA09_SHA256)
        self.assertEqual(h(rebuilt.read_bytes()), BPS_SHA256)
        self.assertEqual((ROOT / "../../maintenance/baseline-patches/Rockman_N1_English_QA09.bps").read_bytes(), rebuilt.read_bytes())
        a8 = n1tool.apply_ips(original, (ROOT / "tests/fixtures/patches/Rockman_EXE_N1_Battle_English_v0.10.7-graphics-a8.ips").read_bytes())
        self.assertEqual(h(a8), "aafa083e8781d58858c35cf729ed18c9269126cba70c789e1e631844071e3749")
        from continuity import apply_bps
        self.assertEqual(apply_bps(original, rebuilt.read_bytes()), target.read_bytes())

    def test_runtime_regression_reports_are_scoped_and_exact(self):
        root = ROOT / "evidence/qa10"
        reports = [json.loads((root / name).read_text()) for name in
                   ("replay_compare.json", "replay_master_title.json")]
        self.assertEqual(sum(r["total_compared_frames"] for r in reports), 75)
        for report in reports:
            self.assertEqual(report["status"], "PASS_SYNTHETIC_REGRESSION")
            self.assertEqual(report["total_changed_pixels"], 0)
            self.assertEqual(report["total_changed_wram_bytes"], 0)
            self.assertEqual(report["qa09_rom_sha256"], QA09_SHA256)
            self.assertEqual(report["qa08_rom_sha256"], QA08_SHA256)
            self.assertTrue(all(x["status"] == "PASS_PIXEL_RAM_EQUIVALENCE" for x in report["cases"]))


if __name__ == "__main__":
    unittest.main()
