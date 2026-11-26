# moon-s3-server

A small S3-compatible object storage server written in MoonBit for local
development, CI and private deployments. Single machine, local disk,
path-style URLs.

**Version:** `0.1.2`; [single-machine delivery acceptance passed](docs/acceptance.md).

## Features

- Bucket/object CRUD, batch delete, paginated ListObjectsV2, Range and conditional requests.
- SigV4, presigned URLs, multiple access keys and per-key bucket permissions.
- Resumable multipart uploads, versioning, server-side copy and custom metadata.
- Bucket payload quotas, bounded disk staging and a configurable free-space reserve.
- Bucket CORS, restricted public-read policies and durable event webhooks.
- Transaction recovery, offline backup/restore, management CLI and Web console.
- JSON configuration, graceful shutdown, logs, metrics and Docker packaging.

New in `0.1.2`: [custom metadata](docs/metadata.md) and
[bucket quotas](docs/quotas.md). See [release notes](docs/release-notes.md).

## Quick start

Requires the [MoonBit CLI](https://www.moonbitlang.com/download/).
CI uses the hash-locked `moon 0.1.20261117` toolchain.

```bash
git clone https://github.com/zzSmall6/moon-s3-server.git
cd moon-s3-server
moon build cmd/main --target native
MOON_S3_ROOT=./data MOON_S3_LISTEN=127.0.0.1:9000 \
  _build/native/debug/build/cmd/main/main.exe
```

In another terminal:

```bash
curl --noproxy '*' -X PUT http://127.0.0.1:9000/demo
printf 'Hello MoonBit!\n' > hello.txt
curl --noproxy '*' -X PUT --data-binary @hello.txt http://127.0.0.1:9000/demo/hello.txt
curl --noproxy '*' http://127.0.0.1:9000/demo/hello.txt
```

Without credentials, access is anonymous. Set `MOON_S3_ACCESS_KEY` and
`MOON_S3_SECRET_KEY`, or configure [multiple keys](docs/credentials.md),
before sharing the service. Use a trusted network and TLS for remote access.
See [configuration and deployment](docs/deployment.md).

## Compatibility and limits

Tested with boto3/botocore `1.44.0`, AWS CLI `2.22.35`, TLS MinIO `mc`
and 33 selected Ceph cases. Use SigV4, path-style addressing and optional
checksums set to `when_required`; see the [exact API boundary](docs/compatibility.md).

- One process per data directory; no distributed storage or online backup.
- No general IAM/ACL, encryption, STS, AWS streaming signatures or UploadPartCopy.
- Object keys: 1–1024 UTF-8 bytes. Custom metadata: 2 KiB of ASCII key/value data.
- Request bodies default to 64 MiB (configurable up to 512 MiB); use multipart for larger objects.
- Process-crash recovery is tested on Linux; power-loss durability and sustained-load guarantees are outside the acceptance scope.

## Tools and development

```bash
python3 scripts/moon_s3.py --help
moon test --target native
moon info && moon fmt
python3 scripts/run_regressions.py
```

The [CLI](docs/cli.md), [Web console](docs/console.md) and
[offline administration](docs/administration.md) guides cover daily operations.
CI runs native checks and all local suites; external compatibility and release
packaging use manual workflows. See [releasing](docs/releasing.md) and the
[deployment recovery drill](docs/recovery-drill.md).

## License

[Apache-2.0](LICENSE).
