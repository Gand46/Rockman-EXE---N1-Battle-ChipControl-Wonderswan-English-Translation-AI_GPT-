# Rockman EXE N1 Battle — English QA09 MANT05

WonderSwan Color localization with an optional, experimental Chip Control RC6
variant. This package includes cumulative editable sources, resource editors,
validation evidence and two independent BPS patches.

[Español](docs/es.md) · [Build](docs/build.md) · [MANT05 changes](docs/qa14-native-ui.md)
· [Illustrated QA report](docs/reports/qa14-native-ui.html) · [History](docs/reports/index.html)

## Choose one cumulative patch

| Variant | Apply directly to the original Japanese ROM | Role |
| --- | --- | --- |
| **QA09 MANT05** | [English MANT05](patches/qa09/Rockman_N1_English_QA09_MANT05.bps) | Default localization |
| QA09 MANT05 + Chip Control RC6 | [Experimental RC6 MANT05](patches/chip-control/Rockman_N1_English_QA09_ChipControl_RC6_MANT05_EXPERIMENTAL.bps) | Optional battle extension |

Both require unmodified Japanese **Rev. 1**, 4,194,304 bytes, SHA-256
`4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed`.
Apply one BPS to that original. Do not apply these patches in sequence.

MANT05 corrects SHOP/PET lettering, SORT typography/alignment, five PET menu
labels and distorted T/C units after Total Chips. It preserves the cumulative
translation and optional RC6 behavior. The illustrated report compares the
original references, MANT04 and final native-resolution captures.

## Build from complete sources

Python 3.11 or later; normal builds use the standard library:

```sh
python scripts/project.py build --source "/path/original.wsc"
python scripts/project.py build --source "/path/original.wsc" --variant all
```

Outputs: `build/mant05/qa09/` and `build/mant05/chip-control/`. The original ROM is
checked and left intact. Windows: `scripts\build.bat "C:\path\original.wsc" --variant all`.
macOS/Linux: `bash scripts/build.command /path/original.wsc --variant all`.

The builder reconstructs QA09's editable manifest/assets, verifies MANT04, applies
QA14 native-font/layout editors, then carries the authenticated RC6 delta onto the
English result if requested. No earlier source ZIP or patched ROM is required.
The English-only build does not need the optional RC6 vendor files.

## Verify and edit

```sh
python -m pip install -r requirements/qa.txt
python scripts/project.py check
python scripts/project.py verify --source "/path/original.wsc"
```

[Editing](docs/editing.md) identifies the source layers. `--baseline` reproduces
historical QA09/MANT03. MANT04 reference BPS remain in `maintenance/mant04-patches/`;
only the two MANT05 player patches appear under `patches/`.

UI validation covers 21 controller routes and 53 native captures per variant,
including a purchase/count update, save and cold reload. Combat regression checks
Y1 AP/SP and restoration against MANT04. See [scope](docs/validation.md).

## Package contents

- `components/qa09/`: cumulative text, graphics, tables, tools and tests.
- `components/chip-control/`: pinned RC6 inputs, editable adapter and tests.
- `scripts/`: orchestration, bounded graphic editors and QA replays.
- `patches/`: the two current cumulative BPS files.
- `docs/`: instructions, native PNGs, measured checks and HTML reports.
- `maintenance/`: predecessors, inheritance inventory and verification records.

Commercial ROMs, private saves and compiled emulators are excluded. RC6's original
assembly was not supplied; its adapter and this integration are editable. See
[provenance](docs/provenance.md) and preserved [publication notes](docs/publication.md)
for the inherited source boundaries.
