"""Opt-in real S3 cache publication and provider conditional-write qualification."""

import os
import uuid

import pytest
from dockflow_core.canonical import digest
from dockflow_core.errors import DockflowError
from dockflow_pipelines.artifacts import ArtifactStore
from dockflow_pipelines.cache_registry import Registry
from dockflow_pipelines.cache_storage import make_manifest
from dockflow_pipelines.metadata import ControlStore
from dockflow_pipelines.records import new_id

pytestmark = [
    pytest.mark.s3,
    pytest.mark.skipif(
        not os.environ.get("DOCKFLOW_TEST_CACHE_S3_ENDPOINT"),
        reason="Set DOCKFLOW_TEST_CACHE_S3_ENDPOINT for a disposable S3 service",
    ),
]


def test_real_s3_conditional_cache_publication_verification_and_corruption(
    tmp_path, monkeypatch
):
    import boto3

    endpoint = os.environ["DOCKFLOW_TEST_CACHE_S3_ENDPOINT"]
    client = boto3.client("s3", endpoint_url=endpoint)
    bucket = "dockflow-cache-test-" + uuid.uuid4().hex
    client.create_bucket(Bucket=bucket)
    try:
        control = ControlStore(tmp_path / "producer", "dockflow-cache-s3")
        options = {
            "backend": "s3",
            "endpoint": endpoint,
            "bucket": bucket,
            "prefix": "dockflow",
            "allow_insecure_http": True,
        }
        artifacts = ArtifactStore(control, options)
        artifacts._client = client
        token = artifacts.storage_identity()
        assert artifacts.storage_identity() == token
        registry = Registry(
            {
                "database": control.database.options,
                "storage_identity": "dockflow-cache-s3",
                "storage_token": token,
            },
            "dockflow-cache-s3",
        )
        registry.initialize()
        with control.owner():
            control.initialize()
            run_id, task_id = new_id("run"), new_id("task")
            ownership = registry.resolve_or_claim(
                digest("s3-key"), "owner", str(uuid.uuid4()), run_id, task_id
            ).ownership
            registry.begin_validation(ownership)
            source = tmp_path / "source"
            source.mkdir()
            (source / "file.txt").write_text("dockflow shared bytes")
            (source / "empty").mkdir()
            producer = {
                "pipeline_name": "dockflow-cache-s3",
                "task_name": "produce",
                "run_id": run_id,
                "task_id": task_id,
                "attempt_id": ownership.attempt_id,
                "definition_id": new_id("definition"),
                "output_name": "dataset",
                "cache_namespace": "cache-v1",
            }
            typ = {"schema_title": "system.Dataset", "schema_version": "0.0.1"}
            # Both bytes and descriptor PUTs commit, then lose their responses.
            # Finalization retries must recover the same immutable publication.
            original_put = client.put_object
            lost = {"/file.txt": False}

            def ambiguous_put(**values):
                result = original_put(**values)
                for suffix in lost:
                    if values["Key"].endswith(suffix) and not lost[suffix]:
                        lost[suffix] = True
                        raise TimeoutError("injected lost storage acknowledgment")
                return result

            monkeypatch.setattr(client, "put_object", ambiguous_put)
            output = artifacts.publish(source, typ, producer)
            assert all(lost.values())
            contract = {
                "artifacts": {
                    "dataset": {
                        "artifactType": {
                            "schemaTitle": "system.Dataset",
                            "schemaVersion": "0.0.1",
                        }
                    }
                }
            }
            manifest = make_manifest(
                {"dataset": output},
                {},
                contract,
                {
                    field: producer[field]
                    for field in ("run_id", "task_id", "attempt_id")
                },
                ownership.cache_key,
                registry.options["storage_identity"],
            )
            artifacts.verify_cache(manifest, registry.options["storage_identity"])
            published = registry.publish(ownership, manifest)
            # Distinct process-local state needs only common provider access.
            consumer = ArtifactStore(
                ControlStore(tmp_path / "consumer", "dockflow-cache-s3"), options
            )
            consumer.verify_cache(
                published["manifest"], registry.options["storage_identity"]
            )
            assert consumer.storage_identity(create=False) == token
            key = artifacts.object_key(output["managed_path"] + "/file.txt")
            with pytest.raises(client.exceptions.ClientError) as conflict:
                client.put_object(
                    Bucket=bucket, Key=key, Body=b"replacement", IfNoneMatch="*"
                )
            assert conflict.value.response["ResponseMetadata"]["HTTPStatusCode"] == 412
            with pytest.raises(DockflowError):
                artifacts.publish(source, typ, producer)
            # An external corruption report invalidates exactly this output set.
            client.put_object(Bucket=bucket, Key=key, Body=b"corrupt")
            with pytest.raises(DockflowError) as error:
                consumer.verify_cache(manifest, registry.options["storage_identity"])
            assert error.value.code == "CACHE_CORRUPT"
            registry.invalidate(
                ownership.cache_key, published["artifact_id"], "CONFIRMED_CORRUPTION"
            )
    finally:
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
            keys = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if keys:
                client.delete_objects(Bucket=bucket, Delete={"Objects": keys})
        client.delete_bucket(Bucket=bucket)


def test_backup_restores_cache_only_publication_and_store_identity(
    database_state, tmp_path, monkeypatch
):
    import json
    import subprocess
    import sys
    from pathlib import Path

    import boto3

    control, _ = database_state
    endpoint = os.environ["DOCKFLOW_TEST_CACHE_S3_ENDPOINT"]
    client = boto3.client("s3", endpoint_url=endpoint)
    bucket = "dockflow-unified-backup-" + uuid.uuid4().hex
    client.create_bucket(Bucket=bucket)
    options = {
        "backend": "s3",
        "endpoint": endpoint,
        "bucket": bucket,
        "prefix": "dockflow",
        "allow_insecure_http": True,
    }
    artifacts = ArtifactStore(control, options)
    artifacts._client = client
    try:
        with control.owner():
            control.initialize()
            token = artifacts.storage_identity()
            cache_options = {
                "database": control.database.options,
                "storage_identity": "dockflow-backup",
                "storage_token": token,
            }
            registry = Registry(cache_options, control.project_id)
            registry.initialize()
            run_id, task_id = new_id("run"), new_id("task")
            ownership = registry.resolve_or_claim(
                digest("backup-key"), "owner", str(uuid.uuid4()), run_id, task_id
            ).ownership
            producer = {
                "pipeline_name": "dockflow-backup",
                "task_name": "produce",
                "run_id": run_id,
                "task_id": task_id,
                "attempt_id": ownership.attempt_id,
                "definition_id": new_id("definition"),
                "output_name": "dataset",
                "cache_namespace": "cache-v1",
            }
            source = tmp_path / "payload"
            source.write_bytes(b"cache-only result")
            captured = {}

            def fail_journal(collection, descriptor):
                captured.update(descriptor)
                raise DockflowError("Injected journal failure")

            with monkeypatch.context() as patch:
                patch.setattr(control, "put", fail_journal)
                with pytest.raises(DockflowError, match="Injected"):
                    artifacts.publish(
                        source,
                        {"schema_title": "system.Dataset", "schema_version": "0.0.1"},
                        producer,
                    )
            assert artifacts.list() == []
            contract = {
                "artifacts": {
                    "dataset": {
                        "artifactType": {
                            "schemaTitle": "system.Dataset",
                            "schemaVersion": "0.0.1",
                        }
                    }
                }
            }
            manifest = make_manifest(
                {"dataset": captured},
                {},
                contract,
                {key: producer[key] for key in ("run_id", "task_id", "attempt_id")},
                ownership.cache_key,
                "dockflow-backup",
            )
            registry.begin_validation(ownership)
            registry.publish(ownership, manifest)
            destination = tmp_path / "backup"
            control.backup(destination, artifacts)
            assert (
                destination / "managed" / captured["managed_path"]
            ).read_bytes() == b"cache-only result"
            assert (
                json.loads(
                    (destination / "managed/.dockflow/storage.json").read_bytes()
                )["identity"]
                == token
            )
        # Restore to the same byte location and a fresh database/staging root.
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
            client.delete_objects(
                Bucket=bucket,
                Delete={
                    "Objects": [
                        {"Key": item["Key"]} for item in page.get("Contents", [])
                    ]
                },
            )
        configuration = tmp_path / "restore.toml"
        configuration.write_text(
            f'schema_version=1\n[project]\nid="{control.project_id}"\n[state]\ndirectory="restored"\n[artifacts]\n'
            + "\n".join(f"{key}={json.dumps(value)}" for key, value in options.items())
        )
        script = Path(__file__).resolve().parents[4] / "tools/backup.py"
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "restore",
                "--config",
                str(configuration),
                "--apply",
                str(destination),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["restored"]
        restored = ControlStore(tmp_path / "restored", control.project_id)
        reopened = Registry(
            {**cache_options, "database": restored.database.options},
            restored.project_id,
        )
        assert (
            reopened.inspect(ownership.cache_key)["artifacts"][0]["manifest"]
            == manifest
        )
        restored_artifacts = ArtifactStore(restored, options)
        assert restored_artifacts.storage_identity(create=False) == token
        assert restored_artifacts.verify_cache(manifest, "dockflow-backup")
    finally:
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
            keys = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if keys:
                client.delete_objects(Bucket=bucket, Delete={"Objects": keys})
        client.delete_bucket(Bucket=bucket)
