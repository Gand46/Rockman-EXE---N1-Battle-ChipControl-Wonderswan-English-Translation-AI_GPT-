#!/usr/bin/env python3
"""Publish PNG/JSON evidence and an offline visual report from verified captures.

Report-only tooling. It never reads ROM payloads or copies private emulator state.
Run again after the final capture suite, so image hashes and build identity agree.
For a portable rebuild from the delivered PNG/JSON files, use --from-public and
the two expected hashes from docs/evidence/qa14/visual/build_identity.json.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import html
import json
import shutil
from pathlib import Path
from PIL import Image

W = None
R = None
PUBLIC = None
REPORT = None

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(path):
    return json.loads(Path(path).read_text())

def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')

def verify_suite(root, expected):
    root = Path(root)
    session = read(root / 'session.json')
    assert session['rom_sha256'] == expected, (str(root), 'capture belongs to another ROM')
    assert len(session['reports']) == 21
    assert sum(len(x['screenshots']) for x in session['reports']) == 53
    assert session['no_prior_release_savestates_loaded'] is True
    assert session['purchase_sram_exact_after_cold_load'] is True
    for case in session['reports']:
        assert case['rom_sha256'] == expected
        assert case['wram_pokes'] == 0
        assert case['source_rom_unchanged'] is True
        for shot in case['screenshots']:
            file = root / case['case'] / shot['png']
            assert sha(file) == shot['sha256'], file
            assert Image.open(file).size == (224, 144), file
    return root, session

def compact_build(manifest):
    variants = {k: {n: v[n] for n in ['rom_sha256', 'bps_sha256', 'rom_bytes', 'bps_bytes', 'checksum']}
                for k, v in manifest['variants'].items()}
    groups = manifest['ui_edits']['modules']['menu']['report']['groups']
    sort = next(g for g in groups if g['id'] == 'FuentesDiferentes_NAME_ATK_TYPE')
    menu = next(g for g in groups if g['id'] == 'Menu_Desalineado')
    return {
        'source_sha256': manifest['source_sha256'],
        'predecessor_sha256': manifest['predecessor_sha256'],
        'variants': variants,
        'ui_changed_nonchecksum_bytes': manifest['ui_edits']['changed_nonchecksum_bytes'],
        'ui_unexpected_changes': manifest['ui_edits']['unexpected_changes'],
        'ui_editor_overlap_bytes': manifest['ui_edits']['editor_overlap_bytes'],
        'shared_font_bank_unchanged': manifest['ui_edits']['shared_font_bank_unchanged'],
        'rc6_functional_bytes_preserved': manifest['chip_control']['functional_bytes_validated'],
        'rc6_functional_conflicts': manifest['chip_control']['functional_conflicts'],
        'sort_labels': sort['labels'],
        'pet_labels': menu['labels'],
        'pet_relocation': menu['relocation'],
        'scope': 'Build identity and bounded binary guards. Visual and navigation findings are recorded separately.'
    }

def main():
    global W, R, PUBLIC, REPORT
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, help='Workspace containing qa_session and support_review; required when importing fresh captures.')
    parser.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parents[1], help='Cumulative Rockman_N1 project root.')
    parser.add_argument('--from-public', action='store_true', help='Rebuild only from the PNG/JSON evidence already included in the project. No ROM, state or SRAM is needed.')
    parser.add_argument('--expect-en', required=True)
    parser.add_argument('--expect-cc', required=True)
    args = parser.parse_args()
    R = args.project_root.resolve()
    W = (args.workspace or R).resolve()
    PUBLIC = R / 'docs/evidence/qa14/visual'
    REPORT = R / 'docs/reports/qa14-native-ui.html'
    if not args.from_public and args.workspace is None:
        parser.error('--workspace is required when importing new capture sessions')
    manifest = read(R / 'build/mant05/build_manifest.json')
    build = compact_build(manifest)
    assert build['variants']['qa09']['rom_sha256'] == args.expect_en
    assert build['variants']['chip-control']['rom_sha256'] == args.expect_cc
    spec = {
        'before/en': ('M04_EN_complete', manifest['predecessor_sha256']),
        'before/cc': ('M04_CC_complete', manifest['chip_control']['mant04_chip_control_sha256']),
        'after/en': ('M05_EN', args.expect_en),
        'after/cc': ('M05_CC', args.expect_cc),
    }
    suites = {name: verify_suite(PUBLIC/name if args.from_public else W/'qa_session'/v[0],v[1]) for name,v in spec.items()}
    if args.from_public:
        support = [dict(row,path=str(PUBLIC/row['path']),source=row['original_name']) for row in read(PUBLIC/'inventory.json')['support_images']]
    else:
        support = read(W / 'support_review/inventory.json')
    assert len(support) == 20
    for entry in support:
        assert sha(entry['path']) == entry['sha256']
    original_paths = {
        'pet': W / 'qa_session/JP/cold/game_carousel_pet.png',
        'menu': W / 'qa_session/JP/menu/game_root_0.png',
        'deck': W / 'qa_session/JP/deck/game_deck.png',
        'total': W / 'qa_session/JP/netnavi/game_netnavi.png',
        'shop': W / 'qa_session/JP_report_extra/shop/game_shop_select_0.png',
        'sort': W / 'qa_session/JP_report_extra/sort/game_sort_0.png',
    }
    if args.from_public:
        original_paths = {key:PUBLIC/'original'/(key+'.png') for key in original_paths}
    for p in original_paths.values():
        assert Image.open(p).size == (224, 144)

    # Public payloads are restricted to these two extensions by construction.
    inventory, assets, image_map, sessions = [], {}, {}, {}
    prior_origins = ({x['path']:x['origin'] for x in read(PUBLIC/'inventory.json')['images']}
                     if args.from_public else {})
    def copy_image(source, relative, origin):
        source = Path(source)
        dest = PUBLIC / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != dest.resolve():
            shutil.copyfile(source, dest)
        digest = sha(dest)
        width, height = Image.open(dest).size
        record = {'path': relative, 'sha256': digest, 'width': width, 'height': height,
                  'bytes': dest.stat().st_size, 'origin': prior_origins.get(relative,origin)}
        inventory.append(record)
        image_map[relative] = record
        if digest not in assets:
            assets[digest] = 'data:image/png;base64,' + base64.b64encode(dest.read_bytes()).decode('ascii')
        return record

    for role, (source, session) in suites.items():
        sessions[role] = session
        for p in sorted(source.rglob('*.png')):
            provenance = p.relative_to(source).as_posix() if args.from_public else str(p.relative_to(W))
            copy_image(p, role + '/' + p.relative_to(source).as_posix(), provenance)
        for p in sorted(source.rglob('*.json')):
            dest = PUBLIC / role / p.relative_to(source)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if p.resolve() != dest.resolve():
                shutil.copyfile(p, dest)
    support_rows = []
    for i, row in enumerate(support, 1):
        relative = ('supports/' + Path(row['path']).name if args.from_public else 'supports/' + f'{i:02d}-' + Path(row['path']).name)
        item = copy_image(row['path'], relative, row['support'])
        item = dict(item, support=row['support'], original_name=row.get('source', Path(row['path']).name))
        support_rows.append(item)
    original_rows = {}
    for key, path in original_paths.items():
        original_rows[key] = copy_image(path, 'original/' + key + '.png', 'JP original · '+key if args.from_public else str(path.relative_to(W)))
        case = read(path.parent/(key+'.json'))['source_capture'] if args.from_public else read(path.parent / (path.parent.name + '.json'))
        assert case['rom_sha256'] == build['source_sha256']
        assert case['wram_pokes'] == 0
        shot = next(s for s in case['screenshots'] if s['sha256'] == sha(path))
        assert shot['sha256'] == sha(path)
        write(PUBLIC / 'original' / (key + '.json'), {'source_capture': case, 'selected_png': key + '.png'})

    common, different, pixel_changes = [], [], []
    for p in sorted((suites['after/en'][0]).rglob('*.png')):
        rel = p.relative_to(suites['after/en'][0]).as_posix()
        cc = suites['after/cc'][0] / rel
        (common if p.read_bytes() == cc.read_bytes() else different).append(rel)
        for variant in ['en', 'cc']:
            before = Image.open(suites['before/' + variant][0] / rel).convert('RGB')
            after = Image.open(suites['after/' + variant][0] / rel).convert('RGB')
            changed = [(i % 224, i // 224) for i, (x, y) in enumerate(zip(before.get_flattened_data(), after.get_flattened_data())) if x != y]
            bbox = ([min(x for x, y in changed), min(y for x, y in changed),
                     max(x for x, y in changed), max(y for x, y in changed)] if changed else None)
            pixel_changes.append({'variant': variant, 'capture': rel, 'different_pixels': len(changed),
                                  'inclusive_bbox': bbox})
    assert len(common) == 51 and different == ['cold/game_title_continue.png', 'reload/game_title_continue.png']

    review = {
        'schema': 1,
        'date': '2026-10-17',
        'status': 'VERIFICADO_EN_LAS_PANTALLAS_Y_RUTAS_DESCRITAS',
        'build': build,
        'access': 'Cold SRAM and Continue, followed by controller-only routes. Branch states were generated by the exact ROM under test. No WRAM pokes.',
        'cases_per_variant': 21,
        'native_captures_per_variant': 53,
        'original_user_supports': 20,
        'identical_ui_captures_between_variants': len(common),
        'different_variant_captures': different,
        'direct_visual_reading': {
            'SHOP': '1 CHIP, 10 CHIPS and INFO use native thin glyphs. All three selectors and 500z/5000z/0z prices remain readable. INFO opens its message; 10 CHIPS reports Low on Zenny; buying one chip reports Got Shockwav! and balance falls 2800Z to 2300Z.',
            'PET_carousel': 'PET, SHOP, BATTLE CHIP GP, FREE BATTLE and HOST TOURNEY are legible with native 8px advances and 7x11 capital faces. Full names, gold separators, arrows and associated panels are visible.',
            'SORT': 'NAME, ATK and TYPE share the 6px native statistics family. All seven selectors were read directly, and activation produces the corresponding captured order. ID, HP, SP and CS preserve the original glyphs.',
            'Menu_Desalineado': 'All five labels are complete, including terminal k in Program Deck and y in Data Library. First ink rows are 20,44,68,92,116, with 24px spacing; original masks were moved by 4px from QA09.',
            'Total_Chips': 'Native T and C suffixes are complete. 9T/13C becomes 9T/14C after purchase, remains 9T/14C on reentry and on cold reload. Both suffix baselines are y45. The original orange Y2 decoration is preserved.'
        },
        'visual_methods': ['Direct native 224x144 PNG reading', 'Integer 3x nearest-neighbor inspection',
                           'Before/after and EN/CC exact pixel comparisons', 'Support-to-finding correspondence'],
        'save_reload': {v: {'purchase_sram_exact_after_cold_load': sessions['after/'+v]['purchase_sram_exact_after_cold_load'],
                           'saved_sram_sha256': next(x['output_sram_sha256'] for x in sessions['after/'+v]['reports'] if x['case']=='purchase')}
                        for v in ['en','cc']},
        'scope_limits': ['The large Total Chips user support is already interpolated, not a native pixel source.',
                         'Hardware playback and complete campaign coverage are not asserted by these UI checks.',
                         'The 10-chip purchase was exercised only with insufficient funds; the successful purchase used 1 CHIP.',
                         'Chip Control RC6 retains its experimental status; UI equivalence is not a global gameplay certification.'],
        'pixel_changes': pixel_changes,
        'pending_within_observed_ui_routes': []
    }
    write(PUBLIC / 'inventory.json', {'images': inventory, 'support_images': support_rows, 'only_public_png_json': True})
    write(PUBLIC / 'visual_review.json', review)
    write(PUBLIC / 'build_identity.json', build)
    if not args.from_public:
        write(PUBLIC / 'support_metrics.json', read(W / 'support_review/visible_metrics.json'))

    # Only sources used for a visible figure are placed in the HTML image database.
    panels = [
        {'id':'shop','title':'SHOP: cantidades e INFO','support':'Fuente_Diferente_SHOP.zip','reference':'shop',
         'text':'Se reconstruyeron «1 CHIP», «10 CHIPS» e «INFO» con glifos literales del banco nativo que también dibuja los precios y el diálogo. Los trazos finos, el avance y la línea base recuperan la relación original de esa pantalla.',
         'checked':'Leídos los tres rótulos, los tres selectores y los precios. INFO abre su explicación; 10 CHIPS muestra «Low on Zenny.» con saldo insuficiente. La compra de 1 CHIP entrega Shockwav y reduce el saldo de 2800Z a 2300Z.',
         'metrics':'Celdas de 8 × 16 px; capitales de 7 × 11 px. Origen común x=24; ancho de 10 CHIPS: 64 px en un campo de 72 px. Los precios conservan sus tiles originales.',
         'items':[('shop/game_shop_select_0.png','1 CHIP · selector 1'),('shop_branches/game_shop_select_1.png','10 CHIPS · selector 2'),('shop_branches/game_shop_select_2.png','INFO · selector 3'),('shop_branches/game_shop_info_action.png','INFO · acción'),('shop_branches/game_shop_insufficient.png','10 CHIPS · fondos insuficientes'),('purchase/game_purchase_received.png','1 CHIP · compra recibida')], 'initial':0},
        {'id':'pet','title':'Carrusel: la referencia es PET','support':'Fuentes_Diferentes_PET.zip','reference':'pet',
         'text':'SHOP, BATTLE CHIP GP, FREE BATTLE y HOST TOURNEY reutilizan ahora las mismas formas nativas y métricas del rótulo PET. Se preservan las mayúsculas, los puntos decorativos y las diferencias de tipografía entre este carrusel y los menús interiores.',
         'checked':'Leídos todos los nombres al recorrer PET → SHOP → BATTLE CHIP GP → FREE BATTLE → HOST TOURNEY → PET. Cada rótulo corresponde a su panel; los nombres largos quedan completos dentro de su franja.',
         'metrics':'Capitales de 7 × 11 px; avance de 8 px; tinta desde y=11. PET permanece intacto. No fue necesario inventar caracteres para este grupo.',
         'items':[('carousel/game_carousel_shop.png','SHOP'),('carousel/game_carousel_gp.png','BATTLE CHIP GP'),('carousel/game_carousel_free.png','FREE BATTLE'),('carousel/game_carousel_host.png','HOST TOURNEY'),('cold/game_carousel_pet.png','PET · referencia conservada'),('carousel/game_carousel_pet_return.png','PET · regreso')], 'initial':0},
        {'id':'sort','title':'SORT: fuente y correspondencia con el selector','support':'FuentesDiferentes_NAME,ATK,TYPE.zip','reference':'sort',
         'text':'NAME, ATK y TYPE se reconstruyeron en la familia compacta de estadísticas de 6 px de altura. La P procede literalmente de SP; las letras adicionales extienden sus astas, cuencos y espaciado. ID, HP, SP y CS mantienen sus máscaras originales.',
         'checked':'Recorridos y activados los siete criterios. NAME, ATK y TYPE ocupan sus intervalos correctos; el ajuste final de un píxel en NAME y ATK iguala su separación respecto a la punta del selector con las referencias. Se conserva la lógica de selección y ordenación.',
         'metrics':'Tinta en y=129…134. NAME empieza en x={name_x}; ATK en x={atk_x}; TYPE en x=184. Anchuras 22 / 17 / 22 px; separación interna de 1 px entre letras. El puntero conserva su animación original.',
         'items':[('sort/game_sort_'+str(i)+'.png', name+' · selector') for i,name in enumerate(['ID','NAME','ATK','HP','SP','CS','TYPE'])] + [('sort_action_'+str(i)+'/game_sort_applied_'+str(i)+'.png',name+' · acción aplicada') for i,name in enumerate(['ID','NAME','ATK','HP','SP','CS','TYPE'])], 'initial':1},
        {'id':'menu','title':'Menú PET: cinco filas a la altura del puntero','support':'Menu_Desalineado.zip','reference':'menu',
         'text':'Se desplazaron las cinco etiquetas completas 4 px hacia abajo respecto de QA09, manteniendo exactamente sus formas y su anchura. MANT04 había aplicado 6 px sobre ventanas incompletas: se recuperaron también los extremos de Program Deck y Data Library.',
         'checked':'Leídas las cinco selecciones y comprobadas sus pantallas de destino: Program Deck, Chip Folder, Data Library, NetNavi y Save. Las etiquetas mantienen una separación vertical uniforme y sus letras finales quedan enteras.',
         'metrics':'Primera fila de tinta en y=20 / 44 / 68 / 92 / 116; paso vertical de 24 px. La ampliación del banco gráfico conserva todas las máscaras sin estrecharlas; se verificaron la carga y la persistencia en VRAM.',
         'items':[('menu/game_root_'+str(i)+'.png',name+' · selector') for i,name in enumerate(['Program Deck','Chip Folder','Data Library','NetNavi','Save'])] + [('deck/game_deck.png','Program Deck · destino'),('folder/game_folder.png','Chip Folder · destino'),('library/game_library.png','Data Library · destino'),('netnavi/game_netnavi.png','NetNavi · destino'),('save_panel/game_save_panel.png','Save · destino')], 'initial':0},
        {'id':'total','title':'Total Chips: unidades legibles y contador persistente','support':'01-Total-Chips-Numero-Artefactos.png','reference':'total',
         'text':'Las dos marcas son las unidades T (tipos) y C (chips), herederas de 種 y 枚 en el original. Se habían dibujado con máscaras estrechas de 3 × 7 px estiradas verticalmente. Se sustituyeron por T y C nativas completas, conservando su función y la decoración naranja.',
         'checked':'Lectura directa: 9T / 13C antes de comprar; 9T / 14C después de comprar un chip, al volver a entrar y tras guardar y arrancar en frío. El saldo pasa de 2800Z a 2300Z. La SRAM guardada coincide byte a byte con la recargada en ambas variantes.',
         'metrics':'Se corrigen cuatro tiles, correspondientes a las dos celdas de 8 × 16 px. Capitales de 7 × 11 px, línea base y=45. No cambia el código de cálculo, el valor del contador ni los elementos vecinos.',
         'items':[('netnavi/game_netnavi.png','Antes de comprar · 9T / 13C'),('purchase/game_netnavi_after_purchase.png','Después de comprar · 9T / 14C'),('purchase/game_netnavi_reentry.png','Reentrada · 9T / 14C'),('reload_netnavi/game_netnavi_cold_after_purchase.png','Carga en frío · 9T / 14C')], 'initial':0},
    ]
    sort_labels = {x['text']:x for x in build['sort_labels']}
    panels[2]['metrics'] = panels[2]['metrics'].format(name_x=sort_labels['NAME']['screen_x'], atk_x=sort_labels['ATK']['screen_x'])
    used = set()
    def image_tag(record, alt, cls='pixel'):
        used.add(record['sha256'])
        return f'<img class="{cls}" data-sha="{record["sha256"]}" alt="{html.escape(alt)}" width="{record["width"]}" height="{record["height"]}" style="--w:{record["width"]}px;--h:{record["height"]}px">'
    def fig(record, heading, alt, kind=''):
        return '<figure class="shot '+kind+'"><figcaption><strong>'+html.escape(heading)+'</strong><span class="dimensions">'+str(record['width'])+' × '+str(record['height'])+' px</span></figcaption><div class="viewport">'+image_tag(record,alt)+'</div><div class="image-meta"><span class="image-label">'+html.escape(alt)+'</span><a class="download-png" download="'+html.escape(Path(record['path']).name)+'">PNG original</a></div></figure>'
    body=[]
    for i,panel in enumerate(panels,1):
        ref=original_rows[panel['reference']]
        rel,label=panel['items'][panel['initial']]
        before=image_map['before/en/'+rel]; after=image_map['after/en/'+rel]
        choices=''.join('<option value="'+str(j)+'"'+(' selected' if j==panel['initial'] else '')+'>'+html.escape(t)+'</option>' for j,(_,t) in enumerate(panel['items']))
        body.append(f'<section class="finding" id="{panel["id"]}"><div class="section-title"><span class="number">0{i}</span><div><p class="eyebrow">Soporte: {html.escape(panel["support"])}</p><h2>{html.escape(panel["title"])}</h2></div></div><p>{html.escape(panel["text"])}</p><p><strong>Comprobado.</strong> {html.escape(panel["checked"])}</p><p class="metrics">{html.escape(panel["metrics"])}</p><div class="section-controls"><label>Estado observado <select class="scene-select" data-panel="{panel["id"]}">{choices}</select></label><a href="#soportes" class="support-link" data-support="{html.escape(panel["support"])}">Ver soporte adjunto</a></div><div class="triptych" data-panel="{panel["id"]}">'+fig(ref,'Referencia original JP','Referencia nativa · '+panel['reference'],'reference')+fig(before,'Antes · QA09 / MANT04',label,'before')+fig(after,'Después · MANT05',label,'after')+'</div></section>')
    # Remaining capture options are available in one gallery rather than repeated sheets.
    ordered_shots = sorted(p.relative_to(suites['after/en'][0]).as_posix() for p in suites['after/en'][0].rglob('*.png'))
    for role in ['before/en','before/cc','after/en','after/cc']:
        used.update(image_map[role+'/'+p]['sha256'] for p in ordered_shots)
    used.update(x['sha256'] for x in support_rows)
    assets = {k:v for k,v in assets.items() if k in used}
    meta = {p:{k:v for k,v in record.items() if k!='origin'} for p,record in image_map.items() if record['sha256'] in used}
    metadata = {'review': review, 'inventory': inventory, 'supports': support_rows}
    encoded_meta = 'data:application/json;base64,'+base64.b64encode(json.dumps(metadata,ensure_ascii=False,indent=2).encode()).decode()
    data = {'assets':assets,'images':meta,'panels':[{k:p[k] for k in ['id','items','initial']} for p in panels],
            'supports':support_rows,'capture_paths':ordered_shots}
    hashes = [('ROM original JP',build['source_sha256']),('MANT04 English',build['predecessor_sha256']),
              ('MANT04 Chip Control',spec['before/cc'][1]),('MANT05 English · ROM',args.expect_en),
              ('MANT05 English · BPS',build['variants']['qa09']['bps_sha256']),
              ('MANT05 Chip Control · ROM',args.expect_cc),('MANT05 Chip Control · BPS',build['variants']['chip-control']['bps_sha256'])]
    hash_rows=''.join('<tr><th>'+html.escape(k)+'</th><td><code>'+v+'</code></td></tr>' for k,v in hashes)
    support_options=''.join('<option value="'+str(i)+'">'+html.escape(f'{i+1:02d} · {r["support"]} · '+r['original_name'])+'</option>' for i,r in enumerate(support_rows))
    capture_options=''.join('<option value="'+html.escape(p)+'">'+html.escape(p)+'</option>' for p in ordered_shots)
    doc='''<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>MANT05 · Revisión visual de interfaz · Rockman N1</title>
<style>
:root{--ink:#152c34;--muted:#516870;--paper:#f4f5f1;--line:#c9d5d5;--accent:#d96b00;--teal:#155c64;--scale:1}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.58 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}header{background:#15373e;color:#f4f5ec;border-top:8px solid #ed8b24;padding:44px max(24px,calc((100vw - 1232px)/2)) 32px}main,footer{max-width:1280px;margin:auto;padding:0 24px}h1{font-size:clamp(30px,4vw,48px);line-height:1.12;max-width:900px;margin:12px 0 18px;letter-spacing:-.025em}h2{font-size:26px;line-height:1.2;margin:0}h3{font-size:20px;margin:0 0 12px}p{margin:14px 0;max-width:1000px}.eyebrow{font-size:12px;font-weight:750;letter-spacing:.08em;text-transform:uppercase;margin:0;overflow-wrap:anywhere}header .lede{max-width:890px;color:#d6e4e2;font-size:18px}.stats{display:flex;gap:12px;flex-wrap:wrap;margin-top:25px}.stats span{padding:7px 12px;border:1px solid #638086;background:#20474e;border-radius:3px;font-size:13px}.stats strong{font-size:17px;color:#fff}nav{display:flex;gap:18px;flex-wrap:wrap;padding:18px 0;border-bottom:1px solid var(--line);font-size:14px}a{color:var(--teal);text-underline-offset:3px}a:hover{color:#994900}button,select{font:inherit;font-size:14px;color:var(--ink);background:#fff;border:1px solid #9bafb4;border-radius:4px;padding:8px 10px}button{cursor:pointer}button[aria-pressed=true]{background:var(--teal);color:#fff;border-color:var(--teal)}button:focus-visible,a:focus-visible,select:focus-visible{outline:3px solid #dd8500;outline-offset:3px}.toolbar{position:sticky;top:0;z-index:4;display:flex;align-items:center;gap:16px;flex-wrap:wrap;background:#edf2edf5;border:1px solid var(--line);padding:12px 16px;margin:22px 0;backdrop-filter:blur(6px)}.toolbar label{display:flex;align-items:center;gap:8px;font-size:14px}.toolbar small{color:var(--muted)}.notice{padding:16px 20px;background:#e5eeeb;border-left:4px solid var(--teal);font-size:14px}.finding{background:#fff;border:1px solid var(--line);padding:28px;margin:30px 0;scroll-margin-top:100px}.section-title{display:flex;align-items:flex-start;gap:16px;margin-bottom:16px}.number{background:#e57910;color:#fff;font-weight:800;min-width:44px;line-height:44px;text-align:center;font-size:20px}.section-title .eyebrow{color:var(--muted);margin-bottom:6px}.metrics{background:#f1f4f1;border-left:3px solid #7d969a;padding:12px 16px;font-size:14px}.section-controls{display:flex;align-items:center;flex-wrap:wrap;gap:20px;margin:24px 0 15px}.section-controls label{display:flex;gap:10px;align-items:center;font-size:14px;max-width:100%}.scene-select{max-width:100%}.support-link{font-size:13px}.triptych{display:flex;gap:18px;flex-wrap:wrap;align-items:flex-start}.shot{margin:0;background:#f1f4f1;border:1px solid #bdcccf;max-width:100%;padding:12px;flex:0 1 auto}.shot.reference{border-top:4px solid #839598}.shot.before{border-top:4px solid #ad6b3f}.shot.after{border-top:4px solid #17767b}figcaption{display:flex;justify-content:space-between;gap:12px;font-size:13px;flex-wrap:wrap;margin-bottom:10px}.dimensions{font-size:11px;color:var(--muted)}.viewport{overflow:auto;max-width:100%;background:#263337;line-height:0;scrollbar-gutter:stable}.pixel{display:block;width:calc(var(--w)*var(--scale));height:calc(var(--h)*var(--scale));max-width:none;image-rendering:pixelated;image-rendering:crisp-edges}.source-large{display:block;max-width:none;image-rendering:auto}.image-meta{display:flex;flex-direction:column;gap:5px;font-size:11px;margin-top:9px;color:var(--muted);max-width:672px;overflow-wrap:anywhere}.download-png{align-self:flex-start}.audit{padding:28px;background:#fff;border:1px solid var(--line);margin:30px 0;scroll-margin-top:95px}.audit ul{padding-left:23px}.audit li{margin:8px 0}table{border-collapse:collapse;width:100%;font-size:14px;margin:18px 0}th,td{border-bottom:1px solid var(--line);padding:10px 12px;text-align:left;vertical-align:top}th{font-weight:650}code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px;overflow-wrap:anywhere}details{margin-top:18px}summary{cursor:pointer;font-weight:650;color:var(--teal);padding:10px 0}.gallery-controls{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:15px 0}.gallery-controls select{max-width:100%}.gallery-controls select.long{width:100%}.gallery-info{font-size:13px;color:var(--muted)}.footer{font-size:13px;color:var(--muted);border-top:1px solid var(--line);padding-top:20px;padding-bottom:40px}.status{font-size:12px;font-weight:650;color:#1b5c49}.caption-note{font-size:13px;color:var(--muted)}@media(max-width:650px){main,footer{padding:0 12px}.finding,.audit{padding:18px 12px}.toolbar{position:static;padding:10px}.section-controls label{display:block}.section-controls select{margin-top:5px}.triptych{gap:14px}h2{font-size:22px}.shot{padding:8px}.hash-table th,.hash-table td{display:block}.hash-table th{border-bottom:none;padding-bottom:0}}@media print{header{padding:20px;background:white;color:#17353c;border-top:4px solid #ed8b24}header .lede{color:#38575d}.toolbar,nav,.section-controls,.gallery-controls,.download-png{display:none}main{max-width:none;padding:0}.finding,.audit{break-inside:avoid;padding:18px;margin:20px 0}.pixel{width:var(--w);height:var(--h)}.stats span{color:#16393f;background:#fff;border-color:#9bafb4}.stats strong{color:#16393f}details{display:block}.source-large{max-width:100%;height:auto}footer{padding:10px 0}.viewport{overflow:visible}}
</style></head><body>
<header><p class="eyebrow">Rockman EXE — N1 Battle · QA09 / MANT05 · 17 de octubre de 2026</p><h1>Revisión visual y funcional<br>de cinco hallazgos</h1><p class="lede">Correcciones acumulativas sobre MANT04, con fuentes propias de cada pantalla, etiquetas alineadas y unidades del contador legibles. Evidencia del original, los soportes adjuntos y las dos compilaciones comprobadas.</p><div class="stats"><span><strong>5</strong> hallazgos</span><span><strong>20</strong> soportes PNG</span><span><strong>21</strong> rutas por variante</span><span><strong>53</strong> capturas por variante</span><span><strong>224 × 144</strong> resolución nativa</span></div></header>
<main><nav aria-label="Secciones"><a href="#shop">SHOP</a><a href="#pet">Carrusel PET</a><a href="#sort">SORT</a><a href="#menu">Menú</a><a href="#total">Total Chips</a><a href="#validacion">Validación</a><a href="#soportes">Soportes</a><a href="#identidad">Identidad</a></nav>
<div class="toolbar"><label>Ampliación <span role="group" aria-label="Escala de píxeles"><button type="button" data-scale="1" aria-pressed="true">1× nativa</button> <button type="button" data-scale="3" aria-pressed="false">3× sin suavizado</button></span></label><label>Variante <select id="variant"><option value="en">English</option><option value="cc">Chip Control RC6</option></select></label><small>Para inspección exacta: zoom del navegador al 100 %.</small></div>
<p class="notice"><strong>Cómo leer la comparación.</strong> «Antes» es la versión vigente MANT04, reconstruida y capturada con la misma partida de prueba. Los adjuntos documentan QA09 y se conservan íntegros. Las imágenes JP son referencias originales; cada sección permite cambiar de opción sin confundir estados. La vista 3× replica píxeles enteros. Las 51 capturas de interfaz son idénticas entre English y Chip Control; las otras dos capturas corresponden al título propio de cada variante.</p>
<noscript><p class="notice">Active JavaScript para mostrar las imágenes embebidas y cambiar las comparaciones. Este archivo no necesita conexión ni descarga recursos externos.</p></noscript>
''' + '\n'.join(body) + '''
<section class="audit" id="validacion"><p class="eyebrow">Alcance comprobado</p><h2>Navegación, representación y persistencia</h2>
<p>Las capturas parten de una carga en frío con SRAM. Las ramificaciones usan estados creados por esa misma ROM y entradas de mando; no se introdujeron valores en RAM. Se inspeccionaron directamente las imágenes nativas y ampliaciones enteras, además de comparar los píxeles antes y después.</p>
<table><thead><tr><th>Grupo</th><th>Comprobación observada</th><th>Resultado</th></tr></thead><tbody>
<tr><th>SHOP</th><td>Tres selectores; INFO; mensaje de fondos insuficientes; compra real de un chip; salida.</td><td class="status">Coherente y legible</td></tr>
<tr><th>Carrusel</th><td>Cuatro rótulos corregidos y regreso a PET; correspondencia entre nombres y paneles.</td><td class="status">Sin recortes observados</td></tr>
<tr><th>SORT</th><td>Siete posiciones y siete activaciones. Fuente compacta, distancia del selector y rótulo activo.</td><td class="status">Correspondencia conservada</td></tr>
<tr><th>Menú PET</th><td>Cinco filas, cinco destinos y regreso. Máscaras completas y espaciado vertical de 24 px.</td><td class="status">Alineación uniforme</td></tr>
<tr><th>Total Chips</th><td>13 → 14 chips; reentrada; guardado; arranque en frío y carga del mismo contador.</td><td class="status">9T / 14C persistente</td></tr></tbody></table>
<p><strong>Límites concretos.</strong> La compra satisfactoria comprobada fue la de 1 CHIP; la opción de 10 CHIPS se ejercitó con fondos insuficientes. Estas rutas validan las pantallas afectadas en el emulador disponible. No constituyen una prueba de toda la campaña ni una ejecución en hardware físico. Chip Control RC6 conserva su estado experimental; su diferencia funcional acumulada se mantiene, con su validación de combate documentada aparte.</p>
<p>El banco compartido de fuentes no se modifica. Las revisiones editan recursos gráficos acotados, preservan los cambios previos y mantienen separadas las familias de títulos, estadísticas, menús y diálogos.</p>
</section>
<section class="audit" id="capturas"><p class="eyebrow">Registro de ejecución</p><h2>Explorar las 53 capturas</h2><p class="caption-note">Una sola galería ofrece toda la secuencia, sin repetirla en decenas de láminas. La variante elegida arriba también se aplica aquí. Cada PNG conserva su tamaño original y se puede descargar.</p><div class="gallery-controls"><label>Versión <select id="capture-era"><option value="after">Después · MANT05</option><option value="before">Antes · MANT04</option></select></label><select id="capture-choice" class="long" aria-label="Captura de ejecución">''' + capture_options + '''</select></div>''' + fig(image_map['after/en/'+ordered_shots[0]],'Captura de ejecución',ordered_shots[0],'capture-gallery') + '''<p id="capture-hash" class="gallery-info"></p></section>
<section class="audit" id="soportes"><p class="eyebrow">Adjuntos originales</p><h2>Los cinco soportes, íntegros y relacionados</h2><p>Los cuatro ZIP contienen 19 capturas de 237 × 144 px: el área de juego mide 224 × 144 y la franja derecha pertenece a la captura del emulador. El PNG adicional de Total Chips mide 1536 × 933 y ya fue ampliado con interpolación; se utiliza para localizar la incidencia, mientras que las conclusiones por píxel se apoyan en las nuevas capturas nativas.</p><div class="gallery-controls"><select id="support-choice" class="long" aria-label="Soporte adjunto">''' + support_options + '''</select></div>''' + fig(support_rows[0],'Soporte adjunto',support_rows[0]['original_name'],'support-gallery') + '''<p id="support-info" class="gallery-info"></p></section>
<section class="audit" id="identidad"><p class="eyebrow">Trazabilidad de la entrega</p><h2>Identidad de las compilaciones</h2><p>Los BPS acumulativos se generan desde la ROM japonesa original Rev 1. Estos SHA-256 vinculan las capturas a los resultados exactos y distinguen la edición English de la variante Chip Control.</p><table class="hash-table"><thead><tr><th>Archivo lógico</th><th>SHA-256</th></tr></thead><tbody>''' + hash_rows + '''</tbody></table><details><summary>Fuentes y evidencia técnica</summary><ul><li>SHOP y unidades: <code>scripts/qa14_shop.py</code> y <code>components/qa09/translation/qa14_shop/</code>.</li><li>Carrusel, menú y SORT: <code>scripts/qa14_menu.py</code> y <code>components/qa09/translation/qa14_menu/</code>.</li><li>Rutas de captura: <code>scripts/qa14_capture_ui.py</code>. Identidad de construcción: <code>build/mant05/build_manifest.json</code>.</li><li>PNG y JSON públicos: <code>docs/evidence/qa14/visual/</code>. El conjunto conserva hashes y procedencia; no incluye ROM, estados del emulador ni SRAM.</li></ul><p><a download="qa14-visual-review-and-inventory.json" href="''' + encoded_meta + '''">Descargar dictamen visual e inventario JSON</a></p></details></section>
</main><footer class="footer"><p>Informe autocontenido: imágenes, estilos y datos incorporados en este archivo. Las lecturas y los resultados se limitan a las rutas y compilaciones identificadas. La fuente tipográfica del propio informe pertenece al sistema; los glifos del juego se muestran en los PNG originales.</p></footer>
<script id="evidence-data" type="application/json">''' + json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('</','<' + chr(92) + '/') + '''</script>
<script>
'use strict';
const db=JSON.parse(document.getElementById('evidence-data').textContent);
let variant='en';
function drawFigure(figure,record,label){
 const img=figure.querySelector('img');
 img.src=db.assets[record.sha256];img.dataset.sha=record.sha256;img.alt=label;
 img.width=record.width;img.height=record.height;
 img.style.setProperty('--w',record.width+'px');img.style.setProperty('--h',record.height+'px');
 img.className=record.width>237?'source-large':'pixel';
 figure.querySelector('.dimensions').textContent=record.width+' × '+record.height+' px';
 figure.querySelector('.image-label').textContent=label;
 const download=figure.querySelector('.download-png');download.href=img.src;download.download=record.path.split('/').pop();
}
document.querySelectorAll('img[data-sha]').forEach(img=>{img.src=db.assets[img.dataset.sha];const a=img.closest('figure').querySelector('.download-png');a.href=img.src;});
function panelDraw(panel){const idx=Number(document.querySelector('.scene-select[data-panel="'+panel.id+'"]').value);const [path,label]=panel.items[idx];const wrapper=document.querySelector('.triptych[data-panel="'+panel.id+'"]');drawFigure(wrapper.querySelector('.before'),db.images['before/'+variant+'/'+path],label);drawFigure(wrapper.querySelector('.after'),db.images['after/'+variant+'/'+path],label);}
document.querySelectorAll('.scene-select').forEach(s=>s.addEventListener('change',()=>panelDraw(db.panels.find(p=>p.id===s.dataset.panel))));
document.querySelectorAll('[data-scale]').forEach(button=>button.addEventListener('click',()=>{document.documentElement.style.setProperty('--scale',button.dataset.scale);document.querySelectorAll('[data-scale]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));}));
function captureDraw(){const path=document.getElementById('capture-choice').value;const era=document.getElementById('capture-era').value;const record=db.images[era+'/'+variant+'/'+path];drawFigure(document.querySelector('.capture-gallery'),record,path);document.getElementById('capture-hash').textContent='SHA-256 · '+record.sha256;}
function supportDraw(){const record=db.supports[Number(document.getElementById('support-choice').value)];drawFigure(document.querySelector('.support-gallery'),record,record.original_name);document.getElementById('support-info').textContent=record.support+' · SHA-256 '+record.sha256+(record.width>237?' · Soporte ya interpolado; se muestra su archivo original sin nuevo remuestreo.':' · 224 × 144 px de juego más 13 px de franja del emulador.');}
document.getElementById('variant').addEventListener('change',e=>{variant=e.target.value;db.panels.forEach(panelDraw);captureDraw();});
document.getElementById('capture-choice').addEventListener('change',captureDraw);document.getElementById('capture-era').addEventListener('change',captureDraw);document.getElementById('support-choice').addEventListener('change',supportDraw);
document.querySelectorAll('.support-link').forEach(a=>a.addEventListener('click',()=>{document.getElementById('support-choice').value=String(db.supports.findIndex(r=>r.support===a.dataset.support));supportDraw();}));
captureDraw();supportDraw();
</script></body></html>'''
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(doc)
    print(json.dumps({'html':str(REPORT),'html_bytes':REPORT.stat().st_size,'html_sha256':sha(REPORT),
                      'public_images':len(inventory),'embedded_unique_images':len(assets),
                      'english_sha256':args.expect_en,'chip_control_sha256':args.expect_cc},indent=2))

if __name__ == '__main__':
    main()
