"""Replay recorded QA09 routes with exact historical input-state and ROM hashes."""
from pathlib import Path
import argparse,json,os,subprocess,sys,hashlib
from qa09_paths import qa08_rom
P=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('case',nargs='?');p.add_argument('--out',type=Path,default=P/'build/qa09_replay');a=p.parse_args();rows=json.loads((P/'evidence/qa09/replay_index.json').read_text())
if not a.case:print('\n'.join(x['case'] for x in rows));sys.exit(0)
r=next(x for x in rows if x['case']==a.case);state=P/r['state'];rom=qa08_rom(P) if r['rom']=='build/qa08/Rockman_N1_English_QA08.wsc' else P/r['rom'];assert hashlib.sha256(state.read_bytes()).hexdigest()==r['state_sha256'];assert hashlib.sha256(rom.read_bytes()).hexdigest()=='41d7fc75e327ad15b72c7f6fc7119e031d6af8cfdb1527eb547b3c86d7cc32dc';a.out.mkdir(parents=True,exist_ok=True)
subprocess.run([sys.executable,str(P/'src/qa09_capture.py'),rom.stem,str(P/r['route']),str(state)],env=dict(os.environ,AUDIT_ROM_DIR=str(rom.parent),QA_CAPTURE_DIR=str(a.out.resolve())),check=True,timeout=90)
