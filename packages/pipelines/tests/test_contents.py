"""Bounded preview correctness, authority, cursor stability and storage protection."""

import base64
import csv
import io
import os
import struct
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
from dockflow_pipelines.config import load_settings
from dockflow_pipelines.contents import (
    CSV_BYTES,
    IMAGE_BYTES,
    JSON_BYTES,
    ArtifactContents,
)
from dockflow_pipelines.service import create_app
from fastapi.testclient import TestClient
from test_web import accepted_snapshot

TYPE = {"schema_title": "system.Dataset", "schema_version": "0.0.1"}
API = "/dockflow/v1/artifacts/"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aP1kAAAAASUVORK5CYII="
)


@pytest.fixture
def served(tmp_path):
    (tmp_path / "inputs").mkdir()
    (tmp_path / "token").write_text("contents-test-token")
    config = tmp_path / "pipelines.toml"
    config.write_text(
        'schema_version=1\n[project]\nid="contents-tests"\n[artifacts]\nexternal_roots=["inputs"]\n[service]\ntoken_file="token"\n'
    )
    app = create_app(load_settings(config), execute=False)
    with TestClient(
        app, headers={"Authorization": "Bearer contents-test-token"}
    ) as client:
        yield app.state.core, client


def register(core, content, name="data.csv", managed=True):
    path = core.settings.root / "inputs" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return core.artifacts.register(path.as_uri(), TYPE, managed=managed)


def target(record):
    return Path(unquote(urlsplit(record["content_uri"]).path))


def preview(client, artifact, **params):
    return client.get(API + artifact["artifact_id"] + "/contents", params=params)


@pytest.mark.parametrize(
    "delimiter,newline", [(",", "\n"), (";", "\r\n"), ("\t", "\n")]
)
def test_csv_pages_preserve_quoted_utf8_cells_and_logical_rows(
    served, delimiter, newline
):
    core, client = served
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter=delimiter, lineterminator=newline)
    writer.writerow(["id", "text", "text", ""])
    expected = [[str(i), 'a "quoted" café\nline', "", "tail"] for i in range(137)]
    writer.writerows(expected)
    artifact = register(core, b"\xef\xbb\xbf" + stream.getvalue().encode())
    before = accepted_snapshot(core)
    rows, token = [], None
    while True:
        response = preview(
            client, artifact, page_size=17, **({"page_token": token} if token else {})
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["format"] == "csv" and data["columns"] == ["id", "text", "text", ""]
        assert data["first_row"] == len(rows) + 1
        rows.extend(data["rows"])
        token = data["next_page_token"]
        if not token:
            break
    assert rows == expected
    assert accepted_snapshot(core) == before


def test_csv_huge_file_uses_bounded_ranges_not_full_materialization(
    served, monkeypatch
):
    core, client = served
    artifact = register(core, b"id,value\n" + b"1,example\n" * 400000)
    original = os.pread
    reads = []

    def measured(fd, length, offset):
        reads.append((length, offset))
        return original(fd, length, offset)

    monkeypatch.setattr(os, "pread", measured)
    first = preview(client, artifact).json()
    second = preview(client, artifact, page_token=first["next_page_token"]).json()
    assert first["last_row"] == 50 and second["first_row"] == 51
    assert max(length for length, _ in reads) <= CSV_BYTES
    assert sum(length for length, _ in reads) < artifact["size_bytes"]
    assert any(offset > 0 for _, offset in reads)


def test_csv_budget_boundary_does_not_skip_partial_quoted_record(served):
    core, client = served
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["id", "text"])
    expected = [[str(i), "é\n" * 25000] for i in range(30)]
    writer.writerows(expected)
    artifact = register(core, output.getvalue().encode())
    rows, token = [], None
    while True:
        response = preview(
            client, artifact, page_size=200, **({"page_token": token} if token else {})
        )
        assert response.status_code == 200, response.text
        rows.extend(response.json()["rows"])
        token = response.json()["next_page_token"]
        if not token:
            break
    assert rows == expected


def test_cursor_tampering_scope_restart_and_file_change(served):
    core, client = served
    artifact = register(core, b"id,value\n" + b"1,a\n" * 100)
    cursor = preview(client, artifact).json()["next_page_token"]
    assert preview(client, artifact, page_token="bad").status_code == 400
    assert preview(client, artifact, page_token=cursor, page_size=20).status_code == 409
    second = register(core, b"id,value\n" + b"1,a\n" * 100, "other.csv")
    assert preview(client, second, page_token=cursor).status_code == 409
    from dockflow_core.errors import DockflowError

    with pytest.raises(DockflowError, match="expired"):
        ArtifactContents(core.artifacts).show(
            artifact["artifact_id"], page_token=cursor
        )
    path = target(artifact)
    old = path.stat()
    os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns + 1000000))
    assert preview(client, artifact, page_token=cursor).status_code == 409


@pytest.mark.parametrize(
    "content,name,status",
    [
        (b'a,b\n1,"unclosed', "bad.csv", 422),
        (b"a,b\n1,\xff", "bad.csv", 422),
        (b"a\n" + b"x" * (128 * 1024 + 1), "big.csv", 413),
        ((",".join(str(i) for i in range(201)) + "\n").encode(), "wide.csv", 413),
        (b'{"unclosed":', "bad.json", 422),
        (b'{"number":NaN}', "bad.json", 422),
        (b"[" * 1000 + b"0" + b"]" * 1000, "deep.json", 413),
        (b"[" + b"0," * 21000 + b"0]", "many.json", 413),
        (b'"' + b"x" * JSON_BYTES + b'"', "large.json", 413),
        (PNG[:16] + struct.pack(">II", 20000, 20000) + PNG[24:], "huge.png", 413),
        (PNG + b"\0" * IMAGE_BYTES, "large.png", 413),
    ],
)
def test_malformed_and_excessive_content_fails_explicitly(
    served, content, name, status
):
    core, client = served
    artifact = register(core, content, name)
    response = preview(client, artifact)
    assert response.status_code == status, response.text


def test_json_preserves_duplicates_precision_surrogates_and_xss_as_data(served):
    core, client = served
    artifact = register(
        core,
        b'{"n":9007199254740993,"n":1e+200,"text":"<svg onload=alert(1)>","escape":"\\ud800","ok":true,"none":null}',
        "data.json",
    )
    response = preview(client, artifact)
    assert response.status_code == 200, response.text
    data = response.json()
    children = data["tree"]["children"]
    assert [item["key"] for item in children[:2]] == ['"n"', '"n"']
    assert [item["node"]["value"] for item in children[:2]] == [
        "9007199254740993",
        "1e+200",
    ]
    assert children[3]["node"]["value"] == '"\\ud800"'
    assert children[4]["node"]["value"] is True
    assert data["checksum_verified"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_images_and_bounded_text_never_serve_active_document_types(served):
    core, client = served
    image = register(core, PNG, "image.png")
    data = preview(client, image).json()
    assert (data["format"], data["mime_type"], data["width"], data["height"]) == (
        "image",
        "image/png",
        1,
        1,
    )
    assert base64.b64decode(data["base64"]) == PNG
    svg = register(core, b'<svg onload="alert(1)"></svg>', "image.svg")
    assert preview(client, svg, format="image").status_code == 422
    assert preview(client, svg, format="text").json()["text"].startswith("<svg")
    text = register(core, ("é" * 100000).encode(), "long.txt")
    data = preview(client, text, format="text").json()
    assert data["truncated"] and len(data["text"].encode()) <= 65536
    binary = register(core, b"SQLite format 3\0binary", "data.sqlite")
    assert preview(client, binary).json()["format"] == "unsupported"


@pytest.mark.parametrize(
    "content,mime,width,height",
    [
        (b"GIF89a" + struct.pack("<HH", 3, 2), "image/gif", 3, 2),
        (
            b"\xff\xd8\xff\xc0\x00\x0b\x08\x00\x02\x00\x03\x01\x01\x11\x00",
            "image/jpeg",
            3,
            2,
        ),
        (
            b"RIFF"
            + struct.pack("<I", 22)
            + b"WEBPVP8X"
            + struct.pack("<I", 10)
            + b"\0" * 4
            + (2).to_bytes(3, "little")
            + (1).to_bytes(3, "little"),
            "image/webp",
            3,
            2,
        ),
        (
            b"RIFF"
            + struct.pack("<I", 18)
            + b"WEBPVP8L"
            + struct.pack("<I", 5)
            + b"\x2f"
            + (2 + (1 << 14)).to_bytes(4, "little")
            + b"\0",
            "image/webp",
            3,
            2,
        ),
    ],
)
def test_supported_raster_canvas_headers_are_recognized(content, mime, width, height):
    from dockflow_pipelines.contents import image_info

    assert image_info(content) == (mime, width, height)


def test_directory_is_paginated_registered_inventory_with_nested_and_empty_folders(
    served,
):
    core, client = served
    root = core.settings.root / "inputs" / "directory"
    (root / "nested" / "empty").mkdir(parents=True)
    (root / "nested" / "file #.json").write_text('{"value":1}')
    for i in range(60):
        (root / f"file-{i:02}.csv").write_text("a\n1\n")
    artifact = core.artifacts.register(root.as_uri(), TYPE, managed=True)
    (target(artifact) / "not-registered.txt").write_text("unregistered")
    data = preview(client, artifact, page_size=20).json()
    assert data["format"] == "directory" and data["total_entries"] == 61
    assert data["items"][0]["name"] == "nested"
    assert len(data["items"]) == 20 and data["next_page_token"]
    assert (
        preview(
            client, artifact, page_size=20, page_token=data["next_page_token"]
        ).json()["items"][0]["name"]
        != "nested"
    )
    nested = preview(client, artifact, path="nested").json()
    assert nested["items"][0]["name"] == "empty"
    assert preview(client, artifact, path="nested/empty").json()["items"] == []
    assert (
        preview(client, artifact, path="nested/file #.json").json()["format"] == "json"
    )
    assert preview(client, artifact, path="not-registered.txt").status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "../secret",
        "/etc/passwd",
        "nested/../file",
        "nested//file",
        "nested\\file",
        ".",
        "nested/./file",
        "\0file",
    ],
)
def test_path_traversal_is_rejected(served, path):
    core, client = served
    artifact = register(core, b"a\n1\n")
    assert preview(client, artifact, path=path).status_code in {400, 409}


def test_symlinks_special_files_changes_and_retirement_are_not_read(served):
    core, client = served
    artifact = register(core, b'{"value":1}', "data.json", managed=False)
    path = target(artifact)
    secret = core.settings.root / "private.json"
    secret.write_text('{"value":2}')
    path.unlink()
    path.symlink_to(secret)
    assert preview(client, artifact).status_code in {400, 403}
    path.unlink()
    os.mkfifo(path)
    assert preview(client, artifact).status_code == 403
    path.unlink()
    path.write_text('{"value":2}')
    assert preview(client, artifact).status_code == 409
    path.unlink()
    assert preview(client, artifact).status_code == 404
    core.store.put("artifacts", {**artifact, "retiring_plan_id": "test-retirement"})
    assert preview(client, artifact).status_code == 410


def test_auth_query_validation_and_metadata_only(served):
    core, client = served
    artifact = register(core, b"a\n1\n")
    route = API + artifact["artifact_id"] + "/contents"
    assert (
        client.get(route, headers={"Authorization": "Bearer wrong"}).status_code == 401
    )
    assert client.get(route + "?page_size=2&page_size=3").status_code == 400
    assert client.get(route + "?unknown=1").status_code == 400
    for params in [
        {"page_size": 0},
        {"page_size": 201},
        {"page_size": "bad"},
        {"format": "html"},
    ]:
        assert preview(client, artifact, **params).status_code == 400
    record = {
        **artifact,
        "payload_kind": "metadata",
        "inventory": [],
        "content_uri": None,
        "size_bytes": 0,
        "metadata": {"score": 0.8},
    }
    core.store.put("artifacts", record)
    data = preview(client, record).json()
    assert data["format"] == "json" and "Metadata-only" in data["message"]


def test_parent_symlink_swap_between_admission_and_open_cannot_escape(
    served, monkeypatch
):
    core, client = served
    artifact = register(core, b"a\n1\n", "folder/data.csv", managed=False)
    parent = target(artifact).parent
    private = core.settings.root / "private"
    private.mkdir()
    (private / "data.csv").write_text("secret\nprivate\n")
    original = core.artifacts._admit

    def swap(uri):
        result = original(uri)
        parent.rename(parent.with_name("moved"))
        parent.symlink_to(private, target_is_directory=True)
        return result

    monkeypatch.setattr(core.artifacts, "_admit", swap)
    response = preview(client, artifact)
    assert response.status_code == 403
    assert "private" not in response.text


def test_read_mutation_and_current_allowlist_are_rechecked(served, monkeypatch):
    core, client = served
    artifact = register(core, b"a\n1\n", managed=False)
    original = os.pread
    changed = False

    def mutate(fd, size, offset):
        nonlocal changed
        result = original(fd, size, offset)
        if not changed:
            changed = True
            target(artifact).write_bytes(b"a\n2\n")
        return result

    monkeypatch.setattr(os, "pread", mutate)
    assert preview(client, artifact).status_code == 409
    core.artifacts.options["external_roots"] = []
    assert preview(client, artifact).status_code == 403


def test_preview_route_schema_is_explicit(served):
    _, client = served
    schema = client.get("/dockflow/v1/openapi.json").json()
    operation = schema["paths"][API + "{artifact_id}/contents"]["get"]
    assert {item["name"] for item in operation["parameters"]} == {
        "artifact_id",
        "path",
        "format",
        "page_size",
        "page_token",
    }
    assert operation["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/ArtifactContents")


class RangeStorage:
    def __init__(self, data):
        self.data = data
        self.etag = '"validator"'
        self.calls = []
        self.ignore_range = False
        self.last_body = None

    def head_object(self, **arguments):
        return {
            "ETag": self.etag,
            "VersionId": "version-one",
            "ContentLength": len(self.data),
        }

    def get_object(self, **arguments):
        self.calls.append(arguments)
        start, end = map(int, arguments["Range"].removeprefix("bytes=").split("-"))
        data = self.data[start : end + 1]
        self.last_body = io.BytesIO(data)
        return {
            "ETag": self.etag,
            "VersionId": "version-one",
            "ContentLength": len(data),
            "ContentRange": None
            if self.ignore_range
            else f"bytes {start}-{end}/{len(self.data)}",
            "Body": self.last_body,
        }


def test_s3_conditional_ranges_versions_changes_and_nonconforming_provider(served):
    core, client = served
    content = b"id,value\n" + b"1,example\n" * 1000
    artifact = register(core, content)
    artifact = core.store.put(
        "artifacts",
        {
            **artifact,
            "ownership": "external",
            "storage_backend": "external",
            "content_uri": "s3://preview-bucket/owned/data.csv",
        },
    )
    core.artifacts.options["allowed_uri_prefixes"] = ["s3://preview-bucket/owned"]
    storage = RangeStorage(content)
    core.artifacts._client = storage
    response = preview(client, artifact)
    assert response.status_code == 200, response.text
    assert storage.calls and all(
        call["IfMatch"] == storage.etag and call["VersionId"] == "version-one"
        for call in storage.calls
    )
    token = response.json()["next_page_token"]
    storage.etag = '"replacement"'
    assert preview(client, artifact, page_token=token).status_code == 409
    storage.ignore_range = True
    assert preview(client, artifact).status_code == 409
    assert storage.last_body.closed
