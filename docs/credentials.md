# Access keys and rotation

The server supports one legacy key pair or a list of 1–64 credentials.
Enabled credentials act on the same storage. Credentials without a
`permissions` field keep full administrator access, including management APIs
and metrics. Add exact bucket grants to restrict application keys to reads or
reads/writes. This provides bucket-level authorization and individual
revocation; it does not provide users, tenants, object ownership or full IAM.

## Configure multiple credentials

Copy [credentials.example.json](../deploy/credentials.example.json) to a local
file, replace all example secrets, protect it with `chmod 600`, and start:

```bash
MOON_S3_CONFIG=./local-config.json \
  _build/native/release/build/cmd/main/main.exe
```

`credentials` is a JSON array. Each entry requires `access_key` and
`secret_key`; `enabled` is an optional boolean defaulting to `true`, and
`permissions` is an optional bucket-grant object. Unknown
fields, duplicate access keys (including disabled entries), invalid types,
empty lists and lists longer than 64 fail startup. New access keys contain
1–128 ASCII letters, digits, hyphens or underscores. Secrets must be nonblank,
at most 4096 UTF-8 bytes, and contain no control characters. The configuration
file and credential-array environment text are each bounded to 64 KiB.

Alternatively set `MOON_S3_CREDENTIALS` to the JSON array itself, for example
through your platform's secret injection. It overrides the file's credentials
array as a whole. The list is never merged with other credential sources.
Malformed overrides fail startup. An explicitly configured array with all
entries disabled keeps authentication enabled and rejects all signed access.
Anonymous object reads still follow any stored public-read policy; health
checks remain public.

## Legacy compatibility and migration

Existing `MOON_S3_ACCESS_KEY` / `MOON_S3_SECRET_KEY` and file fields
`access_key` / `secret_key` keep their existing behavior. Both must be set
and nonempty, or both absent. With neither legacy credentials nor a list,
the server permits anonymous access as before.

Do not combine a credential list with either legacy setting, even an empty
one. Such a conflict fails startup rather than silently leaving an old key
active. When migrating, put the current legacy pair in the list, add the new
pair, and remove both legacy fields and environment variables. Set the server
configuration once and restart. Configuration does not reload live.

The supplied Compose file injects the legacy pair and requires those variables.
To deploy a list with Compose, edit that service's environment to remove both
legacy entries, mount the protected JSON configuration file, and set
`MOON_S3_CONFIG` to its container path, or inject `MOON_S3_CREDENTIALS` instead.
The separate console and management CLI still need one enabled pair in their
own environment; they do not automatically choose a key from the server list.

## Rotate or revoke one key

1. Add a new access key with a new secret and restart the service.
2. Switch the relevant clients, console or CLI to the new pair. Test reads,
   writes and required management operations.
3. Set the old entry to `"enabled": false` (or remove it while retaining at
   least one entry), then restart. The disabled entry still requires valid
   access/secret fields; the server discards its secret from the active map.
4. Confirm old signed requests and old presigned URLs return 403, and that
   the replacement credential remains functional.

Header-signed and presigned requests select the matching enabled access key
and still undergo full signature, timestamp and payload verification. A
disabled/unknown key or incorrect signature cannot fall back to a public-read
policy. Changing a key's secret invalidates signatures made with the old
secret after restart. Keys share multipart state: another enabled key with
write access to that bucket can resume an upload created by the old key, because no per-key ownership is
implemented. Stored data, versions and bucket settings do not change during
rotation.

Credentials are startup settings, excluded from storage backups. Keep them
in your secret-management backup and recovery process. Request logs and
configuration-error messages do not include access keys, secrets or signed
URLs. Metrics remain signed APIs and require an administrator key. Offline admin
uses the local storage lock and requires no S3 credentials.

Run `python3 scripts/credentials_regression.py` for signature isolation,
multi-key CRUD/copy/multipart use, presigned revocation, public-read boundaries,
all-disabled behavior, environment override and invalid-configuration checks.

## Restrict application keys to buckets

```json
{
  "access_key": "backup-application",
  "secret_key": "replace-this-application-secret",
  "permissions": {
    "images": "read",
    "backups": "read-write"
  }
}
```

Bucket names match exactly, case-sensitively, with no wildcards or prefixes.
The grant object supports at most 64 valid bucket names. Missing buckets
remain inaccessible. Unknown permission values, invalid bucket names, reserved
`healthz`/`metrics` names, duplicate JSON fields and non-object grants fail
startup, including for disabled credentials. An empty object grants nothing;
omitting the field grants full administration for compatibility. Keep at least
one protected administrator credential for provisioning and management.

| Capability | `read` | `read-write` |
| --- | --- | --- |
| Object GET/HEAD, historical reads | Yes | Yes |
| Bucket HEAD/location, object/version listing, upload/part listing | Yes | Yes |
| Object PUT/DELETE, historical deletion, batch deletion | No | Yes |
| Multipart create/upload/complete/abort | No | Yes |
| CopyObject destination | No | Yes, with read access to the source bucket |
| Create/delete buckets, list all buckets, metrics | No | No |
| Get/change bucket policy, CORS or versioning settings | No | No |

The administrator creates buckets and configures their settings; application
keys operate on objects within granted buckets. Restricted clients must address
their known buckets directly: `ListBuckets` returns 403 instead of disclosing
other bucket names. Unsupported or malformed operations can still return their
normal validation errors after permission checks.

CopyObject checks both the destination write grant and the source read grant,
including a versioned source. Public source objects do not waive that grant
for a restricted signed copy. Presigned GET/HEAD/PUT requests enforce the same
current credential grants. After changing a key's grants and restarting, old
URLs for revoked buckets fail with 403. A signed request denied by its grants
does not fall back to a public bucket policy. An unsigned public read still
uses the bucket's existing public-read policy; removing a key grant does not
make public data private.

These grants do not restrict individual prefixes, versions, upload creators,
or offline filesystem access. They are startup configuration, not an S3 IAM
API, and changing them requires restart. Authentication still validates
signatures and payloads before authorization; denied upload bodies can use
bounded temporary staging, but cannot publish objects or mutate upload parts.
The separate Web console should retain a trusted administrator credential
because its management views use administrator APIs; this change adds no
per-user console login or tenant isolation. Health and CORS preflight remain
public protocol endpoints.

Run `python3 scripts/permissions_regression.py` to verify the matrix, exact
bucket boundaries, source/destination copy checks, multipart state protection,
presigned revocation and rejection of malformed grants.
