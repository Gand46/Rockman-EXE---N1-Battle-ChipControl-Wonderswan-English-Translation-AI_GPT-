# Build and reproducibility — MANT05

Python 3.11 or newer. Normal builds use the standard library. Provide unmodified
Japanese Rev. 1 outside the source tree: 4,194,304 bytes, SHA-256
`4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed`.

```sh
python scripts/project.py build --source /path/original.wsc
python scripts/project.py build --source /path/original.wsc --variant all
python scripts/project.py check
python scripts/project.py verify --source /path/original.wsc
```

`build/mant05/<variant>/` contains outputs and a build manifest. Each BPS applies
directly to JP. Original input and editable resources remain intact. The builder
reconstructs QA09, authenticates MANT04, merges the independent QA14 resource
editors, checks optional RC6 integration, checksums and BPS roundtrips.

Historical reconstruction:

```sh
python scripts/project.py build --source /path/original.wsc --baseline --variant all
python scripts/build_mant04.py --source /path/original.wsc
```

For intentional QA14 development use `project.py build --allow-modified`. Outputs
are marked development candidates; published BPS are not overwritten. Original,
predecessor, preimage and overlap guards remain mandatory. To edit the historical
base itself, use `--baseline --allow-modified` and reconcile that lineage separately.

Windows: `scripts\build.bat "C:\Games\original.wsc" --variant all`.
macOS/Linux: `bash scripts/build.command /path/original.wsc --variant all`.
Current execution was on Linux; Windows/macOS launchers were inspected, not executed.

## Tests and emulator replay

Install `requirements/qa.txt` for full tests/image analysis. `verify` checks the
inventory, current builds, historical generators in isolation and available tests.
Missing private fixtures are reported explicitly.

```sh
python scripts/qa14_capture_ui.py --rom build/mant05/qa09/Rockman_N1_English_QA09_MANT05.wsc --engine /private/qa --sram /private/winner.srm --output /private/sessions/M05_EN
python scripts/qa14_verify_ui.py --sessions /private/sessions --output /private/ui_runtime.json
```

The comparator expects corresponding `M04_EN_complete`, `M04_CC_complete`, `M05_EN`
and `M05_CC` sessions. Repeat the capture command for each ROM/output name.
The UI seed starts with 2,800 Z and 9 types/13 chips. Routes make an actual one-chip
purchase, save and load in a new process. The UI runner rejects WRAM pokes.
Private QA hashes/provenance are in [the dependency record](../maintenance/qa14-dependencies.json).

`qa14_chipcontrol_runtime.py` uses separately identified inherited synthetic battle
fixtures. See [validation](validation.md). Private saves and compiled cores are
excluded from the source ZIP; normal builds do not depend on them.

## Package

After reviewing deliberate source changes:

```sh
python scripts/project.py check --structure-only
python scripts/project.py snapshot
python scripts/project.py package --output ../Rockman_N1_QA09_MANT05_Fuentes_Completas.zip
```

Packaging is deterministic and excludes private/build files. The release must also
be extracted into a clean directory, rebuilt and tested. The delivery receipt
records those executed checks, not ZIP integrity alone.
