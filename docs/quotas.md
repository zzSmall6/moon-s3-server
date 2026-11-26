# Bucket payload quotas

Administrators can set a retained-payload limit for each bucket at startup:

```json
{
  "bucket_quotas": {
    "images": 1073741824,
    "backups": 5368709120
  }
}
```

`MOON_S3_BUCKET_QUOTAS` accepts the same JSON object and replaces the entire
file map. Omitted buckets are unlimited. The default is an empty map. Quotas
apply to every credential, including administrators and anonymous development
mode. They do not grant access; existing key and bucket policy checks apply.
Exact valid bucket names are required, without wildcards. Reserved service
names are rejected. At most 128 entries are accepted, each an integer from
0 to 5497558138880 (5 TiB) bytes. Zero permits only writes that retain no
payload or reduce an existing over-quota bucket. Invalid maps fail startup.
Restart to change limits. There is no online quota-management API.

## Accounting

Usage is the sum of all retained object/version content lengths plus every
stored multipart part, including parts not selected during completion.
Versioned current-content caches are not charged again for the same version.
Delete markers, metadata, indexes, temporary staging files and transaction
assembly copies are not charged. Consequently this is a retained payload
quota, not a measurement or hard cap of physical filesystem allocation.
Continue using the filesystem reserve and staging limits for disk protection.

- Unversioned overwrite replaces the old object's charged bytes.
- Enabled versioning retains old versions, so a new version adds its full size.
- Suspended versioning replaces the null version but retains named history.
- Deleting a current version through a delete marker does not reclaim its
  historical payload. Delete the retained version explicitly to release it.
- UploadPart adds its stored size, or replaces the previous size for that
  same part number. Failed replacement preserves the old part.
- Completion releases all parts belonging to that upload and charges the
  completed object under the destination's current versioning rules. Unused
  parts are released with the upload. Rejected completion leaves upload parts
  and the prior destination intact for retry or abort.
- Abort or expiration cleanup releases parts when their files are removed.
  Expired parts still on disk remain charged until existing cleanup runs.

PUT, CopyObject, UploadPart and CompleteMultipartUpload check projected usage
under the service's mutation lock before publishing. Concurrent accepted
writes therefore cannot each spend the same remaining quota. Over-quota
writes return HTTP 403 with S3 code `QuotaExceeded`. Uploaded temporary bodies
can consume bounded staging before this check; they are cleaned up on refusal.
Copy checks before creating destination content, and completion checks before
assembly. Quotas do not reserve physical space for those temporary copies.

Lowering a limit below existing usage does not delete data. Reads, deletions
and aborts continue working. A write that strictly reduces retained usage is
allowed even if still above the new limit; a nonreducing write must fit the
limit. Restart and backup/restore recalculate usage from actual storage, rather
than trusting persisted counters. Quota settings are not part of data backups;
restore the intended server configuration separately.

## Metrics and verification

Administrator-authenticated `/metrics` reports these gauges for configured
buckets, including configured buckets that do not yet exist:

- `moon_s3_bucket_quota_bytes{bucket="images"}`
- `moon_s3_bucket_used_bytes{bucket="images"}`
- `moon_s3_bucket_quota_remaining_bytes{bucket="images"}`

Remaining bytes clamp to zero when usage exceeds the configured limit.
Bucket labels come from administrator configuration, not request input.
Unconfigured buckets are not included. Usage scanning and projected-write
checks run under the mutation lock; configured buckets with large inventories
can increase write/metrics latency. This first implementation favors restart
consistency over an incremental persistent index. Physical disk usage, host
quotas and allocation races from unrelated processes remain separate concerns.

Run `python3 scripts/quota_regression.py` for boundary/replacement, concurrent
admission, source/destination copy, historical/marker/suspended behavior,
multipart resume/completion, lowered limits, restart/restore and configuration
validation. Existing no-quota regression suites verify backward compatibility.
