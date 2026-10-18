#!/usr/bin/env python3
"""QA13/MANT04: bounded, editable native-style UI atlas corrections.

Takes the exact QA09 MANT03 ROM in-memory. Regenerates 4bpp assets from
editable glyph masks and guarded map cells; never rewrites executable code,
text tables, font ROM, pointers, palettes, other tile consumers, or SRAM.
Chip Control is layered independently after verifying all target bytes match.
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
from collections import defaultdict

ROOT=Path(__file__).resolve().parents[1]
SYS=ROOT/'components/qa09'
BASE_SHA='d729823bbe6cf9132e6345ed734eb2dbe51885c13d5a17a44a9f7cfae086c326'
CC_SHA='1fec1a21d486fe30931053181810e2d9f82d573c5ece5dae23e1416b060de57e'
ROM_BYTES=0x400000

def digest(x):return hashlib.sha256(x).hexdigest()
def ensure(c,why):
    if not c:raise ValueError(why)
def unpack(t):return [q for b in t for q in (b>>4,b&15)]
def pack(p):
    ensure(len(p)==64 and all(0<=v<=15 for v in p),'not an 8x8 4bpp tile')
    return bytes((p[i]<<4)|p[i+1] for i in range(0,64,2))
def mapid(m,x,y):return int.from_bytes(m[2*(y*32+x):2*(y*32+x)+2],'little')&511
def mapset(m,x,y,t):
    a=2*(y*32+x);w=int.from_bytes(m[a:a+2],'little');m[a:a+2]=((w&~511)|t).to_bytes(2,'little')

def tile(bank,tid,first):
    z=(tid-first)*32;ensure(0<=z<=len(bank)-32,f'tile {tid:X} outside bank')
    return bytes(bank[z:z+32])
def put_tile(bank,tid,first,p):
    z=(tid-first)*32;ensure(0<=z<=len(bank)-32,'invalid tile allocation')
    bank[z:z+32]=p

def native_masks():
    d=json.loads((SYS/'translation/qa03/compact_display_font.json').read_text())['glyphs']
    # Only missing numerals are documented extensions in the same 5x7 pixel grid.
    d['0']=['.###.','##.##','##.##','##.##','##.##','##.##','.###.']
    d['1']=['..##.','.###.','..##.','..##.','..##.','..##.','#####']
    return d

def fill_text(text,width,height,background,face,*,x=None,y=4):
    faces=native_masks()
    text=text.upper()
    ensure(set(text)<=set(faces)|{' '},f'missing native mask for {text}')
    letterspace=1; spacewidth=3
    measured=sum(spacewidth if c==' ' else len(faces[c][0]) for c in text)+sum(1 for a,b in zip(text,text[1:]) if a!=' ' and b!=' ')
    if x is None:x=(width-measured)//2
    ensure(x>=0 and x+measured<=width,f'{text} ({measured}px) outside {width}px; x={x}')
    ensure(y>=0 and y+7<=height,'font exceeds label height')
    canvas=[[background]*width for _ in range(height)]
    cursor=x
    for i,c in enumerate(text):
        if c==' ':cursor+=spacewidth;continue
        for j,ln in enumerate(faces[c]):
            for k,p in enumerate(ln):
                if p=='#':canvas[y+j][cursor+k]=face
        cursor+=len(faces[c][0])+(1 if i+1<len(text) and text[i+1]!=' ' else 0)
    return canvas,{'text':text,'width':measured,'x':x,'y':y,'height':7,'font':'native-derived-compact-5x7-with-documented-numerals'}

def from_rect(m,b,x,y,w,h,first):
    ret=[[0]*(w*8) for _ in range(h*8)]
    for yy in range(h):
        for xx in range(w):
            tid=mapid(m,x+xx,y+yy);p=unpack(tile(b,tid,first))
            for j in range(8):ret[yy*8+j][xx*8:xx*8+8]=p[j*8:j*8+8]
    return ret

def make_patterns(canvas):
    h=len(canvas);w=len(canvas[0]);ensure(w%8==h%8==0,'bad dimensions')
    return [[pack([canvas[y*8+j][x*8+k] for j in range(8) for k in range(8)]) for x in range(w//8)] for y in range(h//8)]

def remap_group(rom,label,mo,ml,to,tl,first,rects,bg_tile,bg,extra_unused_tiles=()):
    m=bytearray(rom[mo:mo+ml]);b=bytearray(rom[to:to+tl]);oldm=bytes(m);oldb=bytes(b)
    allowed={(x+i,y+j) for x,y,w,h,_,_ in rects for i in range(w) for j in range(h)}
    refs=defaultdict(set)
    for a in range(0,len(m),2):refs[int.from_bytes(m[a:a+2],'little')&511].add((a//2%32,a//2//32))
    oldids={mapid(m,x,y) for x,y in allowed};avail=sorted(t for t in oldids if t!=bg_tile and refs[t]<=allowed)
    shared={t for t in oldids if not refs[t]<=allowed}
    ensure(shared<={bg_tile},f'{label}: shared glyph tiles: {shared}')
    for t in extra_unused_tiles:
        ensure(first <= t < first+len(b)//32,f'{label}: extra tile outside bank: {t:X}')
        ensure(not refs[t],f'{label}: extra tile {t:X} is referenced')
        ensure(t not in avail,f'{label}: extra tile {t:X} double allocation')
        ensure(t != 0x45,f'{label}: dynamically appended footer tile must be preserved')
        avail.append(t)
    blank=pack([bg]*64)
    ensure(tile(b,bg_tile,first)==blank,f'{label}: background tile differs')
    pattern_id={blank:bg_tile};assigned={};notes=[]
    for x,y,w,h,canvas,meta in rects:
        ensure(len(canvas)==h*8 and len(canvas[0])==w*8,f'{label}: canvas dimensions')
        for yy,row in enumerate(make_patterns(canvas)):
            for xx,pattern in enumerate(row):
                if pattern not in pattern_id:
                    ensure(len(assigned)<len(avail),f'{label}: not enough exclusive tiles: {len(avail)}')
                    t=avail[len(assigned)];pattern_id[pattern]=t;assigned[t]=pattern
                mapset(m,x+xx,y+yy,pattern_id[pattern])
        notes.append(meta)
    for tid,pat in assigned.items():put_tile(b,tid,first,pat)
    # Clears old exclusive patterns that are no longer addressed to avoid
    # Japanese/TTF residue in accidentally re-used atlas slots.
    for tid in avail[len(assigned):]:put_tile(b,tid,first,blank)
    # Invariants: map attribute/priority bits, non-target map entries and
    # externally referenced tile bytes must remain byte-identical.
    for a in range(0,len(m),2):
        old=int.from_bytes(oldm[a:a+2],'little');new=int.from_bytes(m[a:a+2],'little');pos=(a//2%32,a//2//32)
        ensure((old^new)&~511==0,f'{label}: map attributes modified')
        if pos not in allowed:ensure(old==new,f'{label}: cell {pos} altered')
    for tid,positions in refs.items():
        if not positions<=allowed and first<=tid<first+len(b)//32:
            ensure(tile(b,tid,first)==tile(oldb,tid,first),f'{label}: non-target tile 0x{tid:x} modified')
    changes=[]
    for name,off,old,new in [('map',mo,oldm,m),('tiles',to,oldb,b)]:
        changes.extend(off+i for i,(u,v) in enumerate(zip(old,new)) if u!=v)
    rom[mo:mo+ml]=m;rom[to:to+tl]=b
    return {'group':label,'edits':len(changes),'tile_ids_allocated':sorted(assigned),'map_offset':f'0x{mo:06X}','tile_offset':f'0x{to:06X}','labels':notes,'changed_offsets':changes}

def group_text(rom,label,mo,ml,to,tl,first,bg_tile,bg,face,labels):
    rects=[]
    for name,text,x,y,w,h,left,top in labels:
        canvas,meta=fill_text(text,w*8,h*8,bg,face,x=left,y=top)
        meta['id']=name;meta['tile_rect']=[x,y,w,h];rects.append((x,y,w,h,canvas,meta))
    return remap_group(rom,label,mo,ml,to,tl,first,rects,bg_tile,bg)

def repair_root(rom):
    mo,ml,to,tl=0x042DBA,0x0400,0x07C330,0x0980
    m=rom[mo:mo+ml];bank=rom[to:to+tl]
    items=[('Program Deck',2,2,8,2),('Chip Folder',2,5,7,2),
           ('Data Library',2,8,8,2),('NetNavi',2,11,5,2),('Save',2,14,3,2)]
    rects=[]
    for name,x,y,w,h in items:
        old=from_rect(m,bank,x,y,w,h,1)
        ensure(set(v for row in old for v in row)<={9,1,11},f'PET {name}: unexpected palette')
        active=[j for j,row in enumerate(old) if any(v in (1,11) for v in row)]
        ensure(active and max(active)<=8,f'PET {name}: unexpected source geometry')
        # Keep *every pixel* of the canonical QA09 PET native letterform,
        # including nine vertical rows, outline, capitalization and spacing.
        # The consumer cursor lives lower than these graphics. A lossless +6px
        # shift requires 48 unique 4bpp patterns; the original label-only pool
        # has 34, so explicitly reserve 14 previously UNREFERENCED atlas tiles.
        # Tile 0x45 must remain unavailable (the engine appends its footer row
        # dynamically). No runtime-consumed tile or map border is modified.
        new=[[9]*(w*8) for _ in range(16)]
        for gy in range(10):
            new[6+gy]=old[gy][:]
        rects.append((x,y,w,h,new,{'id':'pet_root_'+name.replace(' ','_').lower(),
            'font':'QA09 native PET glyph bitmap moved verbatim',
            'original_y':[min(active),max(active)],'new_y':[min(active)+6,max(active)+6],
            'all_original_glyph_rows_unchanged':True,'all_horizontal_pixels_unchanged':True,
            'palette_unchanged':True,'no_additional_ttf':True}))
    return remap_group(rom,'pet_root_vertical_alignment',mo,ml,to,tl,1,rects,6,9,
         extra_unused_tiles=(0x33,0x34,0x35,0x36,0x37,0x38,0x39,
                             0x42,0x43,0x44,0x47,0x48,0x49,0x4A))

# Native-consistent 4x6 bold extensions for the tightly spaced sorting bar.
# Original HP/SP/CS labels are 6px high, and remain byte-identical.
SORT_FONT={
 'A':('.##.','##.#','#..#','####','#..#','#..#'),
 'N':('#..#','##.#','####','#.##','#..#','#..#'),
 'M':('#..#','####','####','#..#','#..#','#..#'),
 'E':('####','##..','###.','##..','##..','####'),
 'T':('####','.##.','.##.','.##.','.##.','.##.'),
 'K':('#..#','#.#.','##..','###.','#.#.','#..#'),
 'Y':('#..#','#..#','.##.','.##.','.##.','.##.'),
 'P':('###.','#..#','###.','##..','##..','##..'),
}

def sort_repair(rom):
    mo,ml,to,tl=0x043F40,0x0680,0x07EC10,0x16C0
    bank=bytearray(rom[to:to+tl]);orig=bytes(bank)
    # Preserve all palette, sprite and unrelated consumer bits, including HP/SP/CS.
    rows=[('NAME',37),('ATK',71),('TYPE',184)]
    canvases={'NAME ATK':[[3]*72 for _ in range(8)],'TYPE':[[3]*32 for _ in range(8)]}
    specs=[('NAME','NAME ATK',32,37),('ATK','NAME ATK',32,71),('TYPE','TYPE',184,184)]
    for text,canvasname,offset,x in specs:
        canvas=canvases[canvasname]
        # Gap of one pixel between native-size letters.
        cursor=x-offset
        for c in text:
            for gy,line in enumerate(SORT_FONT[c]):
                for gx,v in enumerate(line):
                    if v=='#':canvas[1+gy][cursor+gx]=9
            cursor+=5
        ensure(cursor-offset<90,f'{text} oversized')
    for name,tileids in [('NAME ATK',tuple(range(0x97,0xA0))),('TYPE',tuple(range(0xB1,0xB5)))]:
        canvas=canvases[name];ensure(len(canvas[0])==len(tileids)*8,'sorting tile geometry')
        for k,t in enumerate(tileids):
            put_tile(bank,t,0,pack([canvas[y][k*8+x] for y in range(8) for x in range(8)]))
    # Verify these are the only consumers of touched bank indices in every
    # known shared 26-row PET bank map.
    allowed={(x,24) for x in list(range(4,13))+list(range(23,27))}
    for mapoff,maplen in [(0x0438BE,0x0680),(0x043F40,0x0680),(0x0445C2,0x0680),(0x044C44,0x0680)]:
        m=rom[mapoff:mapoff+maplen]
        for i in range(0,len(m),2):
            t=int.from_bytes(m[i:i+2],'little')&511
            if t in list(range(0x97,0xA0))+list(range(0xB1,0xB5)):
                ensure((i//2%32,i//2//32) in allowed,'Sorting tile consumer escaped bottom bar')
    # The legacy atlas uses the same IDs in 3 navigation modes.  Change only
    # the 13 owned tile slots, not the map, sprite cursor or nearby HP/SP/CS.
    changes=[to+i for i,(a,b) in enumerate(zip(orig,bank)) if a!=b]
    ensure(all((p-to)//32 in list(range(0x97,0xA0))+list(range(0xB1,0xB5)) for p in changes),'sort change out of range')
    rom[to:to+tl]=bank
    return {'group':'pet_sort_toolbar','edits':len(changes),'tile_offset':f'0x{to:06X}','labels':[{'id':n,'pixel_x':x,'glyph_height':6} for n,x in rows],'native_reference':'unchanged HP/SP/CS 6px glyphs, matching palette and baseline','changed_offsets':changes}

def preserve_native_netnavi(rom):
    # The orange triangular micro-banner is present in original JP.  The top
    # source map tile IDs are byte-identical to QA09; do not erase game art.
    j=ROOT/'docs/evidence/qa13/native_netnavi_provenance.json'
    if j.exists():
        info=json.loads(j.read_text());ensure(info['decision']=='PRESERVE_ORIGINAL','invalid native header policy')
    return {'id':'total_chips_right_orange_header','status':'ORIGINAL_NATIVE_ART_PRESERVED','changed_bytes':0,
            'reason':'Visible in earlier QA04/QA05 native captures; underlying JP/QA09 top map entries and corresponding header tile graphics match. The image does not prove a new chip-count corruption.'}

def apply(base):
    ensure(len(base)==ROM_BYTES,'wrong ROM size')
    ensure(digest(base)==BASE_SHA,'requires exact QA09 MANT03')
    out=bytearray(base)
    groups=[]
    # Preserve all existing graphic glyph construction for the root; rebaseline.
    groups.append(repair_root(out))
    # Carousel headings use one vetted editable pixel-mask family and original
    # palette/border/priority.  They no longer mix external TTF rasterizers.
    groups.append(group_text(out,'carousel_shop',0x041BB2,0x0480,0x0768F0,0x1740,0,5,10,7,
                  [('shop_banner','SHOP',1,1,6,2,None,8)]))
    # GP banner was not reported and remains byte-identical.
    groups.append(group_text(out,'carousel_free',0x0424B6,0x0480,0x079650,0x1580,0,5,10,7,
                  [('free_banner','FREE BATTLE',1,1,9,2,None,8)]))
    groups.append(group_text(out,'carousel_host',0x042938,0x0480,0x07ACA0,0x15C0,0,5,10,7,
                  [('host_banner','HOST TOURNEY',1,1,10,2,None,8)]))
    groups.append(group_text(out,'shop_purchase',0x04604C,0x0480,0x0818A0,0x0600,0,5,2,15,
                  [('shop_1_chip','1 Chip',2,1,8,2,21,1),
                   ('shop_10_chips','10 Chips',2,3,9,2,15,1),
                   ('shop_info','Info',2,7,5,2,11,1)]))
    groups.append(sort_repair(out))
    native=preserve_native_netnavi(out)
    # Unmodified original font and fixed gameplay bytes are invariants.
    ensure(out[0x340310:0x348310]==base[0x340310:0x348310],'native font ROM modified')
    expected=set().union(*(set(g['changed_offsets']) for g in groups))
    actual={i for i,(a,b) in enumerate(zip(base,out)) if a!=b}
    ensure(actual==expected,'unaccounted binary differences')
    ck=sum(out[:-2])&65535;out[-2:]=ck.to_bytes(2,'little')
    return bytes(out),{'status':'PASS_BINARY_SCOPE','base_sha256':BASE_SHA,'rom_sha256':digest(out),
      'changed_non_checksum':len(actual),'changed_checksum':sum(base[i]!=out[i] for i in (-2,-1)),
      'outside_allowed':0,'font_region_unchanged':True,'groups':groups,'netnavi':native,
      'checksum':f'0x{ck:04X}','all_binary_changes':sorted(actual)}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    data,report=apply(a.base.read_bytes());a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(data)
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('groups','all_binary_changes')},indent=2))
if __name__=='__main__':main()
