#!/usr/bin/env python3
"""Verify paired cold-session UI captures, exact scope, navigation and SRAM.

Run after qa14_capture_ui.py on M04_EN_complete, M04_CC_complete, M05_EN
and M05_CC. This checks evidence; direct visual reading is recorded separately.
Private SRAM and RAM inputs are never copied into the public JSON report.
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'components/qa09/src'))
import n1save

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def rectangles(name):
    """Independent screen-space contract: x0,y0,x1,y1, exclusive end."""
    if name.startswith('root_'):
        return [(16,y,88,y+16) for y in (16,40,64,88,112)]
    banners={'carousel_shop':'SHOP','carousel_gp':'BATTLE CHIP GP','carousel_free':'FREE BATTLE',
             'carousel_host':'HOST TOURNEY','shop_exited':'SHOP'}
    if name in banners: return [(8,8,8+(len(banners[name])+4)*8,24)]
    if name.startswith('sort_'): return [(32,128,104,136),(184,128,216,136)]
    if name.startswith('netnavi'): return [(160,32,168,48),(200,32,208,48)]
    if name.startswith('shop_select_') or name in ('shop_info_action','shop_insufficient',
        'purchase_confirm','purchase_received','purchase_menu','shop_farewell'):
        return [(16,8,80,24),(16,24,88,40),(16,56,56,72)]
    return []

def load(path):
    with Image.open(path) as im:
        if im.size != (224,144): raise ValueError(f'Non-native capture: {path}')
        raw=im.convert('RGB').tobytes()
        return list(zip(raw[0::3],raw[1::3],raw[2::3]))

def compare_pair(before,after):
    b=json.loads((before/'session.json').read_text());a=json.loads((after/'session.json').read_text())
    assert a['no_prior_release_savestates_loaded'] and b['no_prior_release_savestates_loaded']
    assert a['seed_sram_sha256']==b['seed_sram_sha256']
    assert len(a['reports'])==len(b['reports'])==21
    br={r['case']:r for r in b['reports']}; records=[]
    for r in a['reports']:
        old=br[r['case']]
        assert r['route_sha256']==old['route_sha256'],f"Input route changed: {r['case']}"
        assert r['rom_sha256']==a['rom_sha256'] and r['wram_pokes']==old['wram_pokes']==0
        assert r['source_rom_unchanged']
        for s in r['screenshots']:
            rel=Path(r['case'])/s['png']; ap=after/rel;bp=before/rel
            # Filenames in the capture helper are identical to case directories.
            assert sha(ap)==s['sha256']
            os=next(x for x in old['screenshots'] if x['name']==s['name'])
            assert sha(bp)==os['sha256']
            av,bv=load(ap),load(bp);dif=[i for i,(x,y) in enumerate(zip(av,bv)) if x!=y]
            rects=rectangles(s['name'])
            outside=[i for i in dif if not any(x0<=i%224<x1 and y0<=i//224<y1 for x0,y0,x1,y1 in rects)]
            assert not outside,f'Unexpected pixels: {after.name}/{rel}: {outside[:8]}'
            ram_a=ap.with_suffix('.ram').read_bytes();ram_b=bp.with_suffix('.ram').read_bytes()
            assert len(ram_a)==len(ram_b)==65536
            low=[i for i in range(0x2000) if ram_a[i]!=ram_b[i]]
            records.append({'capture':rel.as_posix(),'name':s['name'],'before_sha256':sha(bp),
                'after_sha256':sha(ap),'changed_pixels':len(dif),'outside_allowed_pixels':0,
                'allowed_rectangles':rects,'ram_below_0x2000_differences':[hex(i) for i in low]})
    assert len(records)==53
    saves=[]
    for name in ('purchase_saved.srm','purchase_cold.srm'):
        ap,bp=after/name,before/name
        sv=n1save.load_save(ap)
        assert sv.valid,sv.validation_issues()
        assert ap.read_bytes()==bp.read_bytes(),f'Purchase SRAM differs from previous same variant: {name}'
        saves.append({'file':name,'sha256':sha(ap),'bytes':ap.stat().st_size,
            'both_checksums_valid':sv.main.checksum_valid and sv.copy.checksum_valid,
            'copies_identical':sv.copies_identical,'equal_to_same_variant_MANT04':True,
            'main_checksum':f'0x{sv.main.stored_checksum:04X}'})
    assert a['purchase_sram_exact_after_cold_load']
    return {'status':'PASS_PAIRED_PIXEL_SCOPE_AND_SRAM','before_rom_sha256':b['rom_sha256'],
        'after_rom_sha256':a['rom_sha256'],'cases':21,'screenshots':53,
        'route_inputs_identical':True,'wram_pokes':0,'outside_allowed_pixels':0,
        'purchase_saved_then_cold_load_exact':True,'save_checks':saves,'captures':records,
        'ram_note':'RAM differences are reported, not suppressed. UI loading changes graphics buffers; one reentry capture also differs in released stack contents, documented separately. This report does not assert global WRAM equality.'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sessions',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out={'schema':1,'status':'PASS_SCOPED_UI_RUNTIME','variants':{}}
    for v in ('EN','CC'):
        out['variants'][v]=compare_pair(a.sessions/f'M04_{v}_complete',a.sessions/f'M05_{v}')
    # Main menu screens are independent of the optional battle extension.
    en,cc=a.sessions/'M05_EN',a.sessions/'M05_CC'
    cross=[]
    for ep in sorted(en.rglob('*.png')):
        rel=ep.relative_to(en)
        if ep.stem=='game_title_continue': continue # RC6 title intentionally differs.
        assert load(ep)==load(cc/rel),f'UI differs between final variants: {rel}'
        cross.append(rel.as_posix())
    out['between_final_variants']={'identical_ui_captures':len(cross),'captures':cross,
        'excluded':'Two title captures: the optional RC6 title is intentionally distinct.'}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':out['status'],'paired_captures':106,'identical_cross_variant_ui':len(cross),
        'outside_allowed_pixels':0,'natural_purchase_save_checks':'PASS'}))

if __name__=='__main__': main()
