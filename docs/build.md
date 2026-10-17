# Build and verification

## Requirements and input

Python 3.11+. A normal manifest build uses the standard library only. Full generator
verification and some asset tests need the existing pinned dependencies:

```console
python -m pip install -r requirements/qa.txt
```

Provide your own unmodified Japanese ROM. Its size and SHA-256 must match
[`project.json`](../project.json). Keep it outside the repository. Wrong inputs fail
before build output is written. No script downloads game ROMs.

## Current commands (from the repository root)

```console
python scripts/project.py check
python scripts/project.py build --source "/path/original.wsc"
python scripts/project.py build --source "/path/original.wsc" --variant chip-control
python scripts/project.py build --source "/path/original.wsc" --variant all
python scripts/project.py test
python scripts/project.py verify --source "/path/original.wsc"
```

`build` defaults to QA09. `--variant all` is explicit. Outputs have separate directories
and filenames under `build/`. The adapter uses QA09 freshly built from resources,
then applies the hash-guarded RC6 delta and recomputes the WonderSwan checksum.
No input file is patched in place.

`verify` additionally regenerates QA09 through its original QA04→QA09 source chain
inside an isolated tree, compares its exact ROM/BPS identities, checks the repository
inventory and runs all suites. Results/logs remain under ignored `build/`.

`test` without a ROM runs applicable source-only tests and lists skips. Supplying
`--source` also enables binary-delta tests and locally prepares private build fixtures.
A skip is not a passed test. Private original savestates/SRAM are intentionally absent.

## OS launchers

Windows:

```bat
scripts\build.bat "C:\Games\original.wsc"
scripts\build.bat "C:\Games\original.wsc" --variant all
```

macOS/Linux:

```sh
bash scripts/build.command "/path/with spaces/original.wsc"
bash scripts/build.command "/path/with spaces/original.wsc" --variant all
```

Launchers preserve exit codes and resolve their own location. They do not install or
change dependencies. Direct Python commands work independently of launcher permissions.
Windows/macOS execution is configured in CI but not claimed as locally executed here.

## Packaging

Review changes and `git diff`. Then:

```console
python scripts/project.py check --structure-only
python scripts/project.py snapshot
python scripts/project.py package --output ../Rockman_N1_sources.zip
```

`check` verifies snapshot hashes; `--structure-only` allows intentional source edits
without accepting them silently. `snapshot` is an explicit maintainer operation,
not a repair for unknown drift. Packaging uses deterministic names/timestamps,
excludes all build trees/caches, rejects ROM/save/executable payloads, and tests the ZIP.
Extract it into a new directory and run `verify` there. Do not copy private test data
into the distributable ZIP. The companion history archive is optional.

## Git byte preservation

Git import/export was checked in addition to ZIP extraction. Eight inherited vendor/audit
files had CRLF bytes that generic text normalization would rewrite. Explicit `-text`
attributes preserve that vendored subtree and the original audit TSV. Do not remove
those rules without updating and reviewing the source-integrity/provenance records.
