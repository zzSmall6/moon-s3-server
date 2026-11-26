#!/usr/bin/env python3
import concurrent.futures
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from auth_regression import ACCESS_KEY, SECRET_KEY
from operations_regression import PROJECT, BINARY, free_port, running
from s3_client import S3Client, ClientError, object_path


def exceeds(client, method, path, body=b"", headers=None):
    try:
        client.request(method, path, body, headers)
    except ClientError as error:
        assert (error.status, error.code) == (403, "QuotaExceeded"), (error.status, error.code)
    else:
        raise AssertionError("Over-quota write succeeded")


def complete(client, key, identifier, etag):
    document = ET.Element("CompleteMultipartUpload")
    part = ET.SubElement(document, "Part")
    ET.SubElement(part, "PartNumber").text = "1"
    ET.SubElement(part, "ETag").text = etag
    return client.request("POST", object_path("quota-bucket", key, [("uploadId", identifier)]), ET.tostring(document))


def main():
    subprocess.run(["moon", "build", "cmd/main", "--target", "native"], cwd=PROJECT, check=True)
    with tempfile.TemporaryDirectory(prefix="moon-s3-quota-") as temporary:
        directory = pathlib.Path(temporary)
        root = directory / "data"
        settings = dict(root=str(root), listen=f"127.0.0.1:{free_port()}", access_key=ACCESS_KEY, secret_key=SECRET_KEY,
                        bucket_quotas={"quota-bucket": 10, "empty-bucket": 0, "unused-bucket": 20})
        with running(directory, settings) as (_, port, _):
            client = S3Client(f"http://127.0.0.1:{port}", ACCESS_KEY, SECRET_KEY)
            for bucket in ["quota-bucket", "empty-bucket", "unlimited-bucket"]:
                client.request("PUT", "/" + bucket)
            client.request("PUT", "/empty-bucket/empty", b"")
            exceeds(client, "PUT", "/empty-bucket/key", b"x")
            client.request("PUT", "/unlimited-bucket/source", b"s" * 11)
            client.request("PUT", "/quota-bucket/key", b"a" * 10)
            exceeds(client, "PUT", "/quota-bucket/key", b"b" * 11)
            assert client.request("GET", "/quota-bucket/key")[1] == b"a" * 10
            exceeds(client, "PUT", "/quota-bucket/copy", headers={"x-amz-copy-source": "/quota-bucket/key"})
            exceeds(client, "PUT", "/quota-bucket/key", headers={"x-amz-copy-source": "/unlimited-bucket/source"})
            client.request("PUT", "/quota-bucket/key", headers={"x-amz-copy-source": "/quota-bucket/key", "x-amz-metadata-directive": "REPLACE", "x-amz-meta-replaced": "yes"})
            client.request("PUT", "/quota-bucket/key", b"short")
            client.request("PUT", "/quota-bucket/other", b"12345")
            client.request("DELETE", "/quota-bucket/key")
            client.request("DELETE", "/quota-bucket/other")
            def put(number):
                try:
                    client.request("PUT", f"/quota-bucket/race-{number}", b"r" * 6)
                    return "passed"
                except ClientError as error:
                    assert error.code == "QuotaExceeded"
                    return "rejected"
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                assert sorted(pool.map(put, range(2))) == ["passed", "rejected"]
            for entry in client.list_objects("quota-bucket"):
                client.request("DELETE", object_path("quota-bucket", entry["key"]))
            _, aborted = client.xml("POST", "/quota-bucket/aborted?uploads")
            abort_target = object_path("quota-bucket", "aborted", [("uploadId", aborted.findtext("{*}UploadId"))])
            client.request("PUT", abort_target + "&partNumber=1", b"x" * 10)
            exceeds(client, "PUT", "/quota-bucket/blocked", b"x")
            client.request("DELETE", abort_target)
            client.request("PUT", "/quota-bucket/blocked", b"x")
            client.request("DELETE", "/quota-bucket/blocked")
            _, upload = client.xml("POST", "/quota-bucket/multipart?uploads")
            upload_id = upload.findtext("{*}UploadId")
            path = object_path("quota-bucket", "multipart", [("uploadId", upload_id)])
            client.request("PUT", path + "&partNumber=1", b"123456")
            client.request("PUT", path + "&partNumber=2", b"1234")
            exceeds(client, "PUT", path + "&partNumber=1", b"1234567")
            _, parts = client.xml("GET", path)
            assert parts.findtext("{*}Part/{*}Size") == "6"
            part, _ = client.request("PUT", path + "&partNumber=1", b"12345")
            complete(client, "multipart", upload_id, part["etag"])
            assert client.request("GET", "/quota-bucket/multipart")[1] == b"12345"
            text = client.request("GET", "/metrics")[1].decode()
            assert 'moon_s3_bucket_used_bytes{bucket="quota-bucket"} 5\n' in text
            assert 'moon_s3_bucket_quota_remaining_bytes{bucket="quota-bucket"} 5\n' in text
            assert 'moon_s3_bucket_used_bytes{bucket="unused-bucket"} 0\n' in text
            assert 'bucket="unlimited-bucket"' not in text
            client.request("DELETE", "/quota-bucket/multipart")
            client.request("PUT", "/quota-bucket?versioning", b"<VersioningConfiguration><Status>Enabled</Status></VersioningConfiguration>")
            first, _ = client.request("PUT", "/quota-bucket/versioned", b"v" * 6)
            exceeds(client, "PUT", "/quota-bucket/versioned", b"v" * 5)
            second, _ = client.request("PUT", "/quota-bucket/versioned", b"v" * 4)
            marker, _ = client.request("DELETE", "/quota-bucket/versioned")
            exceeds(client, "PUT", "/quota-bucket/another", b"x")
            client.request("DELETE", "/quota-bucket/versioned?versionId=" + first["x-amz-version-id"])
            assert 'moon_s3_bucket_used_bytes{bucket="quota-bucket"} 4\n' in client.request("GET", "/metrics")[1].decode()
            exceeds(client, "PUT", "/quota-bucket/too-big-copy", headers={"x-amz-copy-source": "/unlimited-bucket/source"})
            client.request("DELETE", "/quota-bucket/versioned?versionId=" + marker["x-amz-version-id"])
            assert client.request("GET", "/quota-bucket/versioned")[1] == b"v" * 4
            client.request("PUT", "/quota-bucket?versioning", b"<VersioningConfiguration><Status>Suspended</Status></VersioningConfiguration>")
            client.request("PUT", "/quota-bucket/null", b"n" * 6)
            client.request("PUT", "/quota-bucket/null", b"m" * 6)
            exceeds(client, "PUT", "/quota-bucket/null", b"x" * 7)
            assert not list(root.glob(".request-*.tmp"))
        settings["bucket_quotas"]["quota-bucket"] = 5
        with running(directory, settings) as (_, port, _):
            client = S3Client(f"http://127.0.0.1:{port}", ACCESS_KEY, SECRET_KEY)
            exceeds(client, "PUT", "/quota-bucket/null", b"x" * 6)
            client.request("PUT", "/quota-bucket/null", b"x" * 5)
            assert 'moon_s3_bucket_used_bytes{bucket="quota-bucket"} 9\n' in client.request("GET", "/metrics")[1].decode()
            client.request("DELETE", "/quota-bucket/versioned?versionId=" + second["x-amz-version-id"])
            assert 'moon_s3_bucket_used_bytes{bucket="quota-bucket"} 5\n' in client.request("GET", "/metrics")[1].decode()
        backup, restored = directory / "backup.tar", directory / "restored"
        for arguments in [["backup", "--root", root, "--output", backup], ["restore", "--archive", backup, "--root", restored]]:
            subprocess.run([sys.executable, str(PROJECT / "scripts/admin.py"), *map(str, arguments)], check=True, capture_output=True)
        settings["root"] = str(restored)
        with running(directory, settings, {"MOON_S3_BUCKET_QUOTAS": '{"quota-bucket":5}'}) as (_, port, _):
            client = S3Client(f"http://127.0.0.1:{port}", ACCESS_KEY, SECRET_KEY)
            exceeds(client, "PUT", "/quota-bucket/extra", b"x")
            assert client.request("GET", "/quota-bucket/null")[1] == b"x" * 5
        settings["bucket_quotas"]["quota-bucket"] = 100
        with running(directory, settings) as (_, port, _):
            client = S3Client(f"http://127.0.0.1:{port}", ACCESS_KEY, SECRET_KEY)
            client.request("PUT", "/quota-bucket?versioning", b"<VersioningConfiguration><Status>Enabled</Status></VersioningConfiguration>")
            _, upload = client.xml("POST", "/quota-bucket/null?uploads")
            identifier = upload.findtext("{*}UploadId")
            path = object_path("quota-bucket", "null", [("uploadId", identifier)])
            part, _ = client.request("PUT", path + "&partNumber=1", b"resume")
        settings["bucket_quotas"]["quota-bucket"] = 10
        with running(directory, settings) as (_, port, _):
            client = S3Client(f"http://127.0.0.1:{port}", ACCESS_KEY, SECRET_KEY)
            document = ET.Element("CompleteMultipartUpload")
            entry = ET.SubElement(document, "Part")
            ET.SubElement(entry, "PartNumber").text = "1"
            ET.SubElement(entry, "ETag").text = part["etag"]
            exceeds(client, "POST", path, ET.tostring(document))
            assert client.request("GET", "/quota-bucket/null")[1] == b"x" * 5
            client.request("GET", path)
        settings["bucket_quotas"]["quota-bucket"] = 11
        with running(directory, settings) as (_, port, _):
            client = S3Client(f"http://127.0.0.1:{port}", ACCESS_KEY, SECRET_KEY)
            complete(client, "null", identifier, part["etag"])
            assert client.request("GET", "/quota-bucket/null")[1] == b"resume"
            assert 'moon_s3_bucket_used_bytes{bucket="quota-bucket"} 11\n' in client.request("GET", "/metrics")[1].decode()
            client.request("DELETE", "/quota-bucket/null")
            exceeds(client, "PUT", "/quota-bucket/no-space", b"x")
            _, upload = client.xml("POST", "/quota-bucket/abort?uploads")
            abort_path = object_path("quota-bucket", "abort", [("uploadId", upload.findtext("{*}UploadId"))])
            client.request("DELETE", abort_path)
        environment = {name: value for name, value in os.environ.items() if not name.startswith("MOON_S3_")}
        for quotas in [[], {"*": 10}, {"metrics": 10}, {"quota-bucket": -1}, {"quota-bucket": 0.5}, {"quota-bucket": "10"}, {"quota-bucket": 5497558138881}]:
            config = directory / "invalid.json"
            config.write_text(json.dumps(dict(settings, bucket_quotas=quotas)))
            result = subprocess.run([str(BINARY)], env=dict(environment, MOON_S3_CONFIG=str(config)), capture_output=True, timeout=5)
            assert result.returncode != 0 and b"configuration_invalid" in result.stdout
        config.write_text(json.dumps(dict(settings, bucket_quotas={})))
        for text in ['{"quota-bucket":1,"quota-bucket":2}', '[]', '{"quota-bucket":null}',
                     json.dumps({f"bucket-{index}": 10 for index in range(129)})]:
            result = subprocess.run([str(BINARY)], env=dict(environment, MOON_S3_CONFIG=str(config), MOON_S3_BUCKET_QUOTAS=text), capture_output=True, timeout=5)
            assert result.returncode != 0 and b"configuration_invalid" in result.stdout
    print("Bucket quota passed: overwrite/copy, concurrent admission, part replacement/completion, versions/markers, suspension, reduced limits, metrics, restart/restore and invalid settings.")


if __name__ == "__main__":
    main()
