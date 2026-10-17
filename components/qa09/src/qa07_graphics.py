"""QA07 footer: preserve glyphs; move Help 4px and Code 8px, including cursors."""
from pathlib import Path
import argparse,hashlib,json
import font_atlas_assets_v0_10_6 as f
from qa05_graphics import Face
R=Path(__file__).resolve().parents[1];H=lambda b:hashlib.sha256(b).hexdigest()
BASE='b08dc7a16a41d4e2f4d3cba345e41970f0cf4c3b75a4b218126128720ddc4ae4'
def main():
 p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--jp',type=Path,required=True);a=p.parse_args();rom=a.base.read_bytes();jp=a.jp.read_bytes();assert H(rom)==BASE;assert H(jp)=='4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed'
 q=R/'translation/qa07';q.mkdir(exist_ok=True);m=json.loads((R/'translation/lineage/en_qa06.json').read_text());es={e['id']:e for e in m['binary_entries']};e=es['program_deck_live_ui_tiles'];at=int(e['offset'],0);bank=rom[at:at+e['length']];assert H(bank)==e['asset_sha256'];mp=rom[0x4323c:0x438bc]
 canvas=[[3]*208 for _ in range(8)];details=[]
 for text,x,cols,dx in [('Chip Info',2,7,0),('Navi Help',11,7,-4),('NetNavi Code',20,8,-8)]:
  label=f.Label(text,text,x,24,cols,1,3,9,offset_y=0)
  c,metrics=Face(word_space=2 if text=='NetNavi Code' else 3).raster(label)
  target=(x-2)*8+dx
  for y,row in enumerate(c):
   for xx,v in enumerate(row):
    if v!=3:canvas[y][target+xx]=v
  details.append({'text':text,'shift_x':dx,'face_width':metrics['face_width'],'screen_x':16+target+metrics['offset'][0],'glyphs_unchanged':True})
 class Prepared:
  def raster(self,label):return canvas,{'layout':'existing glyph masks shifted, no rescaling','labels':details}
 label=f.Label('footer','Chip Info / Navi Help / NetNavi Code',2,24,26,1,3,9,background_tile=217)
 pool=f.base_pool_from_targets(mp,[label],{12,217});out,tiles,report,_=f.allocate_group(Prepared(),mp,bank,[label],pool,1,protected_ids={12,217})
 out=bytearray(out)
 for x in range(2,28):
  pos=(24*32+x)*2;word=int.from_bytes(out[pos:pos+2],'little');out[pos:pos+2]=((word&~0x1e00)|0x2800).to_bytes(2,'little')
 # The row's intervening blank cells previously used palette4; label pixels use palette5.
 assert bytes(out[:0x600])==mp[:0x600] and bytes(out[0x640:])==mp[0x640:]
 for pos in range(0,len(mp),2):
  if 0x604<=pos<0x638:continue
  w=int.from_bytes(mp[pos:pos+2],'little');v=int.from_bytes(out[pos:pos+2],'little');assert w==v
  if w&511:assert f.tile_bytes(bank,w&511,1)==f.tile_bytes(tiles,v&511,1)
 assert rom[0x36eda0:0x36eda3]==bytes([0,72,144]) and jp[0x36eda0:0x36eda3]==bytes([0,72,144])
 repl={}
 def put(key,at,b,prior=None):
  path=q/(key+'.bin');path.write_bytes(b);repl[key]={**(prior or {}),'id':key,'offset':f'0x{at:06X}','length':len(b),'expected_sha256':H(jp[at:at+len(b)]),'asset':'qa07/'+path.name,'asset_sha256':H(b)}
 put(e['id'],at,tiles,e);put('program_deck_footer_row',0x4383c,bytes(out[0x600:0x640]));put('program_deck_footer_cursor_x',0x36eda0,bytes([0,68,136]))
 m['binary_entries']=[repl.get(x['id'],x) for x in m['binary_entries']]+[x for k,x in repl.items() if k not in es];m['project_version']='0.10.7-qa07';(R/'translation/lineage/en_qa07.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
 (q/'graphics_report.json').write_text(json.dumps({'base_sha256':BASE,'labels':details,'cursor_before':[0,72,144],'cursor_after':[0,68,136],'cursor_consumer':'ROM329573 reads byte table36EDA0;329591 scales by16;329597 stores cursor coordinate. RAM E EDE/F observed via instrumented core.','rightmost_text_pixel':214,'right_margin_pixels':9,'untargeted_cells_identical':True,'allocation':report,'replacements':repl},indent=2)+'\n');print('QA07 footer generated')
if __name__=='__main__':main()
