"""Verify final QA09 roster masks and transfer of the continuous ending evidence."""
from pathlib import Path
import hashlib,json,numpy as np
from PIL import Image
import n1tool as n
from qa09_paths import qa08_rom
P=Path(__file__).resolve().parents[1];O=P/'evidence/qa09/astra_ending';H=lambda x:hashlib.sha256(x).hexdigest()
def main():
 rom=(P/'build/qa09/Rockman_N1_English_QA09.wsc').read_bytes();old=qa08_rom(P).read_bytes()
 assert H(rom)=='d729823bbe6cf9132e6345ed734eb2dbe51885c13d5a17a44a9f7cfae086c326' and H(old)=='41d7fc75e327ad15b72c7f6fc7119e031d6af8cfdb1527eb547b3c86d7cc32dc'
 _,enc=n.load_table(P/'tables/n1battle_jp.tbl');pixels=np.array(Image.open(O/'notices_final/en_host_navi_roster_full_page00.png').convert('RGB'));checks=[]
 for j,line in enumerate(['Navi list full.','Use Delete for','unneeded data.']):
  cells=[]
  for i,c in enumerate(line):
   raw=np.frombuffer(rom,np.uint8,count=64,offset=0x340310+enc[c]*64).reshape(16,4);native=np.empty((16,8),np.uint8);native[:,::2]=raw>>4;native[:,1::2]=raw&15
   actual=pixels[88+j*16:104+j*16,56+i*8:64+i*8].max(axis=2)<80
   cells.append({'glyph':c,'different_pixels':int(np.count_nonzero(actual!=(native==1)))})
  checks.append({'text':line,'cells':len(line),'different_pixels':sum(c['different_pixels'] for c in cells),'glyphs':cells})
 assert all(c['different_pixels']==0 for c in checks)
 (O/'notices_final/glyph_verification.json').write_text(json.dumps({'rom_sha256':H(rom),'method':'Native font nibble1 vs black runtime pixels x56+8*i,y88+16*j','lines':checks,'status':'PASS_SYNTHETIC'},indent=2)+'\n')
 ranges=[(0x32cf33,0x32f2d1),(0x33ace8,0x33aeea),(0x371c00,0x371ca0),(0x353b12,0x354000),(0x34ab10,0x34b75e),(0x340310,0x348310)];transfer=[]
 for a,b in ranges:
  assert rom[a:b]==old[a:b];transfer.append({'start':hex(a),'end_exclusive':hex(b),'sha256':H(rom[a:b])})
 diffs=[i for i,(a,b) in enumerate(zip(old,rom)) if a!=b]
 assert all(0x3577fe<=i<0x3577fe+94 or 0x36a4e0<=i<0x36a4e0+15592 or i>=len(rom)-2 for i in diffs)
 (O/'qa09_transfer.json').write_text(json.dumps({'qa08_sha256':H(old),'qa09_sha256':H(rom),'changed_bytes':len(diffs),'only_roster_and_description_resource_plus_checksum':True,'ending_and_credits_inheritance':'PASS; continuous QA08 execution transfers through exact unchanged consumers, final scripts, font and credits pool. Sequence not rerun on QA09.','unchanged_ranges':transfer},indent=2)+'\n')
 print('PASS: roster three lines exact; ending/credits transfer exact')
if __name__=='__main__':main()
