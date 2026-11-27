# v0.1.3

## Delivery toolchain update

This release pins `moonc v1.0.0-rc1+3c0520448`, satisfying the
`moonc >= 1.0.0-rc1` delivery requirement. Run `bash scripts/smoke.sh` for
the self-contained runnable example. The package includes the updated README
and [delivery acceptance records](acceptance.md). The only runtime source
change since published 0.1.2 uses the current buffer-write API with unchanged
upload behavior.

## Included from 0.1.2

- Custom `x-amz-meta-*` metadata on PUT and multipart initiation, returned by
  GET/HEAD/Range and historical reads. CopyObject supports COPY/REPLACE.
  Metadata survives recovery and backup/restore; the limit is 2 KiB of ASCII
  key/value data. See [metadata](metadata.md).
- Optional per-bucket retained-payload quotas cover objects, historical
  versions and unfinished multipart parts. Concurrent writes check projected
  usage before publication; excess writes return `403 QuotaExceeded`.
  Metrics expose usage and remaining capacity. See [quotas](quotas.md).

## Upgrade and limits

Stop the server and verify an offline backup before upgrading. Retain matching
server and admin tools: older versions cannot safely handle every current
storage layout or metadata record. See [administration](administration.md).

This version passed [single-machine delivery acceptance](acceptance.md). Compatibility is
the [documented S3 subset](compatibility.md), without general IAM/ACL,
encryption, distributed storage or online backup. Quotas count retained payload,
not physical allocation; inventory scans can slow writes to large buckets.
Allow disk space for staging, transaction copies, history and backups.

## Previous version

`0.1.1` introduced multiple credentials and bucket permissions, streaming
uploads with bounded staging, and a configurable free-disk reserve. These
features remain available in `0.1.3`.
