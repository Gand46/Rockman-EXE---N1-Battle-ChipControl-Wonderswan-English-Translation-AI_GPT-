"""Four native engine condition probes; transient deck/inventory IDs only."""
from pathlib import Path
import json,os,subprocess,hashlib,sys,argparse
from PIL import Image,ImageDraw
P=Path(__file__).resolve().parents[1];H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--rom',type=Path,required=True);ap.add_argument('--state',type=Path,required=True);ap.add_argument('--ram',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();o=a.out.resolve();o.mkdir(parents=True,exist_ok=True);rd=o/'roms';rd.mkdir(exist_ok=True);(rd/'qa08.wsc').write_bytes(a.rom.read_bytes());raw=a.ram.read_bytes();assert raw[0xf38a:0xf398]==bytes.fromhex('01010402010604ff10ff17ff7703');records=[]
 for name,ids in [('fire_base',[12,1,119]),('fire_boost',[12,166,119]),('fire_reverse',[166,12,119]),('reflect',[114,119,1])]:
  d=o/name;d.mkdir(exist_ok=True);new=bytearray(raw);new[0xf37f:0xf388]=bytes([0,1,2]+[255]*6);new[0xf38a:0xf398]=bytes(sum(([x,i+1] for i,x in enumerate(ids)),[])+[4,255,16,255,23,255,119,255]);poke=[[i,raw[i],new[i]] for i in range(0xf37f,0xf398) if raw[i]!=new[i]]
  route=[{'poke':poke,'frames':1,'name':name+'_injected'}]
  for i,k in enumerate(['b','a','a','a']):route.extend([{'keys':[k],'frames':6},{'frames':360,'name':f'{name}_entry{i}'}])
  for i in range(140):route.extend([{'keys':['a'],'frames':6},{'frames':300,'name':f'{name}_{i:03}'}])
  f=d/'route.json';f.write_text(json.dumps(route,indent=2)+'\n');env=dict(os.environ,AUDIT_ROM_DIR=str(rd),QA_CAPTURE_DIR=str(d));subprocess.run([sys.executable,str(P/'src/qa08_battle_capture.py'),'qa08',str(f),str(a.state.resolve())],env=env,stdout=subprocess.DEVNULL,check=True,timeout=60)
  fs=[d/f'qa08_{name}_{i:03}.png' for i in range(0,140,3)];s=Image.new('RGB',(1120,172*((len(fs)+4)//5)),'#eee');draw=ImageDraw.Draw(s)
  for i,f in enumerate(fs):x=i%5*224;y=i//5*172;s.paste(Image.open(f),(x,y));draw.text((x,y+144),f.stem,fill='black')
  s.save(d/'sheet.png');records.append({'case':name,'chip_ids':ids,'writes':poke,'route':name+'/route.json'});print(name,flush=True)
 (o/'provenance.json').write_text(json.dumps({'access':'WRAM_POKE; native battle from natural final preparation, only deck indices and inventory IDs; no HP/statistics/RNG changes; no SRAM exported','rom_sha256':H(a.rom),'state_sha256':H(a.state),'ram_sha256':H(a.ram),'engine_sha256':H(P/'qa/emulator/mednafen_wswan_libretro.so'),'cases':records},indent=2)+'\n');(rd/'qa08.wsc').unlink();rd.rmdir()
if __name__=='__main__':main()
