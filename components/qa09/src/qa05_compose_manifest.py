"""Compose cumulative QA05 from frozen QA04 + guarded graphics/content reports."""
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[1]
def main():
 m=json.loads((ROOT/'translation/lineage/en_qa04.json').read_text());r=json.loads((ROOT/'translation/qa05/graphics_report.json').read_text())['replacements']
 for e in json.loads((ROOT/'translation/qa05/numeric_report.json').read_text())['manifest_replacements']:r[e['id']]=e
 e=json.loads((ROOT/'translation/qa05_content/report.json').read_text())['manifest_replacement'];r[e['id']]=e
 for e in r.values():
  b=(ROOT/'translation'/e['asset']).read_bytes();assert hashlib.sha256(b).hexdigest()==e['asset_sha256'];assert len(b)==e['length']
 ids={e['id'] for e in m['binary_entries']};m['binary_entries']=[r.get(e['id'],e) for e in m['binary_entries']]+[e for k,e in r.items() if k not in ids];m['project_version']='0.10.7-qa05'
 (ROOT/'translation/lineage/en_qa05.json').write_text(json.dumps(m,indent=2,ensure_ascii=False)+'\n');print('Composed',len(r),'updated entries from QA04')
if __name__=='__main__':main()
