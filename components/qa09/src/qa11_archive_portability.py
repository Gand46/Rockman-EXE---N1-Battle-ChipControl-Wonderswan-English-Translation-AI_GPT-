#!/usr/bin/env python3
"""Audit a separately extracted QA09 archive and optionally repair mode-only drift.

Python's zipfile.extractall() does not restore POSIX executable bits. The
continuity snapshot *does* record those bits. This tool never ignores changes
in bytes, missing sources, symlinks or unexpected files; it only repairs an
explicitly identified executable-bit mismatch after comparing every source.

Preferred extraction: continuity.py restore ARCHIVE NEW_DIR --sha256 HASH.
Use this tool for existing extractions made with unzip programs that did not
preserve POSIX modes. Nothing is modified without --repair.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys

from continuity import config_for, differences, head_for, inventory, verify


def classify_drift(expected: dict, observed: dict) -> tuple[dict, list[str], list[str]]:
    """Separate benign (only executable bit) from material content changes."""
    delta = differences(expected, observed)
    mode_only: list[str] = []
    material: list[str] = []
    for rel in delta['changed']:
        a, b = expected[rel], observed[rel]
        if (a.get('kind') == b.get('kind') == 'file'
                and {k: v for k, v in a.items() if k != 'executable'}
                   == {k: v for k, v in b.items() if k != 'executable'}
                and a.get('executable') != b.get('executable')):
            mode_only.append(rel)
        else:
            material.append(rel)
    return delta, mode_only, material


def audit(root: Path, repair: bool = False) -> dict:
    root = root.resolve()
    _, head = head_for(root)
    expected = head['files']
    observed = inventory(root, config_for(root))
    delta, mode_only, material = classify_drift(expected, observed)
    if delta['added'] or delta['removed'] or material:
        return {'status': 'FAIL_SOURCE_DRIFT', 'snapshot_id': head['snapshot_id'],
                'added': delta['added'], 'removed': delta['removed'],
                'content_changed': material, 'mode_only': mode_only, 'repaired': []}
    if mode_only and not repair:
        return {'status': 'PERMISSIONS_NEED_REPAIR', 'snapshot_id': head['snapshot_id'],
                'mode_only': mode_only, 'repaired': [],
                'hint': 'Run again with --repair after validating your archive provenance.'}
    repaired = []
    if repair:
        for rel in mode_only:
            path = root / rel
            if path.is_symlink() or not path.is_file():
                raise RuntimeError(f'Unsafe source type after inventory: {rel}')
            # Recheck bytes immediately before editing metadata (TOCTOU guard).
            from continuity import file_hash
            if file_hash(path) != expected[rel]['sha256']:
                raise RuntimeError(f'Content changed during repair: {rel}')
            mode = stat.S_IMODE(path.stat().st_mode)
            target = (mode & ~0o111) | (0o111 if expected[rel]['executable'] else 0)
            path.chmod(target)
            repaired.append(rel)
    result = verify(root, head['snapshot_id'])
    return {'status': 'PASS', 'snapshot_id': head['snapshot_id'],
            'source_files': result['files'], 'mode_only': mode_only, 'repaired': repaired,
            'byte_modifications': 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--repair', action='store_true', help='Restore executable bits only; no file content edits')
    args = parser.parse_args()
    try:
        report = audit(args.root, args.repair)
    except Exception as exc:
        report = {'status': 'FAIL', 'error': str(exc)}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report['status'] == 'PASS' else 2


if __name__ == '__main__':
    sys.exit(main())
