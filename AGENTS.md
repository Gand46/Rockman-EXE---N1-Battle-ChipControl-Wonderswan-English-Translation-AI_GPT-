# Repository working rules

Read `PROJECT_CONTEXT.md`, `project.json` and the relevant component README first.
Check `python scripts/project.py check`; report existing intentional drift rather
than discarding it. The active baseline is QA09/MANT03 and the optional RC6 adapter.

Keep both outputs independent. Do not change ROM bytes for housekeeping. Preserve
editable assets, generators, tables, credits and tests. Record moves in the migration
ledger; do not infer that old-looking assets or versioned Python modules are unused.

Use `scripts/project.py` for supported builds/tests. Legacy source-generation modules
may be used in an isolated copy only; normal builds must not overwrite edited manifests.
A source snapshot verifies bytes, not gameplay. A historical emulator report is not
a freshly executed test. Label skipped/private fixtures and synthetic access honestly.

Never package original/modified ROMs, save files, compiled emulator binaries or font
installation files. Rebuild and test the ZIP after extraction. Preserve any unresolved
work as a checkpoint; do not invent missing RC6 assembly or redistribution approval.
