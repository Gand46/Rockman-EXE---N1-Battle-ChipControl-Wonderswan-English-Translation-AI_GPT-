"""QA05: full headings and Save, guarded on QA04; packed tiles use runtime ID - first_id."""
from pathlib import Path
import argparse,hashlib,json
import font_atlas_assets_v0_10_6 as fa
from qa04_graphics import Face as BaseFace
ROOT=Path(__file__).resolve().parents[1];H=lambda b:hashlib.sha256(b).hexdigest()
class Face(BaseFace):
 def __init__(self,word_space=3):
  self.glyphs=json.loads((ROOT/'translation/qa05/menu_font.json').read_text())['glyphs'];self.word_space=word_space
 def raster(self,l):
  gs=[self.glyphs[c] if c!=' ' else None for c in l.text];width=sum(len(g[0]) if g else self.word_space for g in gs)+sum(1 for i,g in enumerate(gs[:-1]) if g and gs[i+1]);w,h=l.columns*8,l.rows*8
  x=l.offset_x if l.offset_x is not None else (w-width-1)//2;y=l.offset_y if l.offset_y is not None else 1
  assert x>=0 and x+width+1<=w and y>=0 and y+8+(1 if l.outline is not None else 0)<=h,(l.id,width,w,x,y)
  c=[[l.background]*w for _ in range(h)];mask=[];cur=x
  for i,g in enumerate(gs):
   if g is None:cur+=self.word_space;continue
   for yy,row in enumerate(g):
    for xx,v in enumerate(row):
     if v=='#':mask.append((cur+xx,y+yy))
   cur+=len(g[0])+(1 if i+1<len(gs) and gs[i+1] else 0)
  if l.outline is not None:
   for xx,yy in mask:c[yy+1][xx+1]=l.outline
  for xx,yy in mask:c[yy][xx]=l.face
  return c,{'face_width':width,'cell_height':8,'cap_height':7,'offset':[x,y],'font':'BN6 menu bitmap + extensions','shadow':'1px bottom-right'}
BASE='822467360f2b4aa7e9e173e7606a0e18d74b3e1bb5b42063f695e77e37449c8b'
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--base',type=Path,required=True);ap.add_argument('--jp',type=Path,required=True);a=ap.parse_args();rom=a.base.read_bytes();assert H(rom)==BASE
 jp=a.jp.read_bytes();assert H(jp)=='4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed'
 m=json.loads((ROOT/'translation/lineage/en_qa04.json').read_text());es={e['id']:e for e in m['binary_entries']};repl={};report={}
 def original(k):
  e=es[k];o=int(e['offset'],16);b=rom[o:o+e['length']];assert H(b)==e['asset_sha256'];return b
 def put(k,b):
  e=es[k];assert len(b)==e['length'];name=k+'_qa05.bin';(ROOT/'translation/assets'/name).write_bytes(b);repl[k]={**e,'asset':'assets/'+name,'asset_sha256':H(b)}
 # Save's bank starts at runtime tile 0. Preserve all progress/statistic tiles.
 labels=[fa.Label('save_header','Save',12,0,4,2,2,11,offset_y=0,outline=1,background_tile=1)]
 mp,bank=original('pet_submenu_save_bg0_map'),original('pet_submenu_save_tiles')
 pool=fa.base_pool_from_targets(mp,labels,{1});o,t,r,_=fa.allocate_group(Face(),mp,bank,labels,pool,0,protected_ids={1,0x0c,0x0d,0x29,0x30,0x35})
 put('pet_submenu_save_bg0_map',o);put('pet_submenu_save_tiles',t);report['save']=r
 # Copy the already rendered full shared title into the editor subpanel.
 src=original('pet_submenu_chip_folder_bg0_map');mp=original('program_deck_chip_folder_bg0_map');o=bytearray(mp)
 for y in range(2):
  for x in range(10,18):
   pos=(y*32+x)*2;o[pos:pos+2]=src[pos:pos+2]
 put('program_deck_chip_folder_bg0_map',bytes(o));report['folder']={'text':'Chip Folder','copied_cells':[10,0,8,2],'source':'pet_submenu_chip_folder_bg0_map','bank_unchanged':True}
 # Program Deck bank is loaded one tile after VRAM base. QA04 used zero-based
 # asset IDs as map IDs: that is why a residual P remained to the left of Deck.
 key='program_deck_live_bg0_map';mp=original(key);bank=original('program_deck_live_ui_tiles');full=rom[0x4323c:0x438bc];assert full[:len(mp)]==mp
 # Two blank runtime IDs C/D are identical. Redirect all D consumers to C,
 # freeing D without erasing artwork. B is a retired title glyph with no map refs.
 assert fa.tile_bytes(bank,0x0c,1)==fa.tile_bytes(bank,0x0d,1)==bytes([0x44])*32
 assert fa.refs(full,0x0b)==[]
 remapped=bytearray(full);aliases=[]
 for pos in range(0,len(full),2):
  w=int.from_bytes(full[pos:pos+2],'little')
  if w&511==0x0d:
   remapped[pos:pos+2]=((w&~511)|0x0c).to_bytes(2,'little');aliases.append([pos//2%32,pos//64])
 labels=[fa.Label('live_header','Program Deck',10,0,9,1,4,12,offset_y=0,background_tile=0x0c)]
 o,t,r,_=fa.allocate_group(Face(),bytes(remapped),bank,labels,tuple(range(4,12))+(13,),1,protected_ids={0x0c,0xe8,0xe9})
 # Footer labels are displayed from map row24 while the tooltip scrolls in.
 # Correct the inherited +1 slot error and reuse the same BN6 heading masks.
 tb=bytearray(t);om=bytearray(o);footer=[];footer_cells=set()
 for text,x,ids in [('Chip Info',2,tuple(range(0xe2,0xe9))),('Navi Help',11,(0xce,0xcf,0xd4,0xd5,0xd6,0xd7,0xd8)),('NetNavi Code',20,tuple(range(0xeb,0xf3)))]:
  label=fa.Label('footer',text,x,24,len(ids),1,3,9,offset_y=0)
  canvas,metrics=Face(word_space=2 if text=='NetNavi Code' else 3).raster(label)
  metrics['word_spacing']=2 if text=='NetNavi Code' else 3
  for j,(tid,pattern) in enumerate(zip(ids,fa.canvas_patterns(canvas))):
   assert all(y==24 and ((2<=xx<=8) or (11<=xx<=17) or (20<=xx<=27)) for xx,y in fa.refs(full,tid)),(tid,fa.refs(full,tid))
   fa.put_tile(tb,tid,1,pattern);footer_cells.add((x+j,24))
   pos=(24*32+x+j)*2;word=int.from_bytes(full[pos:pos+2],'little');om[pos:pos+2]=((word&~511)|tid).to_bytes(2,'little')
  footer.append({'text':text,'metrics':metrics,'runtime_tile_ids':list(ids)})
 t=bytes(tb);o=bytes(om);report['footer']=footer
 # Verify final pixels of every static map cell outside explicit labels.

 for pos in range(0,len(full),2):
  x,y=pos//2%32,pos//64
  if (y==0 and 10<=x<19) or (x,y) in footer_cells:continue
  wa=int.from_bytes(full[pos:pos+2],'little');wb=int.from_bytes(o[pos:pos+2],'little')
  assert wa&~511==wb&~511
  if wa&511:assert fa.tile_bytes(bank,wa&511,1)==fa.tile_bytes(t,wb&511,1),(x,y,wa,wb)
 assert o[len(mp):0x600]==full[len(mp):0x600] and o[0x640:]==full[0x640:]

 put(key,o[:len(mp)]);put('program_deck_live_ui_tiles',t)
 report['editor']={'allocation':r,'first_runtime_tile':1,'blank_aliases_redirected':aliases,'untargeted_static_cells_pixel_equal':True,'title_full_width_px':67,'retired_title_tile_reused':'0x00B'}
 (ROOT/'translation/qa05/graphics_report.json').write_text(json.dumps({'base_rom_sha256':BASE,'replacements':repl,'validation':report},indent=2)+'\n')
 m['binary_entries']=[repl.get(e['id'],e) for e in m['binary_entries']]+[e for k,e in repl.items() if k not in es];m['project_version']='0.10.7-qa05'
 (ROOT/'translation/lineage/en_qa05.json').write_text(json.dumps(m,indent=2,ensure_ascii=False)+'\n')
 print('Generated',len(repl),'assets')
if __name__=='__main__':main()
