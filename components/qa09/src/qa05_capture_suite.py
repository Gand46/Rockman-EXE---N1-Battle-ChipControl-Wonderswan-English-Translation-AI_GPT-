"""Final QA05 UI, toolbar and real SRAM/cold-load evidence (Linux libretro)."""
from pathlib import Path
import argparse,subprocess,sys,os,shutil,json,hashlib
ROOT=Path(__file__).resolve().parents[1];H=lambda x:hashlib.sha256(x).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--rom',required=True,type=Path);ap.add_argument('--out',required=True,type=Path);a=ap.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
 romdir=out/'roms';romdir.mkdir(exist_ok=True);shutil.copyfile(a.rom,romdir/'qa05.wsc');env=dict(os.environ,AUDIT_ROM_DIR=str(romdir),QA_CAPTURE_DIR=str(out));calls=[]
 def run(route,state='-',sram='-',save='-'):
  argv=[sys.executable,str(ROOT/'src/qa03_capture.py'),'qa05',str(ROOT/'qa/routes'/route),str(state),str(sram),str(save)];subprocess.run(argv,env=env,stdout=subprocess.DEVNULL,check=True,timeout=60);calls.append({'route':route,'state':str(state),'input_sram':str(sram),'output_sram':str(save)})
 run('qa03_fresh.json')
 run('qa03_save.json',sram=ROOT/'qa/saves/qa04_saved.srm',save=out/'qa05_saved.srm')
 run('qa02_cold_final.json',sram=out/'qa05_saved.srm')
 pet=out/'qa05_cold_menu_restored.state'
 run('qa02_cold_summary.json',pet)
 for route in ['menus.json','chipfolder.json','library.json','netnavi.json']:run(route,pet)
 run('yfolder.json',out/'qa05_110.state');run('qa05_return_deck.json',out/'qa05_120.state')
 for route in ['qa05_tool_help.json','qa05_tool_code.json']:run(route,out/'qa05_111.state')
 run('qa04_wait.json',out/'qa05_127.state');run('qa04_backpack.json',out/'qa05_123.state');run('qa04_past_results.json',out/'qa05_netnavi_full.state')
 run('caps2.json',out/'qa05_039.state');run('en_clear_cursor.json',out/'qa05_129.state')
 (out/'provenance.json').write_text(json.dumps({'rom_sha256':H(a.rom.read_bytes()),'engine_sha256':H((ROOT/'qa/emulator/mednafen_wswan_libretro.so').read_bytes()),'calls':calls,'fresh_route':'no SRAM or savestate input','cold_save':'actual SRAM export then process restart; state only after Continue for subsequent navigation'},indent=2)+'\n')
 shutil.rmtree(romdir);print('Capture suite complete:',out)
if __name__=='__main__':main()
