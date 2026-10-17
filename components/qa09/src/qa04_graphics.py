"""Guarded QA04 UI typography from supplied BN6 menu masks; no dialogue font edits."""
from pathlib import Path
import json,hashlib,argparse
import font_atlas_assets_v0_10_6 as fa
ROOT=Path(__file__).resolve().parents[1];H=lambda b:hashlib.sha256(b).hexdigest()
class Face:
 def __init__(self):self.glyphs=json.loads((ROOT/'translation/qa04/menu_font.json').read_text())['glyphs']
 def raster(self,l):
  gs=[self.glyphs[c] if c!=' ' else None for c in l.text];width=sum(len(g[0]) if g else 3 for g in gs)+sum(1 for i,g in enumerate(gs[:-1]) if g and gs[i+1]);w,h=l.columns*8,l.rows*8
  x=l.offset_x if l.offset_x is not None else (w-width-1)//2;y=l.offset_y if l.offset_y is not None else 1
  assert x>=0 and x+width+1<=w and y>=0 and y+8+(1 if l.outline is not None else 0)<=h,(l.id,width,w,x,y)
  c=[[l.background]*w for _ in range(h)];mask=[];cur=x
  for i,g in enumerate(gs):
   if g is None:cur+=3;continue
   for yy,row in enumerate(g):
    for xx,v in enumerate(row):
     if v=='#':mask.append((cur+xx,y+yy))
   cur+=len(g[0])+(1 if i+1<len(gs) and gs[i+1] else 0)
  if l.outline is not None:
   for xx,yy in mask:c[yy+1][xx+1]=l.outline
  for xx,yy in mask:c[yy][xx]=l.face
  return c,{'face_width':width,'cell_height':8,'cap_height':7,'offset':[x,y],'font':'BN6 menu bitmap + extensions','shadow':'1px bottom-right'}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--base',type=Path,required=True);a=ap.parse_args();rom=a.base.read_bytes();assert H(rom)=='bdfc887a2eced5692094fc596935e65ff19b447247d383234c3fd2851fb41bc8'
 m=json.loads((ROOT/'translation/lineage/en_qa03.json').read_text());es={e['id']:e for e in m['binary_entries']};report={};repl={}
 def original(k):
  e=es[k];b=rom[int(e['offset'],16):int(e['offset'],16)+e['length']];assert H(b)==e['asset_sha256'];return b
 def put(k,b):
  e=es[k];assert len(b)==e['length'];name=k+'_qa04.bin';(ROOT/'translation/assets'/name).write_bytes(b);repl[k]={**e,'asset':'assets/'+name,'asset_sha256':H(b)}
 labels=[fa.Label(k,t,2,y,9,2,9,1,offset_x=1,offset_y=0,outline=11,background_tile=6) for k,t,y in [('program','Program Deck',2),('folder','Chip Folder',5),('library','Data Library',8),('navi','NetNavi',11),('save','Save',14)]]
 mp,bank=original('pet_labels_bg0_map'),original('pet_labels_tiles');pool=fa.base_pool_from_targets(mp,labels,{6});out,tiles,rep,_=fa.allocate_group(Face(),mp,bank,labels,pool,1,protected_ids={6,0x45,0x46});put('pet_labels_bg0_map',out);put('pet_labels_tiles',tiles);report['pet']=rep
 labels=[fa.Label('register_name','Enter Name',7,0,14,2,5,8,offset_y=0,outline=2,background_tile=1)]
 mp,bank=original('name_keyboard_bg0_map'),original('name_keyboard_tiles');pool=fa.base_pool_from_targets(mp,labels,{1});out,tiles,rep,_=fa.allocate_group(Face(),mp,bank,labels,pool,1,protected_ids={0,1,*range(0x17,0x23),0x3b});put('name_keyboard_bg0_map',out);put('name_keyboard_tiles',tiles);report['keyboard_heading']=rep
 # Interior headers: correct actual runtime palette and avoid the clipped top baseline.
 import redbox_font_assets_v0_10_7_rc3 as rb
 def render_header(font,mp,bank,l):
  spec=fa.Label(l.id,l.text,0,0,l.columns,l.rows,l.background,l.face,offset_y=(0 if l.rows==1 or l.id in ('header_net','header_stats') else 1),outline=l.shadow)
  return Face().raster(spec)
 rb.render_label=render_header
 shared_ids={'auto':'program_deck_chip_folder_bg0_map','folder':'pet_submenu_chip_folder_bg0_map','backpack':'pet_submenu_backpack_bg0_map','data':'pet_submenu_data_library_bg0_map'}
 maps={k:rom[int(es[v]['offset'],16):int(es[v]['offset'],16)+0x680] for k,v in shared_ids.items()};bank=original('pet_submenu_chip_library_tiles')
 labels=[rb.MarkedLabel('header_'+k,text,k,x,0,cols,2,9,'solid',background=3) for k,text,x,cols in [('auto','Folder',10,6),('folder','Chip Folder',10,8),('data','Data Library',10,9),('backpack','Backpack',11,7)]]
 outs,tiles,rep,_=rb.allocate_group(None,maps,bank,labels,protected_ids={0x04,0x0B,0x1C,*range(0x10,0x17),*range(0x97,0xA0),*range(0xB1,0xB5)},orphan_allowlist={5,6,7,8,9,10,0xA2,0xA3,0xA4,0xA5,0xB5})
 rb.assert_untargeted_visual_cells_unchanged(maps,bank,outs,tiles,labels)
 for k,v in outs.items():
  size=es[shared_ids[k]]['length'];assert v[size:]==maps[k][size:];put(shared_ids[k],v[:size])
 put('pet_submenu_chip_library_tiles',tiles);report['shared_headers']=rep
 # NetNavi heading shared by current-status and past-results pages.
 net_ids={'net':'pet_submenu_netnavi_bg0_map','stats':'pet_submenu_netnavi_stats_bg0_map'}
 maps={k:original(v) for k,v in net_ids.items()};bank=original('pet_submenu_netnavi_tiles')
 labels=[rb.MarkedLabel('header_'+k,'NetNavi',k,11,0,6,2,3,'solid',background=8,shadow=10) for k in net_ids]
 outs,tiles,rep,_=rb.allocate_group(None,maps,bank,labels)
 rb.assert_untargeted_visual_cells_unchanged(maps,bank,outs,tiles,labels)
 for k,v in outs.items():put(net_ids[k],v)
 put('pet_submenu_netnavi_tiles',tiles);report['netnavi']=rep
 # Runtime uses fixed title IDs 4..9; preserve that mapping instead of reallocating.
 mp=original('program_deck_live_bg0_map');bank=bytearray(original('program_deck_live_ui_tiles'))
 label=fa.Label('live_header','Deck',0,0,6,1,4,12,offset_y=0)
 canvas,metrics=Face().raster(label)
 for i,pattern in enumerate(rb.canvas_patterns(canvas)):
  assert all(x in range(11,17) and y==0 for _,x,y in rb.refs({'program':rom[0x04323C:0x04323C+0x680]},4+i))
  bank[(4+i)*32:(5+i)*32]=pattern
 put('program_deck_live_ui_tiles',bytes(bank));report['live_header']={'metrics':metrics,'fixed_tile_ids':list(range(4,10)),'map_unchanged':True,'short_form':'Deck = Program Deck in editor context'}
 (ROOT/'translation/qa04/graphics_report.json').write_text(json.dumps({'replacements':repl,'validation':report},indent=2)+'\n');print('Generated',len(repl),'guarded assets')
if __name__=='__main__':main()
