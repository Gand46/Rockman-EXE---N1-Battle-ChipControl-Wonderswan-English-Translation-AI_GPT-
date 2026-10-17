"""Audit wrapper should never report success after incomplete or skipped checks."""
import sys
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from qa11_independent_audit import complete_unittest_log

class AuditRunnerChecks(unittest.TestCase):
    def test_existing_and_extended_suites(self):
        self.assertTrue(complete_unittest_log('Ran 64 tests in 0.2s\n\nOK\n'))
        self.assertTrue(complete_unittest_log('Ran 68 tests in 0.2s\n\nOK\n'))
    def test_skip_and_failure_cannot_pass(self):
        self.assertFalse(complete_unittest_log('Ran 67 tests in 0.2s\n\nOK (skipped=2)\n'))
        self.assertFalse(complete_unittest_log('Ran 68 tests in 0.2s\n\nFAILED (failures=1)\n'))
        self.assertFalse(complete_unittest_log('Ran 12 tests in 0.2s\n\nOK\n'))

if __name__=='__main__':
    unittest.main()
