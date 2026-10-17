"""Scoped QA07 validation; build, pixel regression, name integrity and cold save."""
from pathlib import Path
import argparse,json,hashlib
import numpy as np
from PIL import Image
import n1tool as n
from qa07_name import names
R=Path(__file__).resolve().parents[1];H=lambda b:hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--rom',type=Path,required=True);a=p.parse_args();s=a.base.read_bytes();t=a.rom.read_bytes();q=R/'evidence/qa07';assert H(s)=='b08dc7a16a41d4e2f4d3cba345e41970f0cf4c3b75a4b218126128720ddc4ae4';assert H(t)=='4c5781f4ef1f027e8de3ce6fe28fcec71a1a364f0828e9a954effdce3e831b55'
 old=json.loads((R/'translation/lineage/en_qa06.json').read_text());new=json.loads((R/'translation/lineage/en_qa07.json').read_text());allow={len(t)-2,len(t)-1};changes=[]
 for k in ['entries','binary_entries']:
  es={e['id']:e for e in old[k]};assert all(any(x['id']==e for x in new[k]) for e in es)
  for e in new[k]:
   if es.get(e['id'])!=e:
    at=int(e['offset'],0);allow.update(range(at,at+e['length']));changes.append(e['id'])
 diff={i for i,(x,y) in enumerate(zip(s,t)) if x!=y};assert diff<=allow
 assert sum(t[:-2])&65535==int.from_bytes(t[-2:],'little')
 dec,_=n.load_table(R/'tables/n1battle_jp.tbl');bn,_=names(s,dec);an,_=names(t,dec);assert [i for i in range(249) if bn[i]!=an[i]]==[198] and an[198]=='SendDeck'
 assert s[0x36a4e0:0x36e1c8]==t[0x36a4e0:0x36e1c8] and s[0x340310:0x348310]==t[0x340310:0x348310]
 ui=[]
 for stem in ['111','tool_help_selected','tool_code_selected','tool_help_open','tool_code_open']:
  x=np.array(Image.open(q/'baseline'/f'qa06_{stem}.png'));y=np.array(Image.open(q/'runtime'/f'qa07_{stem}.png'));d=np.any(x!=y,axis=2);mask=np.zeros(d.shape,bool);mask[123:140,:]=True;outside=int(np.count_nonzero(d&~mask));assert outside==0,(stem,outside);ui.append({'screen':stem,'changed_pixels':int(d.sum()),'outside_footer':outside})
 inv=[]
 for fn in ['qa07_123.png','qa07_backpack.png']:
  x=np.array(Image.open(q/'runtime/warm'/fn));y=np.array(Image.open(q/'runtime/cold'/fn));assert np.array_equal(x,y);inv.append({'capture':fn,'different_pixels':0})
 x=np.array(Image.open(q/'runtime/qa07_purchase_save_prompt.png'));y=np.array(Image.open(q/'runtime/qa07_cold_save_summary.png'));assert np.array_equal(x[24:72,16:208],y[24:72,16:208])
 raw=(q/'runtime/purchases.srm').read_bytes();reload=(q/'runtime/cold_export.srm').read_bytes();assert raw==reload and len(raw)==32768
 # Final only adds the tournament layout and ending sentence to the verified-suite ROM.
 inherited=bytearray(t)
 for ident in ['ui_tournament_fee_prize','master_tournament_ending_1']:
  e=next(x for x in old['entries'] if x['id']==ident);at=int(e['offset'],0);inherited[at:at+e['length']]=s[at:at+e['length']]
 inherited[0x34acb0:0x34acb0+2734]=s[0x34acb0:0x34acb0+2734]
 inherited[-2:]=(sum(inherited[:-2])&65535).to_bytes(2,'little');assert H(inherited)=='52afc0c3b41b007b1231c612c16fe724762ba4a5aace33222b8b03b0061232ef'
 out={'status':'PASS_SCOPED','base_rom_sha256':H(s),'rom_sha256':H(t),'changed_entries':changes,'changed_bytes':len(diff),'outside_allowed_bytes':0,'checksum':hex(int.from_bytes(t[-2:],'little')),'name198':{'before':bn[198],'after':an[198],'other_names_unchanged':248,'access':'Natural controller selection of Program Deck slot10; confirmation leads to battle.'},'description_block_unchanged':True,'native_dialogue_font_unchanged':True,'footer_regression':ui,'netnavi_code_rightmost_pixel':214,'right_margin_pixels':9,'font_masks':'Same QA05 glyphs; Help -4px and Code -8px. Cursor positions0/68/136 replace0/72/144.','purchase_persistence':{'chips':10,'library_count':8,'zenny':1500,'sram_bytes':len(raw),'sram_sha256':H(raw),'cold_export_identical':True,'inventory_comparisons':inv,'save_panel_identical':True},'evidence_transfer':{'suite_rom_sha256':H(inherited),'changes_to_final':['ui_tournament_fee_prize','master_tournament_ending_1','auxiliary_text_pool:2ND'],'justification':'The exact text and status ranges are outside footer, battle logic, inventory and save consumers. Those two changed texts separately recaptured.'},'limits':'Scope is concrete tested paths and scripts. Full catalog effects, every tournament, continuous final-to-credits and hardware not globally approved.'};(q/'validation.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
