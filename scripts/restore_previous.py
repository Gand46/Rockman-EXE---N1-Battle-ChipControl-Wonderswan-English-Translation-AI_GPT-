#!/usr/bin/env python3
"""Restore the predecessor source tree into a NEW directory using the migration ledger.

The active repository is never changed. The companion archive supplies exact
pre-migration bytes for changed/retired files; unchanged files come from here.
"""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import os
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]

def restore(history: Path, output: Path) -> dict:
    output=output.resolve()
    if output.exists():raise ValueError('Output must be a new, nonexistent directory')
    if output.is_relative_to(ROOT):raise ValueError('Restore outside the active source repository')
    data=json.loads((ROOT/'maintenance/migration.json').read_text(encoding='utf-8'))
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(history) as z, tempfile.TemporaryDirectory(prefix='n1-restore-',dir=output.parent) as tmp:
        stage=Path(tmp)/'source';stage.mkdir()
        for row in data['entries']:
            rel=PurePosixPath(row['original'])
            if rel.is_absolute() or '..' in rel.parts or '\\' in str(rel):raise ValueError('Unsafe historical path')
            if row.get('archive_path'):
                raw=z.read('Rockman_N1_History/'+row['archive_path'])
            else:
                p=(ROOT/row['repository_path']).resolve()
                if not p.is_relative_to(ROOT):raise ValueError('Unsafe current-source path')
                raw=p.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=row['original_sha256']:raise ValueError('Original hash mismatch: '+str(rel))
            p=stage/str(rel);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
            if os.name!='nt':p.chmod(row.get('original_mode') or 0o644)
        if output.exists():raise ValueError('Output was created while restoring; refusing replacement')
        stage.rename(output)
    return {'status':'PASS','restored_files':len(data['entries']),'output':str(output),'active_repository_unchanged':True}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--history',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:result=restore(a.history,a.output)
    except (OSError,ValueError,KeyError,zipfile.BadZipFile) as e:p.exit(1,'FAIL: '+str(e)+'\n')
    print(json.dumps(result,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
