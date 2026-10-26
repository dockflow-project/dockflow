"""One-step upload registration, bounded ZIP extraction and native admission."""

import io
import json
import os
import socket
import stat
import struct
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
from dockflow_core.errors import DockflowError
from dockflow_pipelines import uploads
from dockflow_pipelines.cli import app as cli
from dockflow_pipelines.client import Client
from dockflow_pipelines.config import load_settings
from dockflow_pipelines.service import create_app
from fastapi.testclient import TestClient
from typer.testing import CliRunner

TYPE = {"schema_title": "system.Dataset", "schema_version": "0.0.1"}
URL = "/dockflow/v1/artifacts/upload"


@pytest.fixture
def served(tmp_path):
    config = tmp_path / "pipelines.toml"
    (tmp_path / "token").write_text("upload-test-token")
    config.write_text(
        'schema_version=1\n[project]\nid="upload-tests"\n[service]\ntoken_file="token"\n'
    )
    app = create_app(load_settings(config), execute=False)
    with TestClient(
        app, headers={"Authorization": "Bearer upload-test-token"}
    ) as client:
        yield app.state.core, client


def send(client, data=b"id,value\n1,hello\n", name="data.csv", **options):
    return client.post(
        URL,
        files={"uploadfile": (name, data)},
        data={"options": json.dumps({"type": TYPE, **options})},
    )


def archive(entries=(), compression=zipfile.ZIP_DEFLATED):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=compression) as output:
        for name, data in entries:
            output.writestr(name, data)
    return stream.getvalue()


def payload(record):
    return Path(unquote(urlsplit(record["content_uri"]).path))


def test_file_upload_is_registered_manual_managed_and_previewable(served):
    core, client = served
    result = send(client, metadata={"display_name": "Manual dataset"}, version="v1")
    assert result.status_code == 201, result.text
    record = result.json()
    assert record["origin"] == "external" and record["creation_origin"] == "manual"
    assert record["ownership"] == "managed" and record["producer"] is None
    assert record["source_uri"] is None and record["publication_state"] == "committed"
    assert record["upload"] == {"filename": "data.csv", "archive_mode": "keep"}
    assert record["metadata"] == {"display_name": "Manual dataset"}
    assert record["version"] == "v1" and record["type"] == TYPE
    assert payload(record).read_bytes() == b"id,value\n1,hello\n"
    preview = client.get(
        f"/dockflow/v1/artifacts/{record['artifact_id']}/contents"
    ).json()
    assert preview["format"] == "csv" and preview["name"] == "data.csv"
    assert preview["rows"] == [["1", "hello"]]
    assert core.store.list("runs") == [] and core.store.list("attempts") == []
    assert core.store.check(True, core.artifacts)["valid"]
    again = send(client).json()
    assert again["artifact_id"] != record["artifact_id"]
    assert again["content_uri"] != record["content_uri"]


@pytest.mark.parametrize("compression", [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED])
def test_zip_keep_and_extract_preserve_exact_contents_and_empty_directories(
    served, compression
):
    _, client = served
    data = archive(
        [
            ("nested/rows.csv", b"x,y\n1,2\n"),
            ("empty/", b""),
            ("literal.json", b'{"key":"<script>"}'),
            ("zero", b""),
        ],
        compression,
    )
    kept = send(client, data, "dataset.ZIP").json()
    assert kept["payload_kind"] == "file" and payload(kept).read_bytes() == data
    extracted = send(client, data, "dataset.ZIP", archive_mode="extract")
    assert extracted.status_code == 201, extracted.text
    record = extracted.json()
    assert record["payload_kind"] == "directory"
    assert record["size_bytes"] == len(b"x,y\n1,2\n") + len(b'{"key":"<script>"}')
    assert (payload(record) / "empty").is_dir()
    assert (payload(record) / "nested/rows.csv").read_bytes() == b"x,y\n1,2\n"
    assert not (payload(record) / "dataset.ZIP").exists()
    preview = client.get(
        f"/dockflow/v1/artifacts/{record['artifact_id']}/contents",
        params={"path": "nested/rows.csv"},
    ).json()
    assert preview["rows"] == [["1", "2"]]


def test_empty_file_and_empty_zip_are_valid_distinct_payload_kinds(served):
    _, client = served
    file = send(client, b"", "empty.bin").json()
    directory = send(client, archive(), "empty.zip", archive_mode="extract").json()
    assert file["size_bytes"] == directory["size_bytes"] == 0
    assert file["payload_kind"] == "file" and directory["payload_kind"] == "directory"
    assert directory["inventory"] == [] and payload(directory).is_dir()


@pytest.mark.parametrize(
    "paths",
    [
        ["../escape"],
        ["/absolute"],
        ["a/../../escape"],
        ["C:/drive"],
        ["a\\b"],
        ["./dot"],
        ["a//b"],
        ["a/", "a/"],
        ["same", "same"],
        ["a", "a/b"],
        ["a/b", "a"],
        ["A/b", "a/c"],
        ["file", "FILE"],
        ["café", "cafe\u0301"],
        ["a/CON.csv"],
        ["nul"],
        ["a/trailing."],
        ["a/control\x01"],
        ["/".join(["deep"] * 33)],
        ["a" * 256],
    ],
)
def test_unsafe_and_conflicting_zip_paths_publish_nothing(served, paths):
    core, client = served
    before = list(core.artifacts.managed_root.rglob("*"))
    with (
        pytest.warns(UserWarning)
        if len(paths) > 1 and paths[0] == paths[1]
        else _no_warning()
    ):
        data = archive([(name, b"" if name.endswith("/") else b"x") for name in paths])
    response = send(client, data, "unsafe.zip", archive_mode="extract")
    assert response.status_code == 400, response.text
    assert core.store.list("artifacts") == []
    assert list(core.artifacts.managed_root.rglob("*")) == before


def _no_warning():
    from contextlib import nullcontext

    return nullcontext()


@pytest.mark.parametrize(
    "mode", [stat.S_IFLNK, stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFCHR]
)
def test_zip_links_and_special_files_are_rejected(served, mode):
    _, client = served
    info = zipfile.ZipInfo("special")
    info.create_system = 3
    info.external_attr = (mode | 0o777) << 16
    response = send(
        client, archive([(info, b"target")]), "special.zip", archive_mode="extract"
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "kind", ["truncated", "crc", "encrypted", "compression", "not_zip", "nul"]
)
def test_corrupt_and_unsupported_zip_entries_are_rejected(served, kind):
    core, client = served
    data = bytearray(archive([("entry", b"payload")], zipfile.ZIP_STORED))
    if kind == "truncated":
        data = data[:-12]
    elif kind == "crc":
        data[30 + len("entry")] ^= 1
    elif kind == "encrypted":
        central = data.index(b"PK\x01\x02")
        struct.pack_into("<H", data, central + 8, 1)
        struct.pack_into("<H", data, 6, 1)
    elif kind == "compression":
        data = archive([("entry", b"payload")], zipfile.ZIP_BZIP2)
    elif kind == "not_zip":
        data = b"not a zip"
    else:
        data = data.replace(b"entry", b"en\x00ry")
    result = send(client, bytes(data), "bad.zip", archive_mode="extract")
    assert result.status_code == 400, result.text
    assert core.store.list("artifacts") == []


@pytest.mark.parametrize("limit", ["entries", "expanded", "request", "options"])
def test_upload_resource_limits(served, monkeypatch, limit):
    core, client = served
    data = archive([("first", b"a" * 100), ("second", b"b" * 100)])
    options = {"archive_mode": "extract"}
    if limit == "entries":
        monkeypatch.setattr(uploads, "ZIP_ENTRIES", 1)
    elif limit == "expanded":
        monkeypatch.setattr(uploads, "EXPANDED_BYTES", 150)
    elif limit == "request":
        monkeypatch.setitem(core.settings.service, "request_max_bytes", 100)
    else:
        options["metadata"] = {"large": "x" * uploads.OPTIONS_BYTES}
    result = send(client, data, "large.zip", **options)
    assert result.status_code == 413, result.text
    assert core.store.list("artifacts") == []


@pytest.mark.parametrize(
    "options",
    [
        {"archive_mode": "invalid"},
        {"archive_mode": []},
        {"extra": True},
        {"type": None},
        {"type": {"schema_title": "system.Dataset"}},
        {"metadata": []},
        {"metadata": {"dockflow.secret": True}},
        {"version": 42},
        {"version": ""},
        {"version": "x" * 257},
    ],
)
def test_invalid_options_do_not_create_artifacts(served, options):
    core, client = served
    result = send(client, **options)
    assert result.status_code == 400, result.text
    assert core.store.list("artifacts") == []


@pytest.mark.parametrize("name", ["../data.csv", "NUL", "bad."])
def test_invalid_uploaded_filename(served, name):
    _, client = served
    assert send(client, name=name).status_code == 400


def test_extract_requires_zip_extension_but_keep_accepts_arbitrary_bytes(served):
    _, client = served
    assert (
        send(client, archive(), "dataset.bin", archive_mode="extract").status_code
        == 400
    )
    assert send(client, b"not a valid zip", "dataset.zip").status_code == 201


def test_admission_auth_origin_queries_parts_and_incomplete_bodies(served):
    core, client = served
    assert (
        client.post(URL, headers={"Authorization": "Bearer wrong"}).status_code == 401
    )
    assert (
        client.post(URL, headers={"Origin": "https://other.invalid"}).status_code == 403
    )
    assert client.post(URL, json={}).status_code == 400
    for files, data in [
        ({"uploadfile": ("a.bin", b"a")}, {}),
        ({"wrong": ("a.bin", b"a")}, {"options": json.dumps({"type": TYPE})}),
        ({"uploadfile": ("a.bin", b"a")}, {"options": "{bad"}),
        ({"uploadfile": ("a.bin", b"a")}, {"options": "[]"}),
        (
            {"uploadfile": ("a.bin", b"a")},
            {"options": json.dumps({"type": TYPE}), "extra": "x"},
        ),
    ]:
        assert client.post(URL, files=files, data=data).status_code == 400
    response = client.post(
        URL,
        files=[("uploadfile", ("a", b"a")), ("uploadfile", ("b", b"b"))],
        data={"options": json.dumps({"type": TYPE})},
    )
    assert response.status_code == 400
    response = client.post(
        URL + "?unexpected=1",
        files={"uploadfile": ("a", b"a")},
        data={"options": json.dumps({"type": TYPE})},
    )
    assert response.status_code == 400
    raw = (
        b'--test\r\nContent-Disposition: form-data; name="options"\r\n\r\n'
        + json.dumps({"type": TYPE}).encode()
        + b'\r\n--test\r\nContent-Disposition: form-data; name="uploadfile"; filename="a"\r\n\r\nbytes'
    )
    assert (
        client.post(
            URL,
            content=raw,
            headers={"Content-Type": "multipart/form-data; boundary=test"},
        ).status_code
        == 400
    )
    assert core.store.list("artifacts") == []


def test_staging_cleanup_on_success_validation_and_publication_failure(
    served, monkeypatch, tmp_path
):
    core, client = served
    staging = tmp_path / "private-staging"
    staging.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(staging))
    assert send(client).status_code == 201
    assert list(staging.iterdir()) == []
    assert (
        send(client, b"corrupt", "bad.zip", archive_mode="extract").status_code == 400
    )
    assert list(staging.iterdir()) == []
    before = core.store.list("artifacts")

    def fail(*args):
        raise DockflowError("Storage is unavailable", "UNAVAILABLE", 503)

    monkeypatch.setattr(core.artifacts, "_publish_managed", fail)
    assert send(client).status_code == 503
    assert list(staging.iterdir()) == []
    assert core.store.list("artifacts") == before


def test_python_direct_and_cli_upload_without_server_visible_source_uri(tmp_path):
    config = tmp_path / "pipelines.toml"
    config.write_text('schema_version=1\n[project]\nid="direct-upload"\n')
    file = tmp_path / "client.csv"
    file.write_bytes(b"a,b\n1,2\n")
    result = CliRunner().invoke(
        cli,
        [
            "--config",
            str(config),
            "--json",
            "artifacts",
            "upload",
            str(file),
            "--type",
            "system.Dataset",
            "--metadata",
            'note="uploaded"',
        ],
    )
    assert result.exit_code == 0, result.output
    record = json.loads(result.stdout)["result"]
    assert record["metadata"] == {"note": "uploaded"}
    assert (
        record["source_uri"] is None
        and payload(record).read_bytes() == file.read_bytes()
    )
    file.unlink()
    assert payload(record).read_bytes() == b"a,b\n1,2\n"
    assert CliRunner().invoke(cli, ["artifacts", "upload", "--help"]).exit_code == 0


@pytest.mark.parametrize("kind", ["directory", "symlink", "fifo"])
def test_direct_nonregular_sources_rejected(tmp_path, kind):
    source = tmp_path / "source"
    if kind == "directory":
        source.mkdir()
    elif kind == "symlink":
        (tmp_path / "target").write_bytes(b"data")
        source.symlink_to(tmp_path / "target")
    else:
        os.mkfifo(source)
    with (
        pytest.raises(DockflowError, match="regular file"),
        uploads.open_source(source),
    ):
        pass


def test_upload_openapi_matches_multipart_and_descriptor(served):
    _, client = served
    schema = client.get("/dockflow/v1/openapi.json").json()
    operation = schema["paths"][URL]["post"]
    assert "201" in operation["responses"]
    assert set(operation["requestBody"]["content"]) == {"multipart/form-data"}
    assert "ArtifactUploadOptions" in schema["components"]["schemas"]
    assert "upload" in schema["components"]["schemas"]["Artifact"]["properties"]


def test_legacy_windows_multipart_filename_is_normalized_without_path_selection(served):
    _, client = served
    record = send(client, name="C:\\client\\data.csv").json()
    assert record["upload"]["filename"] == "data.csv"
    assert payload(record).name == "payload"


def test_upload_refuses_busy_and_unready_owner(served):
    core, client = served
    scheduler = client.app.state.scheduler
    scheduler.active_run = "busy-test"
    try:
        assert send(client).status_code == 409
    finally:
        scheduler.active_run = None
    scheduler.ready = False
    try:
        assert send(client).status_code == 503
    finally:
        scheduler.ready = True
    assert core.store.list("artifacts") == []


def test_direct_stream_limit_rejects_actual_bytes_before_publication(served):
    core, _ = served
    with pytest.raises(DockflowError) as error:
        uploads.upload_stream(
            core.artifacts, io.BytesIO(b"12345"), "data.bin", {"type": TYPE}, 4
        )
    assert error.value.code == "REQUEST_TOO_LARGE"
    assert core.store.list("artifacts") == []


def test_zip_entry_preflight_counts_actual_directory_before_loading_entries(
    served, monkeypatch
):
    core, client = served
    data = bytearray(archive([("one", b"1"), ("two", b"2")]))
    end = data.rindex(b"PK\x05\x06")
    struct.pack_into("<HH", data, end + 8, 0, 0)
    monkeypatch.setattr(uploads, "ZIP_ENTRIES", 1)
    assert (
        send(client, bytes(data), "large.zip", archive_mode="extract").status_code
        == 413
    )
    assert core.store.list("artifacts") == []


def test_multipart_options_reject_invalid_utf8_and_duplicate_json_keys(served):
    core, client = served
    for options in [b'{"metadata":{"x":"\xff"}}', b'{"type":{},"type":{}}']:
        raw = (
            b'--test\r\nContent-Disposition: form-data; name="options"\r\n\r\n'
            + options
            + b'\r\n--test\r\nContent-Disposition: form-data; name="uploadfile"; filename="a"\r\n\r\nbytes\r\n--test--\r\n'
        )
        assert (
            client.post(
                URL,
                content=raw,
                headers={"Content-Type": "multipart/form-data; boundary=test"},
            ).status_code
            == 400
        )
    assert core.store.list("artifacts") == []


def test_hashing_and_managed_publication_have_no_open_sql_transaction(
    served, monkeypatch
):
    core, client = served
    original_inventory = uploads.inventory
    original_publish = core.artifacts._publish_managed
    checks = []

    def fingerprint(path):
        assert core.store.database.depth == 0
        checks.append("hash")
        return original_inventory(path)

    def publish(*args):
        assert core.store.database.depth == 0
        checks.append("publish")
        return original_publish(*args)

    monkeypatch.setattr(uploads, "inventory", fingerprint)
    monkeypatch.setattr(core.artifacts, "_publish_managed", publish)
    assert send(client).status_code == 201
    assert checks == ["hash", "publish"]


def test_remote_python_client_and_cli_stream_bytes_with_auth_and_asgi_root_path(
    tmp_path, monkeypatch
):
    import uvicorn

    monkeypatch.setenv("NO_PROXY", "*")
    config = tmp_path / "pipelines.toml"
    (tmp_path / "token").write_text("remote-upload-test-token")
    config.write_text(
        'schema_version=1\n[project]\nid="remote-upload"\n[service]\ntoken_file="token"\n'
    )
    app = create_app(load_settings(config), execute=False)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    endpoint = f"http://127.0.0.1:{listener.getsockname()[1]}"
    # The ASGI server supplies the proxy root path to exercise route normalization.
    server = uvicorn.Server(uvicorn.Config(app, root_path="/proxy", log_level="error"))
    thread = threading.Thread(
        target=lambda: server.run(sockets=[listener]), daemon=True
    )
    thread.start()
    try:
        until = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < until:
            time.sleep(0.01)
        assert server.started
        remote = Client(endpoint, {"token_file": tmp_path / "token"})
        source = tmp_path / "café.csv"
        source.write_bytes(b"id,value\n1,remote\n")
        first = remote.upload_artifact(source, TYPE, metadata={"test": True})
        assert first["upload"]["filename"] == "café.csv"
        assert payload(first).read_bytes() == source.read_bytes()
        archive_path = tmp_path / "dataset.zip"
        archive_path.write_bytes(
            archive([("nested/file.txt", b"remote"), ("empty/", b"")])
        )
        # CLI config contains only client auth; the source is local to the client.
        client_config = tmp_path / "client.toml"
        client_config.write_text(
            'schema_version=1\n[project]\nid="client-only"\n[client]\ntoken_file="token"\n'
        )
        result = CliRunner().invoke(
            cli,
            [
                "--config",
                str(client_config),
                "--endpoint",
                endpoint,
                "--json",
                "artifacts",
                "upload",
                str(archive_path),
                "--archive-mode",
                "extract",
            ],
        )
        assert result.exit_code == 0, result.output
        record = json.loads(result.stdout)["result"]
        assert record["payload_kind"] == "directory"
        assert (payload(record) / "nested/file.txt").read_bytes() == b"remote"
        assert (payload(record) / "empty").is_dir()
        with pytest.raises(DockflowError) as error:
            Client(endpoint).upload_artifact(source, TYPE)
        assert error.value.status == 401
        assert len(app.state.core.store.list("artifacts")) == 2
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive()
