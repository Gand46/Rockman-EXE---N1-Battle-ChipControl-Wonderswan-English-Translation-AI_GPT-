#!/usr/bin/env python3
"""Rebuild QA09 and independently re-run scoped tests and emulator comparisons.

No work is silently inherited as a freshly executed test. Every pass is from
this invocation, while the archived observations remain historical evidence.
ROM files stay local, in the excluded build/ directory.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
JP = '4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed'
QA08 = '41d7fc75e327ad15b72c7f6fc7119e031d6af8cfdb1527eb547b3c86d7cc32dc'
QA09 = 'd729823bbe6cf9132e6345ed734eb2dbe51885c13d5a17a44a9f7cfae086c326'
BPS = '4fbfce1dcf2d0da714b936874167219e05076ad8ac40db0e43bb214eb063b0f2'
CASES = ['guard_fire_native', 'pierce_shield', 'master_title']


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def run(argv: list[str], env: dict, log_dir: Path, name: str, timeout: int) -> dict:
    path = log_dir / (name + '.log')
    try:
        with path.open('wb') as stream:
            proc = subprocess.run(argv, cwd=ROOT, env=env, stdout=stream,
                                  stderr=subprocess.STDOUT, timeout=timeout)
        return {'step': name, 'status': 'PASS' if proc.returncode == 0 else 'FAIL',
                'returncode': proc.returncode, 'log': str(path.relative_to(ROOT))}
    except subprocess.TimeoutExpired as exc:
        return {'step': name, 'status': 'TIMEOUT', 'timeout_seconds': timeout,
                'error': str(exc), 'log': str(path.relative_to(ROOT))}


def complete_unittest_log(log: str, minimum: int = 64) -> bool:
    """Reject skipped/partial suites, accept future additions to the test suite."""
    match = re.search(r'Ran (\d+) tests? in ', log)
    return bool(match and int(match.group(1)) >= minimum
                and 'skipped=' not in log and re.search(r'(?m)^OK\s*$', log))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', type=Path, required=True, help='User-owned original Japanese .wsc (SHA-256 validated)')
    ap.add_argument('--runtime', action='store_true', help='Run emulator replays (Linux x86_64 libretro core only)')
    ap.add_argument('--cases', nargs='+', choices=CASES, default=CASES,
                    help='Select one or more independent runtime routes; recommend one per invocation')
    ap.add_argument('--out', type=Path, default=ROOT / 'evidence/qa11/independent_audit.json')
    args = ap.parse_args()
    source = args.source.resolve()
    output = args.out.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    logs = ROOT / 'build/qa11_audit_logs'
    logs.mkdir(parents=True, exist_ok=True)
    report = {
        'scope': 'QA09 tools and deterministic build; synthetic comparison only, no exhaustive organic-play/hardware claims',
        'start_utc': datetime.now(timezone.utc).isoformat(),
        'platform': platform.platform(),
        'runtime_requested': args.runtime,
        'source_sha256': digest(source) if source.is_file() else None,
        'expected_source_sha256': JP,
        'steps': [],
        'expected_rom_sha256': QA09,
        'expected_bps_sha256': BPS,
        'expected_parent_sha256': QA08,
    }
    report['status'] = 'IN_PROGRESS'
    def persist():
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf8')
    persist()
    if report['source_sha256'] != JP:
        report.update(status='FAIL_WRONG_OR_MISSING_JP', end_utc=datetime.now(timezone.utc).isoformat())
        output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
        print(json.dumps({'status': report['status'], 'report': str(output)}))
        return 2
    env = dict(os.environ, CONTINUITY_INPUT_JP=str(source), PYTHONDONTWRITEBYTECODE='1')
    def step(name: str, args_: list[str], timeout: int):
        row = run([sys.executable, *args_], env, logs, name, timeout)
        report['steps'].append(row)
        persist()  # Checkpoint every completed stage; never claim interrupted work passed.
        return row['status'] == 'PASS'

    if step('build', ['src/build_qa09.py', '--source', str(source)], 240):
        paths = {
            'rom': (ROOT / 'build/qa09/Rockman_N1_English_QA09.wsc', QA09),
            'bps': (ROOT / 'build/qa09/Rockman_N1_English_QA09.bps', BPS),
            'parent': (ROOT / 'build/qa09/qa08_base/Rockman_N1_English_QA08.wsc', QA08),
            'published_bps': (ROOT / '../../maintenance/baseline-patches/Rockman_N1_English_QA09.bps', BPS),
        }
        report['artifacts'] = {k: {'sha256': digest(p) if p.is_file() else None, 'expected': sha}
                               for k, (p, sha) in paths.items()}
        report['steps'].append({'step': 'artifact_hashes', 'status': 'PASS' if all(
            report['artifacts'][k]['sha256'] == sha for k, (_, sha) in paths.items()
        ) else 'FAIL'})
        persist()
        step('validate', ['src/validate_qa09.py'], 90)
        step('ending', ['src/qa09_ending_verify.py'], 90)
        # Prevent skipped tests from counting as PASS: -v output inspected below.
        if step('unit_tests', ['-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py', '-v'], 120):
            log = (logs / 'unit_tests.log').read_text(errors='replace')
            if not complete_unittest_log(log):
                report['steps'][-1]['status'] = 'FAIL_INCOMPLETE_TESTS'
                persist()
        if args.runtime:
            if sys.platform != 'linux' or platform.machine() not in ('x86_64', 'AMD64'):
                report['steps'].append({'step': 'runtime', 'status': 'UNSUPPORTED_PLATFORM',
                                        'reason': 'Bundled libretro binary is Linux x86_64'})
                persist()
            else:
                outputs = []
                for case in args.cases:
                    dest = ROOT / 'build/qa11_audit_logs' / f'runtime_{case}.json'
                    if step('runtime_' + case, ['src/qa10_replay_compare.py', '--cases', case, '--out', str(dest)], 240):
                        payload = json.loads(dest.read_text())
                        outputs.append(payload)
                        if payload['status'] != 'PASS_SYNTHETIC_REGRESSION' or payload['total_changed_pixels'] != 0 or payload['total_changed_wram_bytes'] != 0:
                            report['steps'][-1]['status'] = 'FAIL_RUNTIME_DIFFERENCE'
                            persist()
                report['runtime'] = {'cases': [c['case'] for result in outputs for c in result['cases']],
                                     'frames': sum(result['total_compared_frames'] for result in outputs),
                                     'changed_pixels': sum(result['total_changed_pixels'] for result in outputs),
                                     'changed_wram_bytes': sum(result['total_changed_wram_bytes'] for result in outputs)}
                persist()
    report['status'] = 'PASS' if all(s['status'] == 'PASS' for s in report['steps']) else 'FAIL_OR_UNSUPPORTED'
    report['end_utc'] = datetime.now(timezone.utc).isoformat()
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf8')
    print(json.dumps({'status': report['status'], 'steps': len(report['steps']), 'report': str(output),
                      'runtime': report.get('runtime', 'NOT_REQUESTED')}, ensure_ascii=False))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
