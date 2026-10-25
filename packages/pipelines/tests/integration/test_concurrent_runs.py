"""Distributed Run authority and concurrent project mutation on real PostgreSQL."""

import json
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from dockflow_core.errors import DockflowError
from dockflow_pipelines.config import load_settings
from dockflow_pipelines.core import Core
from dockflow_pipelines.metadata import ControlStore
from dockflow_pipelines.records import new_id


@pytest.fixture
def distributed(database_state):
    store, options = database_state
    if options["backend"] != "postgresql":
        pytest.skip("Distributed execution uses PostgreSQL; SQLite keeps one owner")
    return store, options


def other(store, options, name="other"):
    return ControlStore(store.state.parent / name, store.project_id, storage=options)


def queued(store):
    return store.put("runs", {"run_id": new_id("run"), "state": "queued"})


def expire(store, run_id):
    connection = store.database.adapter.connect()
    try:
        store.database.adapter.execute(
            connection,
            "UPDATE dockflow_run_owners SET lease_expires_at=0 WHERE project_id=? AND run_id=?",
            (store.project_id, run_id),
        )
    finally:
        connection.close()


def test_shared_coordinators_distinct_runs_and_exclusive_maintenance(distributed):
    store, options = distributed
    second = other(store, options)
    with store.owner(), second.owner():
        store.initialize()
        second.initialize()
        first_run, second_run = queued(store), queued(second)
        with (
            store.run_owner(first_run["run_id"]),
            second.run_owner(second_run["run_id"]),
        ):
            store.put("runs", {**first_run, "state": "running"})
            second.put("runs", {**second_run, "state": "running"})
            with pytest.raises(DockflowError, match="another Run"):
                store.put("runs", {**second_run, "state": "failed"})
            with pytest.raises(DockflowError, match="Maintenance"):
                with store.database.maintenance():
                    pass
        with pytest.raises(DockflowError, match="coordinators"):
            store.export_database(store.state.parent / "blocked.sqlite")
    with store.owner():
        store.export_database(store.state.parent / "allowed.sqlite")


def test_claim_race_expiry_fencing_and_late_release(distributed):
    store, options = distributed
    second = other(store, options)
    with store.owner(), second.owner():
        store.initialize()
        run = queued(store)
        with store.run_owner(run["run_id"]) as old:
            store.put("runs", {**run, "state": "running"})
            with pytest.raises(DockflowError) as busy:
                with second.run_owner(run["run_id"]):
                    pass
            assert busy.value.code == "RUN_BUSY"
            old.stop()
            expire(store, run["run_id"])
            with second.run_owner(run["run_id"], recovering=True) as replacement:
                assert replacement.fence == old.fence + 1
                before = len(second.records())
                for operation in (
                    lambda: store.put("runs", {**run, "state": "succeeded"}),
                    lambda: store.log(run["run_id"], "late log"),
                    old.renew,
                ):
                    with pytest.raises(DockflowError) as lost:
                        operation()
                    assert lost.value.code == "OWNERSHIP_LOST"
                assert len(second.records()) == before
                second.put("runs", {**run, "state": "interrupted"})
        assert second.get("runs", run["run_id"])["state"] == "interrupted"


def test_remote_cancellation_survives_stale_worker_run_snapshot(distributed):
    store, options = distributed
    settings = settings_for(store, options, "control")
    control = Core(settings)
    with store.owner(), control.store.owner():
        store.initialize()
        run = queued(store)
        with store.run_owner(run["run_id"]):
            stale = store.put("runs", {**run, "state": "running"})
            control.cancel(run["run_id"])
            updated = store.put("runs", stale)
            assert (
                updated["cancellation_requested"] and updated["state"] == "cancelling"
            )
            assert store.check_execution() is None
            with pytest.raises(DockflowError, match="Stop intent"):
                store.commit_output_set(
                    run["run_id"], new_id("task"), new_id("attempt"), {}, {}
                )


def settings_for(store, options, name):
    root = store.state.parent / name
    root.mkdir(exist_ok=True)
    configuration = root / "project.toml"
    configuration.write_text(
        f'schema_version=1\n[project]\nid="{store.project_id}"\n[state]\n'
        + "\n".join(f"{key}={json.dumps(value)}" for key, value in options.items())
        + "\n[artifacts]\nmanaged_root="
        + json.dumps(str(store.state.parent / "managed"))
        + "\n"
    )
    return load_settings(configuration)


def definition():
    return {
        "pipelineInfo": {"name": "distributed-test"},
        "schemaVersion": "2.1.0",
        "sdkVersion": "kfp-2.17.0",
        "root": {"executorLabel": "exec-echo"},
        "deploymentSpec": {
            "executors": {
                "exec-echo": {
                    "container": {
                        "image": "python:3.13-slim",
                        "command": ["echo", "retained"],
                    }
                }
            }
        },
    }


def test_concurrent_admission_idempotency_and_global_sequence(distributed):
    store, options = distributed
    first = Core(settings_for(store, options, "first"))
    second = Core(settings_for(store, options, "second"))
    with first.store.owner(), second.store.owner():
        first.initialize()
        second.initialize()
        request = {"pipeline_spec": definition()}
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda core: core.submit(request, "same-request"), (first, second)
                )
            )
        assert results[0][0]["run_id"] == results[1][0]["run_id"]
        assert sorted(repeated for _, repeated in results) == [False, True]
        assert len(first.store.list("runs")) == 1
        assert len(first.store.list("experiments")) == 1
        assert first.store.project_metadata(
            "pagination"
        ) == second.store.project_metadata("pagination")
        assert first.store.check()["valid"]
        records = first.store.records()
        assert [record["sequence"] for record in records] == list(
            range(1, len(records) + 1)
        )
        first.settings.service["queue_capacity"] = 1
        with pytest.raises(DockflowError) as full:
            first.submit(request)
        assert full.value.code == "QUEUE_FULL"


PROCESS_SCRIPT = r"""
import json,sys
from pathlib import Path
from dockflow_pipelines.metadata import ControlStore
store=ControlStore(Path(sys.argv[1]),sys.argv[2],storage=json.loads(sys.argv[3]))
with store.owner():
    store.initialize()
    with store.run_owner(sys.argv[4]) as claim:
        store.put("runs",{**store.get("runs",sys.argv[4]),"state":"running"})
        print(claim.fence,flush=True)
        sys.stdin.readline()
"""


def test_independent_process_claims_and_crash_recovery(distributed):
    store, options = distributed
    with store.owner():
        store.initialize()
        runs = [queued(store), queued(store)]
    processes = []
    try:
        for index, run in enumerate(runs):
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    PROCESS_SCRIPT,
                    str(store.state.parent / f"process-{index}"),
                    store.project_id,
                    json.dumps(options),
                    run["run_id"],
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            processes.append(process)
            assert process.stdout.readline().strip() == "1"
        with store.owner():
            assert all(
                store.get("runs", run["run_id"])["state"] == "running" for run in runs
            )
            for run in runs:
                with pytest.raises(DockflowError) as busy:
                    with store.run_owner(run["run_id"], recovering=True):
                        pass
                assert busy.value.code == "RUN_BUSY"
            processes[0].kill()
            processes[0].wait(timeout=10)
            expire(store, runs[0]["run_id"])
            with store.run_owner(runs[0]["run_id"], recovering=True) as replacement:
                assert replacement.fence == 2
                store.put("runs", {**runs[0], "state": "interrupted"})
            assert processes[1].poll() is None
            assert store.get("runs", runs[1]["run_id"])["state"] == "running"
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)


@pytest.mark.parametrize("fault", ["expiry", "heartbeat"])
def test_expired_run_cannot_commit_cache_publication(distributed, monkeypatch, fault):
    import time

    from dockflow_core.canonical import digest
    from dockflow_pipelines.cache_registry import Registry
    from dockflow_pipelines.cache_storage import make_manifest

    store, _ = distributed
    with store.owner():
        store.initialize()
        run = queued(store)
        registry = Registry(
            {
                "database": store.database.options,
                "storage_identity": "distributed-cache-test",
            },
            store.project_id,
        )
        registry.initialize()
        ownership = registry.resolve_or_claim(
            digest("publication"),
            "producer",
            str(uuid.uuid4()),
            run["run_id"],
            new_id("task"),
        ).ownership
        # Use the claim's actual task identity in its immutable provenance.
        manifest = make_manifest(
            {},
            {},
            {},
            {
                "run_id": run["run_id"],
                "task_id": registry.inspect(ownership.cache_key)["attempts"][0][
                    "step_id"
                ],
                "attempt_id": ownership.attempt_id,
            },
            ownership.cache_key,
            "distributed-cache-test",
        )
        registry.begin_validation(ownership)
        transaction = Registry._transaction

        def delayed(self, callback):
            def pause_before_commit(connection):
                result = callback(connection)
                if fault == "expiry":
                    time.sleep(0.3)
                else:
                    store.database.run_claim.lost.set()
                return result

            return transaction(self, pause_before_commit)

        with store.run_owner(
            run["run_id"], {"run_lease_seconds": 0.2, "run_heartbeat_seconds": 10}
        ):
            store.put("runs", {**run, "state": "running"})
            with monkeypatch.context() as patch:
                patch.setattr(Registry, "_transaction", delayed)
                with pytest.raises(DockflowError) as lost:
                    store.publish_cache_result(registry.options, ownership, manifest)
                assert lost.value.code == "OWNERSHIP_LOST"
        assert registry.inspect(ownership.cache_key)["artifacts"] == []
        assert not store.database.poisoned


def test_heartbeat_connection_failure_revokes_only_its_run(distributed, monkeypatch):
    store, options = distributed
    second = other(store, options)
    with store.owner(), second.owner():
        store.initialize()
        run, another = queued(store), queued(second)
        with store.run_owner(run["run_id"]) as claim:
            with monkeypatch.context() as patch:

                def unavailable(**kwargs):
                    raise ConnectionError("injected provider outage")

                patch.setattr(store.database.adapter, "connect", unavailable)
                with pytest.raises(DockflowError):
                    claim.renew()
            assert store.check_execution() == "ownership_lost"
            with pytest.raises(DockflowError):
                store.log(run["run_id"], "unauthorized")
            with second.run_owner(another["run_id"]):
                second.put("runs", {**another, "state": "running"})
                assert second.check_execution() is None


def test_maintenance_blocks_independent_cache_transactions(distributed, monkeypatch):
    import threading

    from dockflow_core.canonical import digest
    from dockflow_pipelines.cache_registry import Registry

    store, options = distributed
    registry = Registry(
        {"database": options, "storage_identity": "maintenance-test"}, store.project_id
    )
    with store.owner():
        store.initialize()
        registry.initialize()
        attempted = threading.Event()
        connect = registry._connect

        def starting():
            attempted.set()
            return connect()

        monkeypatch.setattr(registry, "_connect", starting)
        with ThreadPoolExecutor(max_workers=1) as pool:
            with store.database.maintenance():
                future = pool.submit(
                    registry.resolve_or_claim,
                    digest("maintenance"),
                    "producer",
                    str(uuid.uuid4()),
                    new_id("run"),
                    new_id("task"),
                )
                assert attempted.wait(2)
                assert not future.done()
                with pytest.raises(DockflowError), other(store, options).owner():
                    pass
            assert future.result(timeout=10).kind == "PRODUCE"


def test_direct_submission_reserves_ownership_before_service_dispatch(distributed):
    store, options = distributed
    first = Core(settings_for(store, options, "direct"))
    second = other(store, options)
    with first.store.owner(), second.owner():
        first.initialize()
        run, _ = first.submit({"pipeline_spec": definition()}, reserve=True)
        with pytest.raises(DockflowError) as busy:
            with second.run_owner(run["run_id"]):
                pass
        assert busy.value.code == "RUN_BUSY"
        with first.store.run_owner(run["run_id"]) as claim:
            assert claim.fence == 1
            first.store.put("runs", {**run, "state": "succeeded"})


def test_independent_process_admission_has_one_idempotent_result(distributed):
    store, options = distributed
    configurations = [
        settings_for(store, options, f"admission-{index}").config_path
        for index in range(4)
    ]
    script = r"""
import json,sys
from dockflow_pipelines.config import load_settings
from dockflow_pipelines.core import Core
core=Core(load_settings(sys.argv[1]))
with core.store.owner():
    core.initialize()
    print("ready",flush=True)
    sys.stdin.readline()
    run,_=core.submit({"pipeline_spec":json.loads(sys.argv[2])},"concurrent-admission")
    print(run["run_id"],flush=True)
"""
    processes = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                script,
                str(configuration),
                json.dumps(definition()),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for configuration in configurations
    ]
    try:
        for process in processes:
            assert process.stdout.readline().strip() == "ready"
        for process in processes:
            process.stdin.write("submit\n")
            process.stdin.flush()
        identifiers = []
        for process in processes:
            output, error = process.communicate(timeout=20)
            assert process.returncode == 0, error
            identifiers.append(output.strip())
        assert len(set(identifiers)) == 1 and identifiers[0].startswith("run_")
        assert len(store.list("runs")) == 1
        assert len(store.list("experiments")) == 1
        assert store.check()["valid"]
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)


def test_cache_consumer_does_not_rewrite_live_producer_lifecycle(distributed):
    from dockflow_core.canonical import digest
    from dockflow_pipelines.cache_registry import Registry
    from dockflow_pipelines.cache_storage import make_manifest

    store, options = distributed
    second = other(store, options)
    with store.owner(), second.owner():
        store.initialize()
        first_run, second_run = queued(store), queued(second)
        with (
            store.run_owner(first_run["run_id"]),
            second.run_owner(second_run["run_id"]),
        ):
            store.put("runs", {**first_run, "state": "running"})
            task_id = new_id("task")
            store.put(
                "tasks",
                {"task_id": task_id, "run_id": first_run["run_id"], "state": "running"},
            )
            registry = Registry(
                {"database": options, "storage_identity": "live-producer-test"},
                store.project_id,
            )
            registry.initialize()
            ownership = registry.resolve_or_claim(
                digest("live-producer"),
                "producer",
                str(uuid.uuid4()),
                first_run["run_id"],
                task_id,
            ).ownership
            attempt = store.put(
                "attempts",
                {
                    "attempt_id": ownership.attempt_id,
                    "run_id": first_run["run_id"],
                    "task_id": task_id,
                    "state": "running",
                    "signature": {"value": ownership.cache_key},
                    "outputs": {},
                    "output_parameters": {},
                },
            )
            manifest = make_manifest(
                {},
                {"result": "published"},
                {"parameters": {"result": {"parameterType": "STRING"}}},
                {
                    "run_id": first_run["run_id"],
                    "task_id": task_id,
                    "attempt_id": ownership.attempt_id,
                },
                ownership.cache_key,
                "live-producer-test",
            )
            registry.begin_validation(ownership)
            store.publish_cache_result(registry.options, ownership, manifest)
            snapshot = second.import_cache_result(manifest, {})
            assert snapshot["output_parameters"] == {"result": "published"}
            assert store.get("attempts", ownership.attempt_id) == attempt
            assert store.get("runs", first_run["run_id"])["state"] == "running"
            assert second.verify_output_set(ownership.attempt_id)["valid"]
            assert second.import_cache_result(manifest, {}) == snapshot
            assert store.check()["valid"]
            # The original owner can finish its own journal normally afterwards.
            store.commit_output_set(
                first_run["run_id"],
                task_id,
                ownership.attempt_id,
                {},
                {"result": "published"},
            )
            store.put(
                "attempts",
                {
                    **attempt,
                    "state": "succeeded",
                    "output_parameters": {"result": "published"},
                },
            )
            task = store.get("tasks", task_id)
            store.put(
                "tasks",
                {
                    **task,
                    "state": "succeeded",
                    "outputs": {},
                    "output_parameters": {"result": "published"},
                },
            )
            store.put("runs", {**first_run, "state": "succeeded"})
            second.put("runs", {**second_run, "state": "succeeded"})
    snapshot_path = store.state.parent / "observations.sqlite"
    with store.owner(exclusive=True):
        assert store.rebuild(apply=True)["rebuilt"]
        assert store.check()["valid"]
        store.export_database(snapshot_path)
    restored = ControlStore(
        store.state.parent / "restored-observations", store.project_id
    )
    with restored.owner():
        restored.import_database(snapshot_path)
        restored.initialize()
        assert restored.check()["valid"]
        assert restored.get("attempts", ownership.attempt_id)["state"] == "succeeded"
        assert restored.database.cache_observation(ownership.attempt_id) is not None
