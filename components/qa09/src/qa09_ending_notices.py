#!/usr/bin/env python3
"""Synthetic native dialogue audit: redirect intro new-mail pointer, never publish probe ROMs."""
from pathlib import Path
import argparse,json,struct,hashlib,subprocess,os,sys,shutil
import n1tool as n
P=Path(__file__).resolve().parents[1];H=lambda b:hashlib.sha256(b).hexdigest()
IDS=['ui_save_failed','host_save_failed','host_navi_roster_full']
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--en',type=Path,required=True);ap.add_argument('--jp',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--only');a=ap.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True);romdir=out/'diagnostic_roms';romdir.mkdir(exist_ok=True)
 dec,_=n.load_table(P/'tables/n1battle_jp.tbl');entries={e['id']:e for e in json.loads((P/'translation/lineage/en_qa06.json').read_text())['entries']};records=[]
 fresh=json.loads((P/'qa/routes/qa03_fresh.json').read_text());stop=next(i for i,s in enumerate(fresh) if s.get('name')=='017');cold=[{k:v for k,v in s.items() if k!='name'} for s in fresh[:stop+1]]
 # Let the opening transition finish and the first intro page type fully.
 cold[-1]['frames']=900
 for ident in ([a.only] if a.only else IDS):
  target=int(entries[ident]['offset'],0)
  for lang,source in [('en',a.en),('jp',a.jp)]:
   raw=source.read_bytes();r=bytearray(raw);g=n.TEXT_GROUPS[0];slots=[i for i in range(g.pointer_count) if g.base+struct.unpack_from('<H',r,g.pointer_table+i*2)[0]*2==0x34bce6];assert len(slots)==1
   ptr=g.pointer_table+2*slots[0];delta=target-g.base;assert delta>=0 and delta%2==0 and delta//2<=0xffff
   words=n.words_at(raw,target,min(target+2048,len(raw)));assert words[-1][1]==0x8000
   pages=1+sum(w==0x4000 for _,w in words);struct.pack_into('<H',r,ptr,delta//2);struct.pack_into('<H',r,len(r)-2,sum(r[:-2])&65535)
   changes=[i for i,(x,y) in enumerate(zip(raw,r)) if x!=y];assert set(changes)<={ptr,ptr+1,len(r)-2,len(r)-1}
   name=f'{lang}_{ident}';rom=romdir/(name+'.wsc');rom.write_bytes(r);steps=[dict(x) for x in cold];steps[-1]['name']='page00'
   for page in range(1,pages):steps.extend([{'frames':6,'keys':['a']},{'frames':360,'name':f'page{page:02d}'}])
   route=out/(name+'_route.json');route.write_text(json.dumps(steps,indent=2)+'\n');env=dict(os.environ,AUDIT_ROM_DIR=str(romdir),QA_CAPTURE_DIR=str(out))
   subprocess.run([sys.executable,str(P/'src/qa03_capture.py'),name,str(route)],env=env,check=True,stdout=subprocess.DEVNULL,timeout=60)
   records.append({'id':ident,'lang':lang,'source_rom_sha256':H(raw),'diagnostic_sha256':H(r),'carrier_slot':f'00:{slots[0]:02X}','pointer':hex(ptr),'target':hex(target),'changed_offsets':[hex(i) for i in changes],'expected_pages':pages,'decoded_script':''.join(n.token_for(w,dec) for _,w in words),'route':route.name,'capture_pattern':name+'_pageNN.png'})
   rom.unlink();print(name,pages,flush=True)
 (out/'provenance.json').write_text(json.dumps({'access':'SYNTHETIC POINTER_INJECTION; cold boot with no SRAM/savestate; original intro new-mail pointer redirected to exception message. Native dialogue consumer, original message bytes unmodified. Background/progression/dynamic variables are carrier context, NOT late-game completion.','engine_sha256':H((P/'qa/emulator/mednafen_wswan_libretro.so').read_bytes()),'records':records},ensure_ascii=False,indent=2)+'\n');shutil.rmtree(romdir)
if __name__=='__main__':main()
