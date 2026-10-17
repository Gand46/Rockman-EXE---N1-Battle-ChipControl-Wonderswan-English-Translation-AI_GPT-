from __future__ import annotations

import contextlib
import importlib.util
import io
import hashlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT_ROOT / "src" / "n1save.py"
SPEC = importlib.util.spec_from_file_location("n1save", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
n1save = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = n1save
SPEC.loader.exec_module(n1save)


def make_block(marker: int = 0x42) -> bytearray:
    block = bytearray(n1save.BLOCK_SIZE)
    block[:4] = n1save.SAVE_SIGNATURE
    block[
        n1save.PAYLOAD_LENGTH_OFFSET : n1save.PAYLOAD_LENGTH_OFFSET + 2
    ] = n1save.EXPECTED_PAYLOAD_LENGTH.to_bytes(2, "little")
    block[0x08:0x0C] = bytes((0x01, 0x02, 0x00, 0x01))
    block[0x10] = marker
    block[0x20:0x24] = b"TEST"
    block[
        n1save.CHECKSUM_OFFSET : n1save.CHECKSUM_OFFSET + n1save.CHECKSUM_SIZE
    ] = n1save.calculate_block_checksum(block).to_bytes(
        n1save.CHECKSUM_SIZE, "little"
    )
    return block


def make_raw_save(main_marker: int = 0x42, copy_marker: int | None = None) -> bytes:
    if copy_marker is None:
        copy_marker = main_marker
    data = bytearray(n1save.SRAM_SIZE)
    data[
        n1save.MAIN_BLOCK_OFFSET : n1save.MAIN_BLOCK_OFFSET + n1save.BLOCK_SIZE
    ] = make_block(main_marker)
    data[
        n1save.COPY_BLOCK_OFFSET : n1save.COPY_BLOCK_OFFSET + n1save.BLOCK_SIZE
    ] = make_block(copy_marker)
    return bytes(data)


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = n1save.main(arguments)
    return code, stdout.getvalue(), stderr.getvalue()


class N1SaveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_context = tempfile.TemporaryDirectory(prefix="n1save-test-")
        self.temp = Path(self.temp_context.name)
        self.source = self.temp / "source.sav"
        self.source.write_bytes(make_raw_save())

    def tearDown(self) -> None:
        self.temp_context.cleanup()

    def test_checksum_formula_sums_payload_and_excludes_stored_word(self) -> None:
        block = make_block()
        expected = n1save.calculate_block_checksum(block)
        block[n1save.CHECKSUM_OFFSET] ^= 0xFF
        block[n1save.CHECKSUM_OFFSET + 1] ^= 0xFF
        self.assertEqual(n1save.calculate_block_checksum(block), expected)

        block[n1save.SAVE_HEADER_SIZE] ^= 0xFF
        self.assertNotEqual(n1save.calculate_block_checksum(block), expected)

    def test_info_and_strict_validation(self) -> None:
        image = n1save.load_save(self.source)
        self.assertEqual(image.format_name, n1save.FORMAT_RAW)
        self.assertTrue(image.valid)
        code, stdout, stderr = run_cli(["validate", str(self.source)])
        self.assertEqual(code, 0)
        self.assertIn("VALID", stdout)
        self.assertEqual(stderr, "")

    def test_repair_uses_new_file_and_preserves_original(self) -> None:
        damaged = bytearray(self.source.read_bytes())
        damaged[n1save.MAIN_BLOCK_OFFSET + n1save.CHECKSUM_OFFSET] ^= 0x55
        self.source.write_bytes(damaged)
        original = self.source.read_bytes()
        output = self.temp / "repaired.sav"

        code, _, stderr = run_cli(["repair", str(self.source), str(output)])
        self.assertEqual(code, 0, stderr)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertTrue(n1save.load_save(output).valid)

    def test_high_checksum_byte_is_validated_and_repaired(self) -> None:
        damaged = bytearray(self.source.read_bytes())
        checksum_high = (
            n1save.MAIN_BLOCK_OFFSET + n1save.CHECKSUM_OFFSET + 1
        )
        damaged[checksum_high] ^= 0x40
        self.source.write_bytes(damaged)
        self.assertFalse(n1save.load_save(self.source).main.checksum_valid)

        output = self.temp / "high-byte-repaired.sav"
        code, _, stderr = run_cli(["repair", str(self.source), str(output)])
        self.assertEqual(code, 0, stderr)
        self.assertTrue(n1save.load_save(output).main.checksum_valid)

    def test_repair_rejects_damaged_payload_length(self) -> None:
        damaged = bytearray(self.source.read_bytes())
        damaged[
            n1save.MAIN_BLOCK_OFFSET + n1save.PAYLOAD_LENGTH_OFFSET
        ] ^= 0x01
        self.source.write_bytes(damaged)
        output = self.temp / "must-not-exist.sav"

        code, _, stderr = run_cli(["repair", str(self.source), str(output)])
        self.assertEqual(code, 2)
        self.assertIn("payload length", stderr)
        self.assertFalse(output.exists())

    def test_repair_rejects_in_place_and_existing_output(self) -> None:
        code, _, stderr = run_cli(["repair", str(self.source), str(self.source)])
        self.assertEqual(code, 2)
        self.assertIn("in-place", stderr)

        existing = self.temp / "existing.sav"
        existing.write_bytes(b"keep me")
        code, _, stderr = run_cli(["repair", str(self.source), str(existing)])
        self.assertEqual(code, 2)
        self.assertIn("already exists", stderr)
        self.assertEqual(existing.read_bytes(), b"keep me")

    def test_clone_main_to_redundant_copy(self) -> None:
        self.source.write_bytes(make_raw_save(main_marker=0x10, copy_marker=0x20))
        original = self.source.read_bytes()
        output = self.temp / "cloned.sav"

        code, _, stderr = run_cli(["clone", str(self.source), str(output)])
        self.assertEqual(code, 0, stderr)
        self.assertEqual(self.source.read_bytes(), original)
        result = n1save.load_save(output)
        self.assertTrue(result.valid)
        self.assertTrue(result.copies_identical)

    def test_clone_refuses_invalid_main_checksum(self) -> None:
        damaged = bytearray(self.source.read_bytes())
        damaged[n1save.MAIN_BLOCK_OFFSET + n1save.CHECKSUM_OFFSET] ^= 1
        self.source.write_bytes(damaged)
        output = self.temp / "must-not-exist.sav"

        code, _, stderr = run_cli(["clone", str(self.source), str(output)])
        self.assertEqual(code, 2)
        self.assertIn("invalid main block", stderr)
        self.assertFalse(output.exists())

    def test_export_bizhawk_ieeprom_container(self) -> None:
        raw = self.source.read_bytes()
        ieeprom = bytes((index * 7) & 0xFF for index in range(n1save.BIZHAWK_IEEPROM_SIZE))
        container = self.temp / "game.SaveRAM"
        container.write_bytes(ieeprom + raw)
        original = container.read_bytes()
        output = self.temp / "exported.sav"

        code, stdout, stderr = run_cli(
            ["export-bizhawk", str(container), str(output)]
        )
        self.assertEqual(code, 0, stderr)
        self.assertIn("32768", stdout)
        self.assertEqual(output.read_bytes(), raw)
        self.assertEqual(container.read_bytes(), original)

    def test_export_rejects_raw_sram(self) -> None:
        output = self.temp / "exported.sav"
        code, _, stderr = run_cli(
            ["export-bizhawk", str(self.source), str(output)]
        )
        self.assertEqual(code, 2)
        self.assertIn("33792-byte", stderr)
        self.assertFalse(output.exists())

    def test_diff_reports_bytes_and_returns_conventional_status(self) -> None:
        other = self.temp / "other.sav"
        other.write_bytes(make_raw_save(main_marker=0x44, copy_marker=0x44))
        code, stdout, stderr = run_cli(
            ["diff", str(self.source), str(other), "--max-details", "8"]
        )
        self.assertEqual(code, 1)
        self.assertIn("differ", stdout)
        self.assertEqual(stderr, "")

        code, stdout, _ = run_cli(["diff", str(self.source), str(self.source)])
        self.assertEqual(code, 0)
        self.assertIn("identical", stdout)

    def test_rejects_unknown_sizes_and_ambiguous_32k_files(self) -> None:
        wrong_size = self.temp / "wrong.sav"
        wrong_size.write_bytes(bytes(n1save.SRAM_SIZE + 1))
        code, _, stderr = run_cli(["info", str(wrong_size)])
        self.assertEqual(code, 2)
        self.assertIn("ambiguous size", stderr)

        ambiguous = self.temp / "gba-or-blank.sav"
        ambiguous.write_bytes(bytes(n1save.SRAM_SIZE))
        code, _, stderr = run_cli(["info", str(ambiguous)])
        self.assertEqual(code, 2)
        self.assertIn("ambiguous format", stderr)

    def test_diff_can_compare_raw_with_bizhawk_container(self) -> None:
        container = self.temp / "same.SaveRAM"
        container.write_bytes(bytes(n1save.BIZHAWK_IEEPROM_SIZE) + self.source.read_bytes())
        code, stdout, stderr = run_cli(
            ["diff", str(self.source), str(container)]
        )
        self.assertEqual(code, 0, stderr)
        self.assertIn("identical", stdout)


WORKSPACE_SAVE_ROOT = PROJECT_ROOT.parent / "v03_wsc_progress"
WORKSPACE_SAVES = (
    sorted(WORKSPACE_SAVE_ROOT.glob("*/Mesen2/Saves/*.sav"))
    if WORKSPACE_SAVE_ROOT.is_dir()
    else []
)


ARCHIVED_QA08_SAVE = PROJECT_ROOT / "evidence/qa08/persistence/winner.srm"
ARCHIVED_QA08_COLD = PROJECT_ROOT / "evidence/qa08/persistence/winner_cold.srm"
ARCHIVED_QA08_SHA256 = "4b32fc51fb77d9947d047c8e6babdaf55e24c33f71a06f3cee1530b3d5102910"


class ExistingWorkspaceSaveTest(unittest.TestCase):
    def test_a_recognized_existing_save_via_temporary_copy(self) -> None:
        # The cumulative release carries a known real QA08 save. Do not skip
        # real-save validation solely because an old developer folder is absent.
        candidates = [ARCHIVED_QA08_SAVE, *WORKSPACE_SAVES]
        recognized = None
        for candidate in candidates:
            try:
                image = n1save.load_save(candidate)
            except n1save.SaveToolError:
                continue
            if image.valid:
                recognized = candidate
                break
        if recognized is None:
            self.skipTest("PRIVATE_FIXTURE_NOT_DISTRIBUTED: archived natural QA08 SRAM is intentionally excluded from GitHub; synthetic N1Save tests remain active")
        if recognized == ARCHIVED_QA08_SAVE:
            self.assertEqual(hashlib.sha256(recognized.read_bytes()).hexdigest(), ARCHIVED_QA08_SHA256)
            self.assertEqual(recognized.read_bytes(), ARCHIVED_QA08_COLD.read_bytes())

        with tempfile.TemporaryDirectory(prefix="n1save-real-copy-") as directory:
            copied = Path(directory) / "existing-copy.sav"
            shutil.copy2(recognized, copied)
            image = n1save.load_save(copied)
            self.assertTrue(image.valid)
            self.assertEqual(len(image.sram), n1save.SRAM_SIZE)


if __name__ == "__main__":
    unittest.main()
