"""QA06: changed-span isolation, all descriptor rows and scoped Host regression."""
from pathlib import Path
import argparse,json,hashlib
import numpy as np
from PIL import Image
import n1tool as n
from qa03_tooltip_fix import read_rows
ROOT=Path(__file__).resolve().parents[1];H=lambda b:hashlib.sha256(b).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--base',type=Path,required=True);ap.add_argument('--rom',type=Path,required=True);ap.add_argument('--before-ui',type=Path,required=True);ap.add_argument('--after-ui',type=Path,required=True);a=ap.parse_args();q=ROOT/'evidence/qa06';q.mkdir(exist_ok=True)
 old=json.loads((ROOT/'translation/lineage/en_qa05.json').read_text());new=json.loads((ROOT/'translation/lineage/en_qa06.json').read_text());s=a.base.read_bytes();t=a.rom.read_bytes();assert H(s)=='2ba7864b53c8cdf07b84a02e3078cd5771e7a15bea24861861876e3842742cdd';assert H(t)=='b08dc7a16a41d4e2f4d3cba345e41970f0cf4c3b75a4b218126128720ddc4ae4'
 allowed={len(t)-2,len(t)-1};changed=[]
 for k in ['entries','binary_entries']:
  assert len(old[k])==len(new[k])
  for x,y in zip(old[k],new[k]):
   assert x['id']==y['id']
   if x!=y:
    changed.append(y['id']);at=int(y['offset'],0);allowed.update(range(at,at+y['length']))
 diff={i for i,(x,y) in enumerate(zip(s,t)) if x!=y};assert diff<=allowed and len(changed)==7
 assert sum(t[:-2])&65535==int.from_bytes(t[-2:],'little')
 dec,_=n.load_table(ROOT/'tables/n1battle_jp.tbl');before,_,_=read_rows(s,dec);after,_,_=read_rows(t,dec);rows=[i for i in range(249) if before[i]!=after[i]];assert len(rows)==74
 content=json.loads((ROOT/'translation/qa06_content/report.json').read_text());assert rows==content['changed_rows'] and all(len(r)<=2 and all(len(l)<=25 for l in r) for r in after)
 masks=json.loads((q/'content/mask_verification.json').read_text());assert masks['verification_rom_sha256']==H(t) and masks['all_masks_match'] and len(masks['rows'])==249
 empties=[]
 for row in [195,196,197,199]:
  im=np.array(Image.open(q/'content'/f'synthetic_desc_{row:03d}_tooltip.png').convert('RGB'))
  black=int(np.count_nonzero(np.all(im[88:120,16:216]==0,axis=2)))
  assert black==0,(row,black)
  empties.append({'row':row,'black_text_pixels':black})
 pixels=[]
 for name in [f'host_tourney_{i:02d}' for i in range(6)]+['host_delete']:
  x=np.array(Image.open(a.before_ui/f'qa05_{name}.png').convert('RGB'));y=np.array(Image.open(a.after_ui/f'qa06_{name}.png').convert('RGB'));d=np.any(x!=y,axis=2);mask=np.zeros((144,224),bool)
  if name in ['host_tourney_00','host_tourney_01']:
   for yy in [8,24,40,56]:mask[yy:yy+16,32:104]=True
  else:
   mask[:16,56:120]=True;mask[:16,136:176 if name=='host_delete' else 168]=True
  outside=int(np.count_nonzero(d&~mask));assert outside==0,(name,outside)
  pixels.append({'screen':name,'different_pixels':int(d.sum()),'outside_target_pixels':outside})
 result={'base_rom_sha256':H(s),'rom_sha256':H(t),'changed_entries':changed,'changed_bytes':len(diff),'outside_declared_spans':len(diff-allowed),'checksum':hex(int.from_bytes(t[-2:],'little')),'description_rows_changed':len(rows),'description_rows_preserved':249-len(rows),'descriptor_runtime_rows':249,'glyph_mask_rows_nonempty':245,'empty_descriptors':4,'empty_descriptor_checks':empties,'glyph_mask_all_match':True,'content_rows':110,'chip_descriptions_complete':108,'utility_messages':2,'placeholder_descriptions':135,'ui_regression':pixels,'dialogue_font_bytes_unchanged':s[0x340310:0x348310]==t[0x340310:0x348310],'names_effect_labels_gameplay_unchanged':'Only 6 Host graphics resources plus description resource and checksum changed. No code or statistics changes.','inherited_validation':'QA05 build/save/keyboard/102-frame early route retained with byte-isolated scope; not newly rerun. Shop/UI routes from QA05 state, unchanged resources.','limits':'No natural acquisition for injected chips, full combat, full narrative, ending or hardware approval. Chip OK utility name row198 remains ambiguous.'}
 assert result['dialogue_font_bytes_unchanged'];(q/'validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
