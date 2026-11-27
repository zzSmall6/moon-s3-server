# Delivery acceptance

**The v0.1.2 source with the rc1 toolchain passed delivery acceptance on 2026-11-27.**
The current Linux x86-64 machine is the delivery acceptance environment.
The accepted source is `7e90110899e8de47c332f1ffcb28ca425d5cacf7`.

## Required delivery checks

- **Compiler:** `moonc v1.0.0-rc1+3c0520448 (2026-11-26)`, meeting
  `moonc >= 1.0.0-rc1`. The hash-locked installer verifies this exact version.
- **Runnable example:** `bash scripts/smoke.sh` prints the compiler version,
  builds and starts the native server, verifies bucket creation, upload/download
  byte equality, listing and deletion, then removes temporary data. It passed
  locally and in CI with the rc1 compiler. Manual commands are in the
  [README](../README.mbt.md#quick-start).

Use the [locked toolchain setup](releasing.md#toolchain) to reproduce the
accepted build without replacing an existing MoonBit installation.

## Scope and results

The delivery target is one process on one machine, local-disk storage,
path-style URLs and the [documented S3 API subset](compatibility.md).

| Check | Result | Evidence |
| --- | --- | --- |
| Native checks | Passed | [CI](https://github.com/zzSmall6/moon-s3-server/actions/runs/45959945648): 40 unit tests, 23 local suites and extracted-bundle validation |
| External clients | Passed | [Compatibility run](https://github.com/zzSmall6/moon-s3-server/actions/runs/45959977940): AWS CLI, TLS `mc`, 33 Ceph cases, proxy checks and seven SDK suites, including 100 MiB multipart |
| Release package | Passed | [Release workflow](https://github.com/zzSmall6/moon-s3-server/actions/runs/45959978190): rc1 native binary, checksums, packaged CLI, Docker smoke and recovery drill |
| Local deployment and recovery | Passed | [11-step report](acceptance/deployment-7e90110.json): downloaded CI bundle, nonroot Docker deployment, shutdown, backup, restore, multipart resume and rollback |

Client identities and suite results are retained in the
[compatibility report](acceptance/compatibility-7e90110.json) and
[SDK log](acceptance/sdk-7e90110.log).

Mooncakes `0.1.3` includes this compiler upgrade and the acceptance records.
Its runtime source and locked toolchain match the accepted revision above;
the version and documentation have been updated for publication. The
published `0.1.2` package predates the compiler upgrade. The previous
2026-11-26 reports remain in `docs/acceptance/` as historical evidence.

## Deployment evidence

The deployment test used the downloaded, clean-source Linux x86-64 bundle
from the Release workflow above, built with the locked rc1 compiler.
Its SHA-256 is
`cf16a300d4aba7bf1d6b624d222ec1913d40d7866e1931467b7c196bf5673e8d`.
The report records the compiler, Docker/runtime image identities, harness
hashes, backup digest and per-step results.

Source and restored inventories matched: one bucket, one current object,
three historical versions, one delete marker and one unfinished upload.
Restored content hashes, Content-Type, CORS and public-read policy matched.
The saved multipart upload completed after restore. Rollback preserved the
original volume and its post-snapshot write. Corrupt backups and overwriting
an existing restore directory were rejected. Temporary containers and volumes
were cleaned up without errors.

All checks for this delivery scope are complete. Full AWS S3 compatibility,
hardware power-cut/disk-failure tests and sustained-load guarantees are outside
the agreed scope. When changing machines, versions or storage, repeat the
[deployment recovery drill](recovery-drill.md) for that configuration.
