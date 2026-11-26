# Delivery acceptance

**v0.1.2 passed single-machine delivery acceptance on 2026-11-26.**
The current Linux x86-64 machine is the delivery acceptance environment.
The accepted source is `0f1de7b5a99d3233d9c8cc005c7ec9382daac23d`.

## Scope and results

The delivery target is one process on one machine, local-disk storage,
path-style URLs and the [documented S3 API subset](compatibility.md).

| Check | Result | Evidence |
| --- | --- | --- |
| Native checks | Passed | [CI](https://github.com/zzSmall6/moon-s3-server/actions/runs/45772572694): 40 unit tests, 23 local suites and extracted-bundle validation |
| External clients | Passed | [Compatibility run](https://github.com/zzSmall6/moon-s3-server/actions/runs/45772593589): AWS CLI, TLS `mc`, 33 Ceph cases, proxy checks and seven SDK suites, including 100 MiB multipart |
| Release package | Passed | Clean-source `v0.1.2` bundle: checksums, inventory, packaged binary/CLI, signed Unicode transfers and offline backup/restore |
| Local deployment and recovery | Passed | [11-step report](acceptance/deployment-0f1de7b.json): nonroot Docker deployment, shutdown, backup, restore, multipart resume and rollback |
| Mooncakes publication | Completed | [Zz04321/moon-s3-server 0.1.2](https://mooncakes.io/docs/Zz04321/moon-s3-server); registry build succeeded |

Client identities and suite results are retained in the
[compatibility report](acceptance/compatibility-0f1de7b.json) and
[SDK log](acceptance/sdk-0f1de7b.log).

## Deployment evidence

The deployment test used a locally built, clean-source Linux x86-64 bundle.
Its SHA-256 is
`9db74e0e04396608c1ba8b8bfc1753a81a013363dab4c2a1247ad6ba8c715841`.
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
