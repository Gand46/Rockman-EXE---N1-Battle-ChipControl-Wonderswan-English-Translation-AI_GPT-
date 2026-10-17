#!/usr/bin/env python3
"""Read-only QA07 static targets for utility198, late story and credits."""
from pathlib import Path
import json,struct,hashlib,argparse,subprocess
import n1tool as n,bcc_reference as b
ROOT=Path(__file__).resolve().parents[1]
def sha(x):return hashlib.sha256(x).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--rom',type=Path,required=True);ap.add_argument('--source',type=Path,required=True);a=ap.parse_args()
 r=a.rom.read_bytes();jp=n.read_rom(a.source,require_source=True);assert sha(r)=='b08dc7a16a41d4e2f4d3cba345e41970f0cf4c3b75a4b218126128720ddc4ae4'
 dec,_=n.load_table(ROOT/'tables/n1battle_jp.tbl');m=json.loads((ROOT/'translation/lineage/en_qa06.json').read_text())
 entries=[]
 for e in m['entries']:
  if not any(x in e['id'] for x in ['master_','east_final','west_final','cliff_final','block_final']):continue
  at=int(e['offset'],0);slots=[]
  for g in n.TEXT_GROUPS:
   for i in range(g.pointer_count):
    if g.base+struct.unpack_from('<H',r,g.pointer_table+2*i)[0]*2==at:slots.append(f'{g.index:02X}:{i:02X}')
  entries.append({'id':e['id'],'offset':e['offset'],'slots':slots,'summary':e['source_summary'],'text':e['translation'],'runtime':'NOT_VALIDATED'})
 credit=[]
 for i in range(0x96,0xd0):
  at=0x34acb0+2*struct.unpack_from('<H',r,0x34ab10+i*2)[0];words=n.words_at(r,at,0x34b75e)
  credit.append({'slot':f'05:{i:02X}','offset':hex(at),'text':''.join(n.token_for(w,dec) for _,w in words),'terminated':words[-1][1]==0x8000})
 span=r[0x33ace8:0x33aeea];assert span==jp[0x33ace8:0x33aeea]
 off,seg=struct.unpack_from('<HH',r,0x371ac4);assert 0x300000+seg*16+off==0x33ace8
 utility={}
 for title,data in [('jp',jp),('qa06',r)]:
  at=b.wsc_pointer(data,b.CHIP_NAMES.pointer_start,198,'name198');words=b.read_words(data,at,'name198');utility[title]={'name_target':hex(at),'name':''.join(n.token_for(w,dec) for w in words[:-1])}
 out=ROOT/'evidence/qa07';out.mkdir(parents=True,exist_ok=True)
 result={'rom_sha256':sha(r),'source_sha256':sha(jp),'utility198':utility,'utility_code':{'cursor_slot10_assigns198':'0x328518','suppresses_second_line':'0x32856B','draws_special_card198':'0x328637','A_normal_mode_confirm':'0x327461–0x327498','drag_mode_guard':'0x327444–0x32745E; +0x3F','cancel_drag':'0x32753F–0x327565','name_draw_call':'0x324D1E–0x324D29'},'late_story':entries,'credits':{'routine':'0x33ACE8–0x33AEE9','code_sha256':sha(span),'same_as_JP':True,'exact_entry_far_pointer':'0x371AC4 -> 3ACE:0008','entry_pointer_dispatch_context':'NOT_VALIDATED; do not treat isolated far-pointer match as an organic route','slots':credit,'runtime':'NOT_VALIDATED'},'scope':'Targets for execution, not proof of story/credits traversal.'}
 (out/'astra_trace_targets.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 for label,start,end in [('utility',0x327323,0x32757d),('description',0x3284b1,0x32864f),('credits',0x33ace8,0x33aeea)]:
  q=subprocess.run(['objdump','-D','-b','binary','-mi8086',f'--start-address={start}',f'--stop-address={end}',str(a.rom)],capture_output=True,text=True,check=True);(out/f'astra_{label}_disassembly.txt').write_text(q.stdout)
 print(out/'astra_trace_targets.json')
if __name__=='__main__':main()
