#!/usr/bin/env python3
"""Reproduce both MANT04 ROM variants/BPS from one verified Japanese ROM.

QA09 remains the base; Chip Control is opt-in and experimental. The baseline
rebuild is *always* performed from the editable QA09 manifest plus pinned RC6
IPS. The only changes subsequently allowed are the QA13 graphic tiles/maps,
and the WonderSwan checksum. No commercial ROM is distributed.
"""
from __future__ import annotations
import argparse, json, hashlib, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import project, qa13_visual_repair as visual

BASE_CK='d729823bbe6cf9132e6345ed734eb2dbe51885c13d5a17a44a9f7cfae086c326'
RC6_CK='1fec1a21d486fe30931053181810e2d9f82d573c5ece5dae23e1416b060de57e'

def build_release(source:Path,variant:str='all',output:Path|None=None, publish_bps:bool=False):
    args=argparse.Namespace(source=source, output=output or ROOT/'build/mant04', publish_bps=publish_bps)
    return run(args, variant)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True,help='Verified original Japanese 4MiB ROM')
    p.add_argument('--output',type=Path,default=ROOT/'build/mant04',help='Output directory')
    p.add_argument('--publish-bps',action='store_true',help='Install generated patches in patches/ after validation')
    args=p.parse_args()
    print(json.dumps(run(args, "all"),ensure_ascii=False,indent=2))

def run(args, variant="all"):
    visual.ensure(variant in ("qa09", "chip-control", "all"), "invalid variant")
    targets=["qa09", "chip-control"] if variant=="all" else [variant]
    # Do not require RC6/IPSes to build the plain QA09 localization: optional
    # components must remain optional even during a clean reconstruction.
    needs_rc6="chip-control" in targets
    original=project.original(args.source)
    baseout=ROOT/'build/mant04/original_rebuild'
    records=project.build(args.source,'all' if needs_rc6 else 'qa09',baseout)
    base=Path(records['variants']['qa09']['rom']).read_bytes()
    visual.ensure(visual.digest(base)==BASE_CK,'wrong historical QA09 output')
    qa,new_report=visual.apply(base)
    changed={i for i,(a,b) in enumerate(zip(base,qa)) if a!=b and i<len(qa)-2}
    n1,make_bps,apply_bps=project.qa_modules()
    outputs={'qa09':qa}
    old_rc6=None
    if needs_rc6:
        old_rc6=Path(records['variants']['chip-control']['rom']).read_bytes()
        visual.ensure(visual.digest(old_rc6)==RC6_CK,'wrong experimental RC6 baseline output')
        conflicts=[hex(i) for i in sorted(changed) if base[i]!=old_rc6[i]]
        visual.ensure(not conflicts,f'RC6 conflicts at {conflicts[:10]}')
        combined=bytearray(old_rc6)
        for i in changed:combined[i]=qa[i]
        combined[-2:]=(sum(combined[:-2])&0xffff).to_bytes(2,'little')
        outputs['chip-control']=bytes(combined)
        modified={i for i,(a,b) in enumerate(zip(old_rc6,outputs['chip-control'])) if a!=b and i<len(old_rc6)-2}
        visual.ensure(modified==changed,'RC6 graphics delta differs from QA09 graphics delta')
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    artifacts={}
    for key in targets:
        data=outputs[key]
        p=make_bps(original,data)
        visual.ensure(apply_bps(original,p)==data,f'{key} BPS failed roundtrip')
        actual,calculated=n1.checksum(data)
        visual.ensure(actual==calculated,f'{key} invalid WonderSwan checksum')
        name='Rockman_N1_English_QA09_MANT04' if key=='qa09' else 'Rockman_N1_English_QA09_ChipControl_RC6_MANT04_EXPERIMENTAL'
        directory=out/key;directory.mkdir(parents=True,exist_ok=True)
        rp=directory/(name+'.wsc');pp=directory/(name+'.bps')
        rp.write_bytes(data);pp.write_bytes(p)
        artifacts[key]={'rom_sha256':visual.digest(data),'bps_sha256':visual.digest(p),
            'checksum':f'0x{actual:04X}','rom_bytes':len(data),'bps_bytes':len(p),
            'bps_path':str(pp),'rom_path':str(rp),
            'status':'EXPERIMENTAL' if key=='chip-control' else 'MANT04'}
        release_config=project.config()
        expected=release_config.get('predecessor',release_config['current'])['variants'][key]
        visual.ensure(artifacts[key]['rom_sha256']==expected['rom_sha256'] and
                      artifacts[key]['bps_sha256']==expected['bps_sha256'],
                      f'Pinned MANT04 {key} identity mismatch')
        visual.ensure((ROOT/expected['patch']).read_bytes()==p,
                      f'Published MANT04 patch mismatch {key}')
        if args.publish_bps:
            # Reproducibility gate has passed; the current published patch is
            # already byte-identical. Never replace it with an unpinned result.
            (ROOT/expected['patch']).write_bytes(p)
    public={'status':'PASS_BINARY_AND_REBUILD','baseline_qa09_sha256':BASE_CK,
        'baseline_chip_control_sha256':RC6_CK if needs_rc6 else 'NOT_USED',
        'changed_nonchecksum':len(changed),'outside_visual_allowlist':0,
        'chip_control_overlap_offsets':0 if needs_rc6 else 'NOT_APPLICABLE',
        'original_sha256':visual.digest(original),
        'visual_report':new_report,'artifacts':artifacts,
        'release_identity_check':'PASS','runtime_tested_by_this_script':False,
        'optional_vendor_required':needs_rc6}
    (out/'build_manifest.json').write_text(json.dumps(public,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'status':'PASS','variants':artifacts,'release_identity_check':'PASS',
            'binary_scope':new_report['status'], 'optional_vendor_required':needs_rc6}
if __name__=='__main__':main()
