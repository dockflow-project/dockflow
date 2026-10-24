"""A new direct owner cannot assume an earlier execution stopped with its owner."""

import json
import subprocess
import sys

import pytest
from dockflow_database.errors import DockflowError
from dockflow_pipelines.cli import app, require_direct_idle
from dockflow_pipelines.config import load_settings
from dockflow_pipelines.core import Core
from dockflow_pipelines.records import new_id
from dockflow_pipelines.service import Scheduler
from test_interfaces import fixture_definition
from typer.testing import CliRunner


@pytest.fixture
def settings(tmp_path):
    (tmp_path / "pipeline.json").write_text(json.dumps(fixture_definition()))
    config = tmp_path / ".dockflow-pipelines.toml"
    config.write_text(
        'schema_version=1\n[project]\nid="direct-recovery"\n'
        '[definitions.pipelines]\ntest="pipeline.json"\n'
    )
    return load_settings(config)


def seed(
    settings,
    run_state="succeeded",
    run_uncertain=False,
    attempt_state=None,
    attempt_uncertain=False,
):
    core = Core(settings)
    run = {
        "run_id": new_id("run"),
        "state": run_state,
        "reconciliation_required": run_uncertain,
    }
    with core.store.owner():
        core.initialize()
        core.store.put("runs", run)
        if attempt_state is not None:
            core.store.put(
                "attempts",
                {
                    "attempt_id": new_id("attempt"),
                    "run_id": run["run_id"],
                    "state": attempt_state,
                    "reconciliation_required": attempt_uncertain,
                    "container_id": "retained-unconfirmed-container",
                },
            )
    return core


def assert_refused_without_admission_or_execution(settings, core, monkeypatch):
    import docker
    from dockflow_pipelines.executor import KFPAdapter

    before = core.store.records()
    previous_runs = {item["run_id"] for item in core.store.list("runs")}
    previous_attempts = {item["attempt_id"] for item in core.store.list("attempts")}
    resolve = Core.resolve

    def forbidden(*args, **kwargs):
        pytest.fail("Unresolved prior execution reached admission or Docker execution")

    def checked_resolve(self, operand, *, persist=True):
        if persist:
            forbidden()
        return resolve(self, operand, persist=persist)

    monkeypatch.setattr(Core, "resolve", checked_resolve)
    monkeypatch.setattr(Core, "submit", forbidden)
    monkeypatch.setattr(Core, "execute", forbidden)
    monkeypatch.setattr(KFPAdapter, "load", forbidden)
    monkeypatch.setattr(docker, "from_env", forbidden)
    result = CliRunner().invoke(
        app, ["--config", str(settings.config_path), "--local", "--json", "run", "test"]
    )
    assert result.exit_code == 1, result.output
    error = json.loads(result.stderr)["error"]
    assert error["code"] == "CONFLICT"
    assert "service" in error["message"] and "reconcile/drain" in error["message"]
    assert error["details"]
    assert all(set(item) == {"field", "reason"} for item in error["details"])
    assert all(item["field"] in {"runs", "attempts"} for item in error["details"])
    assert core.store.records() == before
    assert {item["run_id"] for item in core.store.list("runs")} == previous_runs
    assert {
        item["attempt_id"] for item in core.store.list("attempts")
    } == previous_attempts
    assert not settings.work_directory.exists()


@pytest.mark.parametrize(
    "state,uncertain",
    [
        ("queued", False),
        ("running", False),
        ("cancelling", False),
        ("publishing", False),
        ("succeeded", True),
        ("interrupted", True),
    ],
)
def test_direct_run_rejects_prior_nonterminal_or_uncertain_run(
    settings, monkeypatch, state, uncertain
):
    core = seed(settings, state, uncertain)
    assert_refused_without_admission_or_execution(settings, core, monkeypatch)


@pytest.mark.parametrize(
    "state,uncertain",
    [
        ("running", False),
        ("publishing", False),
        ("pending", False),
        ("succeeded", True),
        ("failed", True),
        ("cancelled", True),
        ("interrupted", True),
    ],
)
def test_direct_run_rejects_prior_attempt_even_with_terminal_run(
    settings, monkeypatch, state, uncertain
):
    core = seed(settings, attempt_state=state, attempt_uncertain=uncertain)
    assert_refused_without_admission_or_execution(settings, core, monkeypatch)


def test_abrupt_owner_death_and_released_os_lock_do_not_confirm_container_stopped(
    settings, monkeypatch
):
    run_id, attempt_id = new_id("run"), new_id("attempt")
    script = """
import os, sys
from dockflow_pipelines.config import load_settings
from dockflow_pipelines.core import Core
core = Core(load_settings(sys.argv[1]))
with core.store.owner():
    core.initialize()
    core.store.put('runs', {'run_id': sys.argv[2], 'state': 'running'})
    core.store.put('attempts', {'attempt_id': sys.argv[3], 'run_id': sys.argv[2],
        'state': 'running', 'container_id': 'unconfirmed-orphan'})
    os._exit(0)
"""
    child = subprocess.run(
        [sys.executable, "-c", script, str(settings.config_path), run_id, attempt_id],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert child.returncode == 0, child.stderr
    core = Core(settings)
    # Successful reacquisition proves the OS lock was released by process death.
    with core.store.owner():
        assert core.store.get("runs", run_id)["state"] == "running"
    assert_refused_without_admission_or_execution(settings, core, monkeypatch)


@pytest.mark.parametrize(
    "state", [None, "succeeded", "failed", "cancelled", "interrupted"]
)
def test_direct_run_allows_fresh_state_and_fully_terminal_history(
    settings, monkeypatch, state
):
    core = seed(settings, state, attempt_state=state) if state else Core(settings)
    executions = []

    def execute(self, run, *, on_log=None):
        executions.append(run["run_id"])
        return self.store.put("runs", {**run, "state": "succeeded", "outputs": {}})

    monkeypatch.setattr(Core, "execute", execute)
    result = CliRunner().invoke(
        app, ["--config", str(settings.config_path), "--local", "--json", "run", "test"]
    )
    assert result.exit_code == 0, result.output
    assert len(executions) == 1
    assert json.loads(result.stdout)["result"]["run_id"] == executions[0]
    assert core.store.get("runs", executions[0])["state"] == "succeeded"


def test_direct_idle_check_requires_ownership_and_reports_http_conflict(settings):
    core = seed(settings, "running")
    with pytest.raises(DockflowError, match="ownership"):
        require_direct_idle(core)
    with core.store.owner(), pytest.raises(DockflowError) as error:
        require_direct_idle(core)
    assert error.value.code == "CONFLICT" and error.value.status == 409


def test_direct_idle_guard_rejects_index_reconciliation_before_admission(settings):
    core = Core(settings)
    with core.store.owner():
        core.initialize()
        core.store.set_project_metadata(
            "reconciliation", {"reconciliation_required": True}
        )
        before = core.store.records()
        with pytest.raises(DockflowError, match="reconciliation") as error:
            require_direct_idle(core)
        assert error.value.code == "UNAVAILABLE"
        assert core.store.records() == before
        assert not core.store.list("runs")
    assert not settings.work_directory.exists()


class ControlledContainer:
    def __init__(self, project_id, attempt_id, *, confirm_stop=True):
        self.labels = {
            "dockflow.project": project_id,
            "dockflow.attempt": attempt_id,
        }
        self.attrs = {"State": {"Running": True}}
        self.confirm_stop = confirm_stop
        self.stop_timeouts = []

    def reload(self):
        pass

    def stop(self, *, timeout):
        self.stop_timeouts.append(timeout)
        if self.confirm_stop:
            self.attrs["State"]["Running"] = False

    def remove(self, *, force):
        self.attrs["State"]["Running"] = False

    def logs(self, *, stdout, stderr):
        return b""


class ControlledDocker:
    def __init__(self, containers):
        self.containers = self
        self.by_id = containers
        self.unreachable = False
        self.lookups = []
        self.close_count = 0

    def ping(self):
        from docker.errors import DockerException

        if self.unreachable:
            raise DockerException("daemon unreachable")

    def get(self, identifier):
        from docker.errors import NotFound

        self.lookups.append(identifier)
        if identifier not in self.by_id:
            raise NotFound("container already removed")
        return self.by_id[identifier]

    def close(self):
        self.close_count += 1


def seed_recovery(settings, *, state="failed", attempt_count=1):
    core = Core(settings)
    with core.store.owner():
        core.initialize()
        run = core.store.put(
            "runs",
            {
                "run_id": new_id("run"),
                "state": state,
                "reconciliation_required": True,
                "finished_at": "2026-10-19T10:00:00Z",
                "error": {"reason": "original_failure", "message": "retain history"},
            },
        )
        attempts = []
        containers = {}
        for _ in range(attempt_count):
            task_id, attempt_id = new_id("task"), new_id("attempt")
            core.store.put(
                "tasks",
                {"task_id": task_id, "run_id": run["run_id"], "state": "running"},
            )
            attempt = core.store.put(
                "attempts",
                {
                    "attempt_id": attempt_id,
                    "task_id": task_id,
                    "run_id": run["run_id"],
                    "state": "interrupted",
                    "reconciliation_required": True,
                    "container_id": "container-" + attempt_id,
                },
            )
            attempts.append(attempt)
            containers[attempt["container_id"]] = ControlledContainer(
                settings.project_id, attempt_id
            )
    return core, run, attempts, ControlledDocker(containers)


@pytest.mark.parametrize("state", ["succeeded", "failed", "cancelled", "interrupted"])
def test_confirmed_recovery_clears_terminal_run_hold_and_preserves_history(
    settings, monkeypatch, state
):
    import docker

    core, run, attempts, client = seed_recovery(settings, state=state)
    monkeypatch.setattr(docker, "from_env", lambda: client)
    with core.store.owner():
        with pytest.raises(DockflowError, match="Unresolved prior work"):
            require_direct_idle(core)
        Scheduler(core).reconcile()
        assert core.store.get("runs", run["run_id"]) == {
            **run,
            "reconciliation_required": False,
        }
        recovered = core.store.get("attempts", attempts[0]["attempt_id"])
        assert recovered["state"] == "interrupted"
        assert recovered["reconciliation_required"] is False
        require_direct_idle(core)
    container = client.by_id[attempts[0]["container_id"]]
    assert container.stop_timeouts == [settings.execution["shutdown_grace_seconds"]]
    assert container.attrs["State"]["Running"] is False
    assert client.close_count == 1


@pytest.mark.parametrize("state", ["running", "cancelling"])
def test_confirmed_recovery_interrupts_active_run_and_clears_hold(
    settings, monkeypatch, state
):
    import docker

    core, run, _, client = seed_recovery(settings, state=state)
    monkeypatch.setattr(docker, "from_env", lambda: client)
    with core.store.owner():
        Scheduler(core).reconcile()
        recovered = core.store.get("runs", run["run_id"])
        assert recovered["state"] == "interrupted"
        assert recovered["finished_at"] != run["finished_at"]
        assert recovered["reconciliation_required"] is False
        assert recovered["error"] == {
            "reason": "worker_lost",
            "message": "Recovered after execution owner loss; no automatic rerun",
        }
        require_direct_idle(core)


def test_recovery_leaves_normal_queued_work_unchanged(settings, monkeypatch):
    import docker

    core = seed(settings, "queued")
    client = ControlledDocker({})
    monkeypatch.setattr(docker, "from_env", lambda: client)
    with core.store.owner():
        before = core.store.records()
        Scheduler(core).reconcile()
        assert core.store.records() == before
        with pytest.raises(DockflowError, match="Unresolved prior work"):
            require_direct_idle(core)


def test_recovery_appends_only_the_unsaved_log_tail(settings, monkeypatch):
    import docker

    core, run, attempts, client = seed_recovery(settings)
    attempt = attempts[0]
    container = client.by_id[attempt["container_id"]]
    container.logs = lambda **kw: b"early\nlast\n" if kw["stdout"] else b"warning\n"
    monkeypatch.setattr(docker, "from_env", lambda: client)
    with core.store.owner():
        core.store.log(
            run["run_id"],
            "early\n",
            "stdout",
            attempt["task_id"],
            attempt["attempt_id"],
        )
        Scheduler(core).reconcile()
        Scheduler(core).reconcile()
    entries = core.store.log_entries(run["run_id"])
    assert (
        "".join(e["text"] for e in entries if e["stream"] == "stdout")
        == "early\nlast\n"
    )
    assert "".join(e["text"] for e in entries if e["stream"] == "stderr") == "warning\n"
    assert (
        core.store.attempt_log_snapshot(attempt["attempt_id"], "stdout").decode()
        == "early\nlast\n"
    )


@pytest.mark.parametrize("failure", ["unreachable", "unconfirmed_stop"])
def test_failed_recovery_keeps_terminal_run_and_attempt_held(
    settings, monkeypatch, failure
):
    import docker
    from docker.errors import DockerException

    core, run, attempts, client = seed_recovery(settings)
    client.unreachable = failure == "unreachable"
    client.by_id[attempts[0]["container_id"]].confirm_stop = (
        failure != "unconfirmed_stop"
    )
    monkeypatch.setattr(docker, "from_env", lambda: client)
    with core.store.owner():
        before = core.store.records()
        with pytest.raises((DockerException, DockflowError)):
            Scheduler(core).reconcile()
        assert core.store.get("runs", run["run_id"]) == run
        assert core.store.get("attempts", attempts[0]["attempt_id"]) == attempts[0]
        assert core.store.records() == before
        with pytest.raises(DockflowError, match="Unresolved prior work"):
            require_direct_idle(core)
    assert client.close_count == 1


def test_partial_recovery_keeps_run_hold_until_all_stops_confirmed_then_retry_succeeds(
    settings, monkeypatch
):
    import docker

    core, run, _, client = seed_recovery(settings, attempt_count=2)
    # Follow the actual persistence order so the failure occurs after one accepted recovery.
    first, second = core.store.list("attempts")
    client.by_id[second["container_id"]].confirm_stop = False
    monkeypatch.setattr(docker, "from_env", lambda: client)
    with core.store.owner():
        scheduler = Scheduler(core)
        with pytest.raises(DockflowError, match="stop is unconfirmed"):
            scheduler.reconcile()
        assert (
            core.store.get("attempts", first["attempt_id"])["reconciliation_required"]
            is False
        )
        assert (
            core.store.get("attempts", second["attempt_id"])["reconciliation_required"]
            is True
        )
        assert core.store.get("runs", run["run_id"]) == run
        with pytest.raises(DockflowError, match="Unresolved prior work"):
            require_direct_idle(core)

        client.by_id[second["container_id"]].confirm_stop = True
        scheduler.reconcile()
        assert core.store.get("runs", run["run_id"]) == {
            **run,
            "reconciliation_required": False,
        }
        assert all(
            not attempt["reconciliation_required"]
            for attempt in core.store.list("attempts")
        )
        require_direct_idle(core)
    assert client.lookups.count(first["container_id"]) == 1
    assert client.lookups.count(second["container_id"]) == 2
    assert client.close_count == 2


def test_recovery_refuses_a_different_daemon(settings, monkeypatch):
    import docker

    core, run, attempts, client = seed_recovery(settings)
    with core.store.owner():
        core.store.put("attempts", {**attempts[0], "daemon_id": "original-daemon"})
        client.info = lambda: {"ID": "different-daemon"}
        monkeypatch.setattr(docker, "from_env", lambda: client)
        with pytest.raises(DockflowError, match="different Docker daemon"):
            Scheduler(core).reconcile()
        assert core.store.get("runs", run["run_id"])["reconciliation_required"]
        assert client.lookups == []
