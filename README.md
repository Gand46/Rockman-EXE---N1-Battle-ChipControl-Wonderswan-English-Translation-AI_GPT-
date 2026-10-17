# Rockman EXE N1 Battle · English + optional Chip Control

WonderSwan Color localization. **QA09 / MANT03 is the default release.**
Chip Control RC6 is a separate, optional **experimental binary adaptation**.
Repository layout 2.0 reorganizes the sources; it does not change either game output.

[Español](docs/es.md) · [Build guide](docs/build.md) · [Editing guide](docs/editing.md) · [Reports](docs/reports/index.html)

## Choose one patch

| Variant | Direct Japanese-ROM patch | Status |
| --- | --- | --- |
| **QA09 English** | [QA09 BPS](patches/qa09/Rockman_N1_English_QA09.bps) | Default · scoped synthetic validation |
| QA09 + Chip Control RC6 | [Experimental BPS](patches/chip-control/Rockman_N1_English_QA09_ChipControl_RC6_EXPERIMENTAL.bps) | Optional · experimental |

Both patches use the same **4,194,304-byte Japanese original**:
`4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed`.
Apply **one** BPS directly to that ROM. Never stack these patches or apply the old RC6 IPS to QA09.
No game ROM, save data or compiled emulator is bundled.

## Build

Python 3.11 or newer; the normal manifest build uses only the standard library.

```console
python scripts/project.py build --source "/path/to/original.wsc"
python scripts/project.py build --source "/path/to/original.wsc" --variant chip-control
```

Outputs stay in ignored `build/qa09/` and `build/chip-control/` directories.
The original ROM and editable sources remain untouched. Windows and macOS launchers:
`scripts/build.bat "C:\path\original.wsc"` and `bash scripts/build.command "/path/original.wsc"`.
Add `--variant all` to build both explicitly.

## Verify

```console
python -m pip install -r requirements/qa.txt
python scripts/project.py check
python scripts/project.py verify --source "/path/to/original.wsc"
```

Verification compares both exact ROM/BPS hashes, replays the inherited QA09 resource
generators in an isolated copy, and runs the test suites. It reports skipped private
fixtures separately. It does **not** claim a fresh emulator run or hardware testing.
[Validation scope and results](docs/validation.md).

## Where things belong

| Directory | Purpose |
| --- | --- |
| [components/qa09](components/qa09/README.md) | Editable translation, assets, original project modules and regression tests |
| [components/chip-control](components/chip-control/README.md) | Optional RC6 adapter, vendor inputs and isolated tests |
| [patches](patches/README.md) | Exactly two current player-facing BPS files |
| [docs](docs/README.md) | Current guidance and consolidated HTML reports |
| `scripts/`, `tests/` | Repository entry point, safety checks and packaging tests |
| `maintenance/` | Source inventory, migration ledger and verification records |

Obsolete launchers, standalone historical reports and legacy packaging tools live in
the **separate history ZIP**, not in the working tree. The main source ZIP rebuilds
both variants without that archive. [Architecture and archive policy](docs/architecture.md).

## Sources, credits and publication

QA09 preserves the supplied editable localization and resource-generation sources.
The RC6 package did **not** include its original editable assembly: the adapter is
editable, the RC6 engine is **not source-complete**. No missing engine source is claimed.

Project-authored material retains the [existing MIT license](LICENSE). Game assets,
third-party references and the RC6 payload have separate rights. RC6 redistribution
permission is not documented in the supplied material. See [credits and provenance](docs/provenance.md)
and [publication checklist](docs/publication.md) before publishing binary payloads.
