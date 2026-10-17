#!/usr/bin/env python3
"""Synthetic diagnostic only: route each descriptor row through MegaMan's tooltip.
Copies the supplied QA05 ROM into --output/roms, changes only description-table
slot 200 (4 bytes) plus checksum, then enters Program Deck from a PET104 state.
This proves rendering of that descriptor, not natural acquisition or chip stats.
Never changes the supplied ROM, savestate, graphics or published build.
"""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys
import n1tool as n,bcc_reference as b
ROOT=Path(__file__).resolve().parents[1]
def sha(x):return hashlib.sha256(x).hexdigest()
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--rom',type=Path,required=True);ap.add_argument('--expect-sha',required=True)
 ap.add_argument('--state',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
 ap.add_argument('--rows',default=','.join(map(str,range(5,16))))
 a=ap.parse_args();raw=a.rom.read_bytes();assert len(raw)==0x400000 and sha(raw)==a.expect_sha
 rows=[int(x) for x in a.rows.split(',')];assert rows and set(rows)<=set(range(249))
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);romdir=out/'roms';romdir.mkdir(exist_ok=True);caps=out/'captures';caps.mkdir(exist_ok=True)
 assert not a.rom.resolve().is_relative_to(romdir), 'input must remain outside diagnostic ROM directory'
 state=a.state.resolve();assert state.is_file()
 route=[{'frames':8},{'frames':6,'keys':['a']},{'frames':120},{'frames':6,'keys':['start']},{'frames':120,'name':'tooltip'}]
 routefile=out/'synthetic_route.json';routefile.write_text(json.dumps(route,indent=2)+'\n')
 env=dict(os.environ,AUDIT_ROM_DIR=str(romdir),QA_CAPTURE_DIR=str(caps));results=[]
 at=b.DESCRIPTION_OUTER_POINTERS+200*4
 for row in rows:
  data=bytearray(raw);src=b.DESCRIPTION_OUTER_POINTERS+row*4;data[at:at+4]=raw[src:src+4];n.repair_checksum(data)
  diffs=[i for i,(x,y) in enumerate(zip(raw,data)) if x!=y]
  assert set(diffs)<=set(range(at,at+4))|{len(raw)-2,len(raw)-1}
  stem=f'synthetic_desc_{row:03d}';rom=romdir/(stem+'.wsc');rom.write_bytes(data)
  result=subprocess.run([sys.executable,str(ROOT/'src/qa03_capture.py'),stem,str(routefile),str(state)],env=env,capture_output=True,text=True,timeout=45,check=True)
  png=caps/(stem+'_tooltip.png');assert png.is_file()
  results.append({'row':row,'method':'synthetic ROM pointer substitution: descriptor200 -> descriptor'+str(row),'runtime_carrier':'MegaMan card; artwork/stats intentionally remain MegaMan','diagnostic_rom_sha256':sha(data),'changed_offsets':[hex(i) for i in diffs],'capture':str(png),'capture_sha256':sha(png.read_bytes()),'log':result.stdout.strip(),'natural_reachability':'NOT_VALIDATED','chip_statistics':'NOT_VALIDATED'})
 assert a.rom.read_bytes()==raw
 report={'base_rom':str(a.rom.resolve()),'base_rom_sha256':sha(raw),'base_state':str(state),'base_state_sha256':sha(state.read_bytes()),'source_rom_unchanged':True,'diagnostic_roms_not_for_distribution':True,'rows':results}
 (out/'runtime_report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'rows':len(results),'report':str(out/'runtime_report.json')},indent=2))
if __name__=='__main__':main()
