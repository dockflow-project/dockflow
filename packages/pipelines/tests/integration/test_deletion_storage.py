"""Real S3 deletion is qualified only against uniquely owned disposable buckets."""

import os
import uuid

import pytest
from dockflow_core.errors import DockflowError
from dockflow_pipelines.config import load_settings
from dockflow_pipelines.core import Core
from dockflow_pipelines.deletion import Deletions

pytestmark = pytest.mark.s3
TYPE = {"schema_title": "system.Dataset", "schema_version": "0.0.1"}


@pytest.fixture(params=["sqlite", "postgresql"])
def environment(tmp_path, request):
    endpoint = os.environ.get("DOCKFLOW_TEST_CACHE_S3_ENDPOINT")
    if not endpoint:
        pytest.skip("Requires a disposable S3 endpoint")
    if request.param == "postgresql" and not os.environ.get(
        "DOCKFLOW_TEST_CACHE_POSTGRES_DSN"
    ):
        pytest.skip("Requires a disposable PostgreSQL database")
    import boto3

    client = boto3.client("s3", endpoint_url=endpoint)
    bucket = "dockflow-deletion-" + uuid.uuid4().hex
    client.create_bucket(Bucket=bucket)
    client.put_bucket_versioning(
        Bucket=bucket, VersioningConfiguration={"Status": "Enabled"}
    )
    try:
        config = tmp_path / "dockflow.toml"
        config.write_text(
            f'schema_version=1\n[project]\nid="{bucket}"\n[artifacts]\nbackend="s3"\nendpoint="{endpoint}"\nbucket="{bucket}"\nprefix="owned"\nallow_insecure_http=true\nexternal_roots=["inputs"]\n'
        )
        if request.param == "postgresql":
            with config.open("a") as stream:
                stream.write(
                    '[state]\nbackend="postgresql"\ndsn_env="DOCKFLOW_TEST_CACHE_POSTGRES_DSN"\n'
                )
        (tmp_path / "inputs").mkdir()
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


def test_real_s3_scan_prefix_directory_markers_manual_and_orphans(environment):
    core, client, bucket = environment
    source = core.settings.root / "inputs" / "database"
    source.write_bytes(b"database")
    artifact = core.artifacts.register(source.as_uri(), TYPE, managed=True)
    client.put_object(Bucket=bucket, Key="owned/orphan", Body=b"orphan")
    client.put_object(Bucket=bucket, Key="owned/empty-directory/", Body=b"")
    client.put_object(Bucket=bucket, Key="owned-other/foreign", Body=b"foreign")
    service = Deletions(core)
    scan = service.scan({})
    assert scan["totals"]["artifact_bytes"] == 8
    assert scan["totals"]["orphan_bytes"] == 6
    rows = scan["items"]
    assert any(row["classification"] == "manual_artifact" for row in rows)
    assert any(row["path"] == "empty-directory/" for row in rows)
    assert not any("foreign" in row["path"] for row in rows)
    plan = service.plan({"scan_id": scan["scan_id"], "orphans": True})
    assert len(plan["rows"]) == 2
    assert (
        service.apply({"plan_id": plan["plan_id"], "confirmation": "DANGER"})["state"]
        == "completed"
    )
    assert (
        client.get_object(Bucket=bucket, Key="owned-other/foreign")["Body"].read()
        == b"foreign"
    )
    plan = service.plan(
        {
            "targets": [{"collection": "artifacts", "id": artifact["artifact_id"]}],
            "delete_files": True,
        }
    )
    assert not plan["blockers"]
    assert (
        service.apply({"plan_id": plan["plan_id"], "confirmation": "DANGER"})["state"]
        == "completed"
    )
    assert core.store.list("artifacts") == []
    assert core.store.check()["valid"]
    assert core.artifacts.storage_identity(create=False) == plan["storage_id"]


def test_real_s3_exact_version_deletion_preserves_replacement(environment, monkeypatch):
    core, client, bucket = environment
    client.put_object(Bucket=bucket, Key="owned/orphan", Body=b"original")
    service = Deletions(core)
    scan = service.scan({})
    plan = service.plan({"scan_id": scan["scan_id"], "orphans": True})
    original = client.delete_object

    def race(**arguments):
        client.put_object(Bucket=bucket, Key=arguments["Key"], Body=b"replacement")
        return original(**arguments)

    monkeypatch.setattr(client, "delete_object", race)
    result = service.apply({"plan_id": plan["plan_id"], "confirmation": "DANGER"})
    assert result["state"] == "completed"
    assert (
        client.get_object(Bucket=bucket, Key="owned/orphan")["Body"].read()
        == b"replacement"
    )
    monkeypatch.setattr(client, "delete_object", original)
    result = service.apply({"plan_id": plan["plan_id"], "confirmation": "DANGER"})
    assert result["state"] == "completed"
    assert not result["failures"]


def test_s3_versioning_and_object_lock_fail_before_retirement(environment, monkeypatch):
    core, client, bucket = environment
    client.put_object(Bucket=bucket, Key="owned/orphan", Body=b"original")
    service = Deletions(core)
    scan = service.scan({})
    plan = service.plan({"scan_id": scan["scan_id"], "orphans": True})
    original = client.get_bucket_versioning
    monkeypatch.setattr(
        client, "get_bucket_versioning", lambda **kwargs: {"Status": "Suspended"}
    )
    with pytest.raises(DockflowError, match="versioning"):
        service.apply({"plan_id": plan["plan_id"], "confirmation": "DANGER"})
    assert service.show({"plan_id": plan["plan_id"]})["state"] == "planned"
    monkeypatch.setattr(client, "get_bucket_versioning", original)
    monkeypatch.setattr(
        client,
        "get_object_lock_configuration",
        lambda **kwargs: {"ObjectLockConfiguration": {"ObjectLockEnabled": "Enabled"}},
    )
    with pytest.raises(DockflowError, match="Object-lock"):
        service.apply({"plan_id": plan["plan_id"], "confirmation": "DANGER"})
    assert (
        client.get_object(Bucket=bucket, Key="owned/orphan")["Body"].read()
        == b"original"
    )


def test_unversioned_provider_is_qualified_before_selected_data(
    environment, monkeypatch
):
    core, client, bucket = environment
    # Simulate a provider that acknowledges but ignores If-Match, regardless of
    # which real provider supplies the remaining operations.
    client.put_object(Bucket=bucket, Key="owned/orphan", Body=b"preserve")
    original_versioning = client.get_bucket_versioning
    monkeypatch.setattr(client, "get_bucket_versioning", lambda **kwargs: {})
    service = Deletions(core)
    scan = service.scan({})
    plan = service.plan({"scan_id": scan["scan_id"], "orphans": True})
    original_delete = client.delete_object

    def ignoring_condition(**arguments):
        arguments.pop("IfMatch", None)
        return original_delete(**arguments)

    monkeypatch.setattr(client, "delete_object", ignoring_condition)
    with pytest.raises(DockflowError, match="Enable bucket versioning"):
        service.apply({"plan_id": plan["plan_id"], "confirmation": "DANGER"})
    assert (
        client.get_object(Bucket=bucket, Key="owned/orphan")["Body"].read()
        == b"preserve"
    )
    assert service.show({"plan_id": plan["plan_id"]})["state"] == "planned"
    monkeypatch.setattr(client, "get_bucket_versioning", original_versioning)


def test_s3_lost_delete_acknowledgment_resumes_without_touching_new_version(
    environment, monkeypatch
):
    core, client, bucket = environment
    client.put_object(Bucket=bucket, Key="owned/orphan", Body=b"old")
    service = Deletions(core)
    scan = service.scan({})
    plan = service.plan({"scan_id": scan["scan_id"], "orphans": True})
    original = client.delete_object

    def lost_ack(**arguments):
        original(**arguments)
        raise TimeoutError("synthetic lost deletion acknowledgment")

    monkeypatch.setattr(client, "delete_object", lost_ack)
    assert (
        service.apply({"plan_id": plan["plan_id"], "confirmation": "DANGER"})["state"]
        == "partial"
    )
    client.put_object(Bucket=bucket, Key="owned/orphan", Body=b"new")
    monkeypatch.setattr(client, "delete_object", original)
    assert (
        Deletions(core).apply({"plan_id": plan["plan_id"], "confirmation": "DANGER"})[
            "state"
        ]
        == "completed"
    )
    assert client.get_object(Bucket=bucket, Key="owned/orphan")["Body"].read() == b"new"
