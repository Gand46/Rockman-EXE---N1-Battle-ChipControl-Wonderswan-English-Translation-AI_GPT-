"""QA08: two scoped late-dialogue editorial corrections approved against Japanese."""
from pathlib import Path
import json,hashlib,struct
import n1tool as n
R=Path(__file__).resolve().parents[1]
def main():
 m=json.loads((R/'translation/lineage/en_qa07.json').read_text());m['project_version']='0.10.7-qa08';changes={'master_semifinal_intro':('If you can, that is','If you can, anyway.'),'master_final_intro':('Rare chip, then a[LINE]new deck!','A rare chip![LINE]What deck to build?')}
 for e in m['entries']:
  if e['id'] in changes:
   before,after=changes[e['id']];assert e['translation'].count(before)==1;e['translation']=e['translation'].replace(before,after)
 _,enc=n.load_table(R/'tables/n1battle_jp.tbl');pack=lambda t:b''.join(struct.pack('<H',x) for x in n.encode_text(t,enc))
 for e in m['binary_entries']:
  if e['id']=='battle_messages_b1_data':
   raw=bytearray((R/'translation'/e['asset']).read_bytes());assert raw[0x200:0x214]==bytes.fromhex('ec00f600f900ed00f500ef00ee00000001020980')
   raw[0x200:0x214]=struct.pack('<10H',0xff,0xfd,0xef,0xee,0,0x201,0x81,0x8007,0x8000,0x8000)
   dest=R/'translation/qa08/battle_messages_b1_data.bin';dest.parent.mkdir(exist_ok=True);dest.write_bytes(raw);e['asset']='qa08/'+dest.name;e['asset_sha256']=hashlib.sha256(raw).hexdigest()
 replacement=json.loads((R/'translation/qa08_boost_descriptions/report.json').read_text())['manifest_replacement']
 m['binary_entries']=[replacement if e['id']=='database_chip_descriptions' else e for e in m['binary_entries']]
 (R/'translation/lineage/en_qa08.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
