# Chip Control v0.5.8 RC6 · OPTIONAL / EXPERIMENTAL

This component adapts the supplied **WonderSwan RC6 binary patch** to the exact QA09
localization. It is not enabled by a normal QA09 build and is not a complete editable
reconstruction of the original RC6 engine.

`src/verify_and_build_experimental.py` and `tests/` are the editable adapter.
`vendor/` contains the hash-pinned graphics-a9 and RC6 IPS inputs needed to check the
write-domain compatibility. They are **not player-facing QA09 patch choices**.
`evidence/` and `provenance/` preserve the original compatibility records.

From the repository root:

```console
python scripts/project.py build --source "/path/original.wsc" --variant chip-control
```

The result is separate from QA09 and must match the identity in
[project.json](../../project.json). The adapter checks the 1,959 functional writes,
rejects overlap conflicts and recomputes the two-byte checksum. The cumulative BPS
applies directly to the original Japanese ROM. Never stack it on the English BPS.

Original RC6 assembly/builder sources and redistribution permission are not documented
in the received release. See [provenance](../../docs/provenance.md) before publication.
[Preserved compatibility report](../../docs/reports/chip-control-compatibility.html).
