"""The native KFP hierarchy must survive publication, reuse and recovery."""

import importlib.util
import shutil
from pathlib import Path

import pytest
from dockflow_database.errors import DockflowError
from dockflow_pipelines.artifacts import ArtifactStore
from dockflow_pipelines.metadata import ControlStore
from dockflow_pipelines.records import new_id
from test_s3_artifacts import MemoryS3

DATASET = {"schema_title": "system.Dataset", "schema_version": "0.0.1"}
METRICS = {"schema_title": "system.Metrics", "schema_version": "0.0.1"}


@pytest.fixture(params=["filesystem", "s3"])
def storage(tmp_path, request, monkeypatch):
    options = {
        "backend": request.param,
        "external_roots": [tmp_path / "inputs"],
    }
    client = MemoryS3()
    if request.param == "s3":
        options.update(
            bucket="artifacts",
            prefix="project",
            endpoint="http://test.invalid",
            allow_insecure_http=True,
        )
        monkeypatch.setattr(ArtifactStore, "_s3", lambda self: client)
    else:
        options["managed_root"] = tmp_path / "artifacts"
    control = ControlStore(tmp_path / "state", "layout-test")
    artifacts = ArtifactStore(control, options)
    with control.owner():
        control.initialize()
    return control, artifacts, client


def producer(control, output="dataset", **changes):
    record = {
        "pipeline_name": "sample-training",
        "run_id": new_id("run"),
        "task_name": "prepare",
        "task_id": new_id("task"),
        "attempt_id": new_id("attempt"),
        "definition_id": new_id("definition"),
        "output_name": output,
        **changes,
    }
    control.put("runs", {"run_id": record["run_id"], "state": "succeeded"})
    return record


def commit(control, record, outputs):
    bindings = {name: value["artifact_id"] for name, value in outputs.items()}
    control.put(
        "tasks",
        {
            "task_id": record["task_id"],
            "run_id": record["run_id"],
            "state": "succeeded",
            "outputs": bindings,
            "attempt_ids": [record["attempt_id"]],
        },
    )
    control.put(
        "attempts",
        {
            "attempt_id": record["attempt_id"],
            "task_id": record["task_id"],
            "run_id": record["run_id"],
            "state": "succeeded",
            "publication_state": "committed",
            "outputs": bindings,
        },
    )
    control.commit_output_set(
        record["run_id"], record["task_id"], record["attempt_id"], outputs, {}
    )


def read_recovery(artifacts, client, descriptor):
    return artifacts.recovery_descriptor(descriptor["artifact_id"])


@pytest.mark.parametrize("kind", ["file", "directory", "metadata"])
def test_named_output_payload_and_separate_recovery_descriptor(tmp_path, storage, kind):
    control, artifacts, client = storage
    source = tmp_path / "component-output"
    if kind == "file":
        source.write_bytes(b"data")
    elif kind == "directory":
        (source / "empty").mkdir(parents=True)
        (source / "dataset.json").write_bytes(b"data")
        # User filenames must never collide with Dockflow recovery metadata.
        (source / "artifact.json").write_text("user-owned")
    else:
        source = None
    with control.owner():
        record = producer(control)
        descriptor = artifacts.publish(
            source, METRICS if source is None else DATASET, record, {"rows": 3}
        )
        relative = (
            f"sample-training/{record['run_id']}/prepare/"
            f"{record['attempt_id'].removeprefix('attempt_')}/dataset"
        )
        assert descriptor["managed_path"] == relative
        expected = (
            (artifacts.managed_root / relative).as_uri()
            if artifacts.backend == "filesystem"
            else f"s3://artifacts/project/{relative}"
        )
        assert descriptor["content_uri"] == (None if source is None else expected)
        assert read_recovery(artifacts, client, descriptor) == descriptor
        assert descriptor["artifact_id"] not in relative
        commit(control, record, {"dataset": descriptor})
        destination = tmp_path / "consumer"
        artifacts.materialize(descriptor["artifact_id"], destination)
        if kind == "file":
            assert destination.read_bytes() == b"data"
        elif kind == "directory":
            assert (destination / "dataset.json").read_bytes() == b"data"
            assert (destination / "artifact.json").read_text() == "user-owned"
            assert (destination / "empty").is_dir()
        else:
            assert not destination.exists()
        assert artifacts.verify(descriptor["artifact_id"])["verified"]


def test_outputs_share_attempt_salt_and_retry_never_overwrites(tmp_path, storage):
    control, artifacts, _ = storage
    source = tmp_path / "source"
    source.write_text("first")
    with control.owner():
        record = producer(control)
        first = artifacts.publish(source, DATASET, record)
        sibling = artifacts.publish(
            source, DATASET, {**record, "output_name": "validation"}
        )
        assert (
            first["managed_path"].rsplit("/", 1)[0]
            == sibling["managed_path"].rsplit("/", 1)[0]
        )
        commit(control, record, {"dataset": first, "validation": sibling})
        source.write_text("retry")
        with pytest.raises(DockflowError, match="reserved|already exists"):
            artifacts.publish(source, DATASET, record)
        retry_record = {**record, "attempt_id": new_id("attempt")}
        retry = artifacts.publish(source, DATASET, retry_record)
        commit(control, retry_record, {"dataset": retry})
        assert retry["content_uri"] != first["content_uri"]
        artifacts.materialize(first["artifact_id"], tmp_path / "original")
        assert (tmp_path / "original").read_text() == "first"
        # Reimporting/reusing the stored URI never changes the original contents.
        imported = artifacts.register(first["content_uri"], DATASET)
        assert imported["content_uri"] == first["content_uri"]
        assert artifacts.get(first["artifact_id"])["producer"] == record


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("pipeline_name", "../escape"),
        ("pipeline_name", ".dockflow"),
        ("pipeline_name", "%2e%2e"),
        ("task_name", "nested/escape"),
        ("output_name", "../model"),
        ("output_name", "model\\escape"),
        ("run_id", "/absolute"),
    ],
)
def test_unsafe_publication_names_fail_before_storage(tmp_path, storage, field, bad):
    control, artifacts, client = storage
    source = tmp_path / "source"
    source.write_text("safe")
    with control.owner():
        record = producer(control)
        record[field] = bad
        with pytest.raises(DockflowError, match="Unsafe"):
            artifacts.publish(source, DATASET, record)
    assert not artifacts.managed_root.exists()
    assert not client.objects


def test_new_layout_backup_restore_retains_uris_and_payloads(tmp_path, storage):
    control, artifacts, client = storage
    source = tmp_path / "input"
    source.mkdir()
    (source / "dataset.json").write_text("retained")
    (source / "empty").mkdir()
    with control.owner():
        record = producer(control)
        descriptor = artifacts.publish(source, DATASET, record)
        commit(control, record, {"dataset": descriptor})
        result = control.backup(tmp_path / "backup", artifacts)
        assert ControlStore.verify_backup(tmp_path / "backup")["valid"]
    # Use the actual restore implementation with an isolated provider boundary.
    config = tmp_path / "dockflow.toml"
    text = (
        'schema_version=1\n[project]\nid="layout-test"\n'
        '[state]\ndirectory="state"\n[artifacts]\n'
    )
    if artifacts.backend == "filesystem":
        text += 'backend="filesystem"\nmanaged_root="artifacts"\n'
    else:
        text += (
            'backend="s3"\nbucket="artifacts"\nprefix="project"\n'
            'endpoint="http://test.invalid"\nallow_insecure_http=true\n'
        )
    config.write_text(text)
    script = Path(__file__).resolve().parents[4] / "tools/backup.py"
    spec = importlib.util.spec_from_file_location("layout_backup", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    shutil.rmtree(control.state)
    # A nonempty destination must be refused before copying control records.
    with pytest.raises(DockflowError, match="must be empty"):
        module.restore(tmp_path / "backup", config, True)
    if artifacts.backend == "filesystem":
        shutil.rmtree(artifacts.managed_root)
    else:
        client.objects.clear()
    restored = module.restore(tmp_path / "backup", config, True)
    assert restored["restored"] and restored["check"]["valid"]
    reopened = ControlStore(control.state, "layout-test")
    actual = reopened.get("artifacts", descriptor["artifact_id"])
    assert actual["content_uri"] == descriptor["content_uri"]
    assert result["external_references_included"] is False
    assert ArtifactStore(reopened, artifacts.options).verify(actual)["verified"]


@pytest.mark.parametrize("layout", [None, "kfp-v1"])
def test_unsupported_descriptor_layouts_fail_without_relocation(
    tmp_path, storage, layout
):
    control, artifacts, _ = storage
    source = tmp_path / "source"
    source.write_text("current payload")
    with control.owner():
        descriptor = artifacts.publish(source, DATASET, producer(control))
        original = artifacts.managed_content_path(descriptor)
        descriptor["storage_layout"] = layout
        with pytest.raises(
            DockflowError, match="Unsupported managed artifact storage layout"
        ):
            artifacts.managed_content_path(descriptor)
        if artifacts.backend == "filesystem":
            assert (artifacts.managed_root / original).read_text() == "current payload"


def test_filesystem_publication_refuses_dangling_output_symlink(tmp_path):
    control = ControlStore(tmp_path / "state", "layout-test")
    artifacts = ArtifactStore(control, {"managed_root": tmp_path / "artifacts"})
    source = tmp_path / "source"
    source.write_text("safe")
    with control.owner():
        control.initialize()
        record = producer(control)
        output = (
            artifacts.managed_root
            / "sample-training"
            / record["run_id"]
            / "prepare"
            / record["attempt_id"].removeprefix("attempt_")
            / "dataset"
        )
        output.parent.mkdir(parents=True)
        target = tmp_path / "outside"
        output.symlink_to(target)
        with pytest.raises(DockflowError, match="symlinks"):
            artifacts.publish(source, DATASET, record)
        assert output.is_symlink() and not target.exists()
        assert not artifacts.list()
