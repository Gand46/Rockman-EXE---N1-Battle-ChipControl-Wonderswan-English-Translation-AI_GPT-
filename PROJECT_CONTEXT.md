# Current project state

**Source authority:** this organized layout 2.0, derived from the combined QA09/MANT03
and RC6 repository ZIP identified in `maintenance/migration.json`.
Game versions and patch hashes are defined in `project.json`.

QA09: `PASS_SYNTHETIC_SCOPED` inherited from the verified MANT03 baseline.
Chip Control: optional RC6 binary adaptation, experimental; editable original
assembly and explicit payload redistribution permission remain absent from inputs.

The current operation changes organization, documentation, paths, build orchestration
and repository checks only. New build/test results are in `maintenance/validation.json`.
No new runtime or hardware result is claimed for this layout change.

Use `scripts/project.py` and current `docs/`; do not treat the history ZIP or embedded
historical HTML instructions as current entry points. The archive is not needed to
build either current variant. Every input file is accounted for in the migration ledger.

Private MANT03 and the previous supplied archives remain original backups; they are
not replaced or overwritten. No live GitHub repository has been modified by packaging.

Layout verification: both exact ROM/BPS builds and isolated QA09 generators passed
from a clean candidate ZIP. Tests: QA09 73 passed + 2 private-fixture omissions;
RC6 7 passed; repository 19 passed. Git import/export preserved all 613 source files.
All 1,411 predecessor files were actually restored with the companion history ZIP
and independently matched against the input archive. The final packaging receipt
records the sealed delivery and its independent post-extraction verification.
