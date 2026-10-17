"""QA07 final ROM: footer, deck confirmation, complete loss branch and cold SRAM."""
from pathlib import Path
import argparse,subprocess,sys,os,shutil,json,hashlib
R=Path(__file__).resolve().parents[1];H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--rom',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True);rd=out/'roms';rd.mkdir(exist_ok=True);shutil.copy2(a.rom,rd/'qa07.wsc');calls=[]
 def run(route,state='-',sram='-',save='-',folder=None):
  target=folder or out;target.mkdir(exist_ok=True);env=dict(os.environ,AUDIT_ROM_DIR=str(rd),QA_CAPTURE_DIR=str(target));argv=[sys.executable,str(R/'src/qa03_capture.py'),'qa07',str(R/'qa/routes'/route),str(state),str(sram),str(save)];subprocess.run(argv,env=env,stdout=subprocess.DEVNULL,check=True,timeout=60);calls.append({'route':route,'state':str(state),'sram':str(sram),'save':str(save),'folder':str(target)})
 run('menus.json',R/'evidence/qa05/qa05_cold_menu_restored.state')
 for route in ['qa05_tool_code.json','qa05_tool_help.json']:run(route,out/'qa07_111.state')
 run('qa07_free_confirm.json',R/'evidence/qa06/ui_before/qa05_free_19.state')
 run('qa07_free_yes.json',out/'qa07_submit_ok.state')
 run('qa07_free_fight.json',out/'qa07_after_yes2.state')
 run('qa07_free_turns.json',out/'qa07_fight_15.state')
 run('qa07_free_turns2.json',out/'qa07_turn_39.state')
 run('qa07_free_result.json',out/'qa07_combat2_59.state')
 run('qa07_free_defeat.json',out/'qa07_combat_end_29.state')
 run('qa07_give_up.json',out/'qa07_combat_finish_07.state')
 run('qa07_loss_exit.json',out/'qa07_give_up_result.state')
 run('qa07_purchase_save.json',R/'evidence/qa07/inputs/post_purchases_shop.state',save=out/'purchases.srm')
 run('qa02_cold_final.json',sram=out/'purchases.srm',save=out/'cold_export.srm')
 run('qa02_cold_summary.json',out/'qa07_cold_menu_restored.state')
 for typ,state in [('warm',out/'qa07_menu_after_shop.state'),('cold',out/'qa07_cold_menu_restored.state')]:
  sub=out/typ;run('chipfolder.json',state,folder=sub);run('qa04_backpack.json',sub/'qa07_123.state',folder=sub)
 report={'rom_sha256':H(a.rom),'engine_sha256':H(R/'qa/emulator/mednafen_wswan_libretro.so'),'calls':calls,'access':'Controller-only routes from documented natural savestates. Cold Continue uses cartridge SRAM only, new process, no savestate.','sram_before_sha256':H(out/'purchases.srm'),'sram_after_sha256':H(out/'cold_export.srm')};(out/'provenance.json').write_text(json.dumps(report,indent=2)+'\n');shutil.rmtree(rd);print(json.dumps({k:v for k,v in report.items() if k!='calls'}))
if __name__=='__main__':main()
