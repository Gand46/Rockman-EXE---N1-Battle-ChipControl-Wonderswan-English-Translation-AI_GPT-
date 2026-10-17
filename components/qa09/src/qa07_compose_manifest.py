from pathlib import Path
import json
R=Path(__file__).resolve().parents[1]
m=json.loads((R/'translation/lineage/en_qa07.json').read_text());n=json.loads((R/'translation/qa07/name_report.json').read_text());repl={x['id']:x for x in n['manifest_replacements']};assert all(any(e['id']==k for e in m['binary_entries']) for k in repl);m['binary_entries']=[repl.get(e['id'],e) for e in m['binary_entries']]
for e in m['entries']:
 if e['id']=='ui_tournament_fee_prize':
  assert e['translation']=='[PORTRAIT:F8][RAW:0200] Tourney [RAW:0201][LINE]Fee [RAW:0202]z[LINE]Prize [RAW:0203]z'
  e['translation']='[PORTRAIT:F8][RAW:0200] [RAW:0201][LINE]Tourney fee [RAW:0202]z[LINE]Prize [RAW:0203]z'
for e in m['entries']:
 if e['id']=='master_tournament_ending_1':
  assert 'I only care about[LINE]our potential.' in e['translation']
  e['translation']=e['translation'].replace('I only care about[LINE]our potential.','I only care about[LINE]our growth.')
# RAW0201 copies eight glyphs: preserve second-place meaning within that limit.
import hashlib,struct
import n1tool as n
_,enc=n.load_table(R/'tables/n1battle_jp.tbl')
pack=lambda text: b''.join(struct.pack('<H',x) for x in n.encode_text(text,enc))
for e in m['binary_entries']:
 if e['id']=='auxiliary_text_pool':
  raw=bytearray((R/'translation'/e['asset']).read_bytes());assert raw[0x302:0x316]==pack('RUNNER-UP[END]')
  raw[0x302:0x316]=pack('2ND[END]')+pack('[END]')*6
  old=pack('NO RECORD[END]');assert raw.count(old)==1;at=raw.index(old);raw[at:at+len(old)]=pack('NO REC.[END]')+pack('[END]')*2
  asset=R/'translation/qa07/aux_text_pool.bin';asset.write_bytes(raw)
  e['asset']='qa07/aux_text_pool.bin';e['asset_sha256']=hashlib.sha256(raw).hexdigest()
(R/'translation/lineage/en_qa07.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
