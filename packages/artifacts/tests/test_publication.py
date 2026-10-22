"""Public publication behavior against filesystem and conditional object storage."""

import io
import json
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
from dockflow_artifacts import (
    ArtifactError,
    ConflictError,
    IntegrityError,
    Publisher,
    format_path,
    publication_id,
    step_path,
)


class ObjectError(Exception):
    def __init__(self, code):
        self.response = {"Error": {"Code": code}}


class MemoryS3:
    """Conditional object-store test double; live SeaweedFS is qualified separately."""

    def __init__(self):
        self.objects = {}
        self.lock = threading.Lock()

    def put_object(self, *, Bucket, Key, Body, ContentLength, IfNoneMatch):
        assert IfNoneMatch == "*"
        data = Body.read()
        assert len(data) == ContentLength
        with self.lock:
            if (Bucket, Key) in self.objects:
                raise ObjectError("PreconditionFailed")
            self.objects[Bucket, Key] = data

    def get_object(self, *, Bucket, Key):
        with self.lock:
            if (Bucket, Key) not in self.objects:
                raise ObjectError("NoSuchKey")
            return {"Body": io.BytesIO(self.objects[Bucket, Key])}

    def get_paginator(self, operation):
        assert operation == "list_objects_v2"
        return self

    def paginate(self, *, Bucket, Prefix):
        with self.lock:
            return [
                {
                    "Contents": [
                        {"Key": key}
                        for bucket, key in self.objects
                        if bucket == Bucket and key.startswith(Prefix)
                    ]
                }
            ]


@pytest.fixture(params=["filesystem", "s3"])
def publisher(request, tmp_path, monkeypatch):
    if request.param == "filesystem":
        return Publisher(tmp_path / "published")
    import boto3

    client = MemoryS3()
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: client)
    return Publisher("s3://artifacts/custom")


def test_file_receipt_and_identical_retry(publisher, tmp_path):
    source = tmp_path / "source.json"
    source.write_text('{"model":1}')
    first = publisher.publish(
        source,
        "models/version-1/model.json",
        artifact_type="system.Model",
        metadata={"rows": 50},
    )
    assert first.uri.endswith("/models/version-1/model.json")
    assert "/.dockflow/dockflow-artifacts/manifests/" in first.manifest_uri
    assert first.kind == "file"
    assert first.artifact_type == "system.Model"
    assert first.metadata == {"rows": 50}
    assert first == publisher.verify("models/version-1/model.json")
    assert first == publisher.publish(
        source,
        "models/version-1/model.json",
        artifact_type="system.Model",
        metadata={"rows": 50},
    )
    json.dumps(first.to_dict())


@pytest.mark.parametrize("from_config", [False, True])
def test_s3_construction_defers_client_and_credential_discovery(
    tmp_path, monkeypatch, from_config
):
    import boto3

    client_factory = Mock(return_value=MemoryS3())
    monkeypatch.setattr(boto3, "client", client_factory)
    config = tmp_path / "publication.json"
    config.write_text(
        json.dumps({"schema_version": 1, "root": "s3://artifacts/custom"})
    )
    publisher = (
        Publisher.from_config(config)
        if from_config
        else Publisher("s3://artifacts/custom")
    )
    client_factory.assert_not_called()
    source = tmp_path / "model.json"
    source.write_text('{"model":1}')
    receipt = publisher.publish(source, "model.json")
    assert publisher.verify("model.json") == receipt
    client_factory.assert_called_once()


def test_missing_s3_extra_is_reported_at_first_storage_operation(monkeypatch):
    monkeypatch.setitem(sys.modules, "boto3", None)
    publisher = Publisher("s3://artifacts/custom")
    with pytest.raises(ArtifactError, match=r"Install dockflow-artifacts\[s3\]"):
        publisher.verify("model.json")


def test_directory_preserves_names_and_empty_files(publisher, tmp_path):
    source = tmp_path / "tree"
    (source / "nested").mkdir(parents=True)
    (source / "model.json").write_text("model")
    (source / "nested/weights.bin").write_bytes(b"")
    receipt = publisher.publish(source, "models/v1")
    assert receipt.kind == "directory"
    assert publisher.verify("models/v1") == receipt


@pytest.mark.parametrize("change", ["bytes", "metadata", "type"])
def test_conflicting_publication_does_not_replace(publisher, tmp_path, change):
    source = tmp_path / "model"
    source.write_text("original")
    first = publisher.publish(source, "models/v1")
    options = {}
    if change == "bytes":
        source.write_text("different")
    elif change == "type":
        options["artifact_type"] = "system.Model"
    else:
        options["metadata"] = {"other": True}
    with pytest.raises(ConflictError):
        publisher.publish(source, "models/v1", **options)
    assert publisher.verify("models/v1") == first


@pytest.mark.parametrize("first,second", [("a", "a/b"), ("a/b", "a")])
def test_overlapping_publications_are_rejected(publisher, tmp_path, first, second):
    source = tmp_path / "model"
    source.write_text("contents")
    receipt = publisher.publish(source, first)
    with pytest.raises(ConflictError):
        publisher.publish(source, second)
    assert publisher.verify(first) == receipt


def test_interrupted_upload_resumes_identical_contents(
    publisher, tmp_path, monkeypatch
):
    source = tmp_path / "source"
    source.mkdir()
    (source / "one.txt").write_text("one")
    (source / "two.txt").write_text("two")
    put = publisher._store.put

    def interrupt(key, body):
        if key.endswith("/two.txt"):
            raise OSError("simulated interrupted upload")
        return put(key, body)

    monkeypatch.setattr(publisher._store, "put", interrupt)
    with pytest.raises(OSError):
        publisher.publish(source, "model/v1")
    with pytest.raises(IntegrityError, match="completion"):
        publisher.verify("model/v1")
    monkeypatch.setattr(publisher._store, "put", put)
    result = publisher.publish(source, "model/v1")
    assert publisher.verify("model/v1") == result


def test_concurrent_identical_directory_writers_converge(publisher, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "one").write_bytes(b"x" * 2000)
    (source / "two").write_bytes(b"y" * 2000)
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(
            pool.map(lambda _: publisher.publish(source, "models/v1"), range(8))
        )
    assert all(receipt == receipts[0] for receipt in receipts)
    assert publisher.verify("models/v1") == receipts[0]


def test_source_mutation_cannot_complete(publisher, tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.write_text("original")
    put = publisher._store.put

    def mutate(key, body):
        result = put(key, body)
        if key == "model":
            source.write_text("changed")
        return result

    monkeypatch.setattr(publisher._store, "put", mutate)
    with pytest.raises(IntegrityError, match="Source changed"):
        publisher.publish(source, "model")
    with pytest.raises(IntegrityError, match="completion"):
        publisher.verify("model")


def test_completed_content_mutation_is_not_repaired(tmp_path):
    source = tmp_path / "source"
    source.write_text("original")
    publisher = Publisher(tmp_path / "published")
    publisher.publish(source, "model")
    target = tmp_path / "published/model"
    target.write_text("corrupt")
    with pytest.raises(IntegrityError):
        publisher.publish(source, "model")
    assert target.read_text() == "corrupt"
    target.unlink()
    with pytest.raises(IntegrityError):
        publisher.verify("model")


def test_untracked_directory_addition_is_detected(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "model").write_text("contents")
    publisher = Publisher(tmp_path / "published")
    publisher.publish(source, "bundle")
    (tmp_path / "published/bundle/extra").write_text("unexpected")
    with pytest.raises(IntegrityError):
        publisher.verify("bundle")


@pytest.mark.parametrize(
    "destination",
    [
        "/absolute",
        "../escape",
        "a/../b",
        "a//b",
        ".",
        "a\\b",
        "a%2fb",
        "a?b",
        "a#b",
        ".dockflow-artifacts/model",
        ".dockflow/dockflow-artifacts/model",
        ".dockflow/dockflow-pipelines/model",
        "nested/.dockflow/model",
        "x/.",
    ],
)
def test_unsafe_destinations_are_rejected(tmp_path, destination):
    source = tmp_path / "source"
    source.write_text("data")
    with pytest.raises(ArtifactError):
        Publisher(tmp_path / "published").publish(source, destination)
    assert not (tmp_path / "published").exists()


@pytest.mark.parametrize("kind", ["source", "destination", "parent"])
def test_symlinks_are_rejected(tmp_path, kind):
    source = tmp_path / "source"
    source.write_text("data")
    root = tmp_path / "published"
    root.mkdir()
    if kind == "source":
        alias = tmp_path / "alias"
        alias.symlink_to(source)
        source = alias
    elif kind == "destination":
        (root / "model").symlink_to(tmp_path / "not-created")
    else:
        other = tmp_path / "other"
        other.mkdir()
        root.rmdir()
        root.symlink_to(other)
    with pytest.raises(ArtifactError):
        Publisher(root).publish(source, "model")


def test_overlap_empty_directory_and_nonfinite_metadata(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(ArtifactError):
        Publisher(source).publish(source, "nested")
    with pytest.raises(ArtifactError, match="Empty"):
        Publisher(tmp_path / "published").publish(source, "model")
    model = source / "model"
    model.write_text("data")
    with pytest.raises(ArtifactError, match="finite"):
        Publisher(tmp_path / "published").publish(
            model, "model", metadata={"x": float("nan")}
        )


def test_explicit_config_and_template(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"schema_version": 1, "root": str(tmp_path / "published")})
    )
    publisher = Publisher.from_config(path)
    assert not (tmp_path / "published").exists()
    source = tmp_path / "source"
    source.write_text("data")
    key = format_path(
        "models/{date}/{version}/model.json", date="2026-10-20", version=1
    )
    assert publisher.publish(source, key).uri.endswith(key)
    for template, values in [
        ("{x}", {}),
        ("{x.attr}", {"x": "a"}),
        ("{x}", {"x": "../a"}),
    ]:
        with pytest.raises(ArtifactError):
            format_path(template, **values)


def test_import_has_no_optional_dependency_side_effects():
    subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            """
import sys
import dockflow_artifacts
dockflow_artifacts.Publisher('s3://example-artifacts/published')
assert 'boto3' not in sys.modules
assert 'kfp' not in sys.modules
assert 'dockflow_pipelines' not in sys.modules
""",
        ],
        check=True,
    )


def test_step_paths_publish_and_isolate_explorations(publisher, tmp_path):
    source = tmp_path / "model.json"
    source.write_text("original")
    destination = step_path(
        "model.json",
        step_number=3,
        step_digits=1,
        component_name="train",
        pipeline_name="training",
        publication_id="a" * 64,
    )
    assert destination == f"global/training/step_3__train__{'a' * 64}/model.json"
    first = publisher.publish(source, destination, artifact_type="system.Model")
    assert first == publisher.publish(source, destination, artifact_type="system.Model")
    source.write_text("changed")
    with pytest.raises(ConflictError):
        publisher.publish(source, destination, artifact_type="system.Model")
    other = step_path(
        "model.json",
        step_number=3,
        component_name="train",
        exploration_id="experiment-2",
        step_digits=1,
        pipeline_name="training",
        publication_id="a" * 64,
    )
    second = publisher.publish(source, other, artifact_type="system.Model")
    assert first.uri != second.uri
    assert publisher.verify(destination) == first


@pytest.mark.parametrize("number", [0, -1, 1.5, "1", True, None])
def test_step_paths_reject_invalid_numbers(number):
    with pytest.raises(ArtifactError, match="positive integer"):
        step_path(
            "model.json",
            step_number=number,
            step_digits=1,
            component_name="train",
            pipeline_name="training",
            publication_id="a" * 64,
        )


@pytest.mark.parametrize(
    "field", ["filename", "component_name", "exploration_id", "pipeline_name"]
)
@pytest.mark.parametrize(
    "value", ["", "../other", "a/b", ".dockflow", ".dockflow-artifacts", 7]
)
def test_step_paths_reject_unsafe_names(field, value):
    options = dict(
        filename="model.json",
        step_number=1,
        component_name="train",
        exploration_id="global",
        step_digits=1,
        pipeline_name="training",
        publication_id="a" * 64,
    )
    options[field] = value
    with pytest.raises(ArtifactError):
        step_path(**options)


def test_legacy_publication_records_require_explicit_reset(publisher, tmp_path):
    publisher._store.put(".dockflow-artifacts/claims/existing.json", io.BytesIO(b"{}"))
    source = tmp_path / "source"
    source.write_text("data")
    with pytest.raises(ArtifactError, match="Legacy"):
        publisher.publish(source, "model.json")
    with pytest.raises(ArtifactError, match="Legacy"):
        publisher.verify("model.json")
    assert publisher._store.get("model.json") is None


def test_control_namespace_cannot_be_redirected_by_symlink(tmp_path):
    root = tmp_path / "published"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / ".dockflow").symlink_to(outside, target_is_directory=True)
    source = tmp_path / "source"
    source.write_text("data")
    with pytest.raises(ArtifactError, match="symlinks"):
        Publisher(root).publish(source, "model.json")
    assert not list(outside.iterdir())


def test_parameter_changes_publish_separately_without_overwrite(publisher, tmp_path):
    source = tmp_path / "model.json"
    paths = []
    for seed in (42, 43, 42):
        identity = publication_id(
            component_name="train", component_version="v1", parameters={"seed": seed}
        )
        path = step_path(
            "model.json",
            step_number=2,
            step_digits=2,
            component_name="train",
            pipeline_name="training",
            publication_id=identity,
        )
        source.write_text(str(seed))
        publisher.publish(source, path)
        paths.append(path)
    assert paths[0] == paths[2] != paths[1]
    assert all(path.startswith("global/training/step_02__train__") for path in paths)
    source.write_text("nondeterministic")
    with pytest.raises(ConflictError):
        publisher.publish(source, paths[0])
