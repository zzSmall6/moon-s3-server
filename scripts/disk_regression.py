#!/usr/bin/env python3
import json
import os
import pathlib
import subprocess
import tempfile

from auth_regression import ACCESS_KEY, SECRET_KEY
from operations_regression import PROJECT, free_port, running
from s3_client import S3Client
from streaming_regression import digest_headers, pending, response, eventually


def main():
    subprocess.run(["moon", "build", "cmd/main", "--target", "native"], cwd=PROJECT, check=True)
    with tempfile.TemporaryDirectory(prefix="moon-s3-disk-") as temporary:
        directory = pathlib.Path(temporary)
        settings = dict(root=str(directory / "data"), listen=f"127.0.0.1:{free_port()}",
                        access_key=ACCESS_KEY, secret_key=SECRET_KEY, min_free_disk_bytes=65536)
        with running(directory, settings) as (_, port, _):
            client = S3Client(f"http://127.0.0.1:{port}", ACCESS_KEY, SECRET_KEY)
            client.request("PUT", "/disk-bucket")
            client.request("PUT", "/disk-bucket/key", b"original")
            text = client.request("GET", "/metrics")[1].decode()
            available = int(next(line.split()[1] for line in text.splitlines() if line.startswith("moon_s3_disk_available_bytes ")))
            assert available > 0 and abs(available - os.statvfs(directory).f_bavail * os.statvfs(directory).f_frsize) < 64 * 1024 * 1024
        source = directory / "capacity.c"
        source.write_text('''#include <sys/statvfs.h>
#include <stdlib.h>
#include <stdio.h>
int statvfs(const char *path, struct statvfs *result) {
  FILE *stream = fopen(getenv("MOON_S3_TEST_CAPACITY"), "r");
  long long value = -1;
  if (stream) { fscanf(stream, "%lld", &value); fclose(stream); }
  if (value < 0) return -1;
  *result = (struct statvfs){0};
  result->f_frsize = 1;
  result->f_bavail = value;
  return 0;
}
''')
        library = directory / "capacity.so"
        subprocess.run(["cc", "-shared", "-fPIC", str(source), "-o", str(library)], check=True)
        capacity = directory / "capacity"
        def set_capacity(value):
            staging = directory / "next-capacity"
            staging.write_text(str(value))
            staging.replace(capacity)
        set_capacity(1048576)
        with running(directory, settings, {"LD_PRELOAD": str(library), "MOON_S3_TEST_CAPACITY": str(capacity)}) as (_, port, _):
            client = S3Client(f"http://127.0.0.1:{port}", ACCESS_KEY, SECRET_KEY)
            _, upload = client.xml("POST", "/disk-bucket/part?uploads")
            part = "/disk-bucket/part?uploadId=" + upload.findtext("{*}UploadId") + "&partNumber=1"
            client.request("PUT", part, b"old-part")
            def clean():
                text = client.request("GET", "/metrics")[1].decode()
                return ("moon_s3_staged_request_bytes 0\n" in text and "moon_s3_buffered_request_bytes 0\n" in text
                        and not list((directory / "data").glob(".request-*.tmp")))
            rejected = 0
            for value in [65535, -1]:
                set_capacity(value)
                for path in ["/disk-bucket/key", part]:
                    body = b"replacement"
                    result = response(pending(port, path, len(body), body, digest_headers("PUT", path, port, body)))
                    assert result[0] == 507 and b"InsufficientStorage" in result[1], result
                    rejected += 1
                    eventually(clean)
            set_capacity(65540)
            body = b"more than four bytes"
            assert response(pending(port, "/disk-bucket/key", len(body), body))[0] == 507
            rejected += 1
            set_capacity(1048576)
            body = b"a" * 16384 + b"tail"
            headers = digest_headers("PUT", "/disk-bucket/key", port, body)
            connection = pending(port, "/disk-bucket/key", len(body), body[:16384], headers)
            eventually(lambda: any(path.stat().st_size == 16384 for path in (directory / "data").glob(".request-*.tmp")))
            set_capacity(65536)
            connection.sendall(body[16384:])
            assert response(connection)[0] == 507
            rejected += 1
            eventually(clean)
            chunked = pending(port, "/disk-bucket/key", 0, b"4\r\nnew!\r\n0\r\n\r\n", chunked=True)
            assert response(chunked)[0] == 507
            rejected += 1
            eventually(clean)
            assert client.request("GET", "/disk-bucket/key")[1] == b"original"
            _, parts = client.xml("GET", part.rsplit("&partNumber", 1)[0])
            assert parts.findtext("{*}Part/{*}Size") == "8"
            text = client.request("GET", "/metrics")[1].decode()
            assert f"moon_s3_upload_disk_rejections_total {rejected}\n" in text
            set_capacity(1048576)
            client.request("PUT", "/disk-bucket/key", b"recovered")
            assert client.request("GET", "/disk-bucket/key")[1] == b"recovered"
            eventually(clean)
        for value in [-1, 1099511627777, 0.5, "65536"]:
            invalid = dict(settings, min_free_disk_bytes=value)
            config = directory / "invalid.json"
            config.write_text(json.dumps(invalid))
            environment = {name: value for name, value in os.environ.items() if not name.startswith("MOON_S3_")}
            result = subprocess.run([str(PROJECT / "_build/native/debug/build/cmd/main/main.exe")],
                                    env=dict(environment, MOON_S3_CONFIG=str(config)), capture_output=True, timeout=5)
            assert result.returncode != 0 and b"configuration_invalid" in result.stdout
        set_capacity(0)
        with running(directory, settings, {"LD_PRELOAD": str(library), "MOON_S3_TEST_CAPACITY": str(capacity),
                                           "MOON_S3_MIN_FREE_DISK_BYTES": "0"}) as (_, port, _):
            client = S3Client(f"http://127.0.0.1:{port}", ACCESS_KEY, SECRET_KEY)
            assert b"moon_s3_disk_min_free_bytes 0\n" in client.request("GET", "/metrics")[1]
            client.request("PUT", "/disk-bucket/empty", b"")
    print("Disk reserve regression passed: real capacity, preflight and midstream refusal, chunked bodies, probe failure, old object/part preservation, cleanup, metrics and recovery.")


if __name__ == "__main__":
    main()
