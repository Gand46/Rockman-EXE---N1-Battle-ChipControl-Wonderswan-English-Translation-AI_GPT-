"""Verify QA09 exact change scope, evidence transfer and inherited cold SRAM."""
from pathlib import Path
import argparse,json,hashlib
import n1tool as n
from qa09_paths import qa08_rom
from qa07_name import names
from qa03_tooltip_fix import read_rows
R=Path(__file__).resolve().parents[1];H=lambda b:hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--base',type=Path,default=None);p.add_argument('--rom',type=Path,default=R/'build/qa09/Rockman_N1_English_QA09.wsc');p.add_argument('--public',action='store_true',help='Verify reproducible code/text without private SRAM fixture; never claim persistence was retested');a=p.parse_args();s=(a.base if a.base is not None else qa08_rom(R)).read_bytes();t=a.rom.read_bytes();assert H(s)=='41d7fc75e327ad15b72c7f6fc7119e031d6af8cfdb1527eb547b3c86d7cc32dc';assert H(t)=='d729823bbe6cf9132e6345ed734eb2dbe51885c13d5a17a44a9f7cfae086c326'
 old=json.loads((R/'translation/lineage/en_qa08.json').read_text());new=json.loads((R/'translation/en_qa09.json').read_text());allowed={len(t)-2,len(t)-1};ranges=[]
 for k in ['entries','binary_entries']:
  es={x['id']:x for x in old[k]};assert set(es)=={x['id'] for x in new[k]}
  for e in new[k]:
   if es[e['id']]!=e:
    at=int(e['offset'],0);allowed.update(range(at,at+e['length']));ranges.append([e['id'],hex(at),e['length']])
 assert {x[0] for x in ranges}=={'host_navi_roster_full','database_chip_descriptions'}
 diff={i for i,(x,y) in enumerate(zip(s,t)) if x!=y};assert diff<=allowed
 assert sum(t[:-2])&65535==int.from_bytes(t[-2:],'little')
 dec,_=n.load_table(R/'tables/n1battle_jp.tbl');bn,_=names(s,dec);an,_=names(t,dec);assert bn==an and an[198]=='SendDeck'
 b,_,_=read_rows(s,dec);c,_,_=read_rows(t,dec);assert [i for i in range(249) if b[i]!=c[i]]==[175];assert b[175][0]==c[175][0]
 assert s[0x340310:0x348310]==t[0x340310:0x348310]
 reverse=bytearray(t)
 for _,at,size in ranges:at=int(at,16);reverse[at:at+size]=s[at:at+size]
 reverse[-2:]=(sum(reverse[:-2])&65535).to_bytes(2,'little');assert bytes(reverse)==s
 q=R/'evidence/qa09';mask=json.loads((q/'astra_ending/gaia_final/mask_verification.json').read_text());notice=json.loads((q/'astra_ending/notices_final/glyph_verification.json').read_text());assert mask['all_masks_match'] and mask['verification_rom_sha256']==H(t);assert notice['rom_sha256']==H(t) and all(x['different_pixels']==0 for x in notice['lines'])
 warm_file=R/'evidence/qa08/persistence/winner.srm';cold_file=R/'evidence/qa08/persistence/winner_cold.srm'
 if a.public:
  warm=cold=None
  persistence={'status':'NOT_RETESTED_PUBLIC_FIXTURE_EXCLUDED','sram_bytes':32768,'archived_sha256':'4b32fc51fb77d9947d047c8e6babdaf55e24c33f71a06f3cee1530b3d5102910','historical_evidence':'evidence/qa08/QA08_Informe.html','new_process_test_in_public_package':False}
 else:
  warm=warm_file.read_bytes();cold=cold_file.read_bytes();assert warm==cold and len(warm)==32768
  persistence={'status':'PASS_NEW_PROCESS_INHERITED','sram_bytes':len(warm),'sram_sha256':H(warm),'cold_export_identical':True,'zenny':2800,'chips':11,'library':9}
 result={'status':('PASS_PUBLIC_BINARY_SCOPE_ONLY' if a.public else 'PASS_SYNTHETIC_SCOPED'),'scope':'Current QA09 text/binary checks, with inherited private evidence recorded but not independently retested in public source release','rom_sha256':H(t),'base_rom_sha256':H(s),'changed_bytes':len(diff),'ranges':ranges,'outside_allowed_bytes':0,'gameplay_save_progression_fonts_unchanged':True,'all249_names_unchanged':True,'description_rows_changed':[175],'other248_descriptions_unchanged':True,'final_render':{'roster_lines':3,'gaia_lines':2,'native_glyph_pixel_differences':0},'netnavi_code':{'status':'PASS_INHERITED','right_margin_pixels':9},'utility198':{'status':'PASS_NATURAL_INHERITED','name':'SendDeck'},'gp':{'status':'PASS_SYNTHETIC','tournaments':13,'result_states':3,'detail_views':39,'master_final':'native initialization; final round injected; enemyHP forced0 for reward branch; no claim natural victory','return':'ending and credits returned to title'},'persistence':persistence,'conditions':'See test_matrix.json for exact observations, nonclaims and discarded fixture','evidence_transfer':'All QA09 runtime cases captured on unchanged QA08 game code; only two text resources plus checksum differ. Changed texts independently recaptured on final QA09. Reversing the two resources reconstructs exact QA08.','required_pending':[],'hardware':'N/A_OUT_OF_SCOPE_USER_REQUEST','not_claimed':['All tournaments earned naturally','Every possible chip combination or statistical drop probability','Physical cartridge behavior or physical write-failure simulation']}
 (R/'build/qa09/validation_public.json' if a.public else q/'validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
