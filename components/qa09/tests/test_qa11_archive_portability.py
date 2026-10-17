"""Negative tests: mode-only drift is repairable, never disguise changed bytes."""
import sys
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from qa11_archive_portability import classify_drift


def entry(sha='a'*64, executable=True):
    return {'kind': 'file', 'sha256': sha, 'size': 10, 'executable': executable}


class PortableArchiveTests(unittest.TestCase):
    def test_mode_only_drift_is_distinguished_from_content(self):
        before = {'libretro.so': entry()}
        after = {'libretro.so': entry(executable=False)}
        delta, mode_only, material = classify_drift(before, after)
        self.assertEqual(delta['changed'], ['libretro.so'])
        self.assertEqual(mode_only, ['libretro.so'])
        self.assertFalse(material)

    def test_content_drift_is_not_repairable(self):
        before = {'libretro.so': entry()}
        after = {'libretro.so': entry(sha='b'*64, executable=False)}
        _, mode_only, material = classify_drift(before, after)
        self.assertFalse(mode_only)
        self.assertEqual(material, ['libretro.so'])

    def test_missing_or_added_files_are_not_mode_drift(self):
        delta, modes, material = classify_drift({'a': entry()}, {'b': entry()})
        self.assertEqual(delta['added'], ['b'])
        self.assertEqual(delta['removed'], ['a'])
        self.assertFalse(modes)
        self.assertFalse(material)


if __name__ == '__main__':
    unittest.main()
