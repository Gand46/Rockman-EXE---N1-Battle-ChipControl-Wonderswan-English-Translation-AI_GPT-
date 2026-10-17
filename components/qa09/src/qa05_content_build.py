#!/usr/bin/env python3
"""QA05 bounded description corrections. No manifest, ROM or label-table writes."""
from pathlib import Path
import argparse, hashlib, json, struct
import n1tool as n, bcc_reference as b
from qa03_tooltip_fix import read_rows, allocate
ROOT=Path(__file__).resolve().parents[1]
BASE='14730cbedfa74769483b93ac765a747641203c587c95c165b4073477039f98be'
FAMILY={5:('無','None',40,2),6:('無','None',50,3),7:('無','None',60,5),8:('水','Aqua',20,1),9:('水','Aqua',30,2),10:('水','Aqua',40,4),11:('水','Aqua',50,5),12:('炎','Fire',20,1),13:('炎','Fire',30,2),14:('炎','Fire',40,4),15:('炎','Fire',50,5)}
# Explicit inherited tokens guard the numeric corrections before two-line consolidation.
NUMBERS={3:[('Norm120','Norm110')],20:[('AllAdd20','AllAdd10')],21:[('AllAdd30','AllAdd20')],22:[('AllAdd40','AllAdd30')],24:[('Rnd80','Rnd70')],25:[('Rnd90','Rnd70')],42:[('Pier130','Pier100')],63:[('Stun10','Stun40')],64:[('Stun50','Stun40')],65:[('Stun100','Stun40')],78:[('Cnt50','Cnt40')],79:[('Cnt60','Cnt50')],148:[('Aura80','Aura60'),('Below 80','60 or less')],149:[('Aura80','Aura60'),('Below 80','60 or less')],150:[('Aura80','Aura60'),('Below 80','60 or less')],151:[('Aura80','Aura60'),('Below 80','60 or less')],152:[('Aura100','Aura80'),('Below 100','80 or less')],153:[('Aura120','Aura100'),('Below 120','100 or less')],154:[('Aura150','Aura120'),('Below 150','120 or less')],172:[('Pierc90+','Pierc80+')],174:[('AllAdd50+','AllAdd30+')],175:[('AccC','AccB'),('Rndm100','Rndm100+')],179:[('Rndm250','Rndm150')]}
JP_VALUES={3:'110',20:'10',21:'20',22:'30',24:'70',25:'70',42:'100',63:'40',64:'40',65:'40',78:'40',79:'50',148:'60',149:'60',150:'60',151:'60',152:'80',153:'100',154:'120',172:'80+',174:'30+',175:'100+',179:'150'}
# All native attributes and markers remain visible. Counts derive from guarded JP.
COMPLETE={
 3:('None AccD Norm110','Attack Navi chip'),
 20:('Wood AccA AllAdd10','Hit all chips too'),21:('Wood AccA AllAdd20','Hit all chips too'),22:('Wood AccA AllAdd30','Hit all chips too'),
 24:('None AccD Rnd70','Hit 1 random chip too'),25:('None AccD Rnd70','Hit 1 random chip too'),
 42:('None AccB Pier100','Attack Navi through guard'),
 63:('Elec AccC Stun40','Paralyze Navi this turn'),64:('Elec AccC Stun40','Paralyze Navi this turn'),65:('Elec AccC Stun40','Paralyze Navi this turn'),
 78:('None AccA Cnt40','After guard, attack Navi'),79:('None AccA Cnt50','After guard, attack Navi'),
 148:('Aqua Acc× Aura60','Stop up to 60 except Elec'),149:('Fire Acc× Aura60','Stop up to 60 except Aqua'),150:('Wood Acc× Aura60','Stop up to 60 except Fire'),151:('Elec Acc× Aura60','Stop up to 60 except Wood'),
 152:('None Acc× Aura80','Block up to 80'),153:('None Acc× Aura100','Block up to 100'),154:('None Acc× Aura120','Block up to 120'),
 172:('Fire AccA Pier80+','Navi hit + all chip hits'),
 174:('Elec AccC AllAdd30+','Hit all chips + guard'),
 175:('Wood AccB Rnd100+','Hit 1 chip+prior chip pwr'),
 179:('None AccC Rnd150','Hit 1 random chip too')}
def sha(x):return hashlib.sha256(x).hexdigest()
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',type=Path,required=True);a=ap.parse_args()
 jp=n.read_rom(a.source,require_source=True);m=json.loads((ROOT/'translation/lineage/en_qa04.json').read_text())
 entry=next(e for e in m['binary_entries'] if e['id']=='database_chip_descriptions')
 baseline=(ROOT/'translation'/entry['asset']).read_bytes();assert sha(baseline)==BASE==entry['asset_sha256']
 lo,hi=b.DESCRIPTION_OUTER_POINTERS,b.DESCRIPTION_BLOCK_END
 assert len(baseline)==hi-lo and sha(jp[lo:hi])==entry['expected_sha256']
 data=bytearray(jp);data[lo:hi]=baseline;before_data=bytes(data)
 dec,enc=n.load_table(ROOT/'tables/n1battle_jp.tbl');before,used,lists=read_rows(data,dec);source,_,_=read_rows(jp,dec)
 changes={}
 for i,(j,e,p,s) in FAMILY.items():
  assert source[i]==[f'{j}属性 命中率S ツイカ{p} '+'﹡'*s,'前列バトルチップに ついか攻撃']
  assert before[i]==[e,f'AccS Add{p}','Left Bchip Attack']
  changes[i]=[f'{e} AccS Add{p} '+'﹡'*s,'Hit front chips too']
 for i,pairs in NUMBERS.items():
  assert JP_VALUES[i] in source[i][0]
  if i==175:assert '命中率B' in source[i][0]
  lines=list(before[i])
  for old,new in pairs:
   assert sum(line.count(old) for line in lines)==1,(i,old,lines)
   lines=[line.replace(old,new) for line in lines]
  first,effect=COMPLETE[i]
  stars=source[i][0].count('﹡');assert 1<=stars<=5
  changes[i]=[first+' '+'﹡'*stars,effect]
 # Reuse all existing strings; allocate only structurally unreferenced words.
 existing={}
 for i,lines in enumerate(before):
  ptr=b.wsc_pointer(data,lo,i,'list')
  for k,line in enumerate(lines):existing.setdefault(line,b.wsc_pointer(data,ptr,k,'text'))
 alloc=[];details=[]
 for i,lines in changes.items():
  assert len(lines)==2
  assert sum(x.count('﹡') for x in lines)==source[i][0].count('﹡')
  targets=[]
  for line in lines:
   assert len(line)<=25,(i,line)
   if line not in existing:
    words=b.encode_static(line,enc);payload=struct.pack('<'+'H'*len(words),*words)
    existing[line]=allocate(data,payload,b.DESCRIPTION_TEXT_POOLS,used,alloc,'text')
   targets.append(existing[line])
  payload=b''.join(b.encode_wsc_far_pointer(x) for x in targets)+b'\0'*4
  ptr=allocate(data,payload,b.DESCRIPTION_LIST_POOLS,lists,alloc,'list')
  b.write_wsc_far_pointer(data,lo+i*4,ptr)
  details.append({'row':i,'jp':source[i],'before':before[i],'after':lines,'scope':'F04 full two-line effect and markers' if i in FAMILY else 'F06 complete native effect, attributes and markers in two lines','line_cells':[len(s) for s in lines]})
 after,_,_=read_rows(data,dec)
 for i in range(249):assert after[i]==changes.get(i,before[i])
 allowed=set()
 for i in changes:allowed.update(range(lo+i*4,lo+i*4+4))
 for x in alloc:allowed.update(range(int(x['start'],16),int(x['end_exclusive'],16)))
 changed={i for i,(x,y) in enumerate(zip(before_data,data)) if x!=y};assert changed<=allowed
 dest=ROOT/'translation/qa05_content';dest.mkdir(exist_ok=True)
 payload=bytes(data[lo:hi]);(dest/'descriptions.bin').write_bytes(payload)
 replacement=dict(entry,asset='qa05_content/descriptions.bin',asset_sha256=sha(payload))
 report={'source_sha256':sha(jp),'inherited_description_sha256':BASE,'asset_sha256':sha(payload),'manifest_replacement':replacement,'rows':details,'allocations':alloc,'changed_bytes':len(changed),'other_rows_unchanged':249-len(changes),'labels_untouched':True,'gameplay_untouched':True,'runtime':'PENDING','rectification':'QA04 alignment/corruption claims withdrawn: native font mask comparisons show those screenshots rendered correctly. No alignment-dependent consumer defect established.'}
 (dest/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'asset':replacement,'rows':len(changes)},indent=2))
if __name__=='__main__':main()
