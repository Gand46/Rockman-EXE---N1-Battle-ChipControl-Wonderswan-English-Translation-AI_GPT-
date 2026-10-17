# Architecture and source boundaries

```text
Rockman_N1/
├── README.md / CHANGELOG.md / LICENSE
├── CONTRIBUTING.md / AGENTS.md / PROJECT_CONTEXT.md
├── project.json
├── components/
│   ├── qa09/                 # maintained localization
│   │   ├── src/              # original Python modules + assembler sources
│   │   ├── translation/      # cumulative manifest + editable/resource assets
│   │   ├── tables/           # native character map
│   │   ├── references/       # reference character map
│   │   ├── tests/fixtures/   # test-only historical patches
│   │   ├── evidence/         # records consumed by regression tests
│   │   └── qa/               # source-only emulator + replay routes
│   └── chip-control/         # isolated experimental adapter
│       ├── src/ / tests/
│       ├── vendor/           # hash-pinned IPS inputs; not current downloads
│       ├── evidence/
│       └── provenance/
├── patches/qa09/             # one default BPS
├── patches/chip-control/     # one experimental BPS
├── docs/reports/             # integrated history, compatibility, maintenance
├── scripts/                 # project.py and OS launchers
├── tests/                   # repository safety and separation
├── requirements/            # pinned QA/image-library dependencies
├── maintenance/             # source manifest, migration ledger, validation
└── .github/                 # one CI workflow, PR/issue templates, dependency review
```

## Why some versioned modules and assets remain

A filename containing `v0_9`, `qa04` or `rc3` is not automatically obsolete.
Later generators import earlier codecs, asset layouts and allocation routines.
Prior support manifests are separated in `translation/lineage/`; they are not release choices.
The latest cumulative manifest, generator dependencies, assembler source, editable
artwork and regression baselines are retained. Removing them solely by date would
turn a source release into a patch-only package.

The supported build consumes `components/qa09/translation/en_qa09.json` directly.
It does not compose historical manifests over edited current data. Full verification
also replays the original generator chain in a temporary copy and checks the output.

## History archive

The companion `Rockman_N1_Historical_Archive.zip` contains retired documents,
standalone copies of reports, previous packaging scripts and raw historical records.
It is for provenance/recovery, not a second active repository and not a build dependency.
Older code is preserved as evidence, not advertised as a current runnable command.
Original blobs with identical SHA-256 are stored once and referenced by the ledger.

`maintenance/migration.json` maps each original path to its active or archived location,
records original/current hashes and retains originals of all edited files.
Run `python scripts/project.py verify-history --archive ../Rockman_N1_Historical_Archive.zip`
to verify that every original file can still be accounted for. The original combined
ZIP hash is recorded in that ledger.
