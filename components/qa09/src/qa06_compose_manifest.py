from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[1]
def main():
 m=json.loads((ROOT/'translation/lineage/en_qa05.json').read_text());repl=json.loads((ROOT/'translation/qa06/graphics_report.json').read_text())['replacements'];e=json.loads((ROOT/'translation/qa06_content/report.json').read_text())['manifest_replacement'];repl[e['id']]=e
 for e in repl.values():
  b=(ROOT/'translation'/e['asset']).read_bytes();assert len(b)==e['length'] and hashlib.sha256(b).hexdigest()==e['asset_sha256']
 m['binary_entries']=[repl.get(e['id'],e) for e in m['binary_entries']];m['project_version']='0.10.7-qa06';(ROOT/'translation/lineage/en_qa06.json').write_text(json.dumps(m,indent=2,ensure_ascii=False)+'\n')
if __name__=='__main__':main()
