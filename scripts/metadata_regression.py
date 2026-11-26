#!/usr/bin/env python3
import argparse
import http.client
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from auth_regression import ACCESS_KEY, SECRET_KEY, sign
from credentials_regression import url_request
from operations_regression import PROJECT, BINARY, free_port, running
from presign import presign
from s3_client import S3Client, ClientError, object_path


def metadata(headers):
    return {name[11:]: value for name, value in headers.items() if name.startswith("x-amz-meta-")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sdk", action="store_true")
    args = parser.parse_args()
    subprocess.run(["moon", "build", "cmd/main", "--target", "native"], cwd=PROJECT, check=True)
    with tempfile.TemporaryDirectory(prefix="moon-s3-metadata-") as temporary:
        directory = pathlib.Path(temporary)
        root = directory / "data"
        settings = dict(root=str(root), listen=f"127.0.0.1:{free_port()}", access_key=ACCESS_KEY, secret_key=SECRET_KEY)
        expected = {"owner": 'business=42 "quoted" \\path', "empty": "", "business_id": "42"}
        outgoing = {"x-amz-meta-" + name: value for name, value in expected.items()}
        uploads = []
        def admin(*arguments, check=True):
            return subprocess.run([sys.executable, str(PROJECT / "scripts/admin.py"), *map(str, arguments)], capture_output=True, check=check, timeout=30)
        with running(directory, settings) as (_, port, _):
            endpoint = f"http://127.0.0.1:{port}"
            client = S3Client(endpoint, ACCESS_KEY, SECRET_KEY)
            client.request("PUT", "/meta-bucket")
            client.request("PUT", "/meta-bucket/key", b"original", dict(outgoing, **{"Content-Type": "application/example"}))
            assert metadata(client.request("HEAD", "/meta-bucket/key")[0]) == expected
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            signed = sign("PUT", "/meta-bucket/key", f"127.0.0.1:{port}", b"bad", extra_headers={"x-amz-meta-empty": ""})
            del signed["x-amz-meta-empty"]
            connection.request("PUT", "/meta-bucket/key", b"bad", signed)
            reply = connection.getresponse()
            assert reply.status == 403
            reply.read()
            connection.close()
            assert metadata(client.request("GET", "/meta-bucket/key")[0]) == expected
            assert metadata(client.request("GET", "/meta-bucket/key", headers={"Range": "bytes=0-2"})[0]) == expected
            client.request("PUT", "/meta-bucket/copied", headers={"x-amz-copy-source": "/meta-bucket/key", "x-amz-meta-ignored": "not copied"})
            assert metadata(client.request("HEAD", "/meta-bucket/copied")[0]) == expected
            client.request("PUT", "/meta-bucket/replaced", headers={"x-amz-copy-source": "/meta-bucket/key", "x-amz-metadata-directive": "REPLACE", "x-amz-meta-new": "replacement"})
            assert metadata(client.request("HEAD", "/meta-bucket/replaced")[0]) == {"new": "replacement"}
            signed = sign("PUT", "/meta-bucket/replaced", f"127.0.0.1:{port}", extra_headers={"x-amz-copy-source": "/meta-bucket/key", "x-amz-metadata-directive": "REPLACE"})
            signed["x-amz-meta-unsigned"] = "tampered"
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            connection.request("PUT", "/meta-bucket/replaced", headers=signed)
            reply = connection.getresponse()
            assert reply.status == 403
            reply.read()
            connection.close()
            client.request("PUT", "/meta-bucket/cleared", headers={"x-amz-copy-source": "/meta-bucket/key", "x-amz-metadata-directive": "REPLACE"})
            assert metadata(client.request("HEAD", "/meta-bucket/cleared")[0]) == {}
            for headers in [{"x-amz-meta-a": "x" * 2048}, {"x-amz-meta-": "empty-name"}]:
                try:
                    client.request("PUT", "/meta-bucket/key", b"bad", headers)
                except ClientError as error:
                    assert error.status == 400
                else:
                    raise AssertionError("Invalid metadata accepted")
                assert client.request("GET", "/meta-bucket/key")[1] == b"original"
            client.request("PUT", "/meta-bucket/boundary", b"", {"x-amz-meta-a": "x" * 2047})
            assert len(metadata(client.request("HEAD", "/meta-bucket/boundary")[0])["a"]) == 2047
            client.request("PUT", "/meta-bucket?versioning", b"<VersioningConfiguration><Status>Enabled</Status></VersioningConfiguration>")
            versions = client.list_versions("meta-bucket", prefix="key")
            legacy = next(versions)["version_id"]
            assert metadata(client.request("HEAD", object_path("meta-bucket", "key", [("versionId", legacy)]))[0]) == expected
            version, _ = client.request("PUT", "/meta-bucket/key", b"updated", {"x-amz-meta-owner": "new-version"})
            client.request("PUT", "/meta-bucket/historical-copy", headers={"x-amz-copy-source": "/meta-bucket/key?versionId=" + legacy})
            assert metadata(client.request("HEAD", "/meta-bucket/historical-copy")[0]) == expected
            client.request("DELETE", "/meta-bucket/key?versionId=" + version["x-amz-version-id"])
            assert metadata(client.request("HEAD", "/meta-bucket/key")[0]) == expected
            for name in ["multipart", "unfinished"]:
                _, upload = client.xml("POST", f"/meta-bucket/{name}?uploads", headers=outgoing)
                upload_id = upload.findtext("{*}UploadId")
                path = object_path("meta-bucket", name, [("uploadId", upload_id)])
                part, _ = client.request("PUT", path + "&partNumber=1", b"part-content")
                uploads.append((name, upload_id, part["etag"]))
                try:
                    client.request("PUT", path + "&partNumber=1", b"invalid-part", outgoing)
                except ClientError as error:
                    assert error.status == 400
                else:
                    raise AssertionError("UploadPart silently ignored metadata")
            name, upload_id, etag = uploads[0]
            completion = f'<CompleteMultipartUpload><Part><PartNumber>1</PartNumber><ETag>{etag}</ETag></Part></CompleteMultipartUpload>'.encode()
            client.request("POST", object_path("meta-bucket", name, [("uploadId", upload_id)]), completion)
            assert metadata(client.request("HEAD", "/meta-bucket/multipart")[0]) == expected
            url = presign(endpoint, "meta-bucket", "presigned", ACCESS_KEY, SECRET_KEY, method="PUT")
            assert url_request(url, body=b"presigned", headers=outgoing, method="PUT")[0] == 200
            assert metadata(client.request("HEAD", "/meta-bucket/presigned")[0]) == expected
            if args.sdk:
                import botocore.session
                from botocore.config import Config
                sdk = botocore.session.get_session().create_client("s3", endpoint_url=endpoint, region_name="us-east-1", aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY,
                    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}, proxies={}, request_checksum_calculation="when_required", response_checksum_validation="when_required"))
                sdk.put_object(Bucket="meta-bucket", Key="sdk", Body=b"sdk", Metadata=expected)
                assert sdk.head_object(Bucket="meta-bucket", Key="sdk")["Metadata"] == expected
                sdk.copy_object(Bucket="meta-bucket", Key="sdk-copy", CopySource="meta-bucket/sdk")
                assert sdk.get_object(Bucket="meta-bucket", Key="sdk-copy")["Metadata"] == expected
                sdk.copy_object(Bucket="meta-bucket", Key="sdk-copy", CopySource="meta-bucket/sdk", MetadataDirective="REPLACE", Metadata={"changed": "sdk"})
                assert sdk.head_object(Bucket="meta-bucket", Key="sdk-copy")["Metadata"] == {"changed": "sdk"}
                upload_id = sdk.create_multipart_upload(Bucket="meta-bucket", Key="sdk-multipart", Metadata=expected)["UploadId"]
                etag = sdk.upload_part(Bucket="meta-bucket", Key="sdk-multipart", UploadId=upload_id, PartNumber=1, Body=b"sdk-part")["ETag"]
                sdk.complete_multipart_upload(Bucket="meta-bucket", Key="sdk-multipart", UploadId=upload_id, MultipartUpload={"Parts": [{"PartNumber": 1, "ETag": etag}]})
                assert sdk.head_object(Bucket="meta-bucket", Key="sdk-multipart")["Metadata"] == expected
                sdk_url = sdk.generate_presigned_url("put_object", Params={"Bucket": "meta-bucket", "Key": "sdk-presigned", "Metadata": expected})
                assert url_request(sdk_url, body=b"sdk-presigned", headers=outgoing, method="PUT")[0] == 200
                assert url_request(sdk_url, body=b"bad", method="PUT")[0] == 403
        admin("check", "--root", root)
        archive, restored = directory / "backup.tar", directory / "restored"
        admin("backup", "--root", root, "--output", archive)
        admin("restore", "--archive", archive, "--root", restored)
        settings["root"] = str(restored)
        with running(directory, settings) as (_, port, _):
            client = S3Client(f"http://127.0.0.1:{port}", ACCESS_KEY, SECRET_KEY)
            for name in ["key", "copied", "multipart", "historical-copy", "presigned"]:
                assert metadata(client.request("HEAD", "/meta-bucket/" + name)[0]) == expected
            name, upload_id, etag = uploads[1]
            client.request("POST", object_path("meta-bucket", name, [("uploadId", upload_id)]), f'<CompleteMultipartUpload><Part><PartNumber>1</PartNumber><ETag>{etag}</ETag></Part></CompleteMultipartUpload>'.encode())
            assert metadata(client.request("HEAD", "/meta-bucket/unfinished")[0]) == expected
        scoped = dict(settings)
        scoped.pop("access_key")
        scoped.pop("secret_key")
        scoped["credentials"] = [
            {"access_key": ACCESS_KEY, "secret_key": SECRET_KEY},
            {"access_key": "metadata-reader", "secret_key": "reader-secret", "permissions": {"meta-bucket": "read"}},
            {"access_key": "other-bucket", "secret_key": "other-secret", "permissions": {"another-bucket": "read-write"}},
        ]
        with running(directory, scoped) as (_, port, _):
            endpoint = f"http://127.0.0.1:{port}"
            reader = S3Client(endpoint, "metadata-reader", "reader-secret")
            assert metadata(reader.request("HEAD", "/meta-bucket/key")[0]) == expected
            for scoped_client, method, path, headers in [
                (reader, "PUT", "/meta-bucket/key", outgoing),
                (S3Client(endpoint, "other-bucket", "other-secret"), "HEAD", "/meta-bucket/key", {}),
            ]:
                try:
                    scoped_client.request(method, path, headers=headers)
                except ClientError as error:
                    assert error.status == 403
                else:
                    raise AssertionError("Metadata bypassed bucket grants")
        record = restored / "meta-bucket/objects" / (b"copied".hex() + ".meta")
        record.write_text(record.read_text().replace('user-metadata=', 'user-metadata={"BAD":"invalid"}\nuser-metadata='))
        assert admin("check", "--root", restored, check=False).returncode != 0
        config = directory / "bad.json"
        config.write_text(json.dumps(settings))
        environment = {name: value for name, value in os.environ.items() if not name.startswith("MOON_S3_")}
        result = subprocess.run([str(BINARY)], env=dict(environment, MOON_S3_CONFIG=str(config)), capture_output=True, timeout=5)
        assert result.returncode != 0 and b"recovery_failed" in result.stdout
    print("User metadata passed: PUT/GET/HEAD/Range, copy/replace/clear, legacy and historical versions, multipart resume, presign, limits, backup/restore and corrupt-record refusal.")


if __name__ == "__main__":
    main()
