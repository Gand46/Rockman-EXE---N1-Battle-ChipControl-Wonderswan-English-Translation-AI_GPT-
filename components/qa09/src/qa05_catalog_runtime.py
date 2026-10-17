"""Render all 113 populated card names/effect labels by pointer injection on MegaMan.
Statistics/art remain the carrier; this is not inventory acquisition or combat QA.
"""
from pathlib import Path
import json,hashlib,subprocess,sys,os,argparse
import bcc_reference as b,n1tool as n
ROOT=Path(__file__).resolve().parents[1];H=lambda x:hashlib.sha256(x).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--rom',type=Path,required=True);ap.add_argument('--state',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--rows',required=True);a=ap.parse_args()
 raw=a.rom.read_bytes();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);route=out/'route.json';route.write_text(json.dumps([{'frames':8},{'frames':6,'keys':['a']},{'frames':100,'name':'card'}]));datafile=out/'probe.wsc';result=[]
 for row in map(int,a.rows.split(',')):
  assert 0<=row<249;data=bytearray(raw);allowed={len(raw)-2,len(raw)-1}
  for table in [b.CHIP_NAMES.pointer_start,b.EFFECT_LABELS.pointer_start]:
   start=table+200*4;source=table+row*4;data[start:start+4]=raw[source:source+4];allowed.update(range(start,start+4))
  n.repair_checksum(data);diff=[i for i,(x,y) in enumerate(zip(raw,data)) if x!=y];assert set(diff)<=allowed;datafile.write_bytes(data)
  env=dict(os.environ,AUDIT_ROM_DIR=str(out),QA_CAPTURE_DIR=str(out))
  subprocess.run([sys.executable,str(ROOT/'src/qa03_capture.py'),'probe',str(route),str(a.state.resolve())],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=True,timeout=30)
  png=out/f'row_{row:03d}.png';(out/'probe_card.png').replace(png)
  result.append({'row':row,'diagnostic_sha256':H(data),'changed_offsets':[hex(i) for i in diff],'image':png.name,'sha256':H(png.read_bytes())})
 datafile.unlink();(out/'probe_card.state').unlink();(out/'probe_card.ram').unlink()
 (out/'runtime.json').write_text(json.dumps({'method':'SAVESTATE / POINTER_INJECTION','base_rom_sha256':H(raw),'base_state_sha256':H(a.state.read_bytes()),'carrier':'MegaMan; art/stats are not the injected chip','rows':result},indent=2)+'\n');print('Rendered',len(result),'rows',out)
if __name__=='__main__':main()
