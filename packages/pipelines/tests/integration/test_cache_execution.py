"""Cache integration through the real engine, journal and filesystem adapter."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from dockflow_cli.main import create_app
from dockflow_core.canonical import json_bytes
from dockflow_core.errors import DockflowError
from dockflow_pipelines.artifacts import ArtifactStore
from dockflow_pipelines.cache_registry import Registry, validate_cache
from dockflow_pipelines.config import load_settings
from dockflow_pipelines.engine import execute_run
from dockflow_pipelines.execution_choices import ExecutionChoices
from dockflow_pipelines.executor import ContainerFailed
from dockflow_pipelines.metadata import ControlStore
from dockflow_pipelines.records import new_id
from typer.testing import CliRunner


def definition(cache=True):
    return {
        "pipelineInfo": {"name": "dockflow-cache-fixture"},
        "schemaVersion": "2.1.0",
        "sdkVersion": "kfp-2.17.0",
        "components": {
            "compute": {
                "executorLabel": "exec-compute",
                "inputDefinitions": {
                    "parameters": {
                        "text": {"parameterType": "STRING", "defaultValue": "dockflow"}
                    }
                },
                "outputDefinitions": {
                    "parameters": {"length": {"parameterType": "NUMBER_INTEGER"}},
                    "artifacts": {
                        "result": {
                            "artifactType": {
                                "schemaTitle": "system.Dataset",
                                "schemaVersion": "0.0.1",
                            }
                        }
                    },
                },
            }
        },
        "deploymentSpec": {
            "executors": {
                "exec-compute": {
                    "container": {"image": "dockflow-test:1", "command": ["compute"]}
                }
            }
        },
        "root": {
            "dag": {
                "tasks": {
                    "compute": {
                        "componentRef": {"name": "compute"},
                        "cachingOptions": {"enableCache": cache},
                    }
                }
            }
        },
    }


class Adapter:
    executions = 0
    failures = 0

    def __init__(self, pipeline_root, workspace, **kwargs):
        self.root = pipeline_root

    def load(self, _):
        pass

    def close(self):
        pass

    def stop(self, _):
        return True

    def resolve_image(self, _):
        return {"id": "sha256:" + "a" * 64, "os": "linux", "architecture": "amd64"}

    def run_task(self, **kwargs):
        assert kwargs["should_stop"]() is None
        Adapter.executions += 1
        if Adapter.failures:
            Adapter.failures -= 1
            raise ContainerFailed(1)
        path = self.root / kwargs["attempt_id"] / "result"
        path.parent.mkdir(parents=True, exist_ok=True)
        text = kwargs["arguments"]["text"]
        path.write_text(text)
        return {
            "length": len(text),
            "result": SimpleNamespace(path=str(path), metadata={}),
        }, {}


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    from dockflow_pipelines import engine

    monkeypatch.setattr(engine, "KFPAdapter", Adapter)
    Adapter.executions, Adapter.failures = 0, 0
    config = tmp_path / "pipelines.toml"
    config.write_text(
        'schema_version=1\n[project]\nid="dockflow-cache-fixture"\n[cache]\nstorage_identity="dockflow-cache-test"\nbackoff_seconds=0\nbackoff_max_seconds=0\n'
    )
    settings = load_settings(config)
    settings.cache["storage_token"] = ArtifactStore(
        ControlStore(settings.state, settings.project_id), settings.artifacts
    ).storage_identity()
    return settings


def run(settings, pipeline=None, *, state=None):
    settings = copy.deepcopy(settings)
    if state:
        settings.state = state
        settings.work_directory = state / "work"
    store = ControlStore(
        settings.state, settings.project_id, storage=settings.state_storage
    )
    with store.owner():
        store.initialize()
        artifacts = ArtifactStore(store, settings.artifacts)
        invocation = {
            "run_id": new_id("run"),
            "definition_id": new_id("definition"),
            "pipeline_spec": pipeline or definition(),
            "state": "queued",
            "parameters": {},
            "inputs": {},
        }
        from dockflow_core.canonical import loads

        policies = (
            loads(settings.policies["file"].read_text()).get("tasks", {})
            if settings.policies.get("file")
            else {}
        )
        invocation["execution_choices"] = ExecutionChoices.capture(
            settings, policies
        ).to_record()
        store.put("runs", invocation)
        result = execute_run(store, artifacts, settings, invocation)
        return result, store, artifacts


def test_fresh_staging_reuse_keeps_original_provenance_and_recovers(runtime):
    first, producer, _ = run(runtime)
    assert first["state"] == "succeeded", first.get("error")
    second, consumer, artifacts = run(runtime, state=runtime.state.parent / "consumer")
    assert second["state"] == "succeeded", second.get("error")
    assert Adapter.executions == 1
    local_task = next(
        item for item in consumer.list("tasks") if item["run_id"] == second["run_id"]
    )
    assert local_task["state"] == "reused" and local_task["attempt_ids"] == []
    imported = consumer.get("attempts", local_task["reuse"]["producer_attempt_id"])
    original = producer.list("attempts")[0]
    assert imported["attempt_id"] == original["attempt_id"]
    assert imported["run_id"] == original["run_id"] != second["run_id"]
    assert imported["outputs"] == original["outputs"]
    assert consumer.verify_output_set(imported["attempt_id"])["valid"]
    assert consumer.check(verify_contents=True, artifacts=artifacts)["valid"]
    # Delete projections, then recover only from the accepted atomic import.
    for path in (consumer.state / "artifacts").glob("*.json"):
        path.unlink()
    with consumer.owner():
        consumer.initialize()
    assert (
        artifacts.get(next(iter(imported["outputs"].values())))["producer"][
            "attempt_id"
        ]
        == original["attempt_id"]
    )
    third, _, _ = run(runtime)
    assert third["state"] == "succeeded" and Adapter.executions == 1


def test_missing_or_corrupt_output_invalidates_exact_set_and_recomputes(runtime):
    first, store, artifacts = run(runtime)
    attempt = store.list("attempts")[0]
    descriptor = artifacts.get(attempt["outputs"]["result"])
    from urllib.parse import unquote, urlsplit

    path = Path(unquote(urlsplit(descriptor["content_uri"]).path))
    path.chmod(0o644)
    path.write_text("corruption")
    second, store, _ = run(runtime)
    assert first["state"] == second["state"] == "succeeded", second.get("error")
    assert Adapter.executions == 2
    registry = Registry(runtime.cache, runtime.project_id)
    view = registry.inspect(attempt["signature"]["value"])
    assert [item["state"] for item in view["artifacts"]] == ["INVALID", "AVAILABLE"]
    assert view["entry"]["attempts_started"] == 1


def test_storage_outage_does_not_invalidate_or_duplicate(runtime, monkeypatch):
    _, store, _ = run(runtime)
    attempt = store.list("attempts")[0]

    def unavailable(*args):
        raise DockflowError(
            "Storage temporarily unavailable", "ARTIFACT_UNAVAILABLE", 503
        )

    monkeypatch.setattr(ArtifactStore, "verify_cache", unavailable)
    result, _, _ = run(runtime)
    assert result["state"] == "failed" and Adapter.executions == 1
    registry = Registry(runtime.cache, runtime.project_id)
    assert (
        registry.inspect(attempt["signature"]["value"])["artifacts"][0]["state"]
        == "AVAILABLE"
    )


def test_uncacheable_tasks_never_publish_registry_results(runtime):
    first, store, _ = run(runtime, definition(cache=False))
    second, _, _ = run(runtime, definition(cache=False))
    assert first["state"] == second["state"] == "succeeded"
    assert Adapter.executions == 2
    registry = Registry(runtime.cache, runtime.project_id)
    registry.initialize()
    for attempt in store.list("attempts"):
        with pytest.raises(DockflowError) as error:
            registry.inspect(attempt["signature"]["value"])
        assert error.value.code == "NOT_FOUND"


def test_large_valid_retry_factor_preserves_zero_delay_and_retry_budget(runtime):
    import json

    from dockflow_pipelines.definitions import load_definition

    document = definition(cache=False)
    document["root"]["dag"]["tasks"]["compute"]["retryPolicy"] = {
        "maxRetryCount": 3,
        "backoffFactor": 1e300,
        "backoffDuration": "0s",
    }
    policy = runtime.root / "policies.json"
    policy.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "definition_sha256": load_definition(document).sha256,
                "tasks": {"compute": {"retry_safe": True}},
            }
        )
    )
    runtime.policies["file"] = policy
    Adapter.failures = 3
    result, store, _ = run(runtime, document)
    assert result["state"] == "succeeded", result.get("error")
    assert Adapter.executions == 4
    assert len(store.list("attempts")) == 4


def test_changed_parameters_environment_contract_and_namespace_isolate(runtime):
    first, store, _ = run(runtime)
    pipeline = definition()
    pipeline["components"]["compute"]["inputDefinitions"]["parameters"]["text"][
        "defaultValue"
    ] = "changed"
    changed, _, _ = run(runtime, pipeline)
    assert first["state"] == changed["state"] == "succeeded"
    assert Adapter.executions == 2
    isolated = copy.deepcopy(runtime)
    isolated.cache["namespace"] = "isolated"
    assert run(isolated)[0]["state"] == "succeeded" and Adapter.executions == 3
    signatures = [item["signature"] for item in store.list("attempts")]
    assert signatures[0]["format"] == "dockflow-task-signature-v2"


def test_registry_failure_has_no_unlocked_fallback(runtime, monkeypatch):
    def unavailable(*args):
        raise DockflowError("Registry unavailable", "CACHE_REGISTRY_UNAVAILABLE", 503)

    monkeypatch.setattr(Registry, "initialize", unavailable)
    result, _, _ = run(runtime)
    assert result["state"] == "failed" and Adapter.executions == 0


def test_configuration_rejects_unsafe_topology_and_redacts_dsn(runtime, monkeypatch):
    state, work, artifacts = (
        runtime.state,
        runtime.work_directory,
        runtime.artifacts,
    )
    invalid = [
        {"topology": "shared"},
        {"backend": "postgresql"},
        {
            "backend": "postgresql",
            "dsn_env": "DOCKFLOW_TEST_DSN",
            "registry": "cache.sqlite",
        },
        {
            "backend": "postgresql",
            "dsn_env": "DOCKFLOW_TEST_DSN",
            "topology": "shared",
            "storage_identity": "store",
        },
        {"heartbeat_seconds": 120},
        {"max_attempts": True},
        {"registry": str(work / "unsafe.sqlite")},
        {"wait_seconds": float("inf")},
    ]
    for options in invalid:
        with pytest.raises(DockflowError):
            validate_cache(
                options,
                artifacts,
                {"backend": "sqlite", "database": str(state / "state.sqlite")},
            )
    monkeypatch.setenv("DOCKFLOW_PIPELINES_STATE_BACKEND", "postgresql")
    monkeypatch.setenv("DOCKFLOW_PIPELINES_STATE_DSN_ENV", "DOCKFLOW_STATE_DSN")
    monkeypatch.setenv(
        "DOCKFLOW_STATE_DSN", "postgresql://private:secret@unreachable/dockflow"
    )
    config = runtime.root / "postgres.toml"
    config.write_text('schema_version=1\n[project]\nid="dockflow-cache-fixture"\n')
    settings = load_settings(config)
    assert "secret" not in json_bytes(settings.effective()).decode()
    assert settings.cache["database"] == settings.state_storage
    assert settings.sources["state.backend"] == "environment"
    assert not (runtime.state / "cache-v1").exists()


def test_cache_cli_inspection_and_conditional_reset(runtime):
    _, store, _ = run(runtime)
    key = store.list("attempts")[0]["signature"]["value"]
    runner = CliRunner()
    app = create_app()
    common = ["pipelines", "--config", str(runtime.config_path), "--json", "cache"]
    result = runner.invoke(app, [*common, "show", key])
    assert result.exit_code == 0, result.output
    view = json.loads(result.stdout)["result"]
    selected = view["entry"]["published_artifact_id"]
    result = runner.invoke(
        app,
        [
            *common,
            "invalidate",
            key,
            "--artifact-id",
            selected,
            "--reason",
            "TEST_INVALIDATION",
        ],
    )
    assert result.exit_code == 0, result.output
    revision = json.loads(result.stdout)["result"]["revision"]
    result = runner.invoke(
        app,
        [*common, "reset", key, "--revision", str(revision), "--reason", "TEST_RESET"],
    )
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["pipelines", "cache", "--help"])
    assert result.exit_code == 0


def test_known_network_mount_rejection(tmp_path, monkeypatch):
    from dockflow_core.database import reject_network_sqlite

    original = Path.read_text
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda path, **kwargs: "server / nfs4 rw 0 0\n"
        if str(path) == "/proc/mounts"
        else original(path, **kwargs),
    )
    with pytest.raises(DockflowError, match="local filesystem"):
        reject_network_sqlite(tmp_path / "cache.sqlite")


def test_distinct_storage_with_same_label_is_rejected_before_execution(runtime):
    assert run(runtime)[0]["state"] == "succeeded"
    other = copy.deepcopy(runtime)
    other.artifacts["managed_root"] = runtime.root / "different-managed-store"
    result, _, _ = run(other, state=runtime.root / "other-state")
    assert result["state"] == "failed"
    assert result["error"]["code"] == "CACHE_CONFLICT"
    assert Adapter.executions == 1


def test_stop_intent_prevents_registry_publication(runtime, monkeypatch):
    original = ControlStore.publish_cache_result

    def cancel_before_commit(store, options, ownership, manifest):
        store.append(
            "stop_intent",
            {"run_id": manifest["producer"]["run_id"], "reason": "cancelled"},
        )
        return original(store, options, ownership, manifest)

    monkeypatch.setattr(ControlStore, "publish_cache_result", cancel_before_commit)
    result, store, _ = run(runtime)
    assert result["state"] != "succeeded"
    registry = Registry(runtime.cache, runtime.project_id)
    attempt = store.list("attempts")[0]
    assert registry.inspect(attempt["signature"]["value"])["artifacts"] == []


def test_registry_commit_survives_later_journal_failure(runtime, monkeypatch):
    original = ControlStore.commit_output_set
    injected = [False]

    def fail_once(store, *args, **kwargs):
        if not injected[0]:
            injected[0] = True
            raise DockflowError("Injected journal failure", "UNAVAILABLE", 503)
        return original(store, *args, **kwargs)

    monkeypatch.setattr(ControlStore, "commit_output_set", fail_once)
    first, _, _ = run(runtime)
    assert first["state"] == "failed"
    second, store, artifacts = run(runtime)
    assert second["state"] == "succeeded", second["error"]
    assert Adapter.executions == 1
    assert store.check(verify_contents=True, artifacts=artifacts)["valid"]


def test_finalization_retry_keeps_one_producer_and_one_publication(
    runtime, monkeypatch
):
    original = ArtifactStore._publish_managed_once
    injected = [False]

    def lose_response(store, source, descriptor):
        original(store, source, descriptor)
        if not injected[0]:
            injected[0] = True
            raise TimeoutError("injected lost filesystem finalization response")

    monkeypatch.setattr(ArtifactStore, "_publish_managed_once", lose_response)
    first, store, _ = run(runtime)
    assert first["state"] == "succeeded", first.get("error")
    assert run(runtime)[0]["state"] == "succeeded"
    assert Adapter.executions == 1
    registry = Registry(runtime.cache, runtime.project_id)
    view = registry.inspect(store.list("attempts")[0]["signature"]["value"])
    assert len(view["attempts"]) == len(view["artifacts"]) == 1


def test_incomplete_multi_output_never_publishes_partial_set(runtime, monkeypatch):
    pipeline = definition()
    pipeline["components"]["compute"]["outputDefinitions"]["artifacts"]["missing"] = (
        copy.deepcopy(
            pipeline["components"]["compute"]["outputDefinitions"]["artifacts"][
                "result"
            ]
        )
    )
    failed, store, _ = run(runtime, pipeline)
    assert failed["state"] == "failed"
    attempt = store.list("attempts")[0]
    registry = Registry(runtime.cache, runtime.project_id)
    view = registry.inspect(attempt["signature"]["value"])
    assert (
        not view["artifacts"] and view["entry"]["blocked_reason"] == "VALIDATION_FAILED"
    )


def test_exhausted_transfer_retries_remain_storage_failure_in_shared_budget(
    runtime, monkeypatch
):
    def unavailable(*args):
        raise TimeoutError("injected provider outage")

    with monkeypatch.context() as patch:
        patch.setattr(ArtifactStore, "_publish_managed_once", unavailable)
        failed, store, _ = run(runtime)
    assert failed["state"] == "failed"
    registry = Registry(runtime.cache, runtime.project_id)
    key = store.list("attempts")[0]["signature"]["value"]
    view = registry.inspect(key)
    assert view["attempts"][0]["error_code"] == "ARTIFACT_UNAVAILABLE"
    assert view["entry"]["attempts_started"] == 1
    assert view["entry"]["blocked_reason"] is None and not view["artifacts"]
    assert run(runtime)[0]["state"] == "succeeded"
    assert registry.inspect(key)["entry"]["attempts_started"] == 2


def test_cache_api_models_errors_and_conditional_maintenance(runtime):
    from dockflow_pipelines.service import create_app
    from fastapi.testclient import TestClient

    _, store, _ = run(runtime)
    key = store.list("attempts")[0]["signature"]["value"]
    app = create_app(runtime, execute=False)
    with TestClient(app) as client:
        view = client.get(f"/dockflow/v1/cache/{key}")
        assert view.status_code == 200
        selected = view.json()["entry"]["published_artifact_id"]
        assert (
            client.post(
                f"/dockflow/v1/cache/{key}/invalidate",
                json={"artifact_id": None, "reason": "TEST"},
            ).status_code
            == 400
        )
        assert (
            client.post(
                f"/dockflow/v1/cache/{key}/invalidate", json={"artifact_id": selected}
            ).status_code
            == 400
        )
        invalidated = client.post(
            f"/dockflow/v1/cache/{key}/invalidate",
            json={"artifact_id": selected, "reason": "TEST_INVALIDATION"},
        )
        assert invalidated.status_code == 200
        assert (
            client.post(
                f"/dockflow/v1/cache/{key}/invalidate",
                json={"artifact_id": selected, "reason": "STALE_REPORT"},
            ).status_code
            == 409
        )
        revision = invalidated.json()["revision"]
        assert (
            client.post(
                f"/dockflow/v1/cache/{key}/reset",
                json={"revision": revision - 1, "reason": "TEST_RESET"},
            ).status_code
            == 409
        )
        assert (
            client.post(
                f"/dockflow/v1/cache/{key}/reset",
                json={"revision": revision, "reason": "TEST_RESET"},
            ).status_code
            == 200
        )
        schema = client.get("/dockflow/v1/openapi.json").json()
        assert schema["paths"]["/dockflow/v1/cache/{key}/invalidate"]["post"][
            "requestBody"
        ]["content"]["application/json"]["schema"]["$ref"].endswith("CacheInvalidate")
