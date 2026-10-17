from pathlib import Path
import json
p=Path(__file__).resolve().parents[1];m=json.loads((p/'translation/lineage/en_qa03.json').read_text());r=json.loads((p/'translation/qa04/graphics_report.json').read_text())['replacements'];t=json.loads((p/'translation/assets/qa04_effect_labels_report.json').read_text())['manifest_replacements']
for e in (t.values() if isinstance(t,dict) else t):r[e['id']]=e
m['binary_entries']=[r.get(e['id'],e) for e in m['binary_entries']];m['project_version']='0.10.7-qa04';(p/'translation/lineage/en_qa04.json').write_text(json.dumps(m,indent=2,ensure_ascii=False)+'\n')
