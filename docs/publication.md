# GitHub publication checklist

The ZIP is a source repository layout, not a claim that publication already happened.
Do not upload the historical ZIP into the working tree or nest the source ZIP inside it.
Extract the **contents** of `Rockman_N1/` as the repository root.

Before a public push, resolve the RC6 attribution/redistribution issue described in
[provenance](provenance.md); packaging does not grant permission. Review game-derived
assets/screenshots and third-party license terms. Do not add private ROMs/saves.

## Local sequence

```console
git init -b main
git add .
git status --short
git diff --cached --stat
python scripts/project.py check
python scripts/project.py verify --source "/private/path/original.wsc"
```

Review what is staged before committing. Select the remote explicitly in your own
GitHub account; this package does not guess a repository or embed credentials.
Use source ZIPs and the two separately labelled BPS files as Release assets. Keep the
historical archive as an optional provenance attachment, not part of normal build setup.

## CI policy

One workflow checks both components on Linux, Windows and macOS with Python 3.11.
It does not obtain ROMs, upload build ROMs, use secrets or publish releases.
Permissions are limited to `contents: read`; checkout credential persistence is off.
Actions are pinned to the verified full commit SHA of the previously used major
versions (checkout 4.2.2 and setup-python 5.6.0), not claimed to be the latest releases.
Dependabot is configured for reviewed action updates.

GitHub's primary guidance supports immutable SHA pinning and least permissions:
[secure use](https://docs.github.com/en/actions/reference/security/secure-use),
[checkout permissions](https://github.com/actions/checkout#recommended-permissions).
Pinned revisions:
[checkout 11bd719](https://github.com/actions/checkout/commit/11bd71901bbe5b1630ceea73d27597364c9af683),
[setup-python a26af69](https://github.com/actions/setup-python/commit/a26af69be951a213d495a4c3e4e4022e16d87065).
Remote workflow success must be confirmed after an authorized push; it is not inferred
from the local Linux result.
