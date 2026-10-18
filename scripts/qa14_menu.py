#!/usr/bin/env python3
"""MANT05 native carousel lettering and scoped PET/SORT menu corrections.

Public API: apply(original_jp: bytes, mant04_english: bytes) -> (bytes, dict).
The input is the exact MANT04 English ROM. The caller may merge its reported
non-checksum offsets with independent, conflict-checked corrections. Native
font glyphs are copied from JP; root captions are editable full-width QA09
masks; the small SORT font uses exact native P plus documented extensions.
This module neither writes a ROM nor changes files on import/apply.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "components/qa09/translation/qa14_menu"
ROM_SIZE = 0x400000
JP_SHA = "4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed"
PARENT_SHA = "e9fcfec134135c2f129da79d20b8f42ec4e7b7051e4b3b927036731041418800"
MASK = 0x1FF


def sha(data):
    return hashlib.sha256(data).hexdigest()


def ensure(test, message):
    if not test:
        raise ValueError(message)


def word(m, x, y):
    at = 2 * (y * 32 + x)
    ensure(0 <= at <= len(m) - 2, "tilemap cell outside span")
    return int.from_bytes(m[at:at + 2], "little")


def set_word(m, x, y, value):
    at = 2 * (y * 32 + x)
    ensure(0 <= at <= len(m) - 2, "tilemap write outside span")
    m[at:at + 2] = value.to_bytes(2, "little")


def unpack(data):
    return [v for byte in data for v in (byte >> 4, byte & 15)]


def pack(pixels):
    ensure(len(pixels) == 64 and all(0 <= x < 16 for x in pixels),
           "not a packed 8x8 4bpp tile")
    return bytes((pixels[i] << 4) | pixels[i + 1] for i in range(0, 64, 2))


def get_tile(bank, tile, first=0):
    at = (tile - first) * 32
    ensure(0 <= at <= len(bank) - 32, f"tile {tile:#x} outside bank")
    return bytes(bank[at:at + 32])


def put_tile(bank, tile, pattern, first=0):
    at = (tile - first) * 32
    ensure(0 <= at <= len(bank) - 32 and len(pattern) == 32,
           f"tile write {tile:#x} outside bank")
    bank[at:at + 32] = pattern


def decoded_cell(m, b, x, y, first=0):
    w = word(m, x, y)
    raw = unpack(get_tile(b, w & MASK, first))
    rows = [raw[i:i + 8] for i in range(0, 64, 8)]
    if w & 0x4000:
        rows = [row[::-1] for row in rows]
    if w & 0x8000:
        rows = rows[::-1]
    return rows


def extract_rect(m, b, x, y, width, height, first=0):
    result = [[0] * (width * 8) for _ in range(height * 8)]
    for cy in range(height):
        for cx in range(width):
            rows = decoded_cell(m, b, x + cx, y + cy, first)
            for yy in range(8):
                result[cy * 8 + yy][cx * 8:cx * 8 + 8] = rows[yy]
    return result


def patterns(canvas):
    h, w = len(canvas), len(canvas[0])
    ensure(w % 8 == h % 8 == 0 and all(len(r) == w for r in canvas),
           "canvas must have complete 8x8 cells")
    return {(x // 8, y // 8): pack([canvas[y + j][x + k]
                                  for j in range(8) for k in range(8)])
            for y in range(0, h, 8) for x in range(0, w, 8)}


def references(m):
    result = defaultdict(set)
    for i in range(0, len(m), 2):
        result[int.from_bytes(m[i:i + 2], "little") & MASK].add(
            (i // 2 % 32, i // 64))
    return result


def compose(m0, b0, rectangles, *, first=0, protected=(), allow_unused=False):
    """Allocate exact cell patterns, preserving all non-target consumers.

    A rectangle is (x, y, canvas, attributes-or-None). New carousel cells
    intentionally select native header palette/bank (0x2400) and no flips.
    Other rectangles preserve their source attributes and encode each tile
    in its inverse-flipped orientation, so h/v flags are always respected.
    """
    m, b = bytearray(m0), bytearray(b0)
    refs = references(m0)
    targets = {(x + cx, y + cy)
               for x, y, canvas, _ in rectangles
               for cx, cy in patterns(canvas)}
    ensure(len(targets) == sum(len(patterns(r[2])) for r in rectangles),
           "overlapping target rectangles")
    protection = set(protected)
    old_ids = {word(m0, x, y) & MASK for x, y in targets}
    pool = sorted(t for t in old_ids
                  if first <= t < first + len(b) // 32
                  and t not in protection and refs[t] <= targets)
    # On isolated carousel banks, every static consumer is covered by its
    # complete 18-row map. Only unreferenced slots may supplement the pool.
    if allow_unused:
        pool += [t for t in range(first, first + len(b) // 32)
                 if t not in pool and t not in protection and not refs[t]]
    originals = defaultdict(list)
    for t in range(first, first + len(b) // 32):
        originals[get_tile(b0, t, first)].append(t)
    assigned = {}
    reused = set()
    used_pool = set()
    for x, y, canvas, attrs in rectangles:
        for (cx, cy), visual_pattern in patterns(canvas).items():
            w0 = word(m0, x + cx, y + cy)
            attributes = (w0 & ~MASK) if attrs is None else attrs
            raw = unpack(visual_pattern)
            rows = [raw[i:i + 8] for i in range(0, 64, 8)]
            if attributes & 0x8000:
                rows = rows[::-1]
            if attributes & 0x4000:
                rows = [r[::-1] for r in rows]
            pattern = pack([q for row in rows for q in row])
            if pattern in assigned:
                tid = assigned[pattern]
            else:
                candidates = [t for t in originals.get(pattern, [])
                              if t not in used_pool]
                # Prefer immutable preexisting tile images over any mutation.
                if candidates:
                    tid = sorted(candidates, key=lambda t: (t in pool, t))[0]
                    reused.add(tid)
                else:
                    available = [t for t in pool
                                 if t not in used_pool and t not in reused]
                    ensure(available, "insufficient safe exclusive tile capacity")
                    tid = available[0]
                    used_pool.add(tid)
                    put_tile(b, tid, pattern, first)
                assigned[pattern] = tid
            set_word(m, x + cx, y + cy, attributes | tid)
    # Full displayed pattern equality and palette/priority invariants outside.
    for i in range(0, len(m0), 2):
        x, y = i // 2 % 32, i // 64
        if (x, y) not in targets:
            ensure(m0[i:i + 2] == m[i:i + 2], f"untargeted map cell {x,y}")
            tid = int.from_bytes(m0[i:i + 2], "little") & MASK
            if first <= tid < first + len(b) // 32:
                ensure(get_tile(b0, tid, first) == get_tile(b, tid, first),
                       f"shared tile {tid:#x} modified")
    for x, y, canvas, _ in rectangles:
        ensure(extract_rect(m, b, x, y, len(canvas[0]) // 8,
                            len(canvas) // 8, first) == canvas,
               "tile assignment did not reproduce requested pixels")
    return bytes(m), bytes(b), {
        "target_cells": [list(v) for v in sorted(targets)],
        "rewritten_tile_ids": sorted(used_pool),
        "reused_native_or_matching_tile_ids": sorted(reused),
        "outside_target_pixels_identical": True,
        "map_flip_bits_supported": True,
    }


def native_font(jp):
    result = {}
    for code, ch in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ", 0x5E):
        raw = unpack(jp[0x340310 + code * 64:0x340310 + (code + 1) * 64])
        result[ch] = [[int(v == 1) for v in raw[y * 8:(y + 1) * 8]]
                      for y in range(16)]
    return result


def native_banner(text, glyphs):
    # Match PET: leading 2x2 marker at x11, text starts x24, 8px advance;
    # 11px faces occupy screen rows 11..21 with native 16px glyph cells.
    width = (len(text) + 4) * 8
    canvas = [[10] * width for _ in range(16)]
    for x in (3, width - 5):
        for yy in (7, 8):
            canvas[yy][x:x + 2] = [7, 7]
    for i, ch in enumerate(text):
        if ch == " ":
            continue
        for y, row in enumerate(glyphs[ch]):
            for x, p in enumerate(row):
                if p:
                    canvas[y][16 + i * 8 + x] = 7
    return canvas


def apply(original_jp: bytes, mant04_english: bytes):
    ensure(len(original_jp) == len(mant04_english) == ROM_SIZE, "wrong ROM size")
    ensure(sha(original_jp) == JP_SHA, "wrong original Japanese revision")
    ensure(sha(mant04_english) == PARENT_SHA, "requires exact English QA09 MANT04")
    meta = json.loads((RES / "preconditions.json").read_text())
    for name, spec in meta["spans"].items():
        at, length = int(spec["offset"], 16), spec["length"]
        ensure(sha(mant04_english[at:at + length]) == spec["precondition_sha256"],
               f"wrong MANT04 {name} preimage")
    out = bytearray(mant04_english)
    groups = []

    def span(name):
        s = meta["spans"][name]
        at, ln = int(s["offset"], 16), s["length"]
        return at, ln, bytes(out[at:at + ln])

    def store(group, replacements, details):
        changed = []
        regions = []
        for key, data in replacements.items():
            at, length, old = span(key)
            ensure(len(data) == length, f"{key} size changed")
            changed += [at + i for i, (a, b) in enumerate(zip(old, data)) if a != b]
            out[at:at + length] = data
            regions.append({"resource": key, "offset": hex(at), "bytes": length,
                            "before_sha256": sha(old), "after_sha256": sha(data)})
        groups.append({"id": group, "changed_offsets": sorted(changed),
                       "changed_bytes": len(changed), "regions": regions, **details})

    # Lossless root correction uses the complete inherited 72px captions.
    captions = json.loads((RES / "pet_label_masks.json").read_text())
    rects, labels = [], []
    for row in captions["rows"]:
        original = [[int(v, 16) for v in ln] for ln in row["source_rows"]]
        ensure(len(original) == 16 and all(len(r) == 72 for r in original),
               "root caption mask dimensions")
        active = [y for y, r in enumerate(original) if any(v != 9 for v in r)]
        ensure(active and max(active) + row["shift_y"] < 16,
               "root caption would be clipped")
        canvas = [[9] * 72 for _ in range(16)]
        for y in active:
            canvas[y + row["shift_y"]] = original[y][:]
        rects.append((row["tile_x"], row["tile_y"], canvas, None))
        labels.append({"text": row["text"], "shift_from_QA09_px": row["shift_y"],
                       "native_screen_y": row["tile_y"] * 8 + row["shift_y"],
                       "full_field_width": 72, "pixel_masks_preserved": True})
    _, _, m = span("pet_map")
    # The actual descriptor loads78 tiles; legacy editable spans omitted tile0
    # and tile77. A lossless +4px shift needs70 distinct caption patterns.
    # Relocate the whole native atlas with16 additional slots instead of
    # truncating glyphs or displacing the original selector coordinates.
    relocation = meta["relocation"]
    new_at, new_len = int(relocation["new_source"], 16), int(relocation["new_length"], 16)
    _, _, directory = span("graphics_directory")
    ends = []
    for offset in range(0, len(directory), 8):
        para, count, _, _ = struct.unpack_from("<4H", directory, offset)
        source = 0x70000 + offset + para * 16
        if count:
            ends.append(source + count)
            ensure(source + count <= new_at or source >= new_at + new_len,
                   "relocated PET atlas overlaps a declared graphics resource")
    ensure(max(ends) == 0xD6898 and new_at >= max(ends),
           "graphics directory end differs")
    ensure(original_jp[new_at:new_at + new_len] == mant04_english[new_at:new_at + new_len],
           "relocation would overwrite an existing project contribution")
    original_full = mant04_english[0x7C310:0x7CCD0]
    ensure(len(original_full) == 0x9C0, "wrong original PET descriptor extent")
    full_bank = original_full + bytes([0x99]) * (new_len - len(original_full))
    nm, nb, proof = compose(m, full_bank[32:], rects, first=1, protected=(0x45, 0x46),
                           allow_unused=True)
    _, _, descriptor = span("pet_descriptor")
    ensure(descriptor == bytes.fromhex("25 0c c0 09 00 42 00 01"),
           "PET load descriptor precondition")
    new_descriptor = struct.pack("<HH", (new_at - 0x700C0) // 16, new_len) + descriptor[4:]
    store("Menu_Desalineado", {"pet_map": nm,
                              "pet_relocated_bank": full_bank[:32] + nb,
                              "pet_descriptor": new_descriptor},
          {"labels": labels, "allocation": proof,
           "relocation": relocation,
           "descriptor_flags_and_destination_preserved": True,
           "original_atlas_bytes_preserved": True,
           "cause": "MANT04 shifted incomplete caption windows by6px; full QA09 masks require4px. Program Deck terminal k and Data Library terminal pixels are included."})

    # Native JP PET glyphs equal the original master font, including P/E/T.
    glyphs = native_font(original_jp)
    for ch, address in (("P", 0x75660), ("E", 0x75680), ("T", 0x756A0)):
        c = [[7 if p else 10 for p in row] for row in glyphs[ch]]
        top = pack([v for row in c[:8] for v in row])
        ensure(original_jp[address:address + 32] == top,
               f"PET native master glyph {ch} identity mismatch")
    banner_labels = []
    for key, text in (("shop", "SHOP"), ("gp", "BATTLE CHIP GP"),
                      ("free", "FREE BATTLE"), ("host", "HOST TOURNEY")):
        _, _, m = span(key + "_map")
        _, _, b = span(key + "_tiles")
        canvas = native_banner(text, glyphs)
        nm, nb, proof = compose(m, b, [(1, 1, canvas, 0x2400)],
                               protected=(5,), allow_unused=True)
        details = {"text": text, "glyph_cell": [8, 16], "face_max": [7, 11],
                   "text_origin_screen": [24, 11], "advance": 8,
                   "field_screen": [8, 8, len(canvas[0]), 16],
                   "source": "JP 0x340310+code*64, literal native masks",
                   "missing_glyph_extensions": 0, "allocation": proof}
        banner_labels.append(details)
        store("Fuentes_Diferentes_PET_" + key,
              {key + "_map": nm, key + "_tiles": nb}, details)

    # SORT: exact native P is retained at its original 5x6 dimensions.
    # The original static map is a 26-row atlas; toolbar row24 scrolls toy128.
    _, _, bank = span("sort_tiles")
    _, _, chip_map = span("sort_chip_map")
    jp_bank = original_jp[0x7EC10:0x802D0]
    jp_map = original_jp[0x43F40:0x445C0]
    native_row = extract_rect(jp_map, jp_bank, 0, 24, 28, 1)
    p_mask = ["".join("#" if native_row[y][x] == 9 else "."
                      for x in range(143, 148)) for y in range(1, 7)]
    ensure(p_mask == ["####.", "##.##", "##.##", "####.", "##...", "##..."],
           "native SORT P changed")
    font = json.loads((RES / "sort_extensions.json").read_text())["glyphs"]
    font["P"] = p_mask
    canvases = {"NAME_ATK": [[3] * 72 for _ in range(8)],
                "TYPE": [[3] * 32 for _ in range(8)]}
    labels = []
    for text, which, origin, x in (("NAME", "NAME_ATK", 32, 36),
                                   ("ATK", "NAME_ATK", 32, 70),
                                   ("TYPE", "TYPE", 184, 184)):
        canvas, cursor = canvases[which], x - origin
        for i, ch in enumerate(text):
            mask = font[ch]
            ensure(len(mask) == 6 and len({len(r) for r in mask}) == 1,
                   "SORT extension metrics differ")
            for y, row in enumerate(mask):
                for k, p in enumerate(row):
                    if p == "#":
                        canvas[1 + y][cursor + k] = 9
            cursor += len(mask[0]) + (i + 1 < len(text))
        labels.append({"text": text, "screen_x": x, "screen_y": 129,
                       "face_width": cursor - (x - origin), "face_height": 6})
    nb = bytearray(bank)
    slot_groups = (("NAME_ATK", list(range(0x97, 0xA0))),
                   ("TYPE", list(range(0xB1, 0xB5))))
    changed_tiles = set()
    for which, ids in slot_groups:
        pats = patterns(canvases[which])
        for x, tid in enumerate(ids):
            put_tile(nb, tid, pats[(x, 0)])
            changed_tiles.add(tid)
    for name in ("sort_program_map", "sort_chip_map", "sort_backpack_map", "sort_data_map"):
        _, _, m = span(name)
        for tid in changed_tiles:
            for x, y in references(m)[tid]:
                ensure(y == 24 and (4 <= x < 13 or 23 <= x < 27),
                       f"SORT tile {tid:#x} has external consumer")
                ensure(word(m, x, y) & 0xC000 == 0,
                       "unexpected SORT tile flip")
    store("FuentesDiferentes_NAME_ATK_TYPE", {"sort_tiles": bytes(nb)},
          {"labels": labels, "native_exact": ["P"],
           "native_reference_captions_preserved": ["ID", "HP", "SP", "CS"],
           "extensions": sorted(font.keys() - {"P"}),
           "cursor_code_changed": False, "shared_maps_checked": 4})

    expected = set().union(*(set(g["changed_offsets"]) for g in groups))
    actual = {i for i, (a, b) in enumerate(zip(mant04_english, out)) if a != b}
    ensure(actual == expected, "unexpected changes outside reported ranges")
    ensure(out[0x340310:0x348310] == mant04_english[0x340310:0x348310],
           "native ROM font changed")
    checksum = sum(out[:-2]) & 0xFFFF
    out[-2:] = checksum.to_bytes(2, "little")
    return bytes(out), {"schema": 1, "status": "PASS_BINARY_SCOPE",
        "parent_sha256": PARENT_SHA, "original_sha256": JP_SHA,
        "output_sha256": sha(out), "checksum": hex(checksum),
        "changed_non_checksum": len(actual), "changed_offsets": sorted(actual),
        "outside_allowed": 0, "groups": groups,
        "runtime_confirmed_by_apply": False,
        "scope": "Native carousel masks, five full-width PET labels, three SORT labels"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jp", type=Path, required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    data, report = apply(args.jp.read_bytes(), args.base.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("groups", "changed_offsets")}, indent=2))


if __name__ == "__main__":
    main()
