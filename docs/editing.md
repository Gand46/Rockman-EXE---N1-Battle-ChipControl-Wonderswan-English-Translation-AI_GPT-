# Editing QA09 and Chip Control

## QA09

Start at [the component README](../components/qa09/README.md).
The current cumulative manifest is `components/qa09/translation/en_qa09.json`.
It contains 271 text entries and 84 binary resource entries. Text entries carry
source-span hashes, offsets, lengths and control tokens. Binary entries refer to
resource files below the manifest directory.

Keep portrait/line/wait/end controls, native glyph semantics, allowed ROM ranges,
expected original-span hashes, allocation boundaries and pointers intact.
`tables/n1battle_jp.tbl` and the existing codecs define the encoding. Do not perform
blind whole-ROM replacements. Resource generators, editable graphics/JSON and
assembler files remain in the component; their versioned names identify provenance.

For an intentional editable-manifest experiment:

```console
python scripts/project.py build --source "/path/original.wsc" --allow-modified
```

This writes a `_DEV` output and never overwrites the pinned release BPS. Ordinary
builds require the exact known QA09 output. The supported build does not overwrite
current translations by rerunning old composers. Resource edits must update the
corresponding resource and metadata deliberately; static integration is not visual
or gameplay approval. Verify affected screens and record the new scope separately.

The `verify` regeneration step is intended to certify the pinned delivery. Before a
new game release, reconcile an intentional manifest/resource change with its generator
and update the release expectations only after review, not to suppress a failure.

## Chip Control

The editable surface is the adapter in
`components/chip-control/src/verify_and_build_experimental.py` plus its tests.
Its original RC6 assembly sources are absent. The vendor IPS is a pinned external
binary input; do not describe it as reconstructed original engine source.

The adapter accepts only the exact QA09 release. It must reject a modified QA09
until overlap, checksum and runtime/semantic compatibility are re-audited. New game
behavior requires separate QA; repository reorganization supplies no new gameplay approval.
