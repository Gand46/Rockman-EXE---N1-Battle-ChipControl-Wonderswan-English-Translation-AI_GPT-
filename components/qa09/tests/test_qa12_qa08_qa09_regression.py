"""Independent QA08 -> QA09 scope gates. Requires verified user-owned JP ROM.

To avoid assuming a prior conversation, use CONTINUITY_INPUT_JP=original.wsc.
"""
import os
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import qa12_compare_qa08_qa09 as a


class QA12ScopedRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=os.environ.get('CONTINUITY_INPUT_JP')
        if not source:
            raise unittest.SkipTest('CONTINUITY_INPUT_JP missing')
        cls.src=Path(source).read_bytes()
        if a.digest(cls.src)!=a.JP_SHA:
            raise AssertionError('Unexpected Japanese base ROM SHA256')
        cls.bps8=(ROOT/'tests/fixtures/patches/Rockman_N1_English_QA08.bps').read_bytes()
        cls.bps9=(ROOT/'../../maintenance/baseline-patches/Rockman_N1_English_QA09.bps').read_bytes()
        cls.rom8=a.apply_bps_independent(cls.src,cls.bps8)
        cls.rom9=a.apply_bps_independent(cls.src,cls.bps9)

    def test_01_bps_and_rom_hashes(self):
        self.assertEqual(a.digest(self.bps8),a.QA08_BPS_SHA)
        self.assertEqual(a.digest(self.bps9),a.QA09_BPS_SHA)
        self.assertEqual(a.digest(self.rom8),a.QA08_SHA)
        self.assertEqual(a.digest(self.rom9),a.QA09_SHA)

    def test_02_exact_binary_delta(self):
        result=a.compare_rom_bytes(self.rom8,self.rom9)
        self.assertEqual(result['different_bytes'],72)
        self.assertEqual(result['unexpected_changed_offsets'],0)

    def test_03_all_249_description_consumers(self):
        result=a.source_semantics(self.rom8,self.rom9)
        self.assertEqual(result['changed_rows'],[175])
        self.assertEqual(result['rows_identical'],248)
        self.assertEqual(result['shared_text_bytes_modified'],0)

    def test_04_reject_unlisted_rom_change(self):
        modified=bytearray(self.rom9)
        modified[0x100]=modified[0x100]^1
        with self.assertRaisesRegex(AssertionError,'Unexpected byte difference'):
            a.compare_rom_bytes(self.rom8,bytes(modified))

    def test_05_reject_bps_crc_tamper(self):
        modified=bytearray(self.bps9)
        modified[14]^=1
        with self.assertRaisesRegex(AssertionError,'CRC mismatch'):
            a.apply_bps_independent(self.src,bytes(modified))

    def test_06_reject_wrong_base(self):
        modified=bytearray(self.src)
        modified[111]^=1
        with self.assertRaisesRegex(AssertionError,'CRC mismatch'):
            a.apply_bps_independent(bytes(modified),self.bps9)

if __name__=='__main__':unittest.main()
