#!/usr/bin/env python3
"""Independent QA08 -> QA09 scope / source-regression audit.

Pure standard-library BPS decoder (separate from tools/continuity.py and
from the ROM generator), followed by structural pointer/text verification
against the project's native decoding tables. Never modifies a ROM.

Private original ROM required. User may optionally point to both complete
source ZIPs to verify QA08 inheritance in the cumulative QA09 sources.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
JP_SHA = '4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed'
QA08_SHA = '41d7fc75e327ad15b72c7f6fc7119e031d6af8cfdb1527eb547b3c86d7cc32dc'
QA09_SHA = 'd729823bbe6cf9132e6345ed734eb2dbe51885c13d5a17a44a9f7cfae086c326'
QA08_BPS_SHA = '9ba0894b023f6f120c2b51fb14a120eec8079fedce3787bc092212d4b660ae05'
QA09_BPS_SHA = '4fbfce1dcf2d0da714b936874167219e05076ad8ac40db0e43bb214eb063b0f2'
NAV=(0x3577fe,0x3577fe+94)
DESC=(0x36a4e0,0x36a4e0+15592)
EXPECTED_COUNTS = {'host_navi_roster_full':31,'database_chip_descriptions':39,'rom_checksum':2}
OLD_NAVI='[PORTRAIT:04]Navi list full.[LINE]Delete old data,[LINE]then retry.'
NEW_NAVI='[PORTRAIT:04]Navi list full.[LINE]Use Delete for[LINE]unneeded data.'
GAIA_OLD=['Wood AccB Rnd100+ ﹡﹡﹡﹡﹡','Hit 1 chip+prior chip pwr']
GAIA_NEW=['Wood AccB Rnd100+ ﹡﹡﹡﹡﹡','Hit 1 chip+next chip pwr']

def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def checked(condition, message):
    if not condition:
        raise AssertionError(message)

def apply_bps_independent(source:bytes, patch:bytes)->bytes:
    checked(len(patch)>19 and patch[:4]==b'BPS1','Invalid BPS header')
    source_crc,target_crc,patch_crc=struct.unpack('<III',patch[-12:])
    checked(zlib.crc32(source)==source_crc,'BPS input ROM CRC mismatch')
    checked(zlib.crc32(patch[:-4])==patch_crc,'BPS patch CRC mismatch')
    pos=4;end=len(patch)-12
    def variable():
        nonlocal pos
        val=0;shift=1
        while True:
            checked(pos<end,'BPS variable integer truncated')
            char=patch[pos];pos+=1
            val+=(char&0x7f)*shift
            if char&0x80:return val
            shift<<=7;val+=shift
    source_size=variable();target_size=variable();meta_length=variable()
    checked(source_size==len(source),'BPS source length mismatch')
    checked(pos+meta_length<=end,'BPS metadata overflow')
    pos+=meta_length
    data=bytearray();src_rel=0;tgt_rel=0
    while len(data)<target_size:
        action=variable();mode=action&3;length=(action>>2)+1
        checked(len(data)+length<=target_size,'BPS output overflow')
        if mode==0:
            data.extend(source[len(data):len(data)+length])
        elif mode==1:
            checked(pos+length<=end,'BPS target-read overflow')
            data.extend(patch[pos:pos+length]);pos+=length
        elif mode==2:
            offset=variable();src_rel+=(-1 if offset&1 else 1)*(offset>>1)
            checked(0<=src_rel and src_rel+length<=len(source),'BPS source-copy out of bounds')
            data.extend(source[src_rel:src_rel+length]);src_rel+=length
        else:
            offset=variable();tgt_rel+=(-1 if offset&1 else 1)*(offset>>1)
            checked(0<=tgt_rel<len(data),'BPS target-copy out of bounds')
            for j in range(length):
                checked(tgt_rel+j<len(data),'BPS invalid target-copy overlap')
                data.append(data[tgt_rel+j])
            tgt_rel+=length
    checked(pos==end,'BPS trailing instructions')
    checked(zlib.crc32(data)==target_crc,'BPS target CRC mismatch')
    return bytes(data)

def compare_rom_bytes(a:bytes,b:bytes)->dict:
    checked(len(a)==len(b)==4194304,'ROM size mismatch')
    counts=Counter();positions=[]
    for i,(x,y) in enumerate(zip(a,b)):
        if x==y:continue
        if NAV[0]<=i<NAV[1]:key='host_navi_roster_full'
        elif DESC[0]<=i<DESC[1]:key='database_chip_descriptions'
        elif len(a)-2<=i<len(a):key='rom_checksum'
        else:key='UNEXPECTED'
        counts[key]+=1;positions.append({'offset':f'0x{i:06X}','from':f'{x:02X}','to':f'{y:02X}','class':key})
    checked(dict(counts)==EXPECTED_COUNTS, f'Unexpected byte difference count/ranges: {dict(counts)}')
    for name,rom in [('QA08',a),('QA09',b)]:
        checked(int.from_bytes(rom[-2:],'little')==(sum(rom[:-2])&0xFFFF),f'{name} WonderSwan checksum mismatch')
    return {'different_bytes':len(positions),'difference_counts':dict(counts),
            'allowed_ranges':{'navi':[hex(i) for i in NAV],'descriptions':[hex(i) for i in DESC],
                              'checksum':['0x3ffffe','0x400000']},
            'offsets':positions,'unexpected_changed_offsets':0,
            'checksum_old':a[-2:].hex(),'checksum_new':b[-2:].hex()}

def source_semantics(old:bytes,new:bytes)->dict:
    # The same actual native character-table decoder used by the translation
    # project; pointer iteration across all 249 rows is an explicit invariant.
    import n1tool as n
    import bcc_reference as b
    from qa03_tooltip_fix import read_rows
    dec,enc=n.load_table(ROOT/'tables/n1battle_jp.tbl')
    r0,old_used,_=read_rows(old,dec)
    r1,new_used,_=read_rows(new,dec)
    checked(len(r0)==len(r1)==249,'Wrong chip description catalog length')
    changed=[i for i in range(249) if r0[i]!=r1[i]]
    checked(changed==[175],f'Unexpected affected description rows {changed}')
    checked(r0[175]==GAIA_OLD and r1[175]==GAIA_NEW,'GaiaSwrd wording not as proposed')
    shared=old_used&new_used
    checked(all(old[i]==new[i] for i in shared),'Shared text bytes changed')
    # Check the exact two complete 94-byte encoded notices, including controls,
    # terminator and zero padding, independently of the displayed text label.
    def pack_nav(text):
        words=n.encode_text(text,enc)+[0x8000]
        checked(len(words)<=47,'Navi text buffer overflow')
        return struct.pack('<47H',*(words+[0]*(47-len(words))))
    checked(old[NAV[0]:NAV[1]]==pack_nav(OLD_NAVI),'QA08 Navi payload mismatch')
    checked(new[NAV[0]:NAV[1]]==pack_nav(NEW_NAVI),'QA09 Navi payload mismatch')
    checked(len(n.encode_text(NEW_NAVI,enc))==46,'QA09 Navi exceeds 46 words')
    manifest_old=json.loads((ROOT/'translation/lineage/en_qa08.json').read_text(encoding='utf8'))
    manifest_new=json.loads((ROOT/'translation/en_qa09.json').read_text(encoding='utf8'))
    def index(items):
        data={it['id']:it for it in items}
        checked(len(data)==len(items),'Duplicate source manifest id')
        return data
    expected={'entries':{'host_navi_roster_full'},'binary_entries':{'database_chip_descriptions'}}
    manifest_diff={}
    for key in ('entries','binary_entries'):
        left=index(manifest_old[key]);right=index(manifest_new[key])
        checked(set(left)==set(right),f'Changed manifest IDs: {key}')
        actual={i for i in left if left[i]!=right[i]}
        checked(actual==expected[key],f'Unexpected manifest entry changes: {key}={actual}')
        manifest_diff[key]=sorted(actual)
    checked(next(x for x in manifest_new['entries'] if x['id']=='host_navi_roster_full')['translation']==NEW_NAVI,'New Navi source mismatch')
    for stage,manifest,rom in [('08',manifest_old,old),('09',manifest_new,new)]:
        desc=next(x for x in manifest['binary_entries'] if x['id']=='database_chip_descriptions')
        asset=(ROOT/'translation'/desc['asset']).read_bytes()
        checked(len(asset)==desc['length']==DESC[1]-DESC[0],f'QA{stage} asset size mismatch')
        checked(digest(asset)==desc['asset_sha256'],f'QA{stage} asset SHA mismatch')
        checked(asset==rom[DESC[0]:DESC[1]],f'QA{stage} editable asset differs from ROM')
    return {'rows_total':249,'rows_identical':248,'changed_rows':changed,
            'gaia_before':r0[175],'gaia_after':r1[175],
            'shared_text_bytes_compared':len(shared),'shared_text_bytes_modified':0,
            'nav_original':OLD_NAVI,'nav_final':NEW_NAVI,
            'native_encoded_nav_words':46,'manifest_entries_changed':manifest_diff,
            'qa08_manifest_sha256':digest((ROOT/'translation/lineage/en_qa08.json').read_bytes()),
            'qa09_manifest_sha256':digest((ROOT/'translation/en_qa09.json').read_bytes())}

def source_inheritance(path08:Path,path09:Path)->dict:
    with zipfile.ZipFile(path08) as z8,zipfile.ZipFile(path09) as z9:
        left={x.filename:x for x in z8.infolist()}
        right={x.filename:x for x in z9.infolist()}
        missing=sorted(set(left)-set(right))
        checked(not missing,f'Source files missing from QA09: {missing[:10]}')
        changed=sorted(k for k in left if (left[k].CRC,left[k].file_size)!=(right[k].CRC,right[k].file_size))
        allow_new={'APPLY_PATCH.bat','BUILD_PATCH.bat','CHANGELOG.md','CONTINUITY.json',
                   'PROJECT_CONTEXT.md','README_ES.md','README_QA08.md',
                   'tests/test_graphics_advance_9_program_deck_chip_restore.py','tests/test_n1save.py'}
        # Source documentation can evolve in later maintenance, but inherited
        # engine, assets, font, gameplay, and QA08 builder MUST stay unchanged.
        for key in changed:
            checked(key in allow_new or key.startswith('.continuity/'),
                    f'Inherited QA08 source file unexpectedly modified: {key}')
        checked(not any(k.startswith(('src/','translation/','tables/','qa/')) for k in changed),
                'Inherited engine/translations/fonts/tools modified')
        added=sorted(set(right)-set(left))
        return {'qa08_entries':len(left),'qa09_entries':len(right),
                'inherited_entries':len(left),'inherited_changed_entries':changed,
                'inherited_byte_identical_entries':len(left)-len(changed),
                'new_entries':len(added),'missing_entries':missing,
                'unchanged_assets_and_toolchain':True,
                'note':'CRC32 plus file length for archive entry comparison; each ZIP extracted and CRC verified separately for the release audit.'}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=os.environ.get('CONTINUITY_INPUT_JP'),required=False)
    p.add_argument('--qa08-bps',type=Path,default=ROOT/'tests/fixtures/patches/Rockman_N1_English_QA08.bps')
    p.add_argument('--qa09-bps',type=Path,default=ROOT/'../../patches/qa09/Rockman_N1_English_QA09.bps')
    p.add_argument('--qa08-source-zip',type=Path)
    p.add_argument('--qa09-source-zip',type=Path)
    p.add_argument('--out',type=Path,default=ROOT/'build/qa12_comparison.json')
    args=p.parse_args(argv)
    p.error('--source or CONTINUITY_INPUT_JP required') if not args.source else None
    report={'status':'IN_PROGRESS','scope':'QA08 vs QA09 only, not full natural QA/hardware',
            'tool':'src/qa12_compare_qa08_qa09.py','base_sha256_expected':JP_SHA}
    try:
        src=args.source.read_bytes()
        checked(digest(src)==JP_SHA,'Unexpected original JP ROM SHA256')
        bps8=args.qa08_bps.read_bytes();bps9=args.qa09_bps.read_bytes()
        checked(digest(bps8)==QA08_BPS_SHA,'QA08 BPS SHA mismatch')
        checked(digest(bps9)==QA09_BPS_SHA,'QA09 BPS SHA mismatch')
        old=apply_bps_independent(src,bps8);new=apply_bps_independent(src,bps9)
        checked(digest(old)==QA08_SHA,'Unexpected QA08 ROM SHA256')
        checked(digest(new)==QA09_SHA,'Unexpected QA09 ROM SHA256')
        report['roms']={'jp':JP_SHA,'qa08':QA08_SHA,'qa09':QA09_SHA,
                        'qa08_bps':QA08_BPS_SHA,'qa09_bps':QA09_BPS_SHA}
        report['binary']=compare_rom_bytes(old,new)
        report['semantic']=source_semantics(old,new)
        if args.qa08_source_zip or args.qa09_source_zip:
            checked(bool(args.qa08_source_zip and args.qa09_source_zip),
                    'Source archive comparison needs both ZIP paths')
            report['source_inheritance']=source_inheritance(args.qa08_source_zip,args.qa09_source_zip)
        report['status']='PASS_SCOPED_BINARY_AND_SOURCE'
    except Exception as exc:
        report['status']='FAIL';report['error']=f'{type(exc).__name__}: {exc}'
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print(json.dumps({'status':report['status'],'differences':report.get('binary',{}).get('difference_counts'),
                      'changed_rows':report.get('semantic',{}).get('changed_rows'),
                      'source_inheritance':report.get('source_inheritance',{}).get('missing_entries'),
                      'error':report.get('error'), 'report':str(args.out)},ensure_ascii=False))
    return 0 if report['status']=='PASS_SCOPED_BINARY_AND_SOURCE' else 1

if __name__=='__main__':sys.exit(main())
