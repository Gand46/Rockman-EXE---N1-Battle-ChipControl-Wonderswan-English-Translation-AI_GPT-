# Changelog

## QA09 MANT04 — Visual consistency maintenance (2026-10-17)

- Aligned PET root menu captions with the unmodified pointer, preserving bitmap letterforms.
- Replaced SHOP, HOST TOURNEY, FREE BATTLE static headings with editable compact native-style masks, keeping prices and live counters untouched.
- Matched Program Deck sorting captions `NAME`, `ATK`, `TYPE` to the `HP/SP/CS` baseline using guarded tile-only edits.
- Identified the orange `TOTALCHIPS` header detail as pre-existing Japanese artwork: no destructive change.
- Validated direct-original BPS for two variants, zero conflict bytes with RC6 executable code, scoped emulator captures.
- Promoted MANT04 as current; the original MANT03 BPS is retained solely as a compatibility reference.

# Changelog

## Repository layout 2.0 · 2026-10-16

This is a **repository maintenance change**, not QA10 and not a new Chip Control release.

- Split translation and optional RC6 into sibling components.
- Reduced the root to current project-level files; removed placeholder-only folders.
- Separated the two current BPS files from historical input patches.
- Replaced competing launchers and duplicate workflows with one command interface and one CI workflow.
- Moved superseded documents, packaging scripts and unneeded raw historical evidence into a companion archive.
- Preserved the integrated QA01–QA12 HTML and the RC6 investigation once each.
- Added a path/hash migration ledger, source inventory, safe packaging and regression tests.
- Made the supported build consume the current editable manifest without silently recomposing it.
- Retained an isolated replay of the original resource-generation chain as an additional reconstruction check.

The QA09 and experimental RC6 ROM/BPS identities remain pinned in `project.json`.
Detailed history is in [the integrated report](docs/reports/qa09-complete-history.html).
