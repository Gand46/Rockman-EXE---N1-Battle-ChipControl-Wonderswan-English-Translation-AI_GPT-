# QA14 — SHOP native font and NetNavi counter units

This component is applied by `scripts/qa14_shop.py` to the verified MANT04
graphics. It retains the existing MANT04 text, casing and other corrections.

## Why SHOP needed another correction

The submitted SHOP captures used an external small font. MANT04 replaced it
with the project's compact, authored 5×7 family. That family is still different
from the original type used for products and prices on this screen.

The literal original font is stored at ROM `0x340310`, in 8×16 packed 4bpp
cells. Five independently located original quantity/price digit cells match
this source font exactly, with zero differing foreground pixels. The product
labels now reuse its original `0 1 C H I P S N F O` masks without scaling,
thickening, drawing new letters or changing the runtime font bank.

`1 CHIP`, `10 CHIPS` and `INFO` retain MANT04 capitalization. All three start
at x=24; their original 16-pixel fields begin at y=8, 24 and 56. The largest
label occupies 64 pixels including its space and fits in the 72-pixel original
field. Existing prices, currency, selector, dialogue and frame stay intact.

## What the marks after Total Chips really are

The submitted image points to suffixes next to the two numeric counters.
They are the legitimate translated units `T` (types, original **種**) and
`C` (chips, original **枚**), introduced in
`pet_submenu_assets_v0_9.py`. Their former hand-built 3-pixel-wide glyphs were
stretched vertically to 14 pixels, making T resemble an isolated stem and C
resemble a bracket. They are separate from the orange Y2/MegaMan artwork.

The repair keeps both counters and units. It replaces only the following four
static tile slots with the exact native T/C masks, whose ink is 7×11 pixels
inside the original 8×16 cells:

| Unit | Meaning | Pixel cell origin | Tile IDs in bank `0x080300` |
| --- | --- | --- | --- |
| T | Types | 160, 32 | `0x39`, `0x3E` |
| C | Chips | 200, 32 | `0x3B`, `0x3F` |

Both the NetNavi primary map (`0x0452C6`) and its statistics map (`0x045748`)
are checked for shared consumers. Each changed tile is used only by its
designated unit cell and has no statistics-map consumer. Both maps remain
byte-identical. Numbers, save memory, update code and the orange art remain
byte-identical.

## Editable source and guards

- `labels.json` specifies SHOP wording, rectangle and placement.
- `native_glyphs.json` contains the exact 8×16 masks, original glyph indices,
  ROM offsets and individual hashes for the eleven reused characters.
- The script checks each mask against the verified Japanese source. Editing
  an original mask without updating the design/provenance policy is rejected.
- SHOP can use only its original 23 exclusive label tile slots. The current
  result uses 20 distinct nonblank patterns. Price tiles are excluded.
- Map palette, priority and flip attributes cannot change. All non-target map
  cells and all non-owned tiles are protected.
- QA09's existing 22-byte edits to the unrelated `[V5]`/`[equip1]` glyph slots
  are retained. The eleven characters reused here are byte-identical to JP.
  The complete runtime font bank remains byte-identical to MANT04.

On unmodified MANT04 this component changes 396 non-checksum bytes, all inside
the declared SHOP label map/tile ranges and four NetNavi suffix tiles. The
WonderSwan checksum is recalculated after those edits. `apply(jp, base)`
returns the ROM and a report including every changed non-checksum offset so
the build can combine it with independently checked, disjoint corrections.

## Validation boundary

The module reports binary and glyph provenance checks only. A fresh screen
load is required for runtime inspection: an old savestate can retain stale
VRAM. Navigation, purchases, counter updates and reentry must be recorded by
the final QA capture workflow. Static glyph generation alone does not claim
functional or visual approval.
