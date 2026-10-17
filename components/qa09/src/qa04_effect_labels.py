#!/usr/bin/env python3
"""QA04 safe content: four static ADD labels and three existing tooltip values.
No new strings, no repacking, no change to three-line description structure.
"""
from pathlib import Path
import argparse,hashlib,json,struct
import n1tool as n,bcc_reference as b
from qa03_tooltip_fix import read_rows
ROOT=Path(__file__).resolve().parents[1]
def sha(x):return hashlib.sha256(x).hexdigest()
def text(data,t,dec,style=0):return ''.join(n.token_for(w&~style,dec) for w in b.read_words(data,t,'x')[:-1])
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',required=True,type=Path);a=ap.parse_args();jp=n.read_rom(a.source,require_source=True)
 m=json.loads((ROOT/'translation/lineage/en_qa03.json').read_text());dec,enc=n.load_table(ROOT/'tables/n1battle_jp.tbl');base=bytearray(jp);entries={}
 expected={'database_chip_descriptions':'ed010eadce996188104580e92590d7f1f8a2a8218644f6f4423f9bffe67e23c2','database_effect_label_pointers':'baf060ade9e8198c881aed504201809ea369796001993fb4a23b48086fe28460','database_effect_labels':'9973bd4e3042d71189c26ea6ab852c5b86472aba0b35396e08be2cc048aea52f'}
 for k,h in expected.items():
  e=next(x for x in m['binary_entries'] if x['id']==k);payload=(ROOT/'translation'/e['asset']).read_bytes();assert sha(payload)==h==e['asset_sha256'];start=int(e['offset'],0);assert len(payload)==e['length'] and sha(jp[start:start+len(payload)])==e['expected_sha256'];base[start:start+len(payload)]=payload;entries[k]=e
 data=bytearray(base);before,_,_=read_rows(base,dec);source,_,_=read_rows(jp,dec)
 owners={};strings={}
 for i in range(249):
  li=b.wsc_pointer(base,b.DESCRIPTION_OUTER_POINTERS,i,'list');owners.setdefault(li,[]).append(i)
  for k in range(len(before[i])):
   target=b.wsc_pointer(base,li,k,'string');strings.setdefault(text(base,target,dec),target)
 descchanges=[];allowed=set()
 for i,power in [(5,40),(6,50),(7,60)]:
  assert before[i]==['None',f'AccS Add{power+10}','Left Bchip Attack']
  assert f'ツイカ{power}' in source[i][0]
  li=b.wsc_pointer(base,b.DESCRIPTION_OUTER_POINTERS,i,'list');assert owners[li]==[i],(i,owners[li])
  target=strings[f'AccS Add{power}'];at=li+4;b.write_wsc_far_pointer(data,at,target);allowed.update(range(at,at+4))
  descchanges.append({'row':i,'exclusive_list':hex(li),'owners':owners[li],'pointer_slot':hex(at),'before':before[i][1],'after':f'AccS Add{power}','existing_text_target':hex(target)})
 after,_,_=read_rows(data,dec)
 for i in range(249):
  want=list(before[i])
  if i in [5,6,7]:want[1]=f'AccS Add{(i-1)*10}'
  assert after[i]==want
 labels={};targets={}
 for i in range(249):
  t=b.wsc_pointer(base,b.EFFECT_LABELS.pointer_start,i,'effect');s=text(base,t,dec,0x600);labels[i]=s;targets.setdefault(s,t)
 changes=[]
 for i,power in [(5,40),(6,50),(7,60),(200,40)]:
  assert labels[i]==f'ADD{power+10}'
  jt=b.wsc_pointer(jp,b.EFFECT_LABELS.pointer_start,i,'JP');assert text(jp,jt,dec,0x600)==f'ツイカ{power}'
  at=b.EFFECT_LABELS.pointer_start+i*4;b.write_wsc_far_pointer(data,at,targets[f'ADD{power}']);allowed.update(range(at,at+4));changes.append({'row':i,'before':labels[i],'after':f'ADD{power}','existing_target':hex(targets[f'ADD{power}'])})
 for i in range(249):
  actual=text(data,b.wsc_pointer(data,b.EFFECT_LABELS.pointer_start,i,'effect'),dec,0x600)
  wanted=next((x['after'] for x in changes if x['row']==i),labels[i]);assert actual==wanted
 diff=[i for i,(x,y) in enumerate(zip(base,data)) if x!=y];assert set(diff)<=allowed
 replacements=[]
 for k,name in [('database_chip_descriptions','chip_descriptions_qa04_stats.bin'),('database_effect_label_pointers','effect_labels_pointers_qa04.bin')]:
  e=entries[k];at=int(e['offset'],0);payload=bytes(data[at:at+e['length']]);(ROOT/'translation/assets'/name).write_bytes(payload);replacements.append(dict(e,asset='assets/'+name,asset_sha256=sha(payload)))
 report={'source_rom_sha256':sha(jp),'base':'verified QA03','manifest_replacements':replacements,'description_changes':descchanges,'effect_label_changes':changes,'description_rows_unchanged':246,'effect_label_rows_unchanged':245,'new_strings':0,'new_lists':0,'description_line_counts_preserved':True,'text_bytes_preserved':True,'changed_bytes':len(diff),'unexpected_changed_offsets':0,'open_issue':'11 front-row effect descriptions remain three-line and lack visible effect explanation; experimental new packing rejected after runtime corruption.','status':{'structure':'PASS','runtime':'NOT_VALIDATED','visual':'NOT_VALIDATED','final_approved':False}}
 (ROOT/'translation/assets/qa04_effect_labels_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
