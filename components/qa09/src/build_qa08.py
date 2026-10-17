"""Cumulative QA08 from original Japanese; inherited editable QA07 build plus two texts."""
from pathlib import Path
import argparse,os,sys,subprocess,json,hashlib
from build_qa07 import bps,JP
from continuity import apply_bps
R=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',default=os.environ.get('CONTINUITY_INPUT_JP') or os.environ.get('QA08_JP_ROM'));p.add_argument('--output',type=Path,default=R/'build/qa08');a=p.parse_args()
 if not a.source:p.error('Provide --source original Japanese WSC')
 source=Path(a.source).resolve();raw=source.read_bytes();assert hashlib.sha256(raw).hexdigest()==JP
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 for args in [['build_qa07.py','--source',str(source),'--output',str(out/'qa07_base')],['qa08_boost_descriptions.py','--source',str(source)],['qa08_compose_manifest.py']]:subprocess.run([sys.executable,str(R/'src'/args[0]),*args[1:]],check=True,stdout=subprocess.DEVNULL)
 rom=out/'Rockman_N1_English_QA08.wsc'
 with (out/'build.log').open('w') as log:subprocess.run([sys.executable,str(R/'src/n1tool.py'),'build',str(source),str(R/'translation/lineage/en_qa08.json'),str(rom),'--asset-root',str(R/'translation'),'--table',str(R/'tables/n1battle_jp.tbl'),'--report',str(out/'build_report.json')],check=True,stdout=log)
 target=rom.read_bytes();patch=out/'Rockman_N1_English_QA08.bps';patch.write_bytes(bps(raw,target));assert apply_bps(raw,patch.read_bytes())==target
 report={x.name:{'sha256':hashlib.sha256(x.read_bytes()).hexdigest(),'size':x.stat().st_size} for x in [rom,patch]};(out/'SHA256.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
