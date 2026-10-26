"""Real conditional preview reads against an explicitly disposable S3 endpoint."""

import io
import os
import uuid
import zipfile

import pytest
from dockflow_pipelines.config import load_settings
from dockflow_pipelines.contents import ArtifactContents
from dockflow_pipelines.core import Core
from dockflow_pipelines.uploads import upload_stream

pytestmark = pytest.mark.s3


@pytest.fixture(params=[False, True])
def environment(tmp_path, request):
    endpoint = os.environ.get("DOCKFLOW_TEST_CONTENTS_S3_ENDPOINT")
    if not endpoint:
        pytest.skip("Requires a disposable S3 endpoint")
    import boto3

    client = boto3.client("s3", endpoint_url=endpoint)
    bucket = "dockflow-contents-" + uuid.uuid4().hex
    client.create_bucket(Bucket=bucket)
    if request.param:
        client.put_bucket_versioning(
            Bucket=bucket, VersioningConfiguration={"Status": "Enabled"}
        )
    try:
        (tmp_path / "inputs").mkdir()
        config = tmp_path / "pipelines.toml"
        config.write_text(
            f'schema_version=1\n[project]\nid="contents-integration"\n[artifacts]\nbackend="s3"\nendpoint="{endpoint}"\nbucket="{bucket}"\nprefix="owned"\nallow_insecure_http=true\nexternal_roots=["inputs"]\n'
        )
        core = Core(load_settings(config))
        core.artifacts._client = client
        with core.store.owner():
            core.initialize()
            yield core, client, bucket
    finally:
        for page in client.get_paginator("list_object_versions").paginate(
            Bucket=bucket
        ):
            objects = [
                {"Key": row["Key"], "VersionId": row["VersionId"]}
                for row in [*page.get("Versions", []), *page.get("DeleteMarkers", [])]
            ]
            if objects:
                client.delete_objects(Bucket=bucket, Delete={"Objects": objects})
        client.delete_bucket(Bucket=bucket)


def test_real_s3_ranges_csv_json_and_nested_inventory(environment):
    core, _, _ = environment
    root = core.settings.root / "inputs" / "directory"
    root.mkdir()
    (root / "example.csv").write_bytes(b"id,value\n" + b"1,example\n" * 200000)
    (root / "file #.json").write_text('{"value":9007199254740993}')
    record = core.artifacts.register(
        root.as_uri(),
        {"schema_title": "system.Dataset", "schema_version": "0.0.1"},
        managed=True,
    )
    previews = ArtifactContents(core.artifacts)
    listing = previews.show(record["artifact_id"])
    assert {item["name"] for item in listing["items"]} == {"example.csv", "file #.json"}
    first = previews.show(record["artifact_id"], path="example.csv")
    second = previews.show(
        record["artifact_id"], path="example.csv", page_token=first["next_page_token"]
    )
    assert first["last_row"] == 50 and second["first_row"] == 51
    tree = previews.show(record["artifact_id"], path="file #.json")
    assert (
        tree["checksum_verified"]
        and tree["tree"]["children"][0]["node"]["value"] == "9007199254740993"
    )


def test_real_s3_manual_upload_file_archive_and_extracted_directory(environment):
    core, client, bucket = environment
    options = {"type": {"schema_title": "system.Dataset", "schema_version": "0.0.1"}}
    file = upload_stream(
        core.artifacts,
        io.BytesIO(b"id,text\n1,uploaded\n"),
        "dataset.csv",
        options,
        1024**2,
    )
    assert file["creation_origin"] == "manual" and file["producer"] is None
    assert core.artifacts.verify(file["artifact_id"])["verified"]
    assert ArtifactContents(core.artifacts).show(file["artifact_id"])["rows"] == [
        ["1", "uploaded"]
    ]
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("nested/data.json", '{"message":"uploaded"}')
        output.writestr("empty/", b"")
    kept = upload_stream(
        core.artifacts, io.BytesIO(archive.getvalue()), "dataset.zip", options, 1024**2
    )
    assert kept["payload_kind"] == "file"
    extracted = upload_stream(
        core.artifacts,
        io.BytesIO(archive.getvalue()),
        "dataset.zip",
        {**options, "archive_mode": "extract"},
        1024**2,
    )
    assert extracted["payload_kind"] == "directory"
    assert any(
        entry == {"path": "empty", "kind": "directory"}
        for entry in extracted["inventory"]
    )
    tree = ArtifactContents(core.artifacts).show(
        extracted["artifact_id"], path="nested/data.json"
    )
    assert tree["checksum_verified"]
    assert core.artifacts.verify(extracted["artifact_id"])["verified"]
    assert core.store.check(True, core.artifacts)["valid"]
    assert client.list_objects_v2(Bucket=bucket).get("KeyCount", 0) > 0
