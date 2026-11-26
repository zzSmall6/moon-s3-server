# Custom object metadata

PutObject and CreateMultipartUpload accept `x-amz-meta-NAME` request headers.
GET, HEAD and Range GET return them for the selected object version. They
follow the same authentication and bucket read/write grants as object content.
For example:

```python
client.put_object(Bucket="images", Key="photo.jpg", Body=content,
                  Metadata={"business_id": "42", "source": "camera"})
metadata = client.head_object(Bucket="images", Key="photo.jpg")["Metadata"]
```

## Compatibility profile

- Names normalize to lowercase. Suffixes must contain 1–128 ASCII HTTP token
  characters: letters, digits and `!#$%&'*+-.^_` plus backtick, `|` and `~`.
- Values use printable ASCII (space through `~`); empty values are supported.
  Use an application-defined ASCII encoding for Unicode values. The HTTP stack
  can close malformed/non-ASCII requests before S3 validation.
- The combined byte length of suffixes and values is at most 2048 bytes,
  excluding the `x-amz-meta-` prefixes. Invalid metadata returns 400 before any
  object/part is published. Existing request-header size limits also apply.
- HTTP header whitespace normalization applies; leading/trailing whitespace
  is not preserved byte-for-byte. Metadata names are case-insensitive.
- Custom metadata is accepted only on ordinary object PUT, CopyObject and
  multipart initiation. Supplying it on a part upload or completion, reads,
  deletes or bucket operations returns 400 rather than silently ignoring it.

Replacing an object with a new PUT replaces its entire metadata set. Omitting
metadata on that PUT clears it. Metadata does not alter the content MD5 ETag.
It appears on reads, not bucket listing entries. Browser JavaScript requires
the relevant names in the bucket's CORS `ExposeHeader` configuration to read
them; the server does not automatically expose all metadata.

## Copy and multipart behavior

CopyObject defaults to `x-amz-metadata-directive: COPY`: preserve the selected
source version's Content-Type and all custom metadata. Destination metadata
headers are ignored in COPY mode. With `REPLACE`, only the supplied metadata
is stored, and omitted fields are removed. Content-Type follows the existing
REPLACE default of `application/octet-stream`. Copy source/directive and custom
metadata headers must be signed when authentication is enabled. Copy-to-self
still requires REPLACE. Both source-read and destination-write grants apply.

Multipart metadata is fixed at initiation. UploadPart cannot change it, and
CompleteMultipartUpload uses the persisted initiation metadata. It survives
restart, upload resumption, backup and restore. Presigned PUT supports custom
metadata; to constrain values in a temporary URL, include those headers in the
presigner's SignedHeaders. A host-only presigned URL lets its holder choose
metadata within these limits as part of the authorized upload.

Each version retains its own metadata. Historical GET/HEAD and version-copy
restore return the selected version's metadata, including legacy null versions
imported when versioning is enabled. Delete markers have no custom metadata.

## Storage and recovery

Nonempty metadata is persisted as one optional `user-metadata` JSON field in
current object metadata, version records and multipart manifests, using escaped
strings within the existing journaled storage format. Old records without the
field read as empty metadata. Backup checks validate names, values and size;
corrupt/duplicate records are rejected. Server startup recovery validates
persisted custom metadata before serving requests.

Use this server and its matching admin tool for data containing the new field.
Older admin versions reject the extended records, and older server versions
can reject or lose custom metadata. Stop the service and take a verified
offline backup before upgrading; rolling back requires restoring the backup
with its matching tool version. No automatic metadata format downgrade exists.

Run `python3 scripts/metadata_regression.py`; add `--sdk` with the pinned
botocore environment for SDK PUT/HEAD/GET and COPY/REPLACE checks. The local
suite also exercises empty/escaped values, size boundaries, signed-header
tampering, historical versions, multipart continuation after restore and
corrupt-record refusal.
