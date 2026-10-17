#!/usr/bin/env python3
"""Verify native glyphs for all populated credits lines in unedited runtime captures."""
from pathlib import Path
import argparse,json,struct,hashlib
import numpy as np
from PIL import Image
import n1tool as n
P=Path(__file__).resolve().parents[1];H=lambda x:hashlib.sha256(x).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--rom',type=Path,required=True);ap.add_argument('--captures',type=Path,required=True);ap.add_argument('--prefix',required=True);ap.add_argument('--report',type=Path,required=True);a=ap.parse_args();rom=a.rom.read_bytes();dec,_=n.load_table(P/'tables/n1battle_jp.tbl');images=[(f,np.array(Image.open(f).convert('RGB')).max(axis=2)>100) for f in sorted(a.captures.glob(a.prefix+'_f*.png'))];rows=[]
 for i in range(0x96,0xd0):
  off=0x34acb0+2*struct.unpack_from('<H',rom,0x34ab10+i*2)[0];words=n.words_at(rom,off,0x34b75e);assert words[-1][1]==0x8000;codes=[w for _,w in words[:-1]];text=''.join(n.token_for(w,dec) for w in codes);matches=[]
  if codes:
   glyphs=[]
   for code in codes:
    raw=np.frombuffer(rom,np.uint8,count=64,offset=0x340310+code*64).reshape(16,4);g=np.empty((16,8),np.uint8);g[:,::2]=raw>>4;g[:,1::2]=raw&15;glyphs.append(g==1)
   template=np.concatenate(glyphs,axis=1);assert template.shape[1]<=184
   for f,pix in images:
    for y in range(129):
     if np.array_equal(template,pix[y:y+16,40:40+template.shape[1]]):matches.append({'capture':f.name,'x':40,'y':y,'different_pixels':0});break
    if matches:break
  rows.append({'slot':f'05:{i:02X}','text':text,'populated':bool(codes),'words':len(codes),'exact_native_glyph_match':bool(matches) if codes else None,'evidence':matches})
 result={'rom_sha256':H(rom),'font_sha256':H(rom[0x340310:0x348310]),'native_font':'ROM0x340310, 8x16 packed4bpp, nibble1 matches runtime white pixel; x40 source column, complete16px cells','slots':58,'populated':sum(r['populated'] for r in rows),'blank':sum(not r['populated'] for r in rows),'all_populated_masks_match':all(r['exact_native_glyph_match'] for r in rows if r['populated']),'rows':rows,'limits':'Masks corroborate glyph integrity, not linguistic review or organic progression. Scroll clipping at top/bottom is excluded by choosing a fully visible16px line.'};a.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2));assert result['all_populated_masks_match']
if __name__=='__main__':main()
