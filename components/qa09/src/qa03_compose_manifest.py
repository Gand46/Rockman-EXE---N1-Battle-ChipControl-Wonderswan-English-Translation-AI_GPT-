from pathlib import Path
import json
p=Path(__file__).resolve().parents[1]
m=json.loads((p/'translation/lineage/en_v0_10_7_graphics_a9.json').read_text());g=json.loads((p/'translation/qa03/graphics_report.json').read_text())['replacements'];t=json.loads((p/'translation/assets/qa03_tooltip_fix_report.json').read_text())['manifest_replacement'];g[t['id']]=t
m['binary_entries']=[g.get(e['id'],e) for e in m['binary_entries']]
for e in m['entries']:
 if e['id']=='intro_lan_accepts':
  for k,v in list(e.items()):
   if isinstance(v,str):e[k]=v.replace("This is great! I've[LINE]waited so long!",'BattleChipGP, huh?[LINE]Sounds like fun!')
m['project_version']='0.10.7-qa03';(p/'translation/lineage/en_qa03.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
