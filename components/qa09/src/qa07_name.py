#!/usr/bin/env python3
"""Guarded name198 correction after tracing the Program Deck confirmation action."""
from pathlib import Path
import json,struct,hashlib,argparse
import n1tool as n,bcc_reference as b
ROOT=Path(__file__).resolve().parents[1]
EXPECTED={'database_chip_name_pointers':'8cfeaddd01c871058d860c00d3ab6578d262bcd75bbd5f517ac3d36a32fdd3fc','database_chip_names':'ed59cc24e09d0bced934eb4259c7654ffc5033d264b7fce5f4fb1ddccc93f884'}
def sha(x):return hashlib.sha256(x).hexdigest()
def names(data,dec):
 result=[];used=set()
 for i in range(249):
  t=b.wsc_pointer(data,b.CHIP_NAMES.pointer_start,i,'name');w=b.read_words(data,t,'name')
  assert b.CHIP_NAMES.data_start<=t and t+len(w)*2<=b.CHIP_NAMES.data_end
  used.update(range(t,t+len(w)*2));result.append(''.join(n.token_for(x,dec) for x in w[:-1]))
 return result,used
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);a=ap.parse_args();jp=n.read_rom(a.source,require_source=True)
 dec,enc=n.load_table(ROOT/'tables/n1battle_jp.tbl');m=json.loads((ROOT/'translation/lineage/en_qa06.json').read_text());data=bytearray(jp);entries=[]
 for key,h in EXPECTED.items():
  e=next(x for x in m['binary_entries'] if x['id']==key);raw=(ROOT/'translation'/e['asset']).read_bytes();assert sha(raw)==h==e['asset_sha256'];at=int(e['offset'],0);assert sha(jp[at:at+len(raw)])==e['expected_sha256'];data[at:at+len(raw)]=raw;entries.append(e)
 before,used=names(data,dec);source,_=names(jp,dec);assert before[198]=='Chip OK' and source[198]==''
 base=bytes(data);words=b.encode_static('SendDeck',enc);payload=struct.pack('<'+'H'*len(words),*words);assert len(words)==9
 for pos in range(b.CHIP_NAMES.data_start,b.CHIP_NAMES.data_end-len(payload)+1,2):
  if not set(range(pos,pos+len(payload)))&used:break
 else:raise AssertionError('no unreferenced name pool capacity')
 previous=data[pos:pos+len(payload)];data[pos:pos+len(payload)]=payload
 ptr=b.CHIP_NAMES.pointer_start+198*4;b.write_wsc_far_pointer(data,ptr,pos)
 after,_=names(data,dec)
 for i in range(249):assert after[i]==('SendDeck' if i==198 else before[i])
 changed={i for i,(x,y) in enumerate(zip(base,data)) if x!=y};assert changed<=set(range(ptr,ptr+4))|set(range(pos,pos+len(payload)))
 out=ROOT/'translation/qa07';out.mkdir(exist_ok=True);replacements=[]
 for e in entries:
  at=int(e['offset'],0);raw=bytes(data[at:at+e['length']]);name='name_pointers.bin' if 'pointers' in e['id'] else 'name_data.bin';(out/name).write_bytes(raw);replacements.append(dict(e,asset='qa07/'+name,asset_sha256=sha(raw)))
 report={'source_sha256':sha(jp),'before':'Chip OK','after':'SendDeck','row':198,'native_name':'','reason':'Observed Program Deck slot10 confirmation action; sends deck data and Ready? Yes leads to battle. It is not an inventory chip.','manifest_replacements':replacements,'allocated_at':hex(pos),'previous_allocation_sha256':sha(previous),'changed_bytes':len(changed),'other_248_names_unchanged':True,'gameplay_unchanged':True,'runtime_new_name':'NOT_VALIDATED','source_function_evidence':'evidence/qa07/astra_utility198.md'}
 (out/'name_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
