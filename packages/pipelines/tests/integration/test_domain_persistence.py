"""Domain records retain replay/transaction guarantees without virtual files."""

import json
import subprocess
import sys

import pytest
from dockflow_core.errors import DockflowError
from dockflow_pipelines.records import new_id


def seed(store):
    run_id, task_id, attempt_id = (new_id(kind) for kind in ("run", "task", "attempt"))
    store.put("runs", {"run_id": run_id, "state": "succeeded"})
    store.put("tasks", {"task_id": task_id, "run_id": run_id, "state": "succeeded"})
    store.put(
        "attempts",
        {
            "attempt_id": attempt_id,
            "task_id": task_id,
            "run_id": run_id,
            "state": "succeeded",
        },
    )
    return run_id, task_id, attempt_id


def test_numeric_journal_and_single_resource_projection(database_state):
    store, _ = database_state
    with store.owner():
        store.initialize()
        run_id, task_id, attempt_id = seed(store)
        definition_id = new_id("definition")
        source = b"exact compiled source\n"
        store.save_definition_source(definition_id, source)
        store.snapshot_attempt_log(run_id, task_id, attempt_id, "stdout", b"retained\n")
        store.commit_output_set(run_id, task_id, attempt_id, {}, {})
        tables = store.database.adapter.tables(store.database.connection)
        assert "dockflow_state_objects" not in tables
        events = store.database.events()
        assert [sequence for sequence, _ in events] == list(range(1, len(events) + 1))
        assert {event["kind"] for _, event in events} >= {
            "resource_put",
            "definition_source",
            "attempt_log_snapshot",
            "output_set",
        }
        assert store.definition_source(definition_id) == source
        assert store.attempt_log_snapshot(attempt_id, "stdout") == b"retained\n"
        assert store.has_output_set(attempt_id)
        assert len(store.database.resources("runs")) == 1
        assert store.check()["valid"]


def test_rebuild_repairs_domain_snapshots_and_removes_orphan_resources(database_state):
    store, _ = database_state
    with store.owner():
        store.initialize()
        run_id, task_id, attempt_id = seed(store)
        definition_id = new_id("definition")
        store.save_definition_source(definition_id, b"source")
        store.snapshot_attempt_log(run_id, task_id, attempt_id, "stderr", b"warning")
        store.commit_output_set(run_id, task_id, attempt_id, {}, {})
        alias = store.database.internal_id("runs", run_id)
        with store.database.transaction() as connection:
            for table in (
                "dockflow_definition_sources",
                "dockflow_log_snapshots",
                "dockflow_output_sets",
            ):
                store.database.execute(
                    connection,
                    f"UPDATE {table} SET value=? WHERE project_id=?",
                    (b"{}", store.project_id),
                )
            store.database.put_resource(
                "runs", {"run_id": new_id("run"), "state": "succeeded"}
            )
        assert not store.check()["valid"]
        assert store.rebuild(apply=True)["rebuilt"]
        assert store.definition_source(definition_id) == b"source"
        assert store.attempt_log_snapshot(attempt_id, "stderr") == b"warning"
        assert store.has_output_set(attempt_id)
        assert len(store.list("runs")) == 1
        assert store.database.internal_id("runs", run_id) == alias
        assert store.check()["valid"]


@pytest.mark.parametrize("snapshot", ["source", "log"])
def test_snapshot_projection_failure_rolls_back_event_and_counter(
    database_state, monkeypatch, snapshot
):
    store, _ = database_state
    with store.owner():
        store.initialize()
        run_id, task_id, attempt_id = seed(store)
        count = len(store.records())

        def fail(*args):
            raise RuntimeError("injected domain projection failure")

        with monkeypatch.context() as patch:
            method = (
                "put_definition_source" if snapshot == "source" else "put_log_snapshot"
            )
            patch.setattr(store.database, method, fail)
            with pytest.raises(DockflowError, match="rolled back"):
                if snapshot == "source":
                    store.save_definition_source(new_id("definition"), b"source")
                else:
                    store.snapshot_attempt_log(
                        run_id, task_id, attempt_id, "stdout", b"log"
                    )
        assert len(store.records()) == count
        assert store.database.current_sequence() == count
        assert not store.reconciliation_required
        assert store.check()["valid"]


def test_log_and_resource_mutations_cannot_invert_transaction_locks(database_state):
    store, options = database_state
    script = """
import json,os,sys,threading
from pathlib import Path
from dockflow_pipelines.metadata import ControlStore
from dockflow_pipelines.records import new_id
store=ControlStore(Path(sys.argv[1]),sys.argv[2],storage=json.loads(sys.argv[3]))
with store.owner():
    store.initialize()
    run_id=new_id('run')
    store.put('runs',{'run_id':run_id,'state':'succeeded'})
    logging=threading.Event(); release=threading.Event(); entered=threading.Event()
    original=store.append
    def append(kind,payload):
        if kind=='log':
            logging.set()
            if not release.wait(5): os._exit(4)
        return original(kind,payload)
    store.append=append
    gate=store.database.scope.serialize
    def transaction(connection):
        if threading.current_thread().name=='resource': entered.set()
        return gate(connection)
    store.database.scope.serialize=transaction
    errors=[]
    def write_log():
        try: store.log(run_id,'retained output')
        except BaseException as error: errors.append(error)
    def write_resource():
        try: store.put('runs',{'run_id':run_id,'state':'succeeded'})
        except BaseException as error: errors.append(error)
    first=threading.Thread(target=write_log,daemon=True)
    second=threading.Thread(target=write_resource,name='resource',daemon=True)
    first.start()
    assert logging.wait(5)
    second.start()
    entered.wait(0.2)
    release.set()
    first.join(4); second.join(4)
    if first.is_alive() or second.is_alive(): os._exit(3)
    assert not errors
    assert store.log_entries(run_id)[0]['text']=='retained output'
    assert store.check()['valid']
print('valid')
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(store.state),
            store.project_id,
            json.dumps(options),
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "valid"
