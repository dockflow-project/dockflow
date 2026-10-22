import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from dockflow_pipelines.artifacts import ArtifactStore, inventory
from dockflow_pipelines.canonical import digest
from dockflow_pipelines.errors import DockflowError
from dockflow_pipelines.metadata import ControlStore, new_id

DATASET = {"schema_title": "system.Dataset", "schema_version": "0.0.1"}


def stores(tmp_path, runtime=False, storage_field="root"):
    source = tmp_path / "inputs"
    source.mkdir()
    store = ControlStore(tmp_path / "state", "test-project")
    artifacts = ArtifactStore(
        store,
        {
            "backend": "filesystem",
            storage_field: tmp_path / "artifacts",
            "external_roots": [source],
        },
    )
    return source, store, artifacts


@pytest.mark.parametrize("storage_field", ["root", "managed_root"])
def test_directory_fingerprint_and_isolated_managed_import(tmp_path, storage_field):
    source, store, artifacts = stores(tmp_path, storage_field=storage_field)
    tree = source / "tree"
    (tree / "empty").mkdir(parents=True)
    (tree / "nested").mkdir()
    (tree / "nested/file.txt").write_bytes(b"dataset")
    expected = [
        {"path": "empty", "kind": "directory"},
        {
            "path": "nested/file.txt",
            "kind": "file",
            "size_bytes": 7,
            "sha256": hashlib.sha256(b"dataset").hexdigest(),
        },
    ]
    assert inventory(tree)["fingerprint"]["value"] == digest(
        {"kind": "directory", "entries": expected}
    )
    with store.owner():
        store.initialize(require_mlmd=False)
        descriptor = artifacts.register(tree.as_uri(), DATASET, managed=True)
        parent = tmp_path / "artifacts"
        if storage_field == "root":
            parent /= "managed"
        assert (
            descriptor["content_uri"]
            == (
                parent
                / ".dockflow/dockflow-pipelines"
                / descriptor["artifact_id"]
                / "payload"
            ).as_uri()
        )
        destination = tmp_path / "execution" / "data"
        artifacts.materialize(descriptor["artifact_id"], destination)
        (destination / "nested/file.txt").write_bytes(b"changed")
        assert (tree / "nested/file.txt").read_bytes() == b"dataset"
        assert (
            artifacts.verify(descriptor["artifact_id"])["availability"] == "available"
        )


def test_reference_detects_changed_source_and_prefix_boundaries(tmp_path):
    source, store, artifacts = stores(tmp_path)
    path = source / "file.txt"
    path.write_text("before")
    outside = tmp_path / "inputs-evil"
    outside.mkdir()
    (outside / "data").write_text("unadmitted")
    with store.owner():
        store.initialize(require_mlmd=False)
        descriptor = artifacts.register(path.as_uri(), DATASET)
        path.write_text("after")
        assert artifacts.verify(descriptor["artifact_id"])["availability"] == "corrupt"
        with pytest.raises(DockflowError, match="outside"):
            artifacts.register((outside / "data").as_uri(), DATASET)
        with pytest.raises(DockflowError):
            artifacts.register("https://example.com/data.csv", DATASET)


def test_direct_managed_directory_admission_and_materialization_boundaries(tmp_path):
    source, store, artifacts = stores(tmp_path, storage_field="managed_root")
    path = source / "data"
    path.write_bytes(b"source-data")
    with store.owner():
        store.initialize(require_mlmd=False)
        reference = artifacts.register(path.as_uri(), DATASET)
        assert reference["ownership"] == "reference"
        assert not artifacts.managed_root.exists()
        managed = artifacts.register(path.as_uri(), DATASET, managed=True)
        payload = (
            artifacts.managed_root
            / ".dockflow/dockflow-pipelines"
            / managed["artifact_id"]
            / "payload"
        )
        assert payload.as_uri() == managed["content_uri"]
        assert (
            artifacts.register(payload.as_uri(), DATASET)["fingerprint"]
            == (managed["fingerprint"])
        )
        with pytest.raises(DockflowError, match="overlaps"):
            artifacts.materialize(
                managed["artifact_id"], artifacts.managed_root / "unowned-copy"
            )
        outside = tmp_path / "artifacts-other"
        outside.mkdir()
        (outside / "data").write_bytes(b"source-data")
        with pytest.raises(DockflowError, match="outside"):
            artifacts.register((outside / "data").as_uri(), DATASET)
        destination = tmp_path / "execution" / "data"
        artifacts.materialize(managed["artifact_id"], destination)
        assert destination.read_bytes() == b"source-data"
        assert not (artifacts.managed_root / "managed").exists()


def test_symlinks_and_special_files_are_rejected(tmp_path):
    source, store, artifacts = stores(tmp_path)
    actual = source / "actual"
    actual.write_text("safe")
    link = source / "link"
    link.symlink_to(actual)
    with store.owner():
        store.initialize(require_mlmd=False)
        with pytest.raises(DockflowError, match="symlink"):
            artifacts.register(link.as_uri(), DATASET)
        with pytest.raises(DockflowError, match="reserved"):
            artifacts.register(actual.as_uri(), DATASET, {"dockflow": {}})


@pytest.mark.parametrize("storage_field", ["root", "managed_root"])
def test_output_set_is_commit_boundary_and_stop_intent_wins(tmp_path, storage_field):
    source, store, artifacts = stores(tmp_path, storage_field=storage_field)
    path = source / "model"
    path.write_bytes(b"model")
    run_id, task_id, attempt_id = (new_id(kind) for kind in ("run", "task", "attempt"))
    with store.owner():
        store.initialize(require_mlmd=False)
        store.put("runs", {"run_id": run_id, "state": "running"})
        descriptor = artifacts.publish(
            path,
            DATASET,
            {
                "run_id": run_id,
                "task_id": task_id,
                "attempt_id": attempt_id,
                "definition_id": new_id("definition"),
                "pipeline_name": "persistence-test",
                "task_name": "produce",
                "output_name": "model",
            },
        )
        with pytest.raises(DockflowError, match="not been committed"):
            artifacts.materialize(descriptor["artifact_id"], tmp_path / "work/model")
        marker = store.commit_output_set(
            run_id, task_id, attempt_id, {"model": descriptor}, {"score": 0.9}
        )
        assert marker["parameters"] == {"score": 0.9}
        artifacts.materialize(descriptor["artifact_id"], tmp_path / "work/model")
        assert (tmp_path / "work/model").read_bytes() == b"model"
        store.append("stop_intent", {"run_id": run_id, "reason": "cancelled"})
        assert (
            store.commit_output_set(
                run_id, task_id, attempt_id, {"model": descriptor}, {}
            )
            == marker
        )
        with pytest.raises(DockflowError, match="Stop intent"):
            store.commit_output_set(run_id, task_id, new_id("attempt"), {}, {})


def test_journal_recovers_projection_source_and_logs(tmp_path):
    _, store, _ = stores(tmp_path)
    run_id, definition_id = new_id("run"), new_id("definition")
    with store.owner():
        store.initialize(require_mlmd=False)
        store.put("runs", {"run_id": run_id, "state": "succeeded"})
        store.save_definition_source(definition_id, b"schemaVersion: 2.1.0\n")
        store.log(run_id, "retained output", stream="stdout")
    shutil.rmtree(store.state / "runs")
    shutil.rmtree(store.state / "definitions")
    recovered = ControlStore(store.state, "test-project")
    with recovered.owner():
        recovered.initialize(require_mlmd=False)
        assert recovered.get("runs", run_id)["state"] == "succeeded"
        assert (
            recovered.state / "definitions" / definition_id / "source.yaml"
        ).read_bytes() == b"schemaVersion: 2.1.0\n"
        assert recovered.log_entries(run_id)[0]["text"] == "retained output"
        assert recovered.check()["valid"]


def test_owner_conflict_missing_records_and_mutations_require_owner(tmp_path):
    _, store, _ = stores(tmp_path)
    other = ControlStore(store.state, "test-project")
    with pytest.raises(DockflowError, match="ownership"):
        store.put("runs", {"run_id": new_id("run")})
    with store.owner():
        store.initialize(require_mlmd=False)
        with pytest.raises(DockflowError, match="owned"):
            with other.owner():
                pass
        store.put("runs", {"run_id": new_id("run"), "state": "succeeded"})
        store.put("runs", {"run_id": new_id("run"), "state": "succeeded"})
    (store.state / "records" / "00000000000000000001.json").unlink()
    assert not store.check()["valid"]


def test_real_mlmd_lineage_and_offline_rebuild(tmp_path):
    pytest.importorskip("ml_metadata")
    source, store, artifacts = stores(tmp_path)
    path = source / "dataset"
    path.write_bytes(b"data")
    run_id, task_id, attempt_id = (new_id(kind) for kind in ("run", "task", "attempt"))
    with store.owner():
        store.initialize()
        store.put("runs", {"run_id": run_id, "state": "running"})
        store.put("tasks", {"task_id": task_id, "run_id": run_id, "state": "running"})
        external = artifacts.register(path.as_uri(), DATASET, managed=True)
        produced = artifacts.publish(
            path,
            DATASET,
            {
                "run_id": run_id,
                "task_id": task_id,
                "attempt_id": attempt_id,
                "output_name": "data",
                "definition_id": new_id("definition"),
                "pipeline_name": "persistence-test",
                "task_name": "produce",
            },
        )
        store.commit_output_set(run_id, task_id, attempt_id, {"data": produced}, {})
        store.put(
            "attempts",
            {
                "attempt_id": attempt_id,
                "task_id": task_id,
                "run_id": run_id,
                "state": "succeeded",
                "inputs": {"source": external["artifact_id"]},
                "outputs": {"data": produced["artifact_id"]},
            },
        )
        store.put("runs", {"run_id": run_id, "state": "succeeded"})
        assert store.check(verify_contents=True, artifacts=artifacts)["valid"]
        execution = store.index.store.get_execution_by_type_and_name(
            "dockflow.v1.attempt", attempt_id
        )
        assert len(store.index.store.get_events_by_execution_ids([execution.id])) == 2
        assert store.verify_output_set(attempt_id)["valid"]
        artifacts.pin(produced["artifact_id"])
        assert store.verify_output_set(attempt_id)["valid"]
        marker_path = (
            store.attempt_path(run_id, task_id, attempt_id) / "output-set.json"
        )
        marker_path.unlink()
        assert not store.verify_output_set(attempt_id)["valid"]
        store.initialize()
        assert store.verify_output_set(attempt_id)["valid"]
        report = store.rebuild(apply=True)
        assert report["rebuilt"]
        assert (
            store.get("artifacts", produced["artifact_id"])["producer"]["attempt_id"]
            == attempt_id
        )
        assert store.check()["valid"]


def test_restart_recovers_committed_attempt_without_duplicate_execution(tmp_path):
    source, store, artifacts = stores(tmp_path)
    path = source / "result"
    path.write_bytes(b"committed")
    run_id, task_id, attempt_id = (new_id(kind) for kind in ("run", "task", "attempt"))
    with store.owner():
        store.initialize(require_mlmd=False)
        store.put("runs", {"run_id": run_id, "state": "running"})
        store.put(
            "tasks",
            {
                "task_id": task_id,
                "run_id": run_id,
                "state": "running",
                "attempt_ids": [attempt_id],
            },
        )
        store.put(
            "attempts",
            {
                "attempt_id": attempt_id,
                "run_id": run_id,
                "task_id": task_id,
                "state": "publishing",
            },
        )
        descriptor = artifacts.publish(
            path,
            DATASET,
            {
                "run_id": run_id,
                "task_id": task_id,
                "attempt_id": attempt_id,
                "output_name": "result",
                "definition_id": new_id("definition"),
                "pipeline_name": "persistence-test",
                "task_name": "produce",
            },
        )
        store.commit_output_set(
            run_id, task_id, attempt_id, {"result": descriptor}, {"score": 1.0}
        )
        store.append("stop_intent", {"run_id": run_id, "reason": "interrupted"})
    recovered = ControlStore(store.state, "test-project")
    with recovered.owner():
        recovered.initialize(require_mlmd=False)
        attempt = recovered.get("attempts", attempt_id)
        assert attempt["state"] == "succeeded"
        assert attempt["outputs"] == {"result": descriptor["artifact_id"]}
        assert attempt["output_parameters"] == {"score": 1.0}
        assert len(recovered.list("attempts")) == 1
        assert recovered.get("tasks", task_id)["state"] == "succeeded"
        sequence = len(recovered.records())
        recovered.initialize(require_mlmd=False)
        assert len(recovered.records()) == sequence


@pytest.mark.parametrize("storage_field", ["root", "managed_root"])
def test_offline_backup_verifies_control_and_managed_payloads(tmp_path, storage_field):
    source, store, artifacts = stores(tmp_path, storage_field=storage_field)
    path = source / "file"
    path.write_bytes(b"backup-data")
    with store.owner():
        store.initialize(require_mlmd=False)
        managed = artifacts.register(path.as_uri(), DATASET, managed=True)
        external = artifacts.register(path.as_uri(), DATASET)
        with pytest.raises(DockflowError, match="outside"):
            store.backup(artifacts.managed_root / "backup", artifacts)
        result = store.backup(tmp_path / "backup", artifacts)
        assert result["external_references_included"] is False
        assert ControlStore.verify_backup(tmp_path / "backup")["valid"]
        assert not (tmp_path / "backup/managed" / external["artifact_id"]).exists()
        payload = (
            tmp_path
            / "backup/managed/.dockflow/dockflow-pipelines"
            / managed["artifact_id"]
            / "payload"
        )
        assert payload.read_bytes() == b"backup-data"
        payload.write_bytes(b"damaged")
        with pytest.raises(DockflowError, match="Backup contents"):
            ControlStore.verify_backup(tmp_path / "backup")


def test_check_reports_source_loss_without_claiming_it_was_verified(tmp_path):
    _, store, _ = stores(tmp_path)
    definition_id = new_id("definition")
    with store.owner():
        store.initialize(require_mlmd=False)
        store.save_definition_source(definition_id, b"source")
        (store.state / "definitions" / definition_id / "source.yaml").unlink()
        report = store.check()
        assert not report["valid"]
        assert not report["content_verified"]
        assert "snapshot is missing" in report["errors"][0]["reason"]


@pytest.mark.parametrize("layout", ["root", "managed_root", "old-backup"])
def test_offline_restore_tool_preserves_managed_public_identity(tmp_path, layout):
    pytest.importorskip("ml_metadata")
    storage_field = "root" if layout == "old-backup" else layout
    source, store, artifacts = stores(tmp_path, storage_field=storage_field)
    path = source / "data"
    path.write_bytes(b"restore-me")
    config = tmp_path / "project.toml"
    config.write_text(
        'schema_version=1\n[project]\nid="test-project"\n[state]\ndirectory="state"\n'
        f'[artifacts]\n{storage_field}="artifacts"\nexternal_roots=["inputs"]\n'
    )
    with store.owner():
        store.initialize()
        descriptor = artifacts.register(path.as_uri(), DATASET, managed=True)
        store.backup(tmp_path / "backup", artifacts)
    if layout == "old-backup":
        manifest_path = tmp_path / "backup/backup.json"
        manifest = json.loads(manifest_path.read_text())
        del manifest["managed_root"]
        manifest_path.write_text(json.dumps(manifest))
    store.index = None
    shutil.rmtree(store.state)
    script = Path(__file__).resolve().parents[4] / "tools/backup.py"
    command = [
        sys.executable,
        str(script),
        "restore",
        "--config",
        str(config),
        "--apply",
        str(tmp_path / "backup"),
    ]
    refused = subprocess.run(command, capture_output=True, text=True)
    assert refused.returncode != 0
    assert "managed artifact directory must be empty" in refused.stderr
    assert (
        artifacts.managed_root
        / ".dockflow/dockflow-pipelines"
        / descriptor["artifact_id"]
        / "payload"
    ).read_bytes() == b"restore-me"
    shutil.rmtree(artifacts.managed_root)
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["restored"]
    restored = ControlStore(store.state, "test-project")
    assert (
        restored.get("artifacts", descriptor["artifact_id"])["fingerprint"]
        == descriptor["fingerprint"]
    )
    assert (
        ArtifactStore(restored, artifacts.options).verify(descriptor["artifact_id"])[
            "availability"
        ]
        == "available"
    )


def test_index_failure_remains_a_dispatch_hold_until_full_reconciliation(tmp_path):
    _, store, _ = stores(tmp_path)

    def fail(*args):
        raise OSError("simulated index failure")

    with store.owner():
        store.initialize(require_mlmd=False)
        store.index = SimpleNamespace(put=fail)
        run_id = new_id("run")
        with pytest.raises(DockflowError, match="accepted"):
            store.put("runs", {"run_id": run_id, "state": "queued"})
        assert store.get("runs", run_id)["state"] == "queued"
        assert store.reconciliation_required
        store.index.put = lambda *args: None
        store.put(
            "experiments",
            {
                "experiment_id": new_id("experiment"),
                "display_name": "after index failure",
            },
        )
        assert store.reconciliation_required
        with pytest.raises(DockflowError, match="reconciliation"):
            store.ensure_reconciled()
        store.reconcile_index()
        assert not store.reconciliation_required


def test_durable_logs_fragment_utf8_without_losing_stream_order(tmp_path):
    _, store, _ = stores(tmp_path)
    run_id = new_id("run")
    text = "\U0001f642é" * 9000
    with store.owner():
        store.initialize(require_mlmd=False)
        store.put("runs", {"run_id": run_id, "state": "succeeded"})
        store.log(run_id, text, stream="stdout")
        entries = store.log_entries(run_id)
        assert "".join(entry["text"] for entry in entries) == text
        assert all(len(entry["text"].encode("utf-8")) <= 16384 for entry in entries)
        assert all(entry["stream"] == "stdout" for entry in entries)
        assert [entry["sequence"] for entry in entries] == sorted(
            entry["sequence"] for entry in entries
        )


def test_readonly_metadata_check_compares_index_without_writes(tmp_path):
    pytest.importorskip("ml_metadata")
    _, store, _ = stores(tmp_path)
    with store.owner():
        store.initialize()
        store.put(
            "experiments",
            {
                "experiment_id": new_id("experiment"),
                "display_name": "read-only inspection",
            },
        )
    store.index = None
    database = store.metadata_directory / "mlmd.sqlite"
    before = database.read_bytes()
    modified = database.stat().st_mtime_ns
    inspected = ControlStore(store.state, "test-project")
    assert inspected.open_readonly_index()
    assert inspected.check()["index_checked"]
    assert inspected.check()["valid"]
    assert database.read_bytes() == before
    assert database.stat().st_mtime_ns == modified
    with pytest.raises(DockflowError, match="Read-only"):
        inspected.index.put("runs", {"run_id": new_id("run")})


def test_rebuild_preserves_corrupt_index_bytes_and_replays_history(tmp_path):
    pytest.importorskip("ml_metadata")
    _, store, _ = stores(tmp_path)
    experiment_id = new_id("experiment")
    with store.owner():
        store.initialize()
        store.put(
            "experiments",
            {"experiment_id": experiment_id, "display_name": "recover corrupt index"},
        )
    store.index = None
    database = store.metadata_directory / "mlmd.sqlite"
    damaged = b"a deliberately corrupted SQLite index"
    database.write_bytes(damaged)
    recovered = ControlStore(store.state, "test-project")
    with recovered.owner():
        recovered.initialize(require_mlmd=False)
        report = recovered.rebuild(apply=True)
        assert report["rebuilt"]
        assert report["backup_format"] == "raw-corrupt-index"
        assert (Path(report["backup"]) / "mlmd.sqlite").read_bytes() == damaged
        assert recovered.list("experiments")[0]["experiment_id"] == experiment_id
        assert recovered.check()["valid"]


def test_direct_cli_rebuild_repairs_corrupt_index_and_check_reads_index(tmp_path):
    pytest.importorskip("ml_metadata")
    from dockflow_pipelines.cli import app
    from typer.testing import CliRunner

    _, store, _ = stores(tmp_path)
    config = tmp_path / "project.toml"
    config.write_text(
        'schema_version=1\n[project]\nid="test-project"\n[state]\ndirectory="state"\n'
    )
    experiment_id = new_id("experiment")
    with store.owner():
        store.initialize()
        record = store.put(
            "experiments", {"experiment_id": experiment_id, "display_name": "accepted"}
        )
        store.index.put(
            "experiments", {**record, "display_name": "index-only tampering"}
        )
    store.index = None
    runner = CliRunner()
    prefix = ["--config", str(config), "--json", "metadata"]
    check = runner.invoke(app, prefix + ["check"])
    assert check.exit_code == 0, check.output
    result = json.loads(check.stdout)["result"]
    assert result["index_checked"] and not result["valid"]
    (store.metadata_directory / "mlmd.sqlite").write_bytes(b"corrupted index")
    repaired = runner.invoke(app, prefix + ["rebuild", "--apply"])
    assert repaired.exit_code == 0, repaired.output
    assert json.loads(repaired.stdout)["result"]["backup_format"] == "raw-corrupt-index"
    after = runner.invoke(app, prefix + ["check"])
    assert json.loads(after.stdout)["result"]["valid"]
