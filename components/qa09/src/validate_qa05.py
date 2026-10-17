"""Scoped QA05 verification: binary bounds, fonts, runtime, save and regressions."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--base',type=Path,required=True);ap.add_argument('--rom',type=Path,required=True);a=ap.parse_args();q=ROOT/'evidence/qa05';oldq=ROOT/'evidence/qa04'
 old=json.loads((ROOT/'translation/lineage/en_qa04.json').read_text());new=json.loads((ROOT/'translation/lineage/en_qa05.json').read_text());s=a.base.read_bytes();t=a.rom.read_bytes();sha=lambda b:hashlib.sha256(b).hexdigest()
 assert sha(s)=='822467360f2b4aa7e9e173e7606a0e18d74b3e1bb5b42063f695e77e37449c8b'
 assert sha(t)=='2ba7864b53c8cdf07b84a02e3078cd5771e7a15bea24861861876e3842742cdd'
 allowed={len(t)-2,len(t)-1};changed=[]
 for k in ['entries','binary_entries']:
  assert len(old[k])==len(new[k])
  for x,y in zip(old[k],new[k]):
   assert x['id']==y['id']
   if x!=y:
    changed.append(y['id']);off=int(y['offset'],16);allowed.update(range(off,off+y['length']))
 diff={i for i,(x,y) in enumerate(zip(s,t)) if x!=y};assert diff<=allowed and len(changed)==8
 assert sum(t[:-2])&65535==int.from_bytes(t[-2:],'little')
 arr=lambda p:np.array(Image.open(p).convert('RGB'))
 black=lambda p:arr(p).max(2)<80
 jp,en=black(ROOT/'evidence/qa03/before/jp_130.png'),black(q/'qa05_130.png');caps=[]
 for i in range(26):
  x=24+16*(i%10);y=88+16*(i//10);caps.append(bool(np.array_equal(jp[y:y+16,x:x+8],en[y-32:y-16,x:x+8])))
 jp,en=black(ROOT/'evidence/qa03/before/jp_109.png'),black(q/'qa05_039.png');digits=[bool(np.array_equal(jp[56:72,24+16*i:32+16*i],en[120:136,24+16*i:32+16*i])) for i in range(10)]
 same=bool(np.array_equal(arr(q/'qa05_save_done.png')[20:77,8:216],arr(q/'qa05_cold_save_summary.png')[20:77,8:216]));assert same and all(caps+digits)
 fresh=[]
 for i in range(1,105):
  f=oldq/f'qa04_{i:03d}.png';g=q/f'qa05_{i:03d}.png'
  if f.exists() and g.exists():fresh.append({'frame':i,'equal':bool(np.array_equal(arr(f),arr(g)))})
 assert all(x['equal'] for x in fresh)
 masks=json.loads((q/'content_final/mask_verification.json').read_text());assert masks['verification_rom_sha256']==sha(t) and masks['all_masks_match'] and len(masks['rows'])==34
 assert all(len(x['lines'])==2 and all(l['cells']<=25 and l['different_pixels']==0 for l in x['lines']) for x in masks['rows'])
 nums=json.loads((ROOT/'translation/qa05/numeric_report.json').read_text());catalog=json.loads((q/'catalog_final/runtime.json').read_text());assert len(catalog['rows'])==len(nums['rows'])==23 and catalog['base_rom_sha256']==sha(t)
 names=[x for x in json.loads((q/'catalog_inventory.json').read_text()) if x['name']!='NO DATA'];assert len(names)==113 and max(len(x['name']) for x in names)<=8
 # Name strings and renderer unchanged after the 113-row runtime sweep.
 name_entries=[e for e in new['binary_entries'] if 'name' in e['id']];assert all(e in old['binary_entries'] for e in name_entries)
 r={'rom_sha256':sha(t),'changed_entries':changed,'changed_bytes_from_qa04':len(diff),'changes_outside_declared_spans':len(diff-allowed),'native_caps_equal':sum(caps),'native_digits_equal':sum(digits),'cold_save_summary_pixels_equal':same,'fresh_route_identical_frames':len(fresh),'fresh_route':fresh,'descriptions_two_lines_exact_masks':34,'numeric_labels_corrected_and_captured':23,'catalog_names_runtime_fit':113,'catalog_max_name_cells':max(len(x['name']) for x in names),'checksum':hex(int.from_bytes(t[-2:],'little')),'scope':'Reported QA05 titles, footer, 34 descriptions, 23 effect labels, 113 name widths, early save. Synthetic pointer carriers for catalog/descriptions. Full-game linguistic audit, natural acquisition, combat and hardware NOT_VALIDATED.'}
 (q/'validation.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='fresh_route'}))
if __name__=='__main__':main()
