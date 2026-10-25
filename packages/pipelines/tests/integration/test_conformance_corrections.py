"""Behavioral regressions for the specification conformance review."""

import copy
import json
import os
import threading
from dataclasses import replace
from types import SimpleNamespace

import pytest
from dockflow_core.canonical import digest
from dockflow_core.errors import DockflowError
from dockflow_core.time import utc_now
from dockflow_pipelines.cache_storage import make_manifest
from dockflow_pipelines.cli import file_request
from dockflow_pipelines.client import Client
from dockflow_pipelines.compiled_source import read_compiled_source
from dockflow_pipelines.config import load_settings
from dockflow_pipelines.core import Core
from dockflow_pipelines.definitions import DefinitionError, load_definition
from dockflow_pipelines.engine import _Execution, execute_run
from dockflow_pipelines.executor import resource_limits
from dockflow_pipelines.projections import DOMAINS
from dockflow_pipelines.records import new_id
from dockflow_pipelines.service import Scheduler, create_app
from fastapi.testclient import TestClient


def fixture_definition():
    return {
        "pipelineInfo": {"name": "test-pipeline"},
        "schemaVersion": "2.1.0",
        "sdkVersion": "kfp-2.17.0",
        "components": {
            "comp-echo": {
                "executorLabel": "exec-echo",
                "inputDefinitions": {
                    "parameters": {"value": {"parameterType": "STRING"}}
                },
            }
        },
        "deploymentSpec": {
            "executors": {
                "exec-echo": {
                    "container": {
                        "image": "python:3.13-slim",
                        "command": ["echo"],
                        "args": ["{{$.inputs.parameters['value']}}"],
                    }
                }
            }
        },
        "root": {
            "inputDefinitions": {
                "parameters": {
                    "value": {"parameterType": "STRING", "defaultValue": "hello"}
                }
            },
            "dag": {
                "tasks": {
                    "echo": {
                        "componentRef": {"name": "comp-echo"},
                        "inputs": {
                            "parameters": {
                                "value": {"componentInputParameter": "value"}
                            }
                        },
                    }
                }
            },
        },
    }


@pytest.fixture
def settings(tmp_path):
    source = tmp_path / "pipeline.json"
    source.write_text(json.dumps(fixture_definition()))
    config = tmp_path / "dockflow.toml"
    config.write_text(
        'schema_version=1\n[project]\nid="conformance"\n'
        '[definitions.pipelines]\ntest="pipeline.json"\n'
        "[execution]\ntimeout_seconds=17\nshutdown_grace_seconds=3\ncpu_limit=0.5\n"
        "[service]\nqueue_capacity=20\n"
    )
    return load_settings(config)


@pytest.mark.parametrize("failure", ["queue", "recovery", "process_start"])
def test_scheduler_failure_closes_admission_and_preserves_queue(
    settings, monkeypatch, failure
):
    application = create_app(settings, execute=False)
    with TestClient(application) as client:
        run = client.post(
            "/dockflow/v1/runs", json={"pipeline_spec": fixture_definition()}
        ).json()
        scheduler = application.state.scheduler

        def fail(*args, **kwargs):
            raise OSError("injected dispatch failure")

        with monkeypatch.context() as patch:
            if failure == "queue":
                patch.setattr(
                    application.state.core.store.database.queries, "queued", fail
                )
            elif failure == "recovery":
                patch.setattr(
                    application.state.core.store.database.adapter,
                    "supports_shared_owners",
                    True,
                )
                patch.setattr(scheduler, "reconcile", fail)
            else:
                import multiprocessing.context

                patch.setattr(multiprocessing.context.SpawnProcess, "start", fail)
            scheduler.execution_enabled = True
            scheduler.thread = threading.current_thread()
            scheduler._loop()
        assert not scheduler.available() and scheduler.stopping.is_set()
        assert "restart" in scheduler.error
        assert client.get("/health/ready").status_code == 503
        assert (
            client.post(
                "/dockflow/v1/runs", json={"pipeline_spec": fixture_definition()}
            ).status_code
            == 503
        )
        assert (
            client.post(
                "/apis/v2beta1/runs", json={"pipeline_spec": fixture_definition()}
            ).status_code
            == 503
        )
        assert (
            application.state.core.store.get("runs", run["run_id"])["state"] == "queued"
        )
    with TestClient(create_app(settings, execute=False)) as client:
        assert client.get("/health/ready").status_code == 200
        assert (
            client.get("/dockflow/v1/runs/" + run["run_id"]).json()["state"] == "queued"
        )


def test_remote_name_uses_catalog_pointer_after_rollback(settings, monkeypatch):
    application = create_app(settings, execute=False)
    source = settings.definitions["pipelines"]["test"]
    original = source.read_bytes()
    with TestClient(application) as http:
        remote = Client("http://testserver")

        def request(method, path, body=None, query=None, key=None):
            response = http.request(method, path, json=body, params=query)
            if response.status_code >= 400:
                error = response.json()["error"]
                raise DockflowError(
                    error["message"], error["code"], response.status_code
                )
            return response.json()

        monkeypatch.setattr(remote, "request", request)
        first = remote.operate("definitions.show", {"id": "test"})
        changed = fixture_definition()
        changed["pipelineInfo"]["name"] = "changed"
        source.write_text(json.dumps(changed))
        second = remote.operate("definitions.show", {"id": "test"})
        assert first["definition_id"] != second["definition_id"]
        source.write_bytes(original)
        rolled_back = remote.operate("definitions.show", {"id": "test"})
        assert rolled_back["definition_id"] == first["definition_id"]
        assert (
            application.state.core.resolve("test")["definition_id"]
            == first["definition_id"]
        )
        assert len(application.state.core.store.list("definitions")) == 2
        request_values = file_request("test", settings, remote)
        submitted = http.post("/dockflow/v1/runs", json=request_values)
        assert submitted.status_code == 202
        assert submitted.json()["definition_id"] == first["definition_id"]
        source.unlink()
        with pytest.raises(DockflowError):
            remote.operate("definitions.show", {"id": "test"})
        with pytest.raises(DockflowError, match="Unknown"):
            remote.operate("definitions.show", {"id": "unknown"})


def test_execution_choices_survive_coordinator_changes(
    settings, tmp_path, database_state
):
    store, options = database_state
    settings = replace(
        settings, project_id=store.project_id, state=store.state, state_storage=options
    )
    definition = load_definition(fixture_definition())
    policy = tmp_path / "policies.json"
    policy.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "definition_sha256": definition.sha256,
                "tasks": {"echo": {"cache_safe": False, "retry_safe": True}},
            }
        )
    )
    settings.policies["file"] = policy
    settings.images["pull_policy"] = "never"
    settings.execution["task_mounts"] = [
        {"source": tmp_path / "first", "target": "/data", "read_only": True}
    ]
    core = Core(settings)
    with core.store.owner():
        core.initialize()
        run, _ = core.submit({"pipeline_spec": fixture_definition()})
        accepted = copy.deepcopy(run["execution_choices"])
        policy.unlink()
        current = replace(
            settings,
            work_directory=tmp_path / "second-work",
            execution={
                **settings.execution,
                "timeout_seconds": 0,
                "cpu_limit": 4,
                "shutdown_grace_seconds": 99,
                "task_mounts": [
                    {
                        "source": tmp_path / "second",
                        "target": "/data",
                        "read_only": True,
                    },
                    {
                        "source": tmp_path / "extra",
                        "target": "/extra",
                        "read_only": False,
                    },
                ],
            },
            reuse={"scope": "none"},
            images={"pull_policy": "always"},
            cache={**settings.cache, "wait_seconds": 5},
        )
        other = Core(current)
        detached = other.store.get("runs", run["run_id"])
        execution = _Execution(other.store, other.artifacts, current, detached)
        assert execution.deadline == 17
        assert execution.settings.execution["cpu_limit"] == 0.5
        assert execution.settings.execution["shutdown_grace_seconds"] == 3
        assert execution.settings.images == {"pull_policy": "never"}
        assert execution.settings.reuse == settings.reuse
        assert (
            execution.settings.cache["wait_seconds"] == settings.cache["wait_seconds"]
        )
        assert execution.policies == {"echo": {"cache_safe": False, "retry_safe": True}}
        assert execution.pipeline_root.is_relative_to(current.work_directory)
        assert execution.settings.execution["task_mounts"] == [
            current.execution["task_mounts"][0]
        ]
        assert "source" not in accepted["mounts"][0]
        with pytest.raises(DockflowError, match="immutable"):
            core.store.put(
                "runs",
                {
                    **run,
                    "execution_choices": {
                        **accepted,
                        "images": {"pull_policy": "always"},
                    },
                },
            )
        for execution_options in (
            {**current.execution, "cpu_limit": 0.25},
            {**current.execution, "task_mounts": []},
            {
                **current.execution,
                "task_mounts": [
                    {"source": tmp_path, "target": "/data", "read_only": False}
                ],
            },
        ):
            incompatible = replace(current, execution=execution_options)
            with pytest.raises(DockflowError):
                _Execution(core.store, core.artifacts, incompatible, run)
        result = execute_run(
            core.store,
            core.artifacts,
            replace(current, execution={**current.execution, "cpu_limit": 0.25}),
            run,
        )
        assert result["state"] == "failed"
        assert result["error"]["phase"] == "execution_configuration"
        assert result["execution_choices"] == accepted


def test_recovery_finishes_running_and_pending_tasks(settings, monkeypatch):
    core = Core(settings)
    with core.store.owner():
        core.initialize()
        run, _ = core.submit({"pipeline_spec": fixture_definition()})
        core.store.put("runs", {**run, "state": "running"})
        task_ids = [new_id("task") for _ in range(3)]
        for task_id, state in zip(
            task_ids, ["running", "pending", "running"], strict=True
        ):
            core.store.put(
                "tasks", {"task_id": task_id, "run_id": run["run_id"], "state": state}
            )
        attempts = [new_id("attempt") for _ in range(2)]
        for task_id, attempt_id in zip(
            [task_ids[0], task_ids[2]], attempts, strict=True
        ):
            core.store.put(
                "attempts",
                {
                    "attempt_id": attempt_id,
                    "run_id": run["run_id"],
                    "task_id": task_id,
                    "state": "running",
                },
            )
        core.store.commit_output_set(
            run["run_id"], task_ids[2], attempts[1], {}, {"answer": 42}
        )
        import docker

        monkeypatch.setattr(
            docker,
            "from_env",
            lambda: SimpleNamespace(ping=lambda: None, close=lambda: None),
        )
        Scheduler(core)._reconcile()
        assert core.store.get("runs", run["run_id"])["state"] == "interrupted"
        assert [core.store.get("tasks", task_id)["state"] for task_id in task_ids] == [
            "interrupted",
            "blocked",
            "succeeded",
        ]
        assert core.store.get("tasks", task_ids[2])["output_parameters"] == {
            "answer": 42
        }
        assert core.store.check()["valid"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("cache", "false"),
        ("optional", "false"),
        ("cpu", "0"),
        ("cpu", True),
        ("cpu", 1e300),
        ("memory", 1e300),
        ("memory", "-1G"),
        ("retry", True),
        ("factor", "2"),
    ],
)
def test_invalid_ir_scalars_are_rejected_before_admission(settings, field, value):
    document = fixture_definition()
    task = document["root"]["dag"]["tasks"]["echo"]
    if field == "cache":
        task["cachingOptions"] = {"enableCache": value}
    elif field == "optional":
        document["root"]["inputDefinitions"]["parameters"]["value"]["isOptional"] = (
            value
        )
    elif field in {"cpu", "memory"}:
        document["deploymentSpec"]["executors"]["exec-echo"]["container"][
            "resources"
        ] = {"resourceCpuLimit" if field == "cpu" else "resourceMemoryLimit": value}
    else:
        task["retryPolicy"] = {
            "maxRetryCount" if field == "retry" else "backoffFactor": value
        }
    with pytest.raises(DefinitionError):
        load_definition(document)
    core = Core(settings)
    with core.store.owner():
        core.initialize()
        before = core.store.records()
        with pytest.raises(DockflowError):
            core.submit({"pipeline_spec": document})
        with pytest.raises(DockflowError):
            core.upload_pipeline(json.dumps(document), "invalid")
        assert core.store.records() == before


@pytest.mark.parametrize(
    "cpu,memory,expected",
    [
        ("500m", "128Mi", (500_000_000, 134_217_728)),
        (0.25, 0.5, (250_000_000, 500_000_000)),
        ("2", "2G", (1_000_000_000, 1_000_000_000)),
    ],
)
def test_one_resource_conversion_enforces_caps(cpu, memory, expected):
    limits = resource_limits(
        {"resources": {"resourceCpuLimit": cpu, "resourceMemoryLimit": memory}},
        {"cpu_limit": 1, "memory_limit_bytes": 1_000_000_000},
    )
    assert (limits["nano_cpus"], limits["mem_limit"]) == expected


@pytest.mark.parametrize("kind", ["file_link", "parent_link", "fifo", "oversize"])
def test_compiled_source_rejects_unsafe_objects_without_open(
    tmp_path, monkeypatch, kind
):
    import dockflow_pipelines.compiled_source as capture

    source = tmp_path / "source.json"
    source.write_bytes(b"12345")
    selected = source
    if kind == "file_link":
        selected = tmp_path / "link.json"
        selected.symlink_to(source)
    elif kind == "parent_link":
        link = tmp_path / "linked"
        link.symlink_to(tmp_path, target_is_directory=True)
        selected = link / source.name
    elif kind == "fifo":
        source.unlink()
        os.mkfifo(source)

    def forbidden(*args, **kwargs):
        pytest.fail("Rejected compiled source was opened")

    monkeypatch.setattr(capture.os, "open", forbidden)
    with pytest.raises(ValueError):
        read_compiled_source(selected, 4 if kind == "oversize" else 10)


@pytest.mark.parametrize("change", ["replace", "mutate", "grow"])
def test_compiled_source_rejects_change_during_bounded_capture(
    tmp_path, monkeypatch, change
):
    import dockflow_pipelines.compiled_source as capture

    source = tmp_path / "source.json"
    source.write_bytes(b"initial")
    fdopen = capture.os.fdopen
    observed = []

    class ChangingStream:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def fileno(self):
            return self.stream.fileno()

        def read(self, maximum):
            observed.append(maximum)
            if change == "replace":
                replacement = source.with_suffix(".replacement")
                replacement.write_bytes(b"changed")
                replacement.replace(source)
            else:
                source.write_bytes(b"changed" if change == "mutate" else b"x" * 100)
            return self.stream.read(maximum)

    monkeypatch.setattr(
        capture.os, "fdopen", lambda *args: ChangingStream(fdopen(*args))
    )
    with pytest.raises(ValueError, match="changed"):
        read_compiled_source(source, 20)
    assert observed == [21]


def test_configured_source_does_not_resolve_away_symlinks(settings):
    source = settings.definitions["pipelines"]["test"]
    original = source.with_suffix(".original")
    source.rename(original)
    source.symlink_to(original)
    with pytest.raises(DockflowError, match="symlink"):
        load_settings(settings.config_path)
    with pytest.raises(DefinitionError, match="symlink"):
        load_definition(source)


@pytest.mark.parametrize("value", ["", 1, {}, []])
def test_definition_configuration_requires_nonempty_paths(settings, value):
    from dockflow_pipelines.config import load_settings

    with pytest.raises(DockflowError):
        load_settings(
            settings.config_path, overrides={"definitions.pipelines": {"test": value}}
        )


@pytest.mark.parametrize(
    "field,value",
    [("cpu_limit", 1e-20), ("cpu_limit", 1e300), ("memory_limit_bytes", 2**63)],
)
def test_configuration_rejects_unrepresentable_resource_caps(settings, field, value):
    with pytest.raises(DockflowError, match="representable"):
        load_settings(settings.config_path, overrides={"execution." + field: value})


def test_pipeline_identity_flushes_ancestors_again_on_retry(settings, monkeypatch):
    import dockflow_pipelines.artifacts as filesystem

    core = Core(settings)
    original = filesystem.fsync_directory
    directories = []
    root = core.artifacts.managed_root

    def fail(path):
        if path == root.parent:
            raise OSError("injected ancestor failure")
        return original(path)

    with monkeypatch.context() as patch:
        patch.setattr(filesystem, "fsync_directory", fail)
        with pytest.raises(OSError, match="ancestor"):
            core.artifacts.storage_identity()
    assert (root / ".dockflow" / "storage.json").is_file()

    def synced(path):
        directories.append(path)
        return original(path)

    monkeypatch.setattr(filesystem, "fsync_directory", synced)
    identity = core.artifacts.storage_identity()
    assert identity == core.artifacts.storage_identity(create=False)
    assert directories == [root / ".dockflow", *(root / ".dockflow").parents]


@pytest.mark.parametrize("table", list(DOMAINS))
def test_integrity_check_detects_orphans_in_every_projection(database_state, table):
    store, _ = database_state
    with store.owner():
        store.initialize()
        keys, columns = DOMAINS[table]
        values = {"project_id": store.project_id}
        for column in keys:
            values[column] = (
                987
                if column == "sequence"
                else "stdout"
                if column == "stream"
                else "runs"
                if column == "collection"
                else new_id("run")
            )
        for column in columns:
            values[column] = (
                "{}"
                if table in {"dockflow_state_resources", "dockflow_log_entries"}
                and column == "value"
                else b"{}"
                if column == "value"
                else new_id("run")
            )
        if table == "dockflow_state_resources":
            values["value"] = json.dumps(
                {"run_id": values["public_id"], "state": "succeeded"}
            )
        with store.database.transaction() as connection:
            store.database.execute(
                connection,
                f"INSERT INTO {table} ({','.join(values)}) VALUES ({','.join('?' for _ in values)})",
                tuple(values.values()),
            )
        assert not store.check()["valid"]
        assert store.rebuild(apply=True)["rebuilt"]
        assert store.check()["valid"]


def test_check_refuses_lost_journal_counter(database_state):
    store, _ = database_state
    with store.owner():
        store.initialize()
        store.put("runs", {"run_id": new_id("run"), "state": "succeeded"})
        with store.database.transaction() as connection:
            store.database.execute(
                connection,
                "UPDATE dockflow_project_counters SET sequence=sequence+1 WHERE project_id=?",
                (store.project_id,),
            )
        assert not store.check()["valid"]
        with pytest.raises(DockflowError, match="counter"):
            store.rebuild(apply=True)


def test_check_detects_changed_intact_cache_observation(database_state):
    store, _ = database_state
    with store.owner():
        store.initialize()
        producer = {
            field + "_id": new_id(field) for field in ("run", "task", "attempt")
        }
        manifest = make_manifest(
            {}, {}, {}, {**producer, "finished_at": utc_now()}, "a" * 64, "test-store"
        )
        attempt = {
            **producer,
            "outputs": {},
            "output_parameters": {},
            "state": "succeeded",
            "signature": {"value": "a" * 64},
            "cache_manifest_digest": digest(manifest),
        }
        store.append(
            "cache_observation",
            {
                "manifest": manifest,
                "manifest_digest": digest(manifest),
                "resources": [{"collection": "attempts", "resource": attempt}],
                "projected_artifact_ids": [],
            },
        )
        assert store.check()["valid"]
        with store.database.transaction() as connection:
            store.database.execute(
                connection,
                "UPDATE dockflow_cache_observations SET value=? WHERE project_id=?",
                (b"{}", store.project_id),
            )
        assert not store.check()["valid"]
        store.rebuild(apply=True)
        assert (
            store.database.cache_observation(producer["attempt_id"])["manifest"]
            == manifest
        )
        assert store.check()["valid"]


def test_public_pages_and_logs_fetch_bounded_rows(
    database_state, settings, monkeypatch
):
    store, _ = database_state
    core = Core(replace(settings, project_id=store.project_id))
    core.store = store
    with store.owner():
        store.initialize()
        run_id = new_id("run")
        store.put(
            "runs", {"run_id": run_id, "state": "succeeded", "display_name": "first"}
        )
        store.put(
            "runs",
            {"run_id": new_id("run"), "state": "succeeded", "display_name": "second"},
        )
        for index in range(260):
            store.put(
                "runs",
                {
                    "run_id": new_id("run"),
                    "state": "succeeded",
                    "display_name": f"unrelated-{index}",
                },
            )
        for _ in range(260):
            store.log(run_id, "é")
        calls = []
        query = store.database.queries.select
        log_query = store.database.log_entries

        def selected(*args, **options):
            calls.append(("resources", options["limit"]))
            return query(*args, **options)

        def logs(*args, **options):
            calls.append(("logs", options["limit"]))
            return log_query(*args, **options)

        monkeypatch.setattr(store.database.queries, "select", selected)
        monkeypatch.setattr(store.database, "log_entries", logs)
        monkeypatch.setattr(
            store, "records", lambda: pytest.fail("public page scanned journal")
        )
        monkeypatch.setattr(
            store, "list", lambda *args: pytest.fail("public page listed history")
        )
        first = core.page("runs", page_size=1, sort_by="display_name asc")
        second = core.page(
            "runs",
            page_size=1,
            sort_by="display_name asc",
            page_token=first["next_page_token"],
        )
        assert first["items"][0]["display_name"] == "first"
        assert second["items"][0]["display_name"] == "second"
        chunks = core.logs(run_id)
        assert len(chunks["entries"]) == 256 and not chunks["terminal"]
        tail = core.logs(run_id, cursor=chunks["next_cursor"])
        assert len(tail["entries"]) == 4 and tail["terminal"]
        assert calls == [
            ("resources", 2),
            ("resources", 2),
            ("logs", 257),
            ("logs", 257),
        ]


def test_selective_queries_page_filter_queue_logs_and_rebuild(
    database_state, monkeypatch
):
    store, _ = database_state
    with store.owner():
        store.initialize()
        ids = []
        artifact = new_id("artifact")
        for index, name in enumerate(["é", "A", "a", "é", "z", "Ω"]):
            run_id = new_id("run")
            ids.append(run_id)
            store.put(
                "runs",
                {
                    "run_id": run_id,
                    "display_name": name,
                    "created_at": "same",
                    "state": "queued" if index < 3 else "succeeded",
                    "acceptance_sequence": index + 1,
                    "parameters": {"zero": -0.0},
                    "inputs": {"data": artifact} if index == 2 else {},
                },
            )
            store.log(run_id, str(index))
        from dockflow_pipelines import queries
        from dockflow_pipelines.state_database import StateDatabase

        loads = queries.loads
        fetched = []

        def counted(value):
            fetched.append(value)
            return loads(value)

        with monkeypatch.context() as patch:
            patch.setattr(queries, "loads", counted)
            patch.setattr(
                store, "records", lambda: pytest.fail("hot query scanned journal")
            )
            patch.setattr(
                StateDatabase,
                "resources",
                lambda *args: pytest.fail("hot query listed all resources"),
            )
            page = store.database.queries.select(
                "runs", sort_by="display_name asc", limit=3
            )
            assert [run["display_name"] for run in page] == ["A", "a", "z"]
            assert len(fetched) == 3
            boundary = [page[-1]["display_name"], page[-1]["run_id"]]
            next_page = store.database.queries.select(
                "runs", sort_by="display_name asc", boundary=boundary, limit=3
            )
            assert [run["display_name"] for run in next_page] == ["é", "é", "Ω"]
            assert [
                run["run_id"]
                for run in store.database.queries.select(
                    "runs", filters={"input_artifact_id": artifact}
                )
            ] == [ids[2]]
            assert (
                store.database.queries.count("runs", filters={"state": "queued"}) == 3
            )
            assert [
                run["run_id"] for run in store.database.queries.queued(limit=2)
            ] == ids[:2]
            assert [
                entry["text"] for entry in store.database.log_entries(ids[3], limit=1)
            ] == ["3"]
        assert '"zero":-0.0' in json.dumps(
            store.get("runs", ids[0]), separators=(",", ":")
        )
        assert store.check()["valid"]
        store.rebuild(apply=True)
        assert (
            store.database.queries.count(
                "runs", filters={"input_artifact_id": artifact}
            )
            == 1
        )
        assert store.check()["valid"]


def test_database_uses_resource_ordering_index(database_state):
    store, _ = database_state
    with store.owner():
        store.initialize()
        adapter = store.database.adapter
        created = adapter.text_order(
            f"COALESCE({adapter.json_text('value', 'created_at')},'')"
        )
        with store.database.transaction() as connection:
            if store.database.backend == "postgresql":
                connection.execute("SET LOCAL enable_seqscan=off")
            prefix = (
                "EXPLAIN"
                if store.database.backend == "postgresql"
                else "EXPLAIN QUERY PLAN"
            )
            plan = store.database.execute(
                connection,
                f"{prefix} SELECT value FROM dockflow_state_resources WHERE project_id=? AND collection=? ORDER BY {created} DESC,public_id LIMIT ?",
                (store.project_id, "runs", 3),
            ).fetchall()
        assert "dockflow_resource_created" in str(plan)
