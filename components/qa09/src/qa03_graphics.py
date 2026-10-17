"""Rebuild QA01 graphics from editable native-derived glyph masks.
No TTF dependency, scaling, or changes to the dialogue font. Guard A9 inputs.
"""
from pathlib import Path
import json,hashlib,argparse
import font_atlas_assets_v0_10_6 as fa
ROOT=Path(__file__).resolve().parents[1]
H=lambda b:hashlib.sha256(b).hexdigest()
class Face:
 def __init__(self,compact=False):self.glyphs=json.loads((ROOT/'translation/qa03'/('compact_display_font.json' if compact else 'native_display_font.json')).read_text())['glyphs']
 def raster(self,l):
  space=6 if l.id.startswith('title_') else (4 if l.id.startswith('manual_') else 3);gs=[self.glyphs[c] if c!=' ' else None for c in l.text];width=sum(len(g[0]) if g else space for g in gs)+sum(1 for i,g in enumerate(gs[:-1]) if g and gs[i+1]);height=len(next(g for g in gs if g));w,h=l.columns*8,l.rows*8
  x=l.offset_x if l.offset_x is not None else (w-width)//2;y=l.offset_y if l.offset_y is not None else (h-height)//2
  assert x>=1 and x+width<w and y>=1 and y+height<h,(l.id,width,w,height,h,x,y)
  mask=set();cur=x
  for i,g in enumerate(gs):
   if g is None:cur+=space;continue
   for yy,row in enumerate(g):
    for xx,v in enumerate(row):
     if v=='#':mask.add((cur+xx,y+yy))
   cur+=len(g[0])+(1 if i+1<len(gs) and gs[i+1] else 0)
  c=[[l.background]*w for _ in range(h)]
  if l.outline is not None:
   for xx,yy in mask:
    for dx,dy in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(1,-1),(-1,1),(1,1)]:
     if 0<=xx+dx<w and 0<=yy+dy<h:c[yy+dy][xx+dx]=l.outline
  for xx,yy in mask:c[yy][xx]=l.face
  return c,{'face_width':width,'face_height':height,'offset':[x,y],'font':'native-derived compact' if height==7 else 'native manual Latin + explicit extensions'}
def pack(c,order=None):
 rows=len(c)//8;cols=len(c[0])//8;order=order or [(x,y) for y in range(rows) for x in range(cols)]
 return b''.join(fa.pack_tile([c[y*8+dy][x*8+dx] for dy in range(8) for dx in range(8)]) for x,y in order)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--base',type=Path,required=True);a=ap.parse_args();rom=a.base.read_bytes();assert H(rom)=='27c189a8303ff1ba75a624ea686380c3d9bff618da2a06d8e3e1b0d8ceda53f6'
 m=json.loads((ROOT/'translation/lineage/en_v0_10_7_graphics_a9.json').read_text());es={e['id']:e for e in m['binary_entries']};report={};repl={}
 def original(k):
  e=es[k];b=rom[int(e['offset'],16):int(e['offset'],16)+e['length']];assert H(b)==e['asset_sha256'];return b
 def put(k,b):
  e=es[k];assert len(b)==e['length'];name=k+'_qa03.bin';(ROOT/'translation/assets'/name).write_bytes(b);repl[k]={**e,'asset':'assets/'+name,'asset_sha256':H(b)}
 # Title sprite allocation observed directly in A9 RAM at 0x1c10, x76,y92.
 order=[(x,y) for base in (0,4) for y in range(2) for x in range(base,base+4)]+[(8,0),(8,1)]
 for word,text in [('new_game','NEW GAME'),('continue','CONTINUE')]:
  for state in ['selected','unselected']:
   k='title_'+word+'_'+state;old=original(k);face=3 if state=='selected' else 2
   # Preserve original state's actual palette indices (unselected uses index2).
   values={v for b in old for v in (b>>4,b&15)};face=max(values)
   l=fa.Label(k,text,0,0,9,2,0,face,outline=1)
   canvas,metrics=Face().raster(l);put(k,pack(canvas,order));report[k]={'metrics':metrics,'palette':sorted(values),'sprite_tile_order':order}
 # PET: extend each label rectangle only into the existing empty interior, ending before x88 frame.
 labels=[fa.Label(k,t,2,y,9,2,9,1,offset_x=1,offset_y=1,outline=11,background_tile=6) for k,t,y in [('program','PROGRAM DECK',2),('folder','CHIP FOLDER',5),('library','DATA LIBRARY',8),('navi','NETNAVI',11),('save','SAVE',14)]]
 mp,bank=original('pet_labels_bg0_map'),original('pet_labels_tiles');pool=fa.base_pool_from_targets(mp,labels,{6});out,tiles,rep,_=fa.allocate_group(Face(True),mp,bank,labels,pool,1,protected_ids={6,0x45,0x46})
 put('pet_labels_bg0_map',out);put('pet_labels_tiles',tiles);report['pet']=rep
 # Entry heading: one native-weight line, leaving keyboard and its 36 verified glyphs untouched.
 labels=[fa.Label('register_name','ENTER NAME',7,0,14,2,5,8,offset_y=1,outline=2,background_tile=1)]
 mp,bank=original('name_keyboard_bg0_map'),original('name_keyboard_tiles');pool=fa.base_pool_from_targets(mp,labels,{1});out,tiles,rep,_=fa.allocate_group(Face(True),mp,bank,labels,pool,1,protected_ids={0,1,*range(0x17,0x23),0x3b})
 put('name_keyboard_bg0_map',out);put('name_keyboard_tiles',tiles);report['keyboard_heading']=rep
 # Independent 128x16 manual cover label bank; preserve palette and tile order.
 for k in ['manual_header_first_cover','manual_header_final_cover']:
  original(k);l=fa.Label(k,'PROGRAM DECK MANUAL',0,0,16,2,5,14,outline=2);canvas,metrics=Face().raster(l);put(k,pack(canvas));report[k]=metrics
 # Shared and live headers retain A9: runtime QA rejected the experimental two-line layout.
 (ROOT/'translation/qa03/graphics_report.json').write_text(json.dumps({'replacements':repl,'validation':report},indent=2)+'\n')
 print('Generated',len(repl),'guarded assets')
if __name__=='__main__':main()
