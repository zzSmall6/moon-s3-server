#!/usr/bin/env python3
import http.client
import json
import os
import pathlib
import subprocess
import tempfile
import urllib.parse

from operations_regression import PROJECT, BINARY, free_port, running
from presign import presign
from s3_client import ClientError, S3Client, object_path


FIRST = {"access_key": "application-one", "secret_key": "first-private-secret"}
SECOND = {"access_key": "application-two", "secret_key": "second-private-secret"}
DISABLED = {"access_key": "revoked-application", "secret_key": "revoked-private-secret", "enabled": False}


def denied(client, method, path, body=b"", headers=None):
    try:
        client.request(method, path, body, headers)
    except ClientError as error:
        assert error.status == 403, (error.status, error.code)
    else:
        raise AssertionError("Unauthorized request succeeded")


def url_request(url, body=b"", headers=None, method="GET"):
    address = urllib.parse.urlsplit(url)
    connection = http.client.HTTPConnection(address.hostname, address.port, timeout=10)
    try:
        connection.request(method, address.path + "?" + address.query, body, headers or {})
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def main():
    subprocess.run(["moon", "build", "cmd/main", "--target", "native"], cwd=PROJECT, check=True)
    with tempfile.TemporaryDirectory(prefix="moon-s3-credentials-") as temporary:
        directory = pathlib.Path(temporary)
        settings = dict(root=str(directory / "data"), listen=f"127.0.0.1:{free_port()}",
                        credentials=[FIRST, SECOND, DISABLED])
        with running(directory, settings) as (_, port, log):
            endpoint = f"http://127.0.0.1:{port}"
            def client(credential):
                return S3Client(endpoint, credential["access_key"], credential["secret_key"])
            first, second = client(FIRST), client(SECOND)
            first.request("PUT", "/credentials-bucket")
            second.request("PUT", "/credentials-bucket/key", b"shared content")
            for active in [first, second]:
                assert active.request("GET", "/credentials-bucket/key")[1] == b"shared content"
                active.request("GET", "/metrics")
            for credential in [DISABLED, dict(FIRST, secret_key="wrong-secret"), dict(SECOND, secret_key=FIRST["secret_key"]), dict(FIRST, access_key="unknown")]:
                denied(client(credential), "GET", "/credentials-bucket/key")
                denied(client(credential), "PUT", "/credentials-bucket/key", b"unauthorized")
                denied(client(credential), "GET", "/metrics")
            denied(S3Client(endpoint), "GET", "/credentials-bucket/key")
            saved_url = presign(endpoint, "credentials-bucket", "key", FIRST["access_key"], FIRST["secret_key"], expires=600)
            assert url_request(saved_url) == (200, b"shared content")
            other_url = presign(endpoint, "credentials-bucket", "key", SECOND["access_key"], SECOND["secret_key"])
            assert url_request(other_url)[0] == 200
            put_url = presign(endpoint, "credentials-bucket", "presigned", SECOND["access_key"], SECOND["secret_key"], method="PUT")
            assert url_request(put_url, body=b"presigned upload", method="PUT")[0] == 200
            head_url = presign(endpoint, "credentials-bucket", "presigned", SECOND["access_key"], SECOND["secret_key"], method="HEAD")
            assert url_request(head_url, method="HEAD")[0] == 200
            disabled_url = presign(endpoint, "credentials-bucket", "key", DISABLED["access_key"], DISABLED["secret_key"])
            assert url_request(disabled_url)[0] == 403
            assert url_request(saved_url + "&X-Amz-Credential=application-two")[0] == 403
            assert url_request(saved_url.replace(FIRST["access_key"], SECOND["access_key"]))[0] == 403
            second.request("PUT", "/credentials-bucket/copied", headers={"x-amz-copy-source": "/credentials-bucket/key"})
            assert first.request("GET", "/credentials-bucket/copied")[1] == b"shared content"
            _, upload = first.xml("POST", "/credentials-bucket/multipart?uploads")
            upload_id = upload.findtext("{*}UploadId")
            part_path = object_path("credentials-bucket", "multipart", [("uploadId", upload_id), ("partNumber", "1")])
            second.request("PUT", part_path, b"part")
            denied(client(DISABLED), "PUT", part_path, b"bad")
            policy = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": "*", "Action": "s3:GetObject", "Resource": "arn:aws:s3:::credentials-bucket/*"}]}
            second.request("PUT", "/credentials-bucket?policy", json.dumps(policy).encode())
            assert S3Client(endpoint).request("GET", "/credentials-bucket/key")[1] == b"shared content"
            denied(client(DISABLED), "GET", "/credentials-bucket/key")
            assert url_request(disabled_url)[0] == 403
            denied(S3Client(endpoint), "GET", "/credentials-bucket?list-type=2")
            log.seek(0)
            serialized = log.read().decode()
            assert not any(value in serialized for credential in [FIRST, SECOND, DISABLED] for key, value in credential.items() if key != "enabled")
        settings["credentials"] = [dict(FIRST, enabled=False), SECOND, DISABLED]
        with running(directory, settings) as (_, port, _):
            endpoint = f"http://127.0.0.1:{port}"
            first = S3Client(endpoint, FIRST["access_key"], FIRST["secret_key"])
            second = S3Client(endpoint, SECOND["access_key"], SECOND["secret_key"])
            denied(first, "GET", "/credentials-bucket/key")
            denied(first, "GET", "/metrics")
            old_address = urllib.parse.urlsplit(saved_url)
            assert url_request(saved_url.replace(old_address.netloc, f"127.0.0.1:{port}"), headers={"Host": old_address.netloc})[0] == 403
            assert second.request("GET", "/credentials-bucket/key")[1] == b"shared content"
            second.request("DELETE", "/credentials-bucket?policy")
            denied(S3Client(endpoint), "GET", "/credentials-bucket/key")
        settings["credentials"] = [dict(FIRST, enabled=False)]
        with running(directory, settings) as (_, port, _):
            endpoint = f"http://127.0.0.1:{port}"
            denied(S3Client(endpoint), "GET", "/credentials-bucket/key")
            denied(S3Client(endpoint, FIRST["access_key"], FIRST["secret_key"]), "GET", "/metrics")
        with running(directory, settings, {"MOON_S3_CREDENTIALS": json.dumps([SECOND])}) as (_, port, _):
            S3Client(f"http://127.0.0.1:{port}", SECOND["access_key"], SECOND["secret_key"]).request("GET", "/metrics")
        rotated = dict(SECOND, secret_key="rotated-private-secret")
        with running(directory, settings, {"MOON_S3_CREDENTIALS": json.dumps([rotated])}) as (_, port, _):
            endpoint = f"http://127.0.0.1:{port}"
            denied(S3Client(endpoint, SECOND["access_key"], SECOND["secret_key"]), "GET", "/metrics")
            S3Client(endpoint, rotated["access_key"], rotated["secret_key"]).request("GET", "/metrics")
        invalid_sets = [[], {}, [FIRST, FIRST], [FIRST, dict(FIRST, enabled=False)], [dict(FIRST, enabled="false")],
                        [dict(FIRST, unexpected=True)], [{"access_key": "missing-secret"}],
                        [dict(FIRST, access_key="a/b")], [dict(FIRST, access_key=" ")],
                        [dict(FIRST, secret_key=" ")], [dict(FIRST, secret_key="line\nbreak")],
                        [dict(FIRST, access_key="x" * 129)], [dict(FIRST, secret_key="x" * 4097)],
                        [dict(FIRST, access_key=f"key-{index}") for index in range(65)]]
        environment = {name: value for name, value in os.environ.items() if not name.startswith("MOON_S3_")}
        for value in invalid_sets:
            config = directory / "invalid.json"
            config.write_text(json.dumps(dict(settings, credentials=value)))
            result = subprocess.run([str(BINARY)], env=dict(environment, MOON_S3_CONFIG=str(config)), capture_output=True, timeout=5)
            assert result.returncode != 0 and b"configuration_invalid" in result.stdout
        config = directory / "invalid.json"
        config.write_text(json.dumps(dict(settings, credentials=[FIRST])))
        for overrides in [{"MOON_S3_CREDENTIALS": "[]"}, {"MOON_S3_CREDENTIALS": "not-json"},
                          {"MOON_S3_ACCESS_KEY": "legacy", "MOON_S3_SECRET_KEY": "secret"},
                          {"MOON_S3_ACCESS_KEY": ""},
                          {"MOON_S3_CREDENTIALS": '[{"access_key":"one","access_key":"two","secret_key":"s"}]'}]:
            result = subprocess.run([str(BINARY)], env=dict(environment, MOON_S3_CONFIG=str(config), **overrides), capture_output=True, timeout=5)
            assert result.returncode != 0 and b"configuration_invalid" in result.stdout
            assert FIRST["secret_key"].encode() not in result.stdout
    print("Multi-key acceptance passed: shared operations, signature isolation, presign revocation, public-read boundaries, restart rotation, all-disabled protection, env overrides and invalid configuration refusal.")


if __name__ == "__main__":
    main()
