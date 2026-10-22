"""Exercise adapter transfer/inventory semantics against a controlled S3 boundary."""

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from dockflow_pipelines.artifacts import ArtifactStore
from dockflow_pipelines.errors import DockflowError
from dockflow_pipelines.metadata import ControlStore

DATASET = {"schema_title": "system.Dataset", "schema_version": "0.0.1"}


class MissingObject(Exception):
    response = {"Error": {"Code": "NoSuchKey"}}


class MemoryS3:
    exceptions = SimpleNamespace(ClientError=MissingObject)

    def __init__(self):
        self.objects = {}

    def head_object(self, Bucket, Key):
        try:
            value = self.objects[(Bucket, Key)]
        except KeyError as exc:
            raise MissingObject() from exc
        return {"ContentLength": len(value), "ETag": hashlib.md5(value).hexdigest()}

    def download_file(self, bucket, key, filename, ExtraArgs=None):
        try:
            value = self.objects[(bucket, key)]
        except KeyError as exc:
            raise MissingObject() from exc
        Path(filename).write_bytes(value)

    def upload_file(self, filename, bucket, key):
        self.objects[(bucket, key)] = Path(filename).read_bytes()

    def put_object(self, Bucket, Key, Body, ContentType=None):
        self.objects[(Bucket, Key)] = Body

    def list_objects_v2(self, Bucket, Prefix, MaxKeys=None):
        values = [
            {"Key": key, "Size": len(value), "ETag": hashlib.md5(value).hexdigest()}
            for (bucket, key), value in self.objects.items()
            if bucket == Bucket and key.startswith(Prefix)
        ]
        if MaxKeys:
            values = values[:MaxKeys]
        return {"KeyCount": len(values), "Contents": values}

    def get_paginator(self, operation):
        return SimpleNamespace(
            paginate=lambda **kwargs: [self.list_objects_v2(**kwargs)]
        )


def setup_store(tmp_path):
    control = ControlStore(tmp_path / "state", "s3-test-project")
    store = ArtifactStore(
        control,
        {
            "backend": "s3",
            "bucket": "managed",
            "prefix": "project",
            "endpoint": "http://test.invalid",
            "allow_insecure_http": True,
            "external_roots": [tmp_path / "inputs"],
            "allowed_uri_prefixes": ["s3://external/datasets"],
        },
    )
    store._client = MemoryS3()
    return control, store


def test_s3_import_fingerprints_and_detects_lost_or_corrupt_objects(tmp_path):
    control, store = setup_store(tmp_path)
    store._client.objects[("external", "datasets/data.csv")] = b"data,labels\n1,0\n"
    with control.owner():
        control.initialize(require_mlmd=False)
        descriptor = store.register(
            "s3://external/datasets/data.csv", DATASET, managed=True
        )
        assert descriptor["origin"] == "external"
        assert descriptor["ownership"] == "managed"
        assert descriptor["source_provider_version"]["etag"]
        target = tmp_path / "work" / "data.csv"
        store.materialize(descriptor["artifact_id"], target)
        assert target.read_bytes() == b"data,labels\n1,0\n"
        key = (
            f"project/.dockflow/dockflow-pipelines/{descriptor['artifact_id']}/payload"
        )
        store._client.objects[("managed", key)] = b"changed"
        assert store.verify(descriptor["artifact_id"])["availability"] == "corrupt"
        del store._client.objects[("managed", key)]
        assert store.verify(descriptor["artifact_id"])["availability"] == "missing"


def test_s3_prefix_snapshots_and_segment_allowlist(tmp_path):
    control, store = setup_store(tmp_path)
    store._client.objects[("external", "datasets/partition/a.csv")] = b"a"
    store._client.objects[("external", "datasets/partition/sub/b.csv")] = b"b"
    with control.owner():
        control.initialize(require_mlmd=False)
        descriptor = store.register("s3://external/datasets/partition/", DATASET)
        store._client.objects[("external", "datasets/partition/later.csv")] = b"later"
        target = tmp_path / "selected"
        store.materialize(descriptor["artifact_id"], target)
        assert sorted(
            path.relative_to(target).as_posix() for path in target.rglob("*.csv")
        ) == ["a.csv", "sub/b.csv"]
        with pytest.raises(DockflowError, match="outside"):
            store.register("s3://external/datasets-evil/data.csv", DATASET)
        with pytest.raises(DockflowError, match="Empty S3 prefix"):
            store.register("s3://external/datasets/empty/", DATASET)


def test_s3_managed_directory_retains_empty_subdirectories(tmp_path):
    control, store = setup_store(tmp_path)
    source = tmp_path / "inputs" / "tree"
    (source / "empty").mkdir(parents=True)
    (source / "file").write_text("payload")
    with control.owner():
        control.initialize(require_mlmd=False)
        descriptor = store.register(source.as_uri(), DATASET, managed=True)
        target = tmp_path / "materialized"
        store.materialize(descriptor["artifact_id"], target)
        assert (target / "empty").is_dir()
        assert (target / "file").read_text() == "payload"


def test_recognized_s3_empty_root_is_a_directory_snapshot(tmp_path):
    control, store = setup_store(tmp_path)
    source = tmp_path / "inputs" / "empty"
    source.mkdir(parents=True)
    with control.owner():
        control.initialize(require_mlmd=False)
        original = store.register(source.as_uri(), DATASET, managed=True)
        second = store.register(original["content_uri"], DATASET)
        assert second["payload_kind"] == "directory"
        assert second["inventory"] == []
        assert second["fingerprint"] == original["fingerprint"]
