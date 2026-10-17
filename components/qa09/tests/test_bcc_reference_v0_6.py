from __future__ import annotations

import importlib.util
import struct
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT_ROOT / "src" / "bcc_reference.py"
SPEC = importlib.util.spec_from_file_location("bcc_reference", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
bcc_reference = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bcc_reference
SPEC.loader.exec_module(bcc_reference)


class BccReferenceV06Tests(unittest.TestCase):
    def test_large_card_effect_labels_are_uppercase(self) -> None:
        self.assertEqual(
            bcc_reference.normalize_large_card_effect("Normal"), "NORMAL"
        )
        encode = {character: index + 1 for index, character in enumerate("NORMAL")}
        encoded = bcc_reference.encode_static("NORMAL", encode, style=0x0600)

        self.assertTrue(all((word & 0x0F00) == 0x0600 for word in encoded[:-1]))
        self.assertEqual(encoded[-1], 0x8006)

    def test_generic_navis_are_remapped_by_identity(self) -> None:
        operator_map = bcc_reference.WSC_TO_GBA_OPERATOR_INDEX
        attack_map = bcc_reference.WSC_TO_GBA_NAVI_ATTACK_INDEX

        self.assertEqual(len(operator_map), bcc_reference.WSC_OPERATOR_COUNT)
        self.assertEqual(len(attack_map), bcc_reference.WSC_NAVI_ATTACK_COUNT)
        self.assertEqual(operator_map[:44], tuple(range(44)))
        self.assertEqual(attack_map[:44], tuple(range(44)))
        self.assertEqual(operator_map[44:49], (45, 44, 47, 46, 48))
        self.assertEqual(attack_map[44:49], (45, 44, 47, 46, 48))
        self.assertEqual(operator_map[49:], tuple(range(49, 135)))

    def test_far_pointer_encoding_round_trips_nonzero_offsets(self) -> None:
        rom = bytearray(bcc_reference.WSC_SIZE)
        addresses = (0x300000, 0x367170, 0x367182, 0x3671A4, 0x3FFFFF)

        for index, address in enumerate(addresses):
            pointer = bcc_reference.encode_wsc_far_pointer(address)
            rom[index * 4 : index * 4 + 4] = pointer
            decoded = bcc_reference.wsc_pointer(
                rom, index * 4, 0, f"synthetic[{index}]"
            )
            self.assertEqual(decoded, address)

        low_nibbles = {
            struct.unpack("<HH", bcc_reference.encode_wsc_far_pointer(address))[0]
            for address in addresses[1:4]
        }
        self.assertEqual(low_nibbles, {0, 2, 4})

    def test_original_string_spans_merge_only_occupied_bytes(self) -> None:
        rom = bytearray(bcc_reference.WSC_SIZE)
        layout = bcc_reference.WscFarTable(
            "synthetic", 0x100, 4, 0x300100, 0x300130
        )
        targets = (0x300100, 0x300104, 0x300104, 0x300110)
        strings = {
            0x300100: (0x0001, 0x8001),
            0x300104: (0x0002, 0x0003, 0x8002),
            0x300110: (0x0004, 0x8001),
        }
        for index, target in enumerate(targets):
            bcc_reference.write_wsc_far_pointer(
                rom, layout.pointer_start + index * 4, target
            )
        for target, words in strings.items():
            rom[target : target + len(words) * 2] = struct.pack(
                f"<{len(words)}H", *words
            )

        self.assertEqual(
            bcc_reference.merged_original_string_spans(rom, layout),
            ((0x300100, 0x30010A), (0x300110, 0x300114)),
        )

    def test_best_fit_packer_is_deterministic_and_preserves_gaps(self) -> None:
        spans = ((0x10, 0x1A), (0x20, 0x2C))
        sequences = [
            (0x0011, 0x0012, 0x0013, 0x8003),
            (0x0021, 0x0022, 0x8002),
            (0x0031, 0x8001),
            (0x0011, 0x0012, 0x0013, 0x8003),
        ]
        first = bytearray(b"\xAA" * 0x40)
        second = bytearray(first)

        addresses, report = bcc_reference.pack_unique_best_fit(
            first, sequences, spans, "synthetic"
        )
        repeated_addresses, repeated_report = bcc_reference.pack_unique_best_fit(
            second, sequences, spans, "synthetic"
        )

        self.assertEqual(addresses, [0x10, 0x20, 0x26, 0x10])
        self.assertEqual(addresses, repeated_addresses)
        self.assertEqual(first, second)
        self.assertEqual(report, repeated_report)
        self.assertEqual(report["unique_sequence_count"], 3)
        self.assertEqual(report["used_bytes"], 18)
        self.assertEqual(report["capacity_bytes"], 22)
        self.assertEqual(report["free_bytes"], 4)
        self.assertEqual(first[0x1A:0x20], b"\xAA" * 6)

    def test_best_fit_packer_rejects_overflow(self) -> None:
        output = bytearray(16)
        with self.assertRaises(SystemExit):
            bcc_reference.pack_unique_best_fit(
                output,
                [(0x0001, 0x0002, 0x8002)],
                ((0, 4),),
                "synthetic",
            )


if __name__ == "__main__":
    unittest.main()
