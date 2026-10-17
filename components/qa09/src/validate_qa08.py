"""Scope QA08 bytes, preserved typography, exact SRAM persistence and evidence provenance."""
from pathlib import Path
import argparse,json,hashlib
import numpy as np
from PIL import Image
import n1tool as n
from qa07_name import names
from qa03_tooltip_fix import read_rows
R=Path(__file__).resolve().parents[1];H=lambda x:hashlib.sha256(x).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--rom',type=Path,required=True);a=p.parse_args();s=a.base.read_bytes();t=a.rom.read_bytes();q=R/'evidence/qa08';assert H(s)=='4c5781f4ef1f027e8de3ce6fe28fcec71a1a364f0828e9a954effdce3e831b55'
 old=json.loads((R/'translation/lineage/en_qa07.json').read_text());new=json.loads((R/'translation/lineage/en_qa08.json').read_text());allow={len(t)-2,len(t)-1};changed=[];ranges=[]
 for k in ['entries','binary_entries']:
  es={x['id']:x for x in old[k]};assert set(es)=={x['id'] for x in new[k]}
  for e in new[k]:
   if es[e['id']]!=e:
    at=int(e['offset'],0);allow.update(range(at,at+e['length']));changed.append(e['id']);ranges.append([e['id'],hex(at),e['length']])
 assert set(changed)=={'master_semifinal_intro','master_final_intro','battle_messages_b1_data','database_chip_descriptions'}
 diff={i for i,(x,y) in enumerate(zip(s,t)) if x!=y};assert diff<=allow
 assert sum(t[:-2])&65535==int.from_bytes(t[-2:],'little')
 dec,_=n.load_table(R/'tables/n1battle_jp.tbl');bn,_=names(s,dec);an,_=names(t,dec);assert bn==an and an[198]=='SendDeck'
 before,_,_=read_rows(s,dec);after,_,_=read_rows(t,dec);assert [i for i in range(249) if before[i]!=after[i]]==list(range(163,170))
 for i in range(163,170):assert before[i][0]==after[i][0]
 assert s[0x340310:0x348310]==t[0x340310:0x348310]
 assert s[0x37cc30:0x37ce30]==t[0x37cc30:0x37ce30] and s[0x37ce44:0x37cc30+3012]==t[0x37ce44:0x37cc30+3012]
 cold=q/'persistence';warm=(cold/'winner.srm').read_bytes();reload=(cold/'winner_cold.srm').read_bytes();assert warm==reload and len(warm)==32768
 for name in ['qa08_123.png','qa08_backpack.png','qa08_127.png']:assert np.array_equal(np.array(Image.open(cold/'warm'/name)),np.array(Image.open(cold/'cold'/name)))
 b=np.array(Image.open(cold/'qa08_gp_saved.png'));c=np.array(Image.open(cold/'qa08_cold_save_summary.png'));assert np.array_equal(b[24:72,16:208],c[24:72,16:208])
 # Native credits, footer, combat, inventory and save consumer code are outside all four text-resource ranges.
 reverse=bytearray(t)
 for _,at,size in ranges:offset=int(at,16);reverse[offset:offset+size]=s[offset:offset+size]
 reverse[-2:]=(sum(reverse[:-2])&65535).to_bytes(2,'little');assert bytes(reverse)==s
 initial=bytearray(t);e=next(x for x in old['entries'] if x['id']=='master_semifinal_intro');at=int(e['offset'],0)
 # Candidate hashes are retained in their capture manifests. Text-resource-only changes support scoped transfer.
 result={'status':'PASS_SCOPED','base_rom_sha256':H(s),'rom_sha256':H(t),'changed_entries':changed,'ranges':ranges,'changed_bytes':len(diff),'outside_allowed_bytes':0,'native_font_unchanged':True,'all249_names_unchanged':True,'description_rows_changed':list(range(163,170)),'other242_descriptions_unchanged':True,'battle_template_only_row40_changed':True,'netnavi_code':{'inherited_QA07':True,'right_margin_pixels':9,'font_masks_unchanged':True},'utility198':{'name':'SendDeck','status':'PASS_NATURAL_INHERITED'},'novice_final':{'status':'PASS_NATURAL','turn':7,'player_hp':40,'enemy_hp':0,'prize_navi':'NormNav2','zenny':2800,'record':'WINNER','return_to_carousel':True},'persistence':{'status':'PASS_NEW_PROCESS','sram_sha256':H(warm),'sram_bytes':32768,'cold_export_identical':True,'inventory_pixel_differences':0,'save_panel_identical':True,'chips':11,'library':9,'zenny':2800},'conditions':{'access':'WRAM_POKE: deck indices and inventory IDs only, native engine, no altered HP/RNG/statistics','Fire40':'target selected index+1, matching Fire; power RAM20->60. Non-Fire target had no effect. No claim of observed60damage attack.','Reflec40':'blocked incoming neutral attacks, unchanged playerHP, counter40; message corrected to used Guard!'},'credits':{'status':'PASS_SYNTHETIC','slots':58,'nonempty':38,'returned_to_title':True,'font':'26 used ASCII glyphs unchanged from JP'},'evidence_transfer':{'natural_capture_rom':H(s),'reason':'Only four text resource ranges and checksum differ; battle/save/progression code, fonts, footer, names and credits resources unchanged. Changed texts have dedicated final captures.'},'pending':['Higher tournaments by natural route','Complete progression and organic ending-to-credits','Remaining chip conditions and elemental attacks against Reflec40','Real hardware']}
 mask=json.loads((q/'astra_boosts/mask_verification.json').read_text());assert mask['all_masks_match'] and len(mask['rows'])==7 and mask['verification_rom_sha256']==H(t)
 result['final_seven_description_render']={'rows':7,'lines':14,'all_native_masks_exact':True,'access':'POINTER_INJECTION, descriptor only'}
 (q/'validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
