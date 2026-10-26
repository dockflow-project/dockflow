"""Destructive lifecycle regressions use only disposable project-owned state."""

import json
import os
import time
import uuid
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
from dockflow_core.errors import DockflowError
from dockflow_pipelines.cli import app
from dockflow_pipelines.config import load_settings
from dockflow_pipelines.core import Core
from dockflow_pipelines.deletion import Deletions
from dockflow_pipelines.records import new_id
from dockflow_pipelines.service import create_app
from fastapi.testclient import TestClient
from typer.testing import CliRunner

DATASET = {"schema_title": "system.Dataset", "schema_version": "0.0.1"}


@pytest.fixture(
    params=["sqlite", pytest.param("postgresql", marks=pytest.mark.postgresql)]
)
def settings(tmp_path, request):
    path = tmp_path / "dockflow.toml"
    path.write_text(
        'schema_version=1\n[project]\nid="deletion-tests"\n[artifacts]\nexternal_roots=["inputs"]\n'
    )
    text = path.read_text().replace(
        'id="deletion-tests"', 'id="deletion-tests-' + uuid.uuid4().hex + '"'
    )
    if request.param == "postgresql":
        if not os.environ.get("DOCKFLOW_TEST_CACHE_POSTGRES_DSN"):
            pytest.skip("Set a disposable PostgreSQL test database")
        text += '\n[state]\nbackend="postgresql"\ndsn_env="DOCKFLOW_TEST_CACHE_POSTGRES_DSN"\n'
    path.write_text(text)
    (tmp_path / "inputs").mkdir()
    return load_settings(path)


@pytest.fixture
def core(settings):
    core = Core(settings)
    with core.store.owner():
        core.initialize()
        yield core


def imported(core, *, directory=False):
    path = core.settings.root / "inputs" / new_id("artifact")
    if directory:
        path.mkdir()
        (path / "a").write_bytes(b"aaa")
        (path / "b").write_bytes(b"bbbbb")
    else:
        path.write_bytes(b"manual-data")
    return core.artifacts.register(path.as_uri(), DATASET, managed=True)


def produced(core, *, referenced=True):
    run, task, attempt = new_id("run"), new_id("task"), new_id("attempt")
    core.store.put("runs", {"run_id": run, "state": "succeeded", "task_ids": [task]})
    core.store.put(
        "tasks",
        {
            "task_id": task,
            "run_id": run,
            "state": "succeeded",
            "attempt_ids": [attempt],
        },
    )
    core.store.put(
        "attempts",
        {"attempt_id": attempt, "run_id": run, "task_id": task, "state": "succeeded"},
    )
    path = core.settings.root / "inputs" / attempt
    path.write_bytes(b"produced-data")
    artifact = core.artifacts.publish(
        path,
        DATASET,
        {
            "run_id": run,
            "task_id": task,
            "attempt_id": attempt,
            "pipeline_name": "testing",
            "task_name": "produce",
            "output_name": "data",
        },
    )
    if referenced:
        core.store.commit_output_set(run, task, attempt, {"data": artifact}, {})
        artifact = core.artifacts.get(artifact["artifact_id"])
        for collection, identity in (
            ("runs", run),
            ("tasks", task),
            ("attempts", attempt),
        ):
            value = core.store.get(collection, identity)
            core.store.put(
                collection, {**value, "outputs": {"data": artifact["artifact_id"]}}
            )
    return artifact, run, task, attempt


def target(collection, identity):
    return {"collection": collection, "id": identity}


def artifact_plan(service, artifact, files=True):
    return service.plan(
        {
            "targets": [target("artifacts", artifact["artifact_id"])],
            "delete_files": files,
        }
    )


def apply(service, plan):
    return service.apply({"plan_id": plan["plan_id"], "confirmation": "DANGER"})


def payload(artifact):
    return Path(unquote(urlsplit(artifact["content_uri"]).path))


def test_artifact_and_bytes_share_dependency_gate_then_run_deletion_unlocks(core):
    service = Deletions(core)
    artifact, run, _, _ = produced(core)
    for files in (False, True):
        plan = artifact_plan(service, artifact, files)
        assert plan["blockers"]
        with pytest.raises(DockflowError, match="blocked"):
            apply(service, plan)
    assert payload(artifact).exists()
    run_plan = service.plan({"targets": [target("runs", run)]})
    assert apply(service, run_plan)["state"] == "completed"
    assert payload(artifact).exists()
    assert service.store.list("runs") == []
    assert apply(service, artifact_plan(service, artifact))["state"] == "completed"
    assert not payload(artifact).exists()
    assert service.store.list("artifacts") == []
    with pytest.raises(DockflowError) as error:
        service.store.get("artifacts", artifact["artifact_id"])
    assert error.value.status == 410
    assert service.store.check(artifacts=core.artifacts)["valid"]
    service.store.rebuild(True)
    assert service.store.check(artifacts=core.artifacts)["valid"]
    assert service.store.list("runs") == []
    assert service.store.list("artifacts") == []
    assert service.store.project_metadata("project")["mapping_version"] == 2
    core.initialize()
    assert service.store.list("artifacts") == []


def test_manual_artifacts_never_become_orphans_or_retention_candidates(core):
    service = Deletions(core)
    artifact = imported(core, directory=True)
    orphan = core.artifacts.managed_root / "unclaimed"
    orphan.write_bytes(b"orphan")
    scan = service.scan({})
    manual = [
        row for row in scan["items"] if row["classification"] == "manual_artifact"
    ]
    assert len(manual) == 2
    assert scan["totals"]["artifact_bytes"] == 8
    assert scan["totals"]["orphan_bytes"] == 6
    core.settings.artifacts["retention_days"] = 1
    old = {**artifact, "published_at": "2000-01-01T00:00:00+00:00"}
    core.store.put("artifacts", old)
    assert service.retention({"apply": True})["eligible_artifact_ids"] == []
    plan = service.plan({"scan_id": scan["scan_id"], "orphans": True})
    assert [row["path"] for row in plan["rows"]] == ["unclaimed"]
    apply(service, plan)
    assert not orphan.exists()
    assert payload(artifact).exists()
    selected = service.plan({"scan_id": scan["scan_id"], "selected": [manual[0]["id"]]})
    assert len(selected["rows"]) == 2
    assert selected["estimated_bytes"] == 8
    apply(service, selected)
    assert not (payload(artifact) / "a").exists()
    assert not (payload(artifact) / "b").exists()


def test_pins_and_new_reference_invalidate_existing_plan(core):
    service = Deletions(core)
    artifact = imported(core)
    plan = artifact_plan(service, artifact)
    core.artifacts.pin(artifact["artifact_id"], True)
    with pytest.raises(DockflowError, match="changed"):
        apply(service, plan)
    assert payload(artifact).exists()
    assert artifact_plan(service, core.artifacts.get(artifact["artifact_id"]))[
        "blockers"
    ]
    core.artifacts.pin(artifact["artifact_id"], False)
    plan = artifact_plan(service, core.artifacts.get(artifact["artifact_id"]))
    core.store.put(
        "runs",
        {
            "run_id": new_id("run"),
            "state": "succeeded",
            "inputs": {"data": artifact["artifact_id"]},
        },
    )
    with pytest.raises(DockflowError, match="stale"):
        apply(service, plan)
    assert payload(artifact).exists()


def test_danger_stale_object_and_expired_plan_fail_without_deletion(core):
    service = Deletions(core)
    artifact = imported(core)
    plan = artifact_plan(service, artifact)
    for confirmation in (None, "danger", "DANGER ", True):
        with pytest.raises(DockflowError, match="DANGER"):
            service.apply({"plan_id": plan["plan_id"], "confirmation": confirmation})
    payload(artifact).write_bytes(b"replacement")
    with pytest.raises(DockflowError, match="stale"):
        apply(service, plan)
    plan = artifact_plan(service, artifact)
    plan["expires_at"] = time.time() - 1
    service._save("plan", plan)
    with pytest.raises(DockflowError, match="expired"):
        apply(service, plan)
    assert payload(artifact).read_bytes() == b"replacement"


def test_partial_apply_resumes_same_manifest_after_restart(core, monkeypatch):
    service = Deletions(core)
    artifact = imported(core, directory=True)
    plan = artifact_plan(service, artifact)
    original = service._delete
    calls = []

    def delete(row):
        calls.append(row["path"])
        if row["path"].endswith("/b"):
            raise PermissionError("synthetic")
        original(row)

    monkeypatch.setattr(service, "_delete", delete)
    report = apply(service, plan)
    assert report["state"] == "partial"
    assert len(report["completed"]) == 1
    assert core.store.list("artifacts") == []
    replacement = Deletions(core)
    assert apply(replacement, plan)["state"] == "completed"
    assert len(calls) == 2
    assert apply(replacement, plan)["state"] == "completed"
    assert not (payload(artifact) / "b").exists()


def test_scan_pagination_complete_totals_and_unknown_protection(core):
    service = Deletions(core)
    manual = imported(core)
    core.artifacts.pin(manual["artifact_id"], True)
    root = core.artifacts.managed_root
    for index in range(205):
        (root / f"orphan-{index:03}").write_bytes(b"xx")
    (root / "symlink").symlink_to(
        core.settings.root / "inputs", target_is_directory=True
    )
    scan = service.scan({})
    first = service.scan_show(
        {"scan_id": scan["scan_id"], "page_size": 1, "orphans": True}
    )
    assert first["totals"]["orphan_bytes"] == 410
    assert first["totals"]["selected_bytes"] == 410
    assert first["totals"]["protected_artifact_bytes"] == 11
    assert len(first["selected_ids"]) == 205
    assert first["next_page_token"] == "1"
    plan = service.plan({"scan_id": scan["scan_id"], "orphans": True})
    assert len(plan["rows"]) == 205
    assert all(".dockflow/storage.json" != row["path"] for row in plan["rows"])
    assert all("symlink" != row["path"] for row in plan["rows"])


def test_keep_files_has_durable_retained_classification(core):
    service = Deletions(core)
    artifact = imported(core)
    apply(service, artifact_plan(service, artifact, files=False))
    scan = service.scan({})
    rows = [row for row in scan["items"] if row["artifact_ids"]]
    assert rows and all(row["classification"] == "retained_file" for row in rows)
    assert scan["totals"]["orphan_bytes"] == 0
    assert payload(artifact).exists()


def test_execution_selected_by_retained_run_cannot_be_deleted(core):
    service = Deletions(core)
    _, run, _, attempt = produced(core)
    consumer = new_id("run")
    core.store.put(
        "runs",
        {"run_id": consumer, "state": "succeeded", "use_executions": {"task": attempt}},
    )
    for collection, identity in (("runs", run), ("attempts", attempt)):
        plan = service.plan({"targets": [target(collection, identity)]})
        assert any("Retained" in reason for reason in plan["blockers"])
        with pytest.raises(DockflowError, match="blocked"):
            apply(service, plan)


def test_standalone_publication_is_not_an_orphan(core):
    from dockflow_artifacts import Publisher

    source = core.settings.root / "inputs" / "database"
    source.write_bytes(b"database")
    publisher = Publisher(
        core.artifacts.managed_root,
        database=core.store.database.adapter,
        project_id=core.store.project_id,
    )
    # Use the owner's transactional writer to avoid a second SQLite writer.
    publisher._records = lambda **kwargs: core.artifacts.artifact_records()
    publisher.publish(source, "manual/database")
    service = Deletions(core)
    scan = service.scan({})
    rows = [row for row in scan["items"] if row["path"] == "manual/database"]
    assert rows[0]["classification"] == "publication"
    assert not rows[0]["eligible"]
    assert scan["totals"]["orphan_bytes"] == 0


@pytest.mark.parametrize("value", ["0", "-2", "true", "1.5"])
def test_invalid_retention_configuration(settings, value):
    settings.config_path.write_text(
        settings.config_path.read_text().replace(
            "[artifacts]", f"[artifacts]\nretention_days={value}"
        )
    )
    with pytest.raises(DockflowError):
        load_settings(settings.config_path)


def test_retention_environment_precedence(settings, monkeypatch):
    monkeypatch.setenv("ARTIFACT_RETENTION_DAYS", "30")
    assert load_settings(settings.config_path).artifacts["retention_days"] == 30
    monkeypatch.setenv("DOCKFLOW_PIPELINES_ARTIFACT_RETENTION_DAYS", "60")
    assert load_settings(settings.config_path).artifacts["retention_days"] == 60
    assert (
        load_settings(
            settings.config_path, overrides={"artifacts.retention_days": -1}
        ).artifacts["retention_days"]
        == -1
    )


def test_retention_requires_no_retained_references_and_never_expires_manual(core):
    service = Deletions(core)
    core.settings.artifacts["retention_days"] = 1
    artifact, run, _, _ = produced(core)
    core.store.put(
        "artifacts", {**artifact, "published_at": "2000-01-01T00:00:00+00:00"}
    )
    assert service.retention({})["eligible_artifact_ids"] == []
    apply(service, service.plan({"targets": [target("runs", run)]}))
    preview = service.retention({})
    assert preview["eligible_artifact_ids"] == [artifact["artifact_id"]]
    with pytest.raises(DockflowError, match="DANGER"):
        service.retention({"apply": True})
    result = service.retention({"apply": True}, automatic=True)
    assert result["job"]["state"] == "completed"
    assert not payload(artifact).exists()


def test_api_and_cli_use_reviewed_plan_and_danger(settings):
    application = create_app(settings, execute=False)
    with TestClient(application) as client:
        core = application.state.core
        artifact = imported(core)
        plan = client.post(
            "/dockflow/v1/deletions/plan",
            json={
                "targets": [target("artifacts", artifact["artifact_id"])],
                "delete_files": True,
            },
        ).json()
        assert not plan["blockers"]
        denied = client.post(
            "/dockflow/v1/deletions/apply", json={"plan_id": plan["plan_id"]}
        )
        assert denied.status_code == 409
        assert payload(artifact).exists()
        assert (
            client.post(
                "/dockflow/v1/deletions/apply",
                json={"plan_id": plan["plan_id"], "confirmation": "DANGER"},
            ).json()["state"]
            == "completed"
        )
        assert (
            client.get("/dockflow/v1/artifacts/" + artifact["artifact_id"]).status_code
            == 410
        )
        assert client.post("/dockflow/v1/deletions/apply", json={}).status_code == 400
        assert client.post("/dockflow/v1/storage/scan", json={}).status_code == 200
    runner = CliRunner()
    result = runner.invoke(
        app, ["--config", str(settings.config_path), "--json", "storage", "scan"]
    )
    assert result.exit_code == 0, result.output
    scan = json.loads(result.stdout)["result"]
    assert scan["state"] == "complete"


def test_pending_orphan_job_blocks_new_plans_and_new_alias_on_retry(core, monkeypatch):
    service = Deletions(core)
    path = core.artifacts.managed_root / "orphan"
    path.write_bytes(b"owned")
    scan = service.scan({})
    plan = service.plan({"scan_id": scan["scan_id"], "orphans": True})
    monkeypatch.setattr(
        service, "_delete", lambda row: (_ for _ in ()).throw(PermissionError())
    )
    assert apply(service, plan)["state"] == "partial"
    scan2 = service.scan({})
    row = next(row for row in scan2["items"] if row["path"] == "orphan")
    assert row["pending_plan_ids"] == [plan["plan_id"]]
    assert not row["eligible"]
    artifact = imported(core)
    core.store.put("artifacts", {**artifact, "content_uri": path.as_uri()})
    with pytest.raises(DockflowError, match="ownership changed"):
        apply(Deletions(core), plan)
    assert path.read_bytes() == b"owned"


def test_scan_failure_cannot_enable_bulk_orphan_deletion(core, monkeypatch):
    service = Deletions(core)
    saved = []
    original = service._save

    def save(kind, value):
        if kind == "scan":
            saved.append(value["scan_id"])
        return original(kind, value)

    monkeypatch.setattr(service, "_save", save)

    def incomplete(prefix):
        raise PermissionError("synthetic incomplete listing")
        yield

    monkeypatch.setattr(service, "_files", incomplete)
    with pytest.raises(PermissionError):
        service.scan({})
    failed = service.scan_show({"scan_id": saved[-1]})
    assert failed["state"] == "failed"
    with pytest.raises(DockflowError, match="complete scan"):
        service.plan({"scan_id": saved[-1], "orphans": True})


def test_subdirectory_scan_cannot_delete_partial_directory_artifact(core):
    service = Deletions(core)
    artifact = imported(core, directory=True)
    folder = service._path(artifact)
    scan = service.scan({"prefix": folder + "/a"})
    plan = service.plan(
        {"scan_id": scan["scan_id"], "selected": [scan["items"][0]["id"]]}
    )
    assert any("omits files" in value for value in plan["blockers"])
    with pytest.raises(DockflowError, match="blocked"):
        apply(service, plan)
    assert (payload(artifact) / "b").exists()


def test_new_queued_run_blocks_applying_previously_valid_plan(core):
    service = Deletions(core)
    artifact = imported(core)
    plan = artifact_plan(service, artifact)
    core.store.put("runs", {"run_id": new_id("run"), "state": "queued"})
    with pytest.raises(DockflowError, match="idle project"):
        apply(service, plan)
    assert payload(artifact).exists()


def test_external_reference_never_grants_storage_ownership(core):
    path = core.settings.root / "inputs" / "database"
    path.write_bytes(b"database")
    artifact = core.artifacts.register(path.as_uri(), DATASET)
    service = Deletions(core)
    plan = artifact_plan(service, artifact)
    assert any("External" in value for value in plan["blockers"])
    apply(service, artifact_plan(service, artifact, files=False))
    assert path.read_bytes() == b"database"


def test_deletion_backup_contains_retirement_and_keeps_store_identity(core):
    service = Deletions(core)
    artifact = imported(core)
    plan = artifact_plan(service, artifact)
    apply(service, plan)
    destination = core.settings.root / "backup"
    core.store.backup(destination, core.artifacts)
    assert (destination / "managed/.dockflow/storage.json").exists()
    from dockflow_pipelines.metadata import ControlStore

    snapshot = ControlStore(
        destination,
        core.store.project_id,
        storage={"backend": "sqlite", "database": str(destination / "state.sqlite")},
    )
    assert snapshot.check()["valid"]
    assert snapshot.list("artifacts") == []
    assert snapshot.project_metadata("plan_" + plan["plan_id"])["state"] == "completed"


def test_deleted_execution_logs_are_excluded_from_parent_run(core):
    service = Deletions(core)
    _, run, task, attempt = produced(core, referenced=False)
    core.store.log(run, "retained execution log", task_id=task, attempt_id=attempt)
    assert core.logs(run)["entries"]
    apply(service, service.plan({"targets": [target("attempts", attempt)]}))
    assert core.logs(run)["entries"] == []
    assert core.store.get("runs", run)["state"] == "succeeded"


def test_execution_retirement_invalidates_cache_without_resetting_fences(core):
    from dockflow_core.canonical import digest
    from dockflow_pipelines.cache_registry import Registry
    from dockflow_pipelines.cache_storage import make_manifest

    registry = Registry(core.settings.cache, core.store.project_id)
    run, task = new_id("run"), new_id("task")
    key = digest("retirement-test")
    claim = registry.resolve_or_claim(
        key, "qualification", str(uuid.uuid4()), run, task
    ).ownership
    registry.begin_validation(claim)
    producer = {"run_id": run, "task_id": task, "attempt_id": claim.attempt_id}
    manifest = make_manifest(
        {}, {}, {}, producer, key, registry.options["storage_identity"]
    )
    registry.publish(claim, manifest)
    core.store.put("runs", {"run_id": run, "state": "succeeded"})
    core.store.put("tasks", {"task_id": task, "run_id": run, "state": "succeeded"})
    core.store.put("attempts", {**producer, "state": "succeeded"})
    before = registry.inspect(key)
    service = Deletions(core)
    apply(service, service.plan({"targets": [target("attempts", claim.attempt_id)]}))
    after = registry.inspect(key)
    assert after["entry"]["published_artifact_id"] is None
    assert after["entry"]["generation"] > before["entry"]["generation"]
    assert [value["fencing_token"] for value in after["attempts"]] == [
        value["fencing_token"] for value in before["attempts"]
    ]
    assert after["artifacts"][0]["state"] == "INVALID"


def test_retention_preserves_manual_alias_to_produced_storage(core):
    service = Deletions(core)
    artifact, run, _, _ = produced(core)
    apply(service, service.plan({"targets": [target("runs", run)]}))
    core.settings.artifacts["retention_days"] = 1
    core.store.put(
        "artifacts", {**artifact, "published_at": "2000-01-01T00:00:00+00:00"}
    )
    manual_alias = {
        **artifact,
        "artifact_id": new_id("artifact"),
        "origin": "external",
        "creation_origin": "manual",
        "producer": None,
    }
    core.store.put("artifacts", manual_alias)
    result = service.retention({"apply": True}, automatic=True)
    assert result["eligible_artifact_ids"] == []
    assert payload(artifact).exists()


def test_changed_directory_membership_blocks_existing_artifact_plan(core):
    service = Deletions(core)
    artifact = imported(core, directory=True)
    plan = artifact_plan(service, artifact)
    (payload(artifact) / "new-file").write_bytes(b"preserve new member")
    with pytest.raises(DockflowError, match="gained files"):
        apply(service, plan)
    assert (payload(artifact) / "a").exists()
    assert (payload(artifact) / "new-file").exists()


def test_committed_output_set_protects_artifacts_without_later_resource_updates(core):
    service = Deletions(core)
    artifact, run, task, attempt = produced(core)
    for collection, identity in (("runs", run), ("tasks", task), ("attempts", attempt)):
        core.store.put(
            collection, {**core.store.get(collection, identity), "outputs": {}}
        )
    plan = artifact_plan(service, artifact)
    assert any("Committed output set" in value for value in plan["blockers"])
    with pytest.raises(DockflowError, match="blocked"):
        apply(service, plan)
    assert payload(artifact).exists()


def test_retention_provider_failure_does_not_stop_execution_scheduler(
    core, monkeypatch
):
    from dockflow_pipelines.service import Scheduler

    core.settings.artifacts["retention_days"] = 1

    def unavailable(*args, **kwargs):
        raise OSError("synthetic provider failure")

    monkeypatch.setattr(Deletions, "retention", unavailable)
    scheduler = Scheduler(core)
    scheduler.ready = True
    scheduler.retention_tick()
    assert not scheduler.stopping.is_set()
    assert scheduler.ready
    assert "error" in core.store.project_metadata("retention_status")


def test_cli_artifact_file_deletion_requires_explicit_confirmation(settings):
    core = Core(settings)
    with core.store.owner():
        core.initialize()
        artifact = imported(core)
    runner = CliRunner()
    command = [
        "--config",
        str(settings.config_path),
        "--json",
        "artifacts",
        "delete",
        artifact["artifact_id"],
        "--delete-files",
        "--apply",
    ]
    result = runner.invoke(app, command)
    assert result.exit_code != 0
    assert "DANGER" in result.output
    assert payload(artifact).exists()
    result = runner.invoke(app, [*command, "--confirm", "DANGER"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["result"]["state"] == "completed"
    assert not payload(artifact).exists()


def test_incomplete_projection_never_authorizes_artifact_deletion(core):
    service = Deletions(core)
    artifact = imported(core)
    run = new_id("run")
    core.store.put("runs", {"run_id": run, "state": "succeeded"})
    plan = artifact_plan(service, artifact)
    assert not plan["blockers"]
    with core.store.database.transaction() as connection:
        core.store.database.execute(
            connection,
            "DELETE FROM dockflow_state_resources WHERE project_id=? AND collection='runs' AND public_id=?",
            (core.store.project_id, run),
        )
    with pytest.raises(DockflowError, match="Metadata integrity"):
        apply(service, plan)
    assert payload(artifact).exists()
