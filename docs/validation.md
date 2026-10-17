# Validation boundaries

## This reorganization

Fresh results are recorded in [maintenance/validation.json](../maintenance/validation.json).
The reorganized source and freshly extracted ZIP are checked for layout, Python syntax,
local maintained-document links, patch/asset hashes, forbidden distributable payloads,
component separation and source preservation. Both ROM/BPS outputs must retain the
identities in [project.json](../project.json).

The ordinary QA09 build reads its current cumulative manifest. A second reconstruction
runs the inherited resource-generation chain in isolation. This checks preservation
of the source pipeline as well as the binary release. Neither path modifies the
original game input. Tracked source inventories are compared before and after.

## Historical game evidence

QA09 inherited `PASS_SYNTHETIC_SCOPED`: the QA08→QA09 scope comparison is 72 changed
bytes, limited to the Navi warning, GaiaSwrd resource and checksum. Archived regression
reports record 75 compared frames without image/WRAM differences in three selected routes.
Chip Control's report records scoped RC6 reference comparisons and checksum adaptation.
These historical outcomes are preserved, not represented as re-executed emulation here.

The QA09 source suite has two private-fixture skips when the correct ROM and build
are supplied: an archived real SRAM check and archived runtime savestates. They remain
explicitly skipped. A no-ROM CI run additionally omits tests whose ROM input is absent.
The test command reports actual names and reasons; no missing fixture is counted as PASS.

Full natural playthrough, every chip/AI combination, link-cable behavior and hardware
remain outside this repository-layout validation. Windows/macOS runners and remote
GitHub Actions execution are configured, not locally demonstrated. No repository was
published during this packaging operation.
