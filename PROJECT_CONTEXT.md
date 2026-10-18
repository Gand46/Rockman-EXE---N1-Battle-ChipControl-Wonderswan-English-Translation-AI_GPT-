# Current project state — QA14 / MANT05

**Authority:** the organized MANT04 source ZIP, SHA-256
`231290f82c161f0e94018e1a27376a5c1d5e54e2215f4bed8e636bc456ad68a1`,
superseded the initially visible private MANT03 checkpoint. Both MANT04 ROMs and
BPS were reconstructed exactly from Japanese Rev. 1 before editing. `project.json`
defines current MANT05, predecessor MANT04 and historical MANT03 identities.

## Current changes

- SHOP quantities/INFO and four carousel banners use literal original 8×16 cells.
  The original PET banner is the carousel reference.
- SORT keeps its native six-pixel family, literal P and documented extensions for
  missing capitals. All seven labels align with the original animated cursor.
- Complete PET labels move four pixels down from the inherited QA09 masks.
  A guarded native resource relocation supplies the needed tiles without clipping.
- Total Chips keeps meaningful T/C suffixes, now with complete native glyphs.
  MANT04's investigation of orange header art did not address those suffixes.

## Editable authority and build

Use `python scripts/project.py build --source original.wsc --variant all`.
The builder reconstructs QA09/MANT03, verifies MANT04, then merges independent
QA14 editors with overlap guards. It emits two BPS directly from JP. A normal
build needs only Python and that original, with no previous source ZIP or patched ROM.

`components/qa09/translation/en_qa09.json` and its 271 text/84 binary entries remain
the cumulative base. QA13 and QA14 scripts/JSON are additional editable layers.
Historical composers must run in isolation; normal builds preserve active edits.

## Evidence and limits

Current evidence is in `docs/evidence/qa14/`; the illustrated report is
`docs/reports/qa14-native-ui.html`. Each final variant has 21 cold-SRAM/controller
routes and 53 captures, including every menu/sort selection, actual purchase,
reentry, saving and a new-process cold reload. UI routes contain no WRAM edits.
Combat regression uses explicitly inherited synthetic fixtures and compares each
final variant against its corresponding MANT04 build.

No hardware or exhaustive natural-playthrough result is claimed. RC6 remains an
optional experimental binary adaptation: its original assembly and builder/test
sources were not supplied. The adapter and new corrections are editable.

## Continuity

`maintenance/qa14-inheritance.json` accounts for all MANT04 source files, including
revisions and patch moves. Revised predecessor bytes are retained in
`maintenance/mant04-originals.zip`. Historical reports preserve their original
scope; they are not current instructions. `maintenance/source-manifest.json`
seals the new tree. The delivery receipt records clean extraction/rebuild/tests.

The prior WIP checkpoint is superseded, as recorded in
`maintenance/qa14-work-in-progress.json`. Original archives and the user's JP ROM
are preserved. No live GitHub repository was modified or published by this task.
