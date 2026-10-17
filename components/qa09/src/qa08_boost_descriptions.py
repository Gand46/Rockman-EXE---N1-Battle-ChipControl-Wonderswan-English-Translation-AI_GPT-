#!/usr/bin/env python3
"""Guarded QA08 seven boost-description resource build; no manifest or gameplay writes."""
from pathlib import Path
import argparse,json,hashlib,struct
import n1tool as n,bcc_reference as b
from qa03_tooltip_fix import read_rows,allocate
ROOT=Path(__file__).resolve().parents[1]
BASE_SHA='7f6d4e9e7c2adfa965f53ed683b175bfc63fb295feaccaac33033f4316a7e69c'
def sha(x):return hashlib.sha256(x).hexdigest()
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',type=Path,required=True);a=ap.parse_args()
 jp=n.read_rom(a.source,require_source=True);dec,enc=n.load_table(ROOT/'tables/n1battle_jp.tbl')
 manifest=json.loads((ROOT/'translation/lineage/en_qa07.json').read_text());entry=next(x for x in manifest['binary_entries'] if x['id']=='database_chip_descriptions')
 base=(ROOT/'translation'/entry['asset']).read_bytes();assert sha(base)==BASE_SHA==entry['asset_sha256']
 lo,hi=b.DESCRIPTION_OUTER_POINTERS,b.DESCRIPTION_BLOCK_END
 assert int(entry['offset'],0)==lo and len(base)==hi-lo==entry['length'] and sha(jp[lo:hi])==entry['expected_sha256']
 data=bytearray(jp);data[lo:hi]=base;before,used,lists=read_rows(data,dec);source,_,_=read_rows(jp,dec)
 folder=ROOT/'translation/qa08_boost_descriptions';editable=json.loads((folder/'descriptions.json').read_text())['rows'];changes={r['row']:r for r in editable};assert len(changes)==len(editable)==7
 # Lists owned exclusively by rows being replaced may be safely reclaimed.
 # Preserve the union of every byte referenced by every unchanged row.
 old_list_used=set(lists);retained_lists=set()
 for i in range(249):
  if i in changes:continue
  ptr=b.wsc_pointer(data,lo,i,'unchanged list')
  for k in range(16):
   retained_lists.update(range(ptr+4*k,ptr+4*k+4))
   if data[ptr+4*k:ptr+4*k+4]==b'\0'*4:break
  else:raise AssertionError('unterminated retained list')
 lists=set(retained_lists)
 existing={}
 for i,lines in enumerate(before):
  ptr=b.wsc_pointer(data,lo,i,'list')
  for k,line in enumerate(lines):existing.setdefault(line,b.wsc_pointer(data,ptr,k,'text'))
 alloc=[]
 for i,r in changes.items():
  assert source[i]==r['jp'] and before[i]==r['expected_before'],i
  assert r['after'][0]==before[i][0], 'Attributes/numbers/stars must remain exact'
  lines=r['after'];assert 1<=len(lines)<=2 and all(len(x)<=25 for x in lines),i
  assert sum(x.count('﹡') for x in lines)==sum(x.count('﹡') for x in source[i]),i
  targets=[]
  for line in lines:
   if line not in existing:
    words=b.encode_static(line,enc);payload=struct.pack('<'+'H'*len(words),*words)
    existing[line]=allocate(data,payload,b.DESCRIPTION_TEXT_POOLS,used,alloc,'text')
   targets.append(existing[line])
  payload=b''.join(b.encode_wsc_far_pointer(t) for t in targets)+b'\0'*4
  target=allocate(data,payload,b.DESCRIPTION_LIST_POOLS,lists,alloc,'list')
  b.write_wsc_far_pointer(data,lo+i*4,target)
 after,_,_=read_rows(data,dec)
 for i in range(249):assert after[i]==(changes[i]['after'] if i in changes else before[i])
 populated_chips=[i for i,x in enumerate(source) if x and '属性 命中率' in x[0]]
 assert len(populated_chips)==108
 for i in populated_chips:
  assert len(after[i])==2 and all(len(x)<=25 for x in after[i]),i
  assert sum(x.count('﹡') for x in after[i])==source[i][0].count('﹡'),i
 allowed=set()
 for i in changes:allowed.update(range(lo+i*4,lo+i*4+4))
 for r in alloc:allowed.update(range(int(r['start'],16),int(r['end_exclusive'],16)))
 changed={lo+i for i,(x,y) in enumerate(zip(base,data[lo:hi])) if x!=y};assert changed<=allowed
 payload=bytes(data[lo:hi]);(folder/'descriptions.bin').write_bytes(payload)
 replacement=dict(entry,asset='qa08_boost_descriptions/descriptions.bin',asset_sha256=sha(payload))
 report={'source_sha256':sha(jp),'inherited_asset_sha256':BASE_SHA,'asset_sha256':sha(payload),'manifest_replacement':replacement,'changed_rows':sorted(changes),'changed_bytes':len(changed),'unexpected_changed_offsets':0,'unchanged_rows':242,'inherited_QA07_other242_preserved':True,'whole_catalog_structure':{'chip_rows':108,'all_two_lines_max25':True,'all_native_star_counts_preserved':True,'special_messages':2},'allocations':alloc,'reclaimed_list_bytes_not_owned_by_unchanged_rows':len(old_list_used-retained_lists),'editable_source_sha256':sha((folder/'descriptions.json').read_bytes()),'linguistic':'Seven direction descriptions reviewed against exact JP plus native consumer current-index+1 and element comparison; first lines unchanged','runtime':'NOT_VALIDATED','typography':'NOT_VALIDATED','legibility':'NOT_VALIDATED','visual':'NOT_VALIDATED','gameplay_unchanged':True,'labels_and_names_unchanged':True}
 (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'replacement':replacement,'rows':len(changes),'changed_bytes':len(changed)},indent=2))
if __name__=='__main__':main()
