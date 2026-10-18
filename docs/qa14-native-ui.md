# QA14 / MANT05 — Native UI repair method

The verified organized MANT04 package is the predecessor. QA09 and QA13 are
reconstructed first; QA14 consumes exact MANT04 preimages. Every predecessor file
is accounted for in `maintenance/qa14-inheritance.json`.

## Native references

| Finding | Reference and edit | Preserved |
| --- | --- | --- |
| SHOP | Original product/price digits match the 8×16 font at ROM `0x340310`. Copy literal masks for 1 CHIP,10 CHIPS,INFO; origin x24, row cells y8/y24/y56. | Prices, palettes, selector and actions. |
| Carousel | PET P/E/T match the original master font exactly. Reuse its capitals,8px advance and7×11 faces for four banners. | PET, building art and actions. |
| SORT | Original ID/HP/SP/CS define the6px bold family. P is copied; A/N/M/E/T/K/Y are explicit extensions. NAME x36,ATK x70,TYPE x184. | ID/HP/SP/CS and all seven selector/handler positions. |
| PET root | Preserve full72px QA09 masks, moved down4px with24px row spacing. MANT04's incomplete +6px windows cut terminal glyphs. | Full captions, palette, cursor and actions. |
| Total Chips | Earlier T/C unit suffixes were artificial3×14 glyphs. Replace four tiles with literal8×16 cells. | Numeric fields, count logic, units and orange header art. |

The SORT cursor oscillates2px. A complete cycle establishes a common one-pixel
gap at its leftmost phase. ID/HP already match SP/CS; NAME/ATK are moved accordingly.
N uses a6px face to retain a readable diagonal while NAME keeps its right boundary.

## PET atlas capacity

A lossless4px shift requires more distinct tiles than the old exclusive pool.
The complete native atlas is relocated into a guarded resource-area gap with16
additional slots. The existing descriptor/loader handles it; no new code is added.

| Property | Original/MANT04 | MANT05 |
| --- | --- | --- |
| Descriptor | `0x0700C0` | Source paragraph/length updated |
| ROM source | `0x07C310` | `0x0D7000` |
| Length | `0x09C0` (78 tiles) | `0x0BC0` (94 tiles) |
| Relative paragraph | `0x0C25` | `0x66F4` |
| VRAM extent | `0x8000–0x89BF` | `0x8000–0x8BBF` |
| Flags | `0x4200`,`0x0100` | Preserved |

The160-entry directory ends declared resources at `0x0D6898`. The new range has
its original preimage and overlaps no declared resource or existing translation
contribution. Old atlas and adjacent palette remain. Runtime evidence checks all
new VRAM writes, selections and reentries, rather than relying only on blank bytes.

## Integration

`qa14_menu.py` and `qa14_shop.py` independently receive JP and the same MANT04
English bytes. `build_mant05.py` merges disjoint offsets, preserves the complete
shared font bank, fixes checksum and rejects unreported writes.
`qa14_chipcontrol.py` verifies RC6, protects consumed spans including unchanged IPS
holes and carries every English change into the optional variant.

Editable masks, text, positions and provenance are under
`components/qa09/translation/qa14_menu/` and `qa14_shop/`. No installed font or
bitmap scaling generates the ROM lettering. See [editing](editing.md).

## Evidence

[Illustrated report](reports/qa14-native-ui.html) · [UI comparisons](evidence/qa14/ui_runtime.json)
· [RC6 static checks](evidence/qa14/chip_control_static.json)
· [Combat regression](evidence/qa14/chip_control/runtime.json).

The supplied Total Chips image was enlarged non-integrally. Exact pixel judgments
use fresh native224×144 captures with integer nearest-neighbor zooms.
Hardware and exhaustive natural play remain outside this release. Original RC6
assembly/build sources are the inherited source-completeness gap.
