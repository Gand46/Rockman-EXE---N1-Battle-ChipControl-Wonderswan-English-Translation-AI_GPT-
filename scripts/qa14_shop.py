#!/usr/bin/env python3
"""SHOP and NetNavi units: literal original 8x16 font, bounded MANT04 repair.

Input is the verified Japanese original plus MANT04 (or another disjoint
graphics correction retaining these exact input spans).  All editable text,
positions and source-derived glyph masks live in translation/qa14_shop.
No executable instruction, numeric value, palette or runtime font is edited.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'components/qa09/translation/qa14_shop'
JP_SHA = '4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed'
MANT04_SHA = 'e9fcfec134135c2f129da79d20b8f42ec4e7b7051e4b3b927036731041418800'
FONT_START, FONT_SIZE = 0x340310, 0x8000
ROM_SIZE = 0x400000
SPANS = {
    'shop_map': (0x04604C, 0x0480, 'c324072248f0cc86f3dd85f327cb52ccbf7f39e3548fe97ac294c617fa753314'),
    'shop_tiles': (0x0818A0, 0x0600, 'fd83abf008b41881987ef7a71bcf99ccb5644d5696b94ff4e7539feb2e0d49ee'),
    'netnavi_map': (0x0452C6, 0x0480, '5eb4372bbb109f22e39e3fbc82bcf84d00936cc9a32ba283cc5ddfaecc1ad6d0'),
    'netnavi_tiles': (0x080300, 0x0D40, '1021ecb81399d3860c53da3a27a098f8a5f8627a53a6d39b8d749a42d29135c8'),
}
# Every slot is owned by the three original Japanese product-label rectangles.
# Original numeric price glyphs 19/1B/23/25/2E/2F are deliberately excluded.
SHOP_POOL = (0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x1A, 0x1C,
             0x1D, 0x1E, 0x1F, 0x20, 0x21, 0x22, 0x24, 0x26,
             0x27, 0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2D)
PRICE_CELLS = ({(x, y) for y in (1, 2) for x in range(14, 18)} |
               {(x, y) for y in (3, 4) for x in range(13, 18)} |
               {(x, y) for y in (7, 8) for x in range(16, 18)})
UNIT_SLOTS = {'T': ((20, 4, 0x39), (20, 5, 0x3E)),
              'C': ((25, 4, 0x3B), (25, 5, 0x3F))}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def ensure(condition, message):
    if not condition:
        raise ValueError(message)


def unpack(data):
    return [p for b in data for p in (b >> 4, b & 15)]


def pack(pixels):
    ensure(len(pixels) == 64 and all(0 <= p < 16 for p in pixels), 'invalid 4bpp tile')
    return bytes((pixels[i] << 4) | pixels[i + 1] for i in range(0, 64, 2))


def word(tilemap, x, y):
    pos = 2 * (y * 32 + x)
    return int.from_bytes(tilemap[pos:pos + 2], 'little')


def set_id(tilemap, x, y, tile_id):
    pos = 2 * (y * 32 + x)
    tilemap[pos:pos + 2] = ((word(tilemap, x, y) & ~511) | tile_id).to_bytes(2, 'little')


def refs(tilemap, tile_id):
    return {(i // 2 % 32, i // 2 // 32) for i in range(0, len(tilemap), 2)
            if int.from_bytes(tilemap[i:i + 2], 'little') & 511 == tile_id}


def font_masks(jp):
    data = json.loads((ASSETS / 'native_glyphs.json').read_text())
    ensure(data['source_rom_sha256'] == JP_SHA, 'glyph provenance changed')
    ensure(digest(jp[FONT_START:FONT_START + FONT_SIZE]) == data['font_sha256'], 'native font hash')
    masks = {}
    for character, item in data['glyphs'].items():
        raw = jp[FONT_START + item['index'] * 64:FONT_START + (item['index'] + 1) * 64]
        ensure(digest(raw) == item['source_sha256'], f'original glyph {character!r} changed')
        source = unpack(raw)
        derived = [''.join('#' if p == 1 else '.' for p in source[y * 8:y * 8 + 8]) for y in range(16)]
        ensure(derived == item['mask'], f'editable mask {character!r} differs from native source')
        masks[character] = derived
    return masks, data


def draw_text(masks, text, width, background, face, left):
    ensure(0 <= left and left + len(text) * 8 <= width, f'{text!r} does not fit field')
    canvas = [[background] * width for _ in range(16)]
    for index, character in enumerate(text):
        if character == ' ':
            continue
        ensure(character in masks, f'no native glyph {character!r}')
        for y, line in enumerate(masks[character]):
            for x, enabled in enumerate(line):
                if enabled == '#':
                    canvas[y][left + index * 8 + x] = face
    return canvas


def patterns(canvas):
    return [pack([canvas[ty * 8 + y][tx * 8 + x] for y in range(8) for x in range(8)])
            for ty in range(len(canvas) // 8) for tx in range(len(canvas[0]) // 8)]


def original_shop_crosscheck(jp, masks):
    """Establish this font's provenance on this actual screen, by exact pixels."""
    mo, ml, _ = SPANS['shop_map']
    to, tl, _ = SPANS['shop_tiles']
    tilemap, bank = jp[mo:mo + ml], jp[to:to + tl]
    checks = []
    for character, x, y in [('1', 64, 8), ('1', 64, 24), ('0', 72, 24),
                             ('0', 120, 8), ('0', 128, 8)]:
        expected = masks[character]
        differences = 0
        for yy in range(16):
            for xx in range(8):
                tid = word(tilemap, (x + xx) // 8, (y + yy) // 8) & 511
                pixels = unpack(bank[tid * 32:(tid + 1) * 32])
                actual = pixels[((y + yy) % 8) * 8 + (x + xx) % 8] == 15
                differences += actual != (expected[yy][xx] == '#')
        ensure(differences == 0, f'original SHOP {character} at {x},{y} uses another font')
        checks.append({'character': character, 'pixel_origin': [x, y], 'mask_differences': differences})
    return checks


def repair_shop(out, masks, config):
    mo, ml, _ = SPANS['shop_map']
    to, tl, _ = SPANS['shop_tiles']
    old_map, old_bank = bytes(out[mo:mo + ml]), bytes(out[to:to + tl])
    tilemap, bank = bytearray(old_map), bytearray(old_bank)
    labels = config['shop_labels']
    targets = {(label['x'] + x, label['y'] + y) for label in labels
               for y in range(2) for x in range(label['columns'])}
    ensure(not targets & PRICE_CELLS, 'product rectangles intersect prices')
    for tid in SHOP_POOL:
        ensure(refs(tilemap, tid) <= targets, f'SHOP tile {tid:02X} has another consumer')
    blank = pack([2] * 64)
    ensure(old_bank[5 * 32:6 * 32] == blank, 'SHOP background is not native color 2')
    for tid in SHOP_POOL:
        bank[tid * 32:(tid + 1) * 32] = blank
    assigned, records = {blank: 5}, []
    for label in labels:
        canvas = draw_text(masks, label['text'], label['columns'] * 8, 2, 15, label['left'])
        for index, pattern in enumerate(patterns(canvas)):
            if pattern not in assigned:
                count = len(assigned) - 1
                ensure(count < len(SHOP_POOL), 'native SHOP labels exceed exclusive tile pool')
                tid = SHOP_POOL[count]
                assigned[pattern] = tid
                bank[tid * 32:(tid + 1) * 32] = pattern
            set_id(tilemap, label['x'] + index % label['columns'],
                   label['y'] + index // label['columns'], assigned[pattern])
        records.append({**label, 'pixel_origin': [label['x'] * 8 + label['left'], label['y'] * 8],
                        'font_cell': [8, 16], 'cell_width': len(label['text']) * 8})
    for index in range(0, ml, 2):
        before, after = int.from_bytes(old_map[index:index + 2], 'little'), int.from_bytes(tilemap[index:index + 2], 'little')
        ensure((before ^ after) & ~511 == 0, 'SHOP palette/priority/flip attributes changed')
        if (index // 2 % 32, index // 2 // 32) not in targets:
            ensure(before == after, 'SHOP map changed outside product fields')
    for tid in range(tl // 32):
        if tid not in SHOP_POOL:
            ensure(bank[tid * 32:(tid + 1) * 32] == old_bank[tid * 32:(tid + 1) * 32], 'SHOP neighboring tile changed')
    ensure(all(word(tilemap, *p) == word(old_map, *p) for p in PRICE_CELLS), 'SHOP price map changed')
    out[mo:mo + ml], out[to:to + tl] = tilemap, bank
    allowed = {mo + 2 * (y * 32 + x) + byte for x, y in targets for byte in (0, 1)}
    allowed |= {to + tid * 32 + byte for tid in SHOP_POOL for byte in range(32)}
    return {'labels': records, 'font': 'literal original ROM 8x16 font, no scaling or redrawing',
            'assigned_patterns': len(assigned) - 1, 'exclusive_capacity': len(SHOP_POOL),
            'price_cells_unchanged': True, 'palette_attributes_unchanged': True,
            'tile_ids': [f'0x{tid:02X}' for tid in SHOP_POOL]}, allowed


def repair_units(out, masks):
    mo, ml, _ = SPANS['netnavi_map']
    to, tl, _ = SPANS['netnavi_tiles']
    tilemap = bytes(out[mo:mo + ml])
    # The adjacent statistics map loads the same bank, so it is a guard map.
    stats = bytes(out[0x045748:0x045748 + 0x0480])
    bank = bytearray(out[to:to + tl])
    allowed, records = set(), []
    for character, cells in UNIT_SLOTS.items():
        pats = patterns(draw_text(masks, character, 8, 8, 6, 0))
        for (x, y, tid), pattern in zip(cells, pats):
            ensure(word(tilemap, x, y) & 511 == tid, 'NetNavi unit tile assignment changed')
            ensure(refs(tilemap, tid) == {(x, y)}, f'unit tile {tid:02X} has another primary consumer')
            ensure(not refs(stats, tid), f'unit tile {tid:02X} also used in statistics')
            bank[tid * 32:(tid + 1) * 32] = pattern
            allowed |= {to + tid * 32 + byte for byte in range(32)}
        records.append({'character': character, 'meaning': 'types' if character == 'T' else 'chips',
                        'original_japanese': '種' if character == 'T' else '枚',
                        'pixel_origin': [cells[0][0] * 8, cells[0][1] * 8],
                        'font_cell': [8, 16], 'native_ink_height': 11,
                        'tile_ids': [f'0x{t:02X}' for _, _, t in cells]})
    out[to:to + tl] = bank
    return {'cause': 'legitimate type/chip unit suffixes T/C previously drawn as narrow 3x14 artificial glyphs',
            'decision': 'preserve both units and repair their literal native glyphs; no blind erasure',
            'units': records, 'primary_map_unchanged': True, 'statistics_map_unchanged': True,
            'orange_header_art_unchanged': True, 'numeric_values_and_consumer_code_unchanged': True}, allowed


def apply(jp: bytes, base: bytes):
    ensure(len(jp) == ROM_SIZE and digest(jp) == JP_SHA, 'requires the verified Japanese Rev 1 ROM')
    ensure(len(base) == ROM_SIZE, 'wrong input ROM size')
    for name, (offset, length, sha) in SPANS.items():
        ensure(digest(base[offset:offset + length]) == sha, f'{name}: input differs from MANT04')
    masks, provenance = font_masks(jp)
    # QA09 legitimately retains historical edits to two other font slots.
    # Verify the selected source glyphs, and preserve the entire base bank.
    for character, item in provenance['glyphs'].items():
        offset = FONT_START + item['index'] * 64
        ensure(base[offset:offset + 64] == jp[offset:offset + 64], f'base glyph {character!r} altered')
    config = json.loads((ASSETS / 'labels.json').read_text())
    source_checks = original_shop_crosscheck(jp, masks)
    out = bytearray(base)
    shop, shop_allowed = repair_shop(out, masks, config)
    units, units_allowed = repair_units(out, masks)
    allowed = shop_allowed | units_allowed
    changed = {i for i, (a, b) in enumerate(zip(base, out)) if a != b}
    ensure(changed <= allowed, 'change outside SHOP product graphics/NetNavi unit tiles')
    ensure(out[FONT_START:FONT_START + FONT_SIZE] == base[FONT_START:FONT_START + FONT_SIZE], 'runtime font modified')
    checksum = sum(out[:-2]) & 65535
    out[-2:] = checksum.to_bytes(2, 'little')
    return bytes(out), {
        'status': 'PASS_BINARY_SCOPE', 'module': 'qa14_shop',
        'base_sha256': digest(base), 'canonical_mant04_base': digest(base) == MANT04_SHA,
        'original_sha256': JP_SHA, 'output_sha256': digest(out),
        'original_font_sha256': provenance['font_sha256'],
        'preserved_base_font_sha256': digest(base[FONT_START:FONT_START + FONT_SIZE]),
        'all_used_glyphs_exact_original': True,
        'original_shop_font_crosschecks': source_checks,
        'shop': shop, 'total_chips': units,
        'changed_non_checksum_bytes': len(changed), 'outside_allowed_bytes': 0,
        'changed_offsets': sorted(changed), 'checksum': f'0x{checksum:04X}',
        'runtime_and_visual_status': 'REQUIRES_RECAPTURE_AFTER_SCREEN_RELOAD',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    result, report = apply(args.source.read_bytes(), args.base.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(result)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'changed_offsets'}, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
