"""QA09 scoped roster warning and confirmed Gaia next-board-chip description."""
from pathlib import Path
import hashlib,json,struct,copy
import n1tool as n
R=Path(__file__).resolve().parents[1]
BEFORE='[PORTRAIT:04]Navi list full.[LINE]Delete old data,[LINE]then retry.'
AFTER='[PORTRAIT:04]Navi list full.[LINE]Use Delete for[LINE]unneeded data.'
def main():
 source=R/'translation/lineage/en_qa08.json';m=json.loads(source.read_text());old=copy.deepcopy(m)
 es=[e for e in m['entries'] if e['id']=='host_navi_roster_full'];assert len(es)==1;e=es[0]
 assert e['offset']=='0x3577FE' and e['length']==94 and e['expected_sha256']=='f762723ea6019d34dbc853af7dad0ff8bdaf4bc78eadf035ecf66941df076d86'
 assert e['translation']==BEFORE and e['terminator']=='END' and e['pad_after_terminator']
 _,enc=n.load_table(R/'tables/n1battle_jp.tbl')
 def blob(t):
  w=n.encode_text(t,enc)+[0x8000];assert len(w)<=47
  return struct.pack('<47H',*(w+[0]*(47-len(w))))
 b0,b1=blob(BEFORE),blob(AFTER);assert len(n.encode_text(AFTER,enc))==46
 e['translation']=AFTER;m['project_version']='0.10.7-qa09'
 assert [a['id'] for a,b in zip(m['entries'],old['entries']) if a!=b]==['host_navi_roster_full']
 replacement=json.loads((R/'translation/qa09_gaia/report.json').read_text())['manifest_replacement']
 m['binary_entries']=[replacement if e['id']=='database_chip_descriptions' else e for e in m['binary_entries']]
 assert [a['id'] for a,b in zip(m['binary_entries'],old['binary_entries']) if a!=b]==['database_chip_descriptions']
 dest=R/'translation/en_qa09.json';dest.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
 out=R/'evidence/qa09/astra_ending';out.mkdir(parents=True,exist_ok=True)
 report={'id':e['id'],'offset':e['offset'],'length':94,'before':BEFORE,'after':AFTER,'source_manifest_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'manifest_sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'before_payload_sha256':hashlib.sha256(b0).hexdigest(),'after_payload_sha256':hashlib.sha256(b1).hexdigest(),'encoded_bytes':len(b1),'lines':[15,14,14],'evidence_delete':'evidence/qa06/ui_final/qa06_host_delete.png','changed_entry_count':1,'changed_binary_entries':['database_chip_descriptions'],'gaia_report':'translation/qa09_gaia/report.json'}
 (out/'roster_change.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
