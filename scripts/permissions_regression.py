#!/usr/bin/env python3
import json
import os
import pathlib
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from auth_regression import ACCESS_KEY, SECRET_KEY
from credentials_regression import denied, url_request
from operations_regression import PROJECT, BINARY, free_port, running
from presign import presign
from s3_client import S3Client, object_path


ADMIN = {"access_key": ACCESS_KEY, "secret_key": SECRET_KEY}
READER = {"access_key": "bucket-reader", "secret_key": "reader-secret", "permissions": {"source-bucket": "read"}}
WRITER = {"access_key": "bucket-writer", "secret_key": "writer-secret", "permissions": {"target-bucket": "read-write"}}
BRIDGE = {"access_key": "copy-client", "secret_key": "bridge-secret", "permissions": {"source-bucket": "read", "target-bucket": "read-write"}}
EMPTY = {"access_key": "no-buckets", "secret_key": "empty-secret", "permissions": {}}


def main():
    subprocess.run(["moon", "build", "cmd/main", "--target", "native"], cwd=PROJECT, check=True)
    with tempfile.TemporaryDirectory(prefix="moon-s3-permissions-") as temporary:
        directory = pathlib.Path(temporary)
        settings = dict(root=str(directory / "data"), listen=f"127.0.0.1:{free_port()}",
                        credentials=[ADMIN, READER, WRITER, BRIDGE, EMPTY])
        with running(directory, settings) as (_, port, _):
            endpoint = f"http://127.0.0.1:{port}"
            def client(entry):
                return S3Client(endpoint, entry["access_key"], entry["secret_key"])
            admin, reader, writer, bridge, empty = [client(entry) for entry in settings["credentials"]]
            for bucket in ["source-bucket", "target-bucket", "private-bucket", "source-bucket-extra"]:
                admin.request("PUT", "/" + bucket)
                admin.request("PUT", "/" + bucket + "/key", b"original")
            admin.request("PUT", "/source-bucket?versioning", b"<VersioningConfiguration><Status>Enabled</Status></VersioningConfiguration>")
            metadata, _ = admin.request("PUT", "/source-bucket/key", b"versioned")
            version_id = metadata["x-amz-version-id"]
            for path in ["/source-bucket/key", "/source-bucket/key?versionId=" + version_id, "/source-bucket?list-type=2", "/source-bucket?versions", "/source-bucket?location"]:
                reader.request("GET", path)
            reader.request("HEAD", "/source-bucket")
            reader.request("HEAD", "/source-bucket/key")
            for entry in [READER, WRITER, BRIDGE, EMPTY]:
                scoped = client(entry)
                denied(scoped, "GET", "/")
                denied(scoped, "GET", "/metrics")
                denied(scoped, "HEAD", "/metrics")
                denied(scoped, "PUT", "/new-bucket")
                for selector in ["policy", "versioning", "cors"]:
                    for method in ["GET", "PUT", "DELETE"]:
                        denied(scoped, method, "/target-bucket?" + selector, b"{}" if method == "PUT" else b"")
                denied(scoped, "DELETE", "/target-bucket")
                denied(scoped, "GET", "/private-bucket/key")
                denied(scoped, "PUT", "/private-bucket/key", b"bad")
                denied(scoped, "DELETE", "/private-bucket/key")
                denied(scoped, "GET", "/private-bucket?versions")
                denied(scoped, "POST", "/private-bucket?delete", b"<Delete><Object><Key>key</Key></Object></Delete>")
                scoped.request("GET", "/healthz")
            denied(reader, "GET", "/source-bucket-extra/key")
            denied(reader, "PUT", "/source-bucket/key", b"bad")
            denied(reader, "DELETE", "/source-bucket/key?versionId=" + version_id)
            denied(reader, "POST", "/source-bucket?delete", b"<Delete><Object><Key>key</Key></Object></Delete>")
            denied(reader, "POST", "/source-bucket/new-upload?uploads")
            denied(empty, "GET", "/source-bucket/key")
            writer.request("PUT", "/target-bucket/owned", b"allowed")
            assert writer.request("GET", "/target-bucket/owned")[1] == b"allowed"
            writer.request("GET", "/target-bucket?list-type=2")
            writer.request("DELETE", "/target-bucket/owned")
            writer.request("POST", "/target-bucket?delete", b"<Delete><Object><Key>missing</Key></Object></Delete>")
            denied(writer, "PUT", "/target-bucket/copy", headers={"x-amz-copy-source": "/source-bucket/key"})
            denied(bridge, "PUT", "/source-bucket/copy", headers={"x-amz-copy-source": "/target-bucket/key"})
            denied(bridge, "PUT", "/target-bucket/copy", headers={"x-amz-copy-source": "/private-bucket/key"})
            bridge.request("PUT", "/target-bucket/copy", headers={"x-amz-copy-source": "/source-bucket/key?versionId=" + version_id})
            assert writer.request("GET", "/target-bucket/copy")[1] == b"versioned"
            writer.request("PUT", "/target-bucket/same-copy", headers={"x-amz-copy-source": "/target-bucket/copy"})
            denied(bridge, "PUT", "/target-bucket/copy", headers={"x-amz-copy-source": "/%70rivate-bucket/key"})
            _, upload = admin.xml("POST", "/source-bucket/pending?uploads")
            source_id = upload.findtext("{*}UploadId")
            source_path = object_path("source-bucket", "pending", [("uploadId", source_id)])
            reader.request("GET", source_path)
            reader.request("GET", "/source-bucket?uploads")
            for method, path, body in [("PUT", source_path + "&partNumber=1", b"bad"),
                                       ("POST", source_path, b"<CompleteMultipartUpload/>"),
                                       ("DELETE", source_path, b"")]:
                denied(reader, method, path, body)
                denied(writer, method, path, body)
            _, upload = writer.xml("POST", "/target-bucket/upload?uploads")
            upload_id = upload.findtext("{*}UploadId")
            target = object_path("target-bucket", "upload", [("uploadId", upload_id)])
            metadata, _ = writer.request("PUT", target + "&partNumber=1", b"multipart")
            writer.request("GET", target)
            body = ET.Element("CompleteMultipartUpload")
            part = ET.SubElement(body, "Part")
            ET.SubElement(part, "PartNumber").text = "1"
            ET.SubElement(part, "ETag").text = metadata["etag"]
            writer.request("POST", target, ET.tostring(body))
            assert writer.request("GET", "/target-bucket/upload")[1] == b"multipart"
            _, upload = writer.xml("POST", "/target-bucket/abort?uploads")
            writer.request("DELETE", object_path("target-bucket", "abort", [("uploadId", upload.findtext("{*}UploadId"))]))
            saved_url = presign(endpoint, "source-bucket", "key", READER["access_key"], READER["secret_key"])
            assert url_request(saved_url)[1] == b"versioned"
            for entry, bucket, method, expected in [(READER, "source-bucket", "PUT", 403), (READER, "private-bucket", "GET", 403),
                                                     (WRITER, "target-bucket", "PUT", 200), (WRITER, "private-bucket", "PUT", 403)]:
                url = presign(endpoint, bucket, "presigned", entry["access_key"], entry["secret_key"], method=method)
                assert url_request(url, body=b"payload" if method == "PUT" else b"", method=method)[0] == expected
            policy = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": "*", "Action": "s3:GetObject", "Resource": "arn:aws:s3:::private-bucket/*"}]}
            admin.request("PUT", "/private-bucket?policy", json.dumps(policy).encode())
            assert S3Client(endpoint).request("GET", "/private-bucket/key")[1] == b"original"
            denied(reader, "GET", "/private-bucket/key")
            assert admin.request("GET", "/private-bucket/key")[1] == b"original"
            assert admin.request("GET", "/source-bucket/key")[1] == b"versioned"
        settings["credentials"][1] = dict(READER, permissions={})
        with running(directory, settings) as (_, port, _):
            endpoint = f"http://127.0.0.1:{port}"
            denied(S3Client(endpoint, READER["access_key"], READER["secret_key"]), "GET", "/source-bucket/key")
            assert url_request(saved_url)[0] == 403
        invalid = [None, [], {"*": "read"}, {"metrics": "read"}, {"healthz": "read"}, {"source-bucket": "write"},
                   {"source-bucket": True}, {f"bucket-{index}": "read" for index in range(65)}]
        for grants in invalid:
            settings["credentials"] = [dict(READER, permissions=grants)]
            config = directory / "invalid.json"
            config.write_text(json.dumps(settings))
            environment = {name: value for name, value in os.environ.items() if not name.startswith("MOON_S3_")}
            result = subprocess.run([str(BINARY)], env=dict(environment, MOON_S3_CONFIG=str(config)), capture_output=True, timeout=5)
            assert result.returncode != 0 and b"configuration_invalid" in result.stdout
        settings["credentials"] = [ADMIN]
        config.write_text(json.dumps(settings))
        duplicate = '[{"access_key":"duplicate","secret_key":"secret","permissions":{"source-bucket":"read","source-bucket":"read-write"}}]'
        result = subprocess.run([str(BINARY)], env=dict(environment, MOON_S3_CONFIG=str(config), MOON_S3_CREDENTIALS=duplicate), capture_output=True, timeout=5)
        assert result.returncode != 0 and b"configuration_invalid" in result.stdout
    print("Bucket permissions passed: exact grants, read-only/write boundaries, management denial, both copy endpoints, multipart lifecycle, presign/public-read isolation, restart revocation and invalid grants.")


if __name__ == "__main__":
    main()
