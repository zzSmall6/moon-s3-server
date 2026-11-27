# v0.1.2 preview

## Delivery toolchain update

The repository now pins `moonc v1.0.0-rc1+3c0520448`, satisfying the
`moonc >= 1.0.0-rc1` delivery requirement. Run `bash scripts/smoke.sh` for
the self-contained runnable example. This source/toolchain update follows
the published Mooncakes 0.1.2 package; use the accepted Git revision and
matching release bundle identified in [acceptance](acceptance.md).

## Changes since 0.1.1

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
features remain available in `0.1.2`.
