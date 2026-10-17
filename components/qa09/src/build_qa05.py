"""Cumulative JP -> QA05 build and BPS; editable-source build wrapper (Pillow for shared graphics module)."""
import argparse,hashlib,json,os,struct,subprocess,sys,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
JP='4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed'
def number(n):
 out=bytearray()
 while True:
  x=n&127;n>>=7
  if n==0:out.append(x|128);return out
  out.append(x);n-=1
def bps(source,target):
 out=bytearray(b'BPS1')+number(len(source))+number(len(target))+number(0)
 i=0
 while i<len(target):
  same=i<len(source) and source[i]==target[i];j=i+1
  while j<len(target) and (j<len(source) and source[j]==target[j])==same:j+=1
  out+=number(((j-i-1)<<2)|(0 if same else 1))
  if not same:out+=target[i:j]
  i=j
 out+=struct.pack('<II',zlib.crc32(source),zlib.crc32(target));out+=struct.pack('<I',zlib.crc32(out));return bytes(out)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--source',default=os.environ.get('CONTINUITY_INPUT_JP') or os.environ.get('QA05_JP_ROM'));ap.add_argument('--output',type=Path,default=ROOT/'build/qa05');a=ap.parse_args()
 if not a.source:ap.error('Provide --source original Japanese WSC, or QA05_JP_ROM')
 source=Path(a.source).resolve();raw=source.read_bytes();assert hashlib.sha256(raw).hexdigest()==JP,'Wrong original Japanese ROM'
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);rom=out/'Rockman_N1_English_QA05.wsc'
 # Regenerate every QA05 delta from its editable source and the frozen QA04 base.
 baseout=out/'qa04_base'
 for argv in [
  ['build_qa04.py','--source',str(source),'--output',str(baseout)],
  ['qa05_graphics.py','--base',str(baseout/'Rockman_N1_English_QA04.wsc'),'--jp',str(source)],
  ['qa05_numeric_labels.py','--base',str(baseout/'Rockman_N1_English_QA04.wsc'),'--jp',str(source)],
  ['qa05_content_build.py','--source',str(source)],
  ['qa05_compose_manifest.py']]:
  subprocess.run([sys.executable,str(ROOT/'src'/argv[0]),*argv[1:]],check=True,stdout=subprocess.DEVNULL)
 with (out/'build.log').open('w') as log:
  subprocess.run([sys.executable,str(ROOT/'src/n1tool.py'),'build',str(source),str(ROOT/'translation/lineage/en_qa05.json'),str(rom),'--asset-root',str(ROOT/'translation'),'--table',str(ROOT/'tables/n1battle_jp.tbl'),'--report',str(out/'build_report.json')],stdout=log,check=True)
 target=rom.read_bytes();patch=bps(raw,target);(out/'Rockman_N1_English_QA05.bps').write_bytes(patch)
 from continuity import apply_bps
 assert apply_bps(raw,patch)==target
 report={p.name:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size} for p in [rom,out/'Rockman_N1_English_QA05.bps']}
 (out/'SHA256.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
