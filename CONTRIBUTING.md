# Contributing

Start with [architecture](docs/architecture.md), [editing](docs/editing.md) and
[validation](docs/validation.md). Keep changes scoped to one component. Use a branch
and a pull request; do not replace QA09 with the experimental RC6 build.

A useful change includes the editable source/resource change, its rationale,
reproduction steps, affected offsets/screens, tests and a clearly labelled result.
Never upload ROMs, SRAM, savestates, private paths or emulator binaries.

Run `python scripts/project.py check --structure-only` while editing, then build and
test the affected component. `--allow-modified` is available only for intentional QA09
development output; it never replaces the pinned release BPS. Regenerate the source
inventory with `python scripts/project.py snapshot` only after reviewing the diff.
Update `CHANGELOG.md` and `PROJECT_CONTEXT.md` for a maintained change.

Use `python scripts/project.py package --output ../Rockman_N1_sources.zip` for a
source-only archive. Test from a fresh extraction before release. Keep historical
commands in the archive rather than adding old BUILD_QAxx launchers to the root.
