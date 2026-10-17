"""Bounded representative QA09 native battle conditions. Only transient inventory/deck setup."""
from pathlib import Path
import os,json,subprocess,sys,argparse,hashlib
from PIL import Image,ImageDraw
P=Path(__file__).resolve().parents[1];H=lambda x:hashlib.sha256(x).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--only',default='');a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True);state=P/'evidence/qa08/placeone/qa08_placeone_001.state';raw=state.with_suffix('.ram').read_bytes();rom=P/'build/qa08/Rockman_N1_English_QA08.wsc';cases=[('atk10',[163,163,1,1,1]),('aqua40',[167,167,8,8,8]),('wood40',[168,168,20,20,20]),('elec40',[169,169,63,63,63]),('quad',[53]*5),('stun',[72]*5),('aura80',[152]*5),('aura60',[148]*5),('crossshield',[78]*5),('meteor',[94]*5),('gaia',[1,1,175,175,175]),('gaia_next',[175,175,1,1,1]),('catcher',[115]*5),('pierce',[40]*5)];out=[]
 if a.only:cases=[x for x in cases if x[0] in a.only.split(',')]
 for name,ids in cases:
  d=a.out/name;d.mkdir(exist_ok=True);new=bytearray(raw);new[0xf37f:0xf388]=bytes(list(range(len(ids)))+[255]*(9-len(ids)));new[0xf38a:0xf398]=bytes(sum(([x,i+1] for i,x in enumerate(ids)),[])+[119,255]*(7-len(ids)));poke=[[i,raw[i],new[i]] for i in range(0xf37f,0xf398) if raw[i]!=new[i]];route=[{'poke':poke,'allowed_addresses':[x[0] for x in poke],'frames':1,'name':name+'_setup'}]
  for i,k in enumerate(['b','a','a','a']):route.extend([{'keys':[k],'frames':6},{'frames':360,'name':f'{name}_entry{i}'}])
  for i in range(70):route.extend([{'keys':['a'],'frames':6},{'frames':300,'name':f'{name}_{i:03}'}])
  f=d/'route.json';f.write_text(json.dumps(route,indent=2)+'\n');env=dict(os.environ,AUDIT_ROM_DIR=str(rom.parent),QA_CAPTURE_DIR=str(d));subprocess.run([sys.executable,str(P/'src/qa09_capture.py'),rom.stem,str(f),str(state)],env=env,check=True,stdout=subprocess.DEVNULL,timeout=45)
  # Compact contact sheet preserves complete dialog and HP strips; individual full frames included.
  fs=[d/f'{rom.stem}_{name}_{i:03}.png' for i in range(70)];sheet=Image.new('RGB',(1120,110*14),'#eee');dr=ImageDraw.Draw(sheet)
  for i,p in enumerate(fs):im=Image.open(p);x=i%5*224;y=i//5*110;sheet.paste(im.crop((0,0,224,16)),(x,y));sheet.paste(im.crop((0,80,224,144)),(x,y+16));dr.text((x,y+81),f'{name}_{i:03}',fill='black')
  sheet.save(d/'sheet.png');out.append({'case':name,'ids':ids,'route':name+'/route.json'});print(name,flush=True)
 (a.out/'provenance.json').write_text(json.dumps({'rom_sha256':H(rom.read_bytes()),'state':str(state.relative_to(P)),'state_sha256':H(state.read_bytes()),'access':'WRAM_POKE, only inventory chipIDs/assignment and deck indices. Native engine initializes stats; no HP/RNG patches; no SRAM exported.','cases':out},indent=2)+'\n')
if __name__=='__main__':main()
