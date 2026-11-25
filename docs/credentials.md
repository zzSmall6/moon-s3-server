# Access keys and rotation

The server supports one legacy key pair or a list of 1–64 credentials.
All enabled credentials act on the same storage and have the same full
permissions, including management APIs and metrics. This provides separate
application secrets and individual revocation; it does not provide users,
tenants, object ownership or bucket-level authorization.

## Configure multiple credentials

Copy [credentials.example.json](../deploy/credentials.example.json) to a local
file, replace all example secrets, protect it with `chmod 600`, and start:

```bash
MOON_S3_CONFIG=./local-config.json \
  _build/native/release/build/cmd/main/main.exe
```

`credentials` is a JSON array. Each entry requires `access_key` and
`secret_key`; `enabled` is an optional boolean defaulting to `true`. Unknown
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
secret after restart. All keys share multipart state: another enabled key can
resume an upload created by the old key, because no per-key ownership is
implemented. Stored data, versions and bucket settings do not change during
rotation.

Credentials are startup settings, excluded from storage backups. Keep them
in your secret-management backup and recovery process. Request logs and
configuration-error messages do not include access keys, secrets or signed
URLs. Metrics remain signed APIs and accept any enabled key. Offline admin
uses the local storage lock and requires no S3 credentials.

Run `python3 scripts/credentials_regression.py` for signature isolation,
multi-key CRUD/copy/multipart use, presigned revocation, public-read boundaries,
all-disabled behavior, environment override and invalid-configuration checks.
