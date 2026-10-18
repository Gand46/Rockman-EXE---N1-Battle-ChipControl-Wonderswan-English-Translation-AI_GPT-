#!/usr/bin/env python3
"""Account for every file in the authenticated MANT04 source predecessor.

Unchanged files stay in place, old player patches have explicit moved paths,
and original bytes of revised files are retained in a compact companion archive
inside the new sources. The new integrity inventory cannot include its own hash.
"""
from __future__ import annotations
import argparse, hashlib, json, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PARENT_SHA='231290f82c161f0e94018e1a27376a5c1d5e54e2215f4bed8e636bc456ad68a1'

def sha(data): return hashlib.sha256(data).hexdigest()

def run(parent):
    assert sha(parent.read_bytes())==PARENT_SHA,'Wrong MANT04 source package'
    archive=ROOT/'maintenance/mant04-originals.zip'
    report_path=ROOT/'maintenance/qa14-inheritance.json'
    preserved={};records=[]
    with zipfile.ZipFile(parent) as z:
        for info in sorted(z.infolist(),key=lambda v:v.filename):
            if info.is_dir():continue
            assert info.filename.startswith('Rockman_N1/')
            rel=info.filename[len('Rockman_N1/'):]
            assert not Path(rel).is_absolute() and '..' not in Path(rel).parts
            original=z.read(info);oldsha=sha(original);current=ROOT/rel
            rec={'original_path':rel,'original_sha256':oldsha,'original_bytes':len(original)}
            if rel=='maintenance/source-manifest.json':
                preserved[rel]=original
                rec.update({'status':'REPLACED_INTEGRITY_INVENTORY','original_in_archive':rel,
                    'current_hash_note':'The new inventory is sealed after this ledger; including its hash here would create a cycle.'})
            elif current.is_file() and current.read_bytes()==original:
                rec.update({'status':'UNCHANGED','current_path':rel,'current_sha256':oldsha})
            elif rel.startswith('patches/') and rel.endswith('.bps'):
                moved=ROOT/'maintenance/mant04-patches'/Path(rel).name
                assert moved.is_file() and moved.read_bytes()==original,f'Missing moved predecessor patch: {rel}'
                rec.update({'status':'MOVED_UNCHANGED','current_path':moved.relative_to(ROOT).as_posix(),'current_sha256':oldsha})
            else:
                assert current.is_file(),f'Unaccounted deletion: {rel}'
                preserved[rel]=original
                rec.update({'status':'REVISED_ORIGINAL_RETAINED','current_path':rel,
                    'current_sha256':sha(current.read_bytes()),'original_in_archive':rel})
            records.append(rec)
    archive.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for rel,data in sorted(preserved.items()):
            info=zipfile.ZipInfo(rel,(2026,10,17,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.create_system=3;info.external_attr=0o100644<<16;z.writestr(info,data)
    # Independently read each retention destination, not the in-memory input.
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for rec in records:
            data=z.read(rec['original_in_archive']) if 'original_in_archive' in rec else (ROOT/rec['current_path']).read_bytes()
            assert sha(data)==rec['original_sha256'],rec['original_path']
    report={'schema':1,'status':'PASS_ALL_PREDECESSOR_FILES_RETAINED',
        'predecessor_package':parent.name,'predecessor_package_sha256':PARENT_SHA,
        'original_files':len(records),'unaccounted_original_files':0,
        'counts':{s:sum(r['status']==s for r in records) for s in sorted({r['status'] for r in records})},
        'preserved_originals_archive':archive.relative_to(ROOT).as_posix(),
        'preserved_originals_archive_sha256':sha(archive.read_bytes()),
        'reconstruction_requires_predecessor_zip':False,'files':records}
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return {k:v for k,v in report.items() if k!='files'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--predecessor-zip',type=Path,required=True)
    print(json.dumps(run(p.parse_args().predecessor_zip),indent=2))
