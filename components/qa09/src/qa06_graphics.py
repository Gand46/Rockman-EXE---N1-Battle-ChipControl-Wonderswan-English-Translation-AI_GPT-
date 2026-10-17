"""QA06 bounded Host typography: 4 quantities and paired Entry Name headings."""
from pathlib import Path
import argparse,json,hashlib
import font_atlas_assets_v0_10_6 as fa
ROOT=Path(__file__).resolve().parents[1];H=lambda b:hashlib.sha256(b).hexdigest();BASE='2ba7864b53c8cdf07b84a02e3078cd5771e7a15bea24861861876e3842742cdd'
class Face:
 def __init__(self):self.glyphs=json.loads((ROOT/'translation/qa06/menu_font.json').read_text())['glyphs']
 def raster(self,l):
  gs=[self.glyphs[c] if c!=' ' else None for c in l.text];width=sum(len(g[0]) if g else 3 for g in gs)+sum(1 for i,g in enumerate(gs[:-1]) if g and gs[i+1]);w,h=l.columns*8,l.rows*8;x=(w-width)//2;y=1
  assert x>=0 and x+width<=w
  c=[[l.background]*w for _ in range(h)];cur=x
  if l.id.startswith('count_'):
   number=l.text.split()[0];nw=sum(len(self.glyphs[c][0]) for c in number)+len(number)-1;cur=18-nw
  for k,g in zip(l.text,gs):
   if g is None:
    cur=24 if l.id.startswith('count_') else cur+2
    continue
   for yy,row in enumerate(g):
    for xx,v in enumerate(row):
     if v=='#':c[y+yy-(1 if k.isdigit() else 0)][cur+xx]=l.face
   cur+=len(g[0])+1
  return c,{'face_width':width,'offset':[x,y],'capital_height':7,'digit_height':8,'baseline':y+6,'font':'BN6 menu masks + exact BN6 numeric reference'}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--base',type=Path,required=True);a=ap.parse_args();rom=a.base.read_bytes();assert H(rom)==BASE
 m=json.loads((ROOT/'translation/lineage/en_qa05.json').read_text());es={e['id']:e for e in m['binary_entries']};repl={};reports={}
 groups=[('host_entrant_count',[fa.Label('count_'+str(num),str(num)+' Navis',4,y,9 if num==128 else 8,2,bg,15,background_tile=bt) for num,y,bg,bt in [(16,1,11,10),(32,3,2,5),(64,5,11,10),(128,7,2,5)]]),('host_entry_select',[fa.Label('entry_name','Entry Name',7,0,8,2,4,8,background_tile=1),fa.Label('select','Select',17,0,4,2,4,8,background_tile=1)]),('host_entry_delete',[fa.Label('entry_name','Entry Name',7,0,8,2,3,7,background_tile=1),fa.Label('delete','Delete',17,0,5,2,3,7,background_tile=1)])]
 for name,labels in groups:
  mk=name+'_bg0_map';tk=name+'_bg0_tiles';me,te=es[mk],es[tk]
  def old(e):
   at=int(e['offset'],16);b=rom[at:at+e['length']];assert H(b)==e['asset_sha256'];return b
  mp,bank=old(me),old(te);protected={l.background_tile for l in labels};pool=fa.base_pool_from_targets(mp,labels,protected)
  out,t,r,_=fa.allocate_group(Face(),mp,bank,labels,pool,0,protected_ids=protected)
  # Exact visual equality outside label cells, even for shared tile consumers.
  targets=fa.cells_for(labels)
  for pos in range(0,len(mp),2):
   cell=(pos//2%32,pos//64)
   if cell not in targets:
    x=int.from_bytes(mp[pos:pos+2],'little');y=int.from_bytes(out[pos:pos+2],'little');assert x==y and fa.tile_bytes(bank,x&511,0)==fa.tile_bytes(t,y&511,0)
  for k,e,b in [(mk,me,out),(tk,te,t)]:
   f=ROOT/'translation/qa06'/(k+'.bin');f.write_bytes(b);repl[k]={**e,'asset':'qa06/'+f.name,'asset_sha256':H(b)}
  reports[name]=r
 (ROOT/'translation/qa06/graphics_report.json').write_text(json.dumps({'base_sha256':BASE,'replacements':repl,'validation':reports,'outside_target_cells_pixel_changes':0},indent=2)+'\n');print('Generated',len(repl),'guarded resources')
if __name__=='__main__':main()
