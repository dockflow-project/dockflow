"""Database ownership: real contenders, crashes, session loss and rollback."""

import json
import os
import subprocess
import sys
import threading

import pytest
from dockflow_database.errors import DockflowError
from dockflow_pipelines.canonical import json_bytes
from dockflow_pipelines.metadata import ControlStore
from dockflow_pipelines.records import new_id


def contender(store, options, root=None):
    return ControlStore(
        root or store.state.parent / "worker-b", store.project_id, storage=options
    )


def test_competing_owner_readonly_history_and_diagnostic_safety(database_state):
    store, options = database_state
    other = contender(store, options)
    with store.owner("http://127.0.0.1:8080", exclusive=True):
        store.initialize()
        identifier = new_id("run")
        store.put("runs", {"run_id": identifier, "state": "succeeded"})
        owner = store.database.owner_metadata()
        with pytest.raises(DockflowError) as error, other.owner():
            pytest.fail("A second owner was admitted")
        assert error.value.code == "CONFLICT"
        assert error.value.details[0]["owner"] == owner
        assert other.get("runs", identifier)["state"] == "succeeded"
        assert store.database.owner_metadata() == owner
    with other.owner():
        assert other.database.owner_metadata()["owner_id"] != owner["owner_id"]
        other.initialize()
        assert other.check()["valid"]


@pytest.mark.parametrize("crash", [False, True])
def test_independent_process_exit_releases_ownership(database_state, crash):
    store, options = database_state
    script = r"""
import json, sys
from pathlib import Path
from dockflow_pipelines.metadata import ControlStore
from dockflow_pipelines.records import new_id
store = ControlStore(Path(sys.argv[1]), sys.argv[2], storage=json.loads(sys.argv[3]))
with store.owner(exclusive=True):
    store.initialize()
    run = store.put('runs', {'run_id': new_id('run'), 'state': 'succeeded'})
    print(run['run_id'], flush=True)
    sys.stdin.readline()
"""
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            script,
            str(store.state),
            store.project_id,
            json.dumps(options),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        identifier = process.stdout.readline().strip()
        assert identifier.startswith("run_"), process.stderr.read()
        with (
            pytest.raises(DockflowError, match="owned"),
            contender(store, options).owner(),
        ):
            pass
        if crash:
            process.kill()
        else:
            process.stdin.write("exit\n")
            process.stdin.flush()
        process.wait(timeout=15)
        with contender(store, options).owner() as recovered:
            recovered.initialize()
            assert recovered.get("runs", identifier)["state"] == "succeeded"
            assert recovered.check()["valid"]
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)


def test_projection_failure_rolls_back_journal_and_resources(
    database_state, monkeypatch
):
    store, _ = database_state
    with store.owner(exclusive=True):
        store.initialize()
        before = store.records()
        original = store._project
        identifier = new_id("run")

        def fail_after_projection(record):
            original(record)
            raise OSError("injected projection failure")

        with monkeypatch.context() as patch:
            patch.setattr(store, "_project", fail_after_projection)
            with pytest.raises(DockflowError, match="rolled back"):
                store.put("runs", {"run_id": identifier, "state": "succeeded"})
        assert store.records() == before
        assert store.list("runs") == []
        with pytest.raises(DockflowError, match="not found"):
            store.get("runs", identifier)
        store.put("runs", {"run_id": identifier, "state": "succeeded"})
        assert store.records()[-1]["sequence"] == len(before) + 1
        assert store.check()["valid"]


def test_project_isolation_and_database_only_retention(database_state):
    store, options = database_state
    identifier = new_id("run")
    definition = new_id("definition")
    with store.owner(exclusive=True):
        store.initialize()
        store.put("runs", {"run_id": identifier, "state": "succeeded"})
        store.save_definition_source(definition, b"exact compiled bytes\n")
        store.log(identifier, "retained stdout", "stdout")
    assert not (store.state / "runs").exists()
    assert not (store.state / "records").exists()
    assert not (store.state / "definitions").exists()
    isolated = ControlStore(
        store.state.parent / "different-project",
        store.project_id + "-other",
        storage=options,
    )
    assert isolated.list("runs") == []
    with contender(store, options).owner() as recovered:
        recovered.initialize()
        assert recovered.definition_source(definition) == b"exact compiled bytes\n"
        assert recovered.log_entries(identifier)[0]["text"] == "retained stdout"
        assert recovered.check()["valid"]
    if options["backend"] == "postgresql":
        assert not store.state.exists()


def test_nested_threads_share_one_acquisition(database_state):
    store, options = database_state
    with store.owner(exclusive=True):
        owner = store.database.owner_metadata()

        def participate():
            with store.owner(exclusive=True):
                assert store.database.owner_metadata() == owner

        thread = threading.Thread(target=participate)
        thread.start()
        thread.join(timeout=10)
        assert not thread.is_alive()
        with pytest.raises(DockflowError), contender(store, options).owner():
            pass
    with contender(store, options).owner():
        pass


def test_postgresql_lost_session_cannot_write_after_takeover(database_state):
    store, options = database_state
    if options["backend"] != "postgresql":
        pytest.skip("PostgreSQL session fencing")
    import psycopg

    with store.owner(exclusive=True):
        store.initialize()
        connection = store.database.connection
        pid = connection.info.backend_pid
        with psycopg.connect(
            os.environ[options["dsn_env"]], autocommit=True
        ) as administrative:
            administrative.execute("SELECT pg_terminate_backend(%s)", (pid,))
        with contender(store, options).owner() as replacement:
            replacement.initialize()
            replacement.put("runs", {"run_id": new_id("run"), "state": "succeeded"})
            with pytest.raises(DockflowError):
                store.put("runs", {"run_id": new_id("run"), "state": "succeeded"})
        assert len(contender(store, options).list("runs")) == 1


@pytest.mark.parametrize("path_kind", ["symlink", "directory", "fifo"])
def test_unsafe_sqlite_database_types_fail_closed(tmp_path, path_kind):
    path = tmp_path / "state.sqlite"
    target = tmp_path / "untouched"
    target.write_bytes(b"untouched")
    if path_kind == "symlink":
        path.symlink_to(target)
    elif path_kind == "directory":
        path.mkdir()
    else:
        if not hasattr(os, "mkfifo"):
            pytest.skip("FIFO requires POSIX")
        os.mkfifo(path)
    store = ControlStore(
        tmp_path / "work",
        "dockflow-unsafe",
        storage={"backend": "sqlite", "database": str(path)},
    )
    with pytest.raises(DockflowError), store.owner():
        pass
    assert target.read_bytes() == b"untouched"


def test_untrusted_owner_diagnostics_never_leak_credentials(database_state):
    store, options = database_state
    with store.owner(exclusive=True):
        with store.database.transaction() as connection:
            store.database.execute(
                connection,
                "UPDATE dockflow_state_owners SET value=? WHERE project_id=?",
                (
                    json_bytes(
                        {
                            "schema_version": 1,
                            "endpoint": "http://secret:password@127.0.0.1:8080",
                            "private": "hidden",
                        }
                    ),
                    store.project_id,
                ),
            )
        with pytest.raises(DockflowError) as error, contender(store, options).owner():
            pass
        assert "password" not in json.dumps(error.value.as_dict())
        assert "hidden" not in json.dumps(error.value.as_dict())


def test_consistent_read_snapshot_during_committed_updates(database_state):
    store, options = database_state
    identifier = new_id("run")
    with store.owner(exclusive=True):
        store.initialize()
        original = store.put("runs", {"run_id": identifier, "state": "running"})
        reader = contender(store, options)
        with reader.database.snapshot():
            assert reader.get("runs", identifier)["state"] == "running"
            store.put("runs", {**original, "state": "succeeded"})
            assert reader.get("runs", identifier)["state"] == "running"
        assert reader.get("runs", identifier)["state"] == "succeeded"


def test_lost_commit_response_requires_inspection_and_fresh_ownership(
    database_state, monkeypatch
):
    store, options = database_state
    identifier = new_id("run")
    with store.owner(exclusive=True):
        store.initialize()
        execute = store.database.execute
        lost = False

        def execute_with_lost_response(connection, sql, parameters=()):
            nonlocal lost
            result = execute(connection, sql, parameters)
            if sql == "COMMIT" and not lost:
                lost = True
                raise DockflowError("injected lost COMMIT response", "UNAVAILABLE", 503)
            return result

        with monkeypatch.context() as patch:
            patch.setattr(store.database, "execute", execute_with_lost_response)
            with pytest.raises(DockflowError, match="lost COMMIT"):
                store.put("runs", {"run_id": identifier, "state": "succeeded"})
        assert store.get("runs", identifier)["state"] == "succeeded"
        assert store.reconciliation_required
        with pytest.raises(DockflowError, match="uncertain"):
            store.put("runs", {"run_id": new_id("run"), "state": "succeeded"})
    with contender(store, options).owner() as recovered:
        recovered.initialize()
        assert len(recovered.list("runs")) == 1
        assert recovered.check()["valid"]
