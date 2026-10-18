#!/usr/bin/env python3
"""Build cumulative MANT05 variants from the verified original and editable sources.

The previous MANT04 output is reconstructed in this invocation. Independent UI
editors receive that same verified preimage; their disjoint writes are merged
before the independently authenticated RC6 delta is carried onto the result.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import project
import build_mant04
import qa14_shop
import qa14_menu
import qa14_chipcontrol

ROOT = Path(__file__).resolve().parents[1]
PREDECESSOR_EN = 'e9fcfec134135c2f129da79d20b8f42ec4e7b7051e4b3b927036731041418800'

def merge_editors(original: bytes, predecessor: bytes):
    project.require(project.sha(predecessor)==PREDECESSOR_EN, 'Expected verified MANT04 English preimage')
    output=bytearray(predecessor); owners={}; modules={}
    for name, editor in [('menu',qa14_menu),('shop',qa14_shop)]:
        candidate,report=editor.apply(original,predecessor)
        project.require(len(candidate)==len(predecessor),'UI editor changed ROM size')
        changed={i for i,(a,b) in enumerate(zip(predecessor[:-2],candidate[:-2])) if a!=b}
        conflicts=changed & owners.keys()
        project.require(not conflicts,f'UI editor overlaps prior writes: {name}: {sorted(conflicts)[:10]}')
        for i in changed: output[i]=candidate[i]; owners[i]=name
        modules[name]={'report':report,'changed_bytes':len(changed),'changed_offsets':sorted(changed)}
    output[-2:]=(sum(output[:-2])&65535).to_bytes(2,'little')
    actual={i for i,(a,b) in enumerate(zip(predecessor[:-2],output[:-2])) if a!=b}
    project.require(actual==set(owners),'Unexpected merged modification')
    project.require(output[0x340310:0x348310]==predecessor[0x340310:0x348310], 'Shared native font bank changed')
    return bytes(output),{'modules':modules,'changed_nonchecksum_bytes':len(actual),
                         'unexpected_changes':0,'editor_overlap_bytes':0,'shared_font_bank_unchanged':True}

def build_release(source:Path,variant='all',output:Path|None=None,development=False):
    project.require(variant in ('qa09','chip-control','all'),'Invalid variant')
    original=project.original(source)
    out=project.output_guard(output or ROOT/'build/mant05',source)
    targets=['qa09','chip-control'] if variant=='all' else [variant]
    needs_rc6='chip-control' in targets
    previous=build_mant04.build_release(source,'all' if needs_rc6 else 'qa09',ROOT/'build/mant04')
    base=Path(previous['variants']['qa09']['rom_path']).read_bytes()
    english,edits=merge_editors(original,base)
    outputs={'qa09':english}; compatibility=None
    if needs_rc6:
        prior_rc6=Path(previous['variants']['chip-control']['rom_path']).read_bytes()
        outputs['chip-control'],compatibility=qa14_chipcontrol.apply(base,prior_rc6,english)
    n1,make_bps,apply_bps=project.qa_modules()
    artifacts={}; out.mkdir(parents=True,exist_ok=True)
    for key in targets:
        data=outputs[key]; patch=make_bps(original,data)
        project.require(apply_bps(original,patch)==data,f'{key}: cumulative BPS roundtrip failed')
        stored,calculated=n1.checksum(data)
        project.require(stored==calculated,f'{key}: WonderSwan checksum mismatch')
        name='Rockman_N1_English_QA09_MANT05' if key=='qa09' else 'Rockman_N1_English_QA09_ChipControl_RC6_MANT05_EXPERIMENTAL'
        target=out/key;target.mkdir(parents=True,exist_ok=True)
        rp=target/(name+'.wsc');pp=target/(name+'.bps')
        if not development:
            expected=project.config()['current']['variants'][key]
            project.require(project.sha(data)==expected['rom_sha256'] and project.sha(patch)==expected['bps_sha256'],
                            f'{key}: current release fingerprint mismatch; inspect intentional edits with --allow-modified')
            project.require((ROOT/expected['patch']).read_bytes()==patch,f'{key}: published BPS mismatch')
        rp.write_bytes(data);pp.write_bytes(patch)
        artifacts[key]={'rom_path':str(rp),'bps_path':str(pp),'rom_sha256':project.sha(data),
                        'bps_sha256':project.sha(patch),'rom_bytes':len(data),'bps_bytes':len(patch),
                        'checksum':f'0x{stored:04X}','runtime_tested_by_builder':False,
                        'status':'DEVELOPMENT_CANDIDATE' if development else 'PASS_EXACT_REBUILD'}
    project.require(project.sha(source.read_bytes())==project.sha(original),'Original ROM was modified')
    manifest={'status':'BUILT_DEVELOPMENT_CANDIDATE' if development else 'PASS_REPRODUCIBLE_SCOPE',
              'source_sha256':project.sha(original),'predecessor_sha256':PREDECESSOR_EN,
              'variants':artifacts,'ui_edits':edits,'chip_control':compatibility,
              'optional_rc6_required':needs_rc6,'source_unchanged':True,'runtime_tested_by_this_script':False}
    project.json_write(out/'build_manifest.json',manifest)
    return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--variant',choices=('qa09','chip-control','all'),default='all')
    p.add_argument('--output',type=Path);p.add_argument('--development',action='store_true')
    a=p.parse_args();r=build_release(a.source,a.variant,a.output,a.development)
    print(json.dumps({k:r[k] for k in ('status','variants','optional_rc6_required')},indent=2))
