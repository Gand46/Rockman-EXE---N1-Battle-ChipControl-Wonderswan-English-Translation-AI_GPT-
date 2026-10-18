# QA09 MANT05 · English localization

**Default component. No Chip Control hooks are added to this build.**
The patch and ROM identities are in [project.json](../../project.json).

| Area | Contents |
| --- | --- |
| `translation/en_qa09.json` | Current cumulative edit manifest |
| `translation/assets/` and versioned subdirectories | Resource fragments, editable graphics/data and generation records |
| `src/` | Encoding, insertion, allocation, graphic/text generators and regression tooling |
| `tables/`, `references/` | Native/reference character maps |
| `tests/fixtures/patches/` | Test-only QA08/A8 reference patches, not current downloads |
| `evidence/` | Historical records directly consumed by current regression tests |
| `qa/` | Source-only emulator and original replay routes; no compiled core or private saves |

From the repository root use `python scripts/project.py build --source /path/original.wsc` for **MANT05**; the historical QA09 manifest is reconstructed first and QA13 reconstructs the verified predecessor, then QA14 applies the native UI corrections from editable scripts and JSON resources.
See [editing](../../docs/editing.md) before changing data. Versioned support manifests in `translation/lineage/`
and module names are retained where they preserve resource-generation lineage and tests;
`en_qa09.json` is the cumulative base manifest; QA13/QA14 edits are additional source layers. See `../../docs/editing.md`.

Original diagnostic programs may require private fixtures not distributed here.
The supported repository commands report missing fixtures rather than claiming runtime success.
