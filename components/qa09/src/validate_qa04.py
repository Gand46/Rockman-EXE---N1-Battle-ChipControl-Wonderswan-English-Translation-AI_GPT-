"""Validate scoped QA04 binary changes and evidence; use --base QA03 --rom QA04."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--base',type=Path,required=True);ap.add_argument('--rom',type=Path,required=True);ap.add_argument('--captures',type=Path,default=ROOT/'evidence/qa04');a=ap.parse_args();q=a.captures
 old=json.loads((ROOT/'translation/lineage/en_qa03.json').read_text());new=json.loads((ROOT/'translation/lineage/en_qa04.json').read_text());s=a.base.read_bytes();t=a.rom.read_bytes();assert hashlib.sha256(s).hexdigest()=='bdfc887a2eced5692094fc596935e65ff19b447247d383234c3fd2851fb41bc8'
 allowed={len(t)-2,len(t)-1};changed=[]
 for k in ['entries','binary_entries']:
  for x,y in zip(old[k],new[k]):
   assert x['id']==y['id']
   if x!=y:
    changed.append(y['id']);off=int(y['offset'],16);allowed.update(range(off,off+y['length']))
 diff={i for i,(x,y) in enumerate(zip(s,t)) if x!=y};assert diff<=allowed
 assert sum(t[:-2])&65535==int.from_bytes(t[-2:],'little')
 black=lambda f:np.array(Image.open(f))[:,:,:3].max(2)<80
 jp,en=black(ROOT/'evidence/qa03/before/jp_130.png'),black(q/'qa04_130.png');caps=[]
 for i,c in enumerate('ABCDEFGHIJKLMNOPQRSTUVWXYZ'):
  x=24+16*(i%10);y=88+16*(i//10);caps.append(bool(np.array_equal(jp[y:y+16,x:x+8],en[y-32:y-16,x:x+8])))
 jp,en=black(ROOT/'evidence/qa03/before/jp_109.png'),black(q/'qa04_039.png');digits=[bool(np.array_equal(jp[56:72,24+16*i:32+16*i],en[120:136,24+16*i:32+16*i])) for i in range(10)]
 saved=np.array(Image.open(q/'qa04_save_done.png'));loaded=np.array(Image.open(q/'qa04_cold_save_summary.png'));same=bool(np.array_equal(saved[20:77,8:216],loaded[20:77,8:216]));assert all(caps+digits) and same
 r={'rom_sha256':hashlib.sha256(t).hexdigest(),'changed_entries':changed,'changed_bytes_from_qa03':len(diff),'changes_outside_declared_spans':len(diff-allowed),'native_caps_equal':sum(caps),'native_digits_equal':sum(digits),'cold_save_summary_pixels_equal':same,'checksum':hex(int.from_bytes(t[-2:],'little')),'scope':'Sample UI and early save; 11 family effect omissions remain; no full-game certification'}
 (q/'validation.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
if __name__=='__main__':main()
