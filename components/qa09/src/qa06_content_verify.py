#!/usr/bin/env python3
"""Check every displayed glyph against the original 8x16 ROM font, archive PNG evidence."""
from pathlib import Path
import argparse,hashlib,json,shutil
import numpy as np
from PIL import Image
import n1tool as n
ROOT=Path(__file__).resolve().parents[1]
def sha(x):return hashlib.sha256(x).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--rom',type=Path,required=True);ap.add_argument('--runtime',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--historical',action='store_true');a=ap.parse_args()
 rom=a.rom.read_bytes();_,enc=n.load_table(ROOT/'tables/n1battle_jp.tbl')
 from qa03_tooltip_fix import read_rows
 dec,_=n.load_table(ROOT/'tables/n1battle_jp.tbl');decoded,_,_=read_rows(rom,dec);rows={i:{'after':lines} for i,lines in enumerate(decoded)}
 runtime=json.loads((a.runtime/'runtime_report.json').read_text());out=a.out;out.mkdir(parents=True,exist_ok=True);result=[]
 if not a.historical:assert runtime['base_rom_sha256']==sha(rom)
 for r in runtime['rows']:
  row=r['row'];lines=rows[row]['after'][:2];src=Path(r['capture']);dst=out/src.name;shutil.copyfile(src,dst)
  pixels=np.array(Image.open(src).convert('RGB'));checks=[]
  for j,line in enumerate(lines):
   differences=0;cell_differences=[]
   for i,c in enumerate(line):
    glyph=enc[c];raw=np.frombuffer(rom,np.uint8,count=64,offset=0x340310+glyph*64).reshape(16,4)
    native=np.empty((16,8),np.uint8);native[:,::2]=raw>>4;native[:,1::2]=raw&15
    actual=pixels[88+j*16:104+j*16,16+i*8:24+i*8].max(axis=2)<80
    count=int(np.count_nonzero(actual!=(native==1)));differences+=count
    cell_differences.append({'character':c,'glyph':hex(glyph),'different_pixels':count})
   checks.append({'line':j+1,'text':line,'cells':len(line),'different_pixels':differences,'cell_checks':cell_differences})
  result.append({'row':row,'capture':dst.name,'capture_sha256':sha(src.read_bytes()),'lines':checks,'all_visible_glyph_masks_match':all(x['different_pixels']==0 for x in checks),'all_declared_lines_visible':len(rows[row]['after'])<=2,'inherited_third_line_still_not_shown':len(rows[row]['after'])>2})
 state=Path(runtime['base_state']);shutil.copyfile(state,out/'base_pet104.state')
 (out/'runtime_provenance.json').write_text(json.dumps(runtime,indent=2)+'\n')
 shutil.copyfile(a.runtime/'synthetic_route.json',out/'synthetic_route.json')
 report={'verification_rom_sha256':sha(rom),'font_region':'0x340310; 512 glyphs * 64 bytes, 8x16 packed 4bpp','font_sha256':sha(rom[0x340310:0x340310+512*64]),'method':'Native glyph nibble1 vs rendered black pixel at x16+8*i, y88+16*line; exact masks, no OCR. Runtime uses original font with palette2/3.','savestate_pointer_injection':True,'historical_reinspection':a.historical,'rows':result,'all_masks_match':all(x['all_visible_glyph_masks_match'] for x in result),'limits':'Descriptor carrier is MegaMan; displayed card artwork, label and stats are carrier values. Does not establish natural acquisition or gameplay power. Empty rows have no glyphs to compare; counts are separated in the QA06 validation.'}
 (out/'mask_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'rows':len(result),'all_masks_match':report['all_masks_match'],'out':str(out)},indent=2))
 assert report['all_masks_match']
if __name__=='__main__':main()
