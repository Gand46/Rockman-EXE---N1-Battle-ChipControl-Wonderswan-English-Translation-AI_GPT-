"""Correct 23 JP/EN numeric card-label discrepancies, without touching battle data."""
from pathlib import Path
import argparse,json,hashlib,struct
import bcc_reference as b,n1tool as n
from qa03_tooltip_fix import allocate
from qa04_effect_labels import text
ROOT=Path(__file__).resolve().parents[1];H=lambda x:hashlib.sha256(x).hexdigest()
FIXES={3:'NOR110',20:'~ADD10',21:'~ADD20',22:'~ADD30',24:'RAND70',25:'RAND70',42:'PIE100',63:'STUN40',64:'STUN40',65:'STUN40',78:'CNT40',79:'CNT50',148:'AURA60',149:'AURA60',150:'AURA60',151:'AURA60',152:'AURA80',153:'AUR100',154:'AUR120',172:'PIE80+',174:'~AD30+',179:'RND150',203:'RNDM50'}
# JP composite numeric glyphs are rendered as 110/100/150 etc. These source
# values were confirmed from JP runtime screenshots, not generic table tokens.
POWERS={3:110,20:10,21:20,22:30,24:70,25:70,42:100,63:40,64:40,65:40,78:40,79:50,148:60,149:60,150:60,151:60,152:80,153:100,154:120,172:80,174:30,179:150,203:50}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--base',required=True,type=Path);ap.add_argument('--jp',required=True,type=Path);a=ap.parse_args();base=a.base.read_bytes();assert H(base)=='822467360f2b4aa7e9e173e7606a0e18d74b3e1bb5b42063f695e77e37449c8b';jp=n.read_rom(a.jp,require_source=True)
 m=json.loads((ROOT/'translation/lineage/en_qa04.json').read_text());entries={x['id']:x for x in m['binary_entries']};dec,enc=n.load_table(ROOT/'tables/n1battle_jp.tbl');data=bytearray(base)
 used=set();targets={};before={};alloc=[];details=[];allowed=set()
 for row in range(249):
  t=b.wsc_pointer(base,b.EFFECT_LABELS.pointer_start,row,'effect');w=b.read_words(base,t,'effect');s=text(base,t,dec,0x600);before[row]=s;targets.setdefault(s,t);used.update(range(t,t+2*len(w)))
 for row,s in FIXES.items():
  assert len(s)<=6 and s!=before[row];power=POWERS[row];assert str(power) in s
  if s not in targets:
   w=b.encode_static(s,enc);w=tuple(x|0x600 if not x&0x8000 else x for x in w);payload=struct.pack('<'+'H'*len(w),*w)
   targets[s]=allocate(data,payload,[(b.EFFECT_LABELS.data_start,b.EFFECT_LABELS.data_end)],used,alloc,'effect-label')
  at=b.EFFECT_LABELS.pointer_start+row*4;b.write_wsc_far_pointer(data,at,targets[s]);allowed.update(range(at,at+4))
  jt=b.wsc_pointer(jp,b.EFFECT_LABELS.pointer_start,row,'source');details.append({'row':row,'before':before[row],'after':s,'jp_label_words':[hex(x) for x in b.read_words(jp,jt,'source')],'jp_runtime_power':power,'jp_runtime_image':f'catalog_jp/row_{row:03d}.png','gameplay_modified':False})
 for v in alloc:allowed.update(range(int(v['start'],16),int(v['end_exclusive'],16)))
 diffs={i for i,(x,y) in enumerate(zip(base,data)) if x!=y};assert diffs<=allowed
 for row in range(249):assert text(data,b.wsc_pointer(data,b.EFFECT_LABELS.pointer_start,row,'after'),dec,0x600)==FIXES.get(row,before[row])
 repl=[]
 for key in ['database_effect_label_pointers','database_effect_labels']:
  e=entries[key];at=int(e['offset'],16);asset=key+'_qa05.bin';payload=bytes(data[at:at+e['length']]);(ROOT/'translation/assets'/asset).write_bytes(payload);repl.append(dict(e,asset='assets/'+asset,asset_sha256=H(payload)))
 report={'base_sha256':H(base),'jp_sha256':H(jp),'manifest_replacements':repl,'rows':details,'allocations':alloc,'changed_bytes':len(diffs),'unchanged_label_rows':249-len(FIXES),'scope':'Textual values only; no battle tables/code modified. Plus and all-target markers retained.'}
 (ROOT/'translation/qa05/numeric_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print('Fixed labels',len(FIXES),'allocated records',len(alloc))
if __name__=='__main__':main()
