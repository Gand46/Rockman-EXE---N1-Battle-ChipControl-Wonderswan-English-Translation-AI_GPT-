#!/usr/bin/env python3
"""Bounded two-row WSC tooltip fix. Writes only NEW assets/report, never ROM/manifest.

Usage: python3 tools/qa03_tooltip_fix.py --source /path/to/original.wsc
The a9 block is preserved byte-for-byte except pointers of rows 4/200 and new
records allocated in structurally unreferenced text/list pool ranges.
"""
from pathlib import Path
import argparse, hashlib, json, struct
import bcc_reference as b
import n1tool as n

ROOT=Path(__file__).resolve().parents[1]
BASE_SHA='c82bca60046678fdb269bd7b085abfe4387e88f62cd62fc36759b3739c4ba2a6'
REPLACEMENTS={4:['None AccS Add30 ﹡','Hit front chips too'],200:['None AccA DodgeB ChgShot','Hit front chips too ﹡﹡﹡﹡﹡']}
EXPECTED_EN={4:['None','AccS Add30','Left Bchip Attack'],200:['None AccA DodgeB','ChgShot Atk None','Left Bchip Attack']}
EXPECTED_JP={4:['無属性 命中率S ツイカ30 ﹡','前列バトルチップに ついか攻撃'],200:['無属性 命中率A チャージショット ﹡﹡﹡﹡﹡','前列バトルチップに ついか攻撃']}

def digest(x):return hashlib.sha256(x).hexdigest()
def read_rows(data,dec):
    rows=[];text_used=set();list_used=set()
    for i in range(b.DESCRIPTION_COUNT):
        at=b.wsc_pointer(data,b.DESCRIPTION_OUTER_POINTERS,i,'description'); row=[]
        assert any(s<=at<e for s,e in b.DESCRIPTION_LIST_POOLS)
        for k in range(16):
            p=at+k*4
            assert any(s<=p and p+4<=e for s,e in b.DESCRIPTION_LIST_POOLS)
            list_used.update(range(p,p+4))
            off,seg=struct.unpack_from('<HH',data,p)
            if off==seg==0:break
            target=0x300000+seg*16+off
            words=b.read_words(data,target,'description')
            assert any(s<=target and target+len(words)*2<=e for s,e in b.DESCRIPTION_TEXT_POOLS)
            assert words[-1]==0x8000|len(words[:-1])
            text_used.update(range(target,target+len(words)*2))
            row.append(''.join(n.token_for(w,dec) for w in words[:-1]))
        else:raise AssertionError('unterminated row')
        rows.append(row)
    return rows,text_used,list_used

def allocate(data,payload,pools,used,allocations,kind):
    for start,end in pools:
        for pos in range(start,end-len(payload)+1,2):
            occupied=set(range(pos,pos+len(payload)))
            if not occupied&used:
                previous=bytes(data[pos:pos+len(payload)])
                data[pos:pos+len(payload)]=payload;used.update(occupied)
                allocations.append({'kind':kind,'start':hex(pos),'end_exclusive':hex(pos+len(payload)),'previous_sha256':digest(previous),'new_sha256':digest(payload)})
                return pos
    raise AssertionError('no verified unreferenced pool capacity')

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',required=True,type=Path);args=ap.parse_args()
    jp=n.read_rom(args.source,require_source=True)
    baseline_path=ROOT/'translation/assets/chip_descriptions.bin'; baseline=baseline_path.read_bytes()
    assert digest(baseline)==BASE_SHA
    manifest=json.loads((ROOT/'translation/lineage/en_v0_10_7_graphics_a9.json').read_text())
    entry=next(x for x in manifest['binary_entries'] if x['id']=='database_chip_descriptions')
    assert entry['asset_sha256']==BASE_SHA and int(entry['offset'],0)==b.DESCRIPTION_OUTER_POINTERS
    lo,hi=b.DESCRIPTION_OUTER_POINTERS,b.DESCRIPTION_BLOCK_END
    assert len(baseline)==hi-lo and digest(jp[lo:hi])==entry['expected_sha256']
    dec,enc=n.load_table(ROOT/'tables/n1battle_jp.tbl')
    data=bytearray(jp);data[lo:hi]=baseline
    before,text_used,list_used=read_rows(data,dec);jp_rows,_,_=read_rows(jp,dec)
    allocations=[];details=[]
    for i,lines in REPLACEMENTS.items():
        assert before[i]==EXPECTED_EN[i] and jp_rows[i]==EXPECTED_JP[i]
        addresses=[]
        for line in lines:
            assert len(line)<=25, (i,line)
            payload=struct.pack('<'+'H'*(len(line)+1),*b.encode_static(line,enc))
            addresses.append(allocate(data,payload,b.DESCRIPTION_TEXT_POOLS,text_used,allocations,'text'))
        pointers=b''.join(b.encode_wsc_far_pointer(p) for p in addresses)+b'\0'*4
        target=allocate(data,pointers,b.DESCRIPTION_LIST_POOLS,list_used,allocations,'list')
        b.write_wsc_far_pointer(data,lo+i*4,target)
        details.append({'row':i,'jp_lines':jp_rows[i],'previous_en_lines':before[i],'new_en_lines':lines,'cell_width_pixels':8,'max_cells':25,'line_cell_widths':[len(s)*8 for s in lines],'tooltip_observed_origin_x':16,'static_end_x_exclusive':[16+len(s)*8 for s in lines],'runtime_status':'NOT_VALIDATED'})
    after,_,_=read_rows(data,dec)
    for i in range(b.DESCRIPTION_COUNT):assert after[i]==REPLACEMENTS.get(i,before[i])
    allowed=set()
    for i in REPLACEMENTS:allowed.update(range(lo+i*4,lo+i*4+4))
    for a in allocations:allowed.update(range(int(a['start'],16),int(a['end_exclusive'],16)))
    changed=[lo+k for k,(x,y) in enumerate(zip(baseline,data[lo:hi])) if x!=y]
    assert set(changed)<=allowed
    asset=ROOT/'translation/assets/chip_descriptions_qa03.bin';asset.write_bytes(data[lo:hi])
    replacement=dict(entry,asset='assets/'+asset.name,asset_sha256=digest(data[lo:hi]))
    report={'scope':'rows 4 (Shotgun) and 200 (MegaMan) only','base_asset_sha256':BASE_SHA,'source_rom_sha256':digest(jp),'new_asset_sha256':digest(data[lo:hi]),'allocations':allocations,'changed_bytes':len(changed),'unexpected_changed_offsets':0,'unchanged_other_rows':247,'manifest_replacement':replacement,'rows':details,'diagnosis':'GBA import supplies 3 lines; runtime sample shows only first 2. Effect explanation exists in data but not visible. This fix consolidates to 2 lines and restores JP markers.','retained_additional_attribute':'DodgeB retained from existing EN, absent from JP visible description.','removed_redundant_label':'Atk None omitted; existing None element retained on line 1.','out_of_scope':'Other GBA-derived stat differences, remaining 247 descriptions, renderer and font unchanged.','status':{'CONTENT_AND_STRUCTURE':'PASS','RUNTIME':'NOT_VALIDATED','VISUAL':'NOT_VALIDATED','FINAL_APPROVED':False}}
    (ROOT/'translation/assets/qa03_tooltip_fix_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'asset':str(asset),'sha256':report['new_asset_sha256'],'changed_bytes':len(changed),'other_rows_unchanged':247},indent=2))

if __name__=='__main__':main()
