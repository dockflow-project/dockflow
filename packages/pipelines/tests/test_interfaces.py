import json

import pytest
from dockflow_pipelines.cli import app
from dockflow_pipelines.config import load_settings
from dockflow_pipelines.core import Core
from dockflow_pipelines.errors import DockflowError
from dockflow_pipelines.metadata import ControlStore
from dockflow_pipelines.service import create_app
from fastapi.testclient import TestClient
from typer.testing import CliRunner


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
    definition = tmp_path / "pipeline.json"
    definition.write_text(json.dumps(fixture_definition()))
    config = tmp_path / ".dockflow-pipelines.toml"
    config.write_text(
        'schema_version=1\n[project]\nid="interface-tests"\n[definitions.pipelines]\ntest="pipeline.json"\n[artifacts]\nexternal_roots=["inputs"]\n[service]\nqueue_capacity=2\n'
    )
    return load_settings(config)


def test_configuration_resolves_from_file_and_rejects_overlap(
    settings, monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path.parent)
    assert settings.root == tmp_path
    assert settings.work_directory == tmp_path / ".dockflow/work"
    assert not settings.state.exists()
    monkeypatch.setenv("DOCKFLOW_PIPELINES_WORK_DIRECTORY", str(tmp_path))
    with pytest.raises(DockflowError, match="contain control"):
        load_settings(settings.config_path)
    assert not settings.state.exists()


@pytest.mark.parametrize(
    "extra",
    [
        "[unknown]\nfield=1\n",
        "[execution]\ntask_parallelism=2\n",
        "[client]\npoll_interval_seconds=nan\n",
    ],
)
def test_invalid_settings_never_create_state(settings, extra):
    with settings.config_path.open("a") as stream:
        stream.write(extra)
    with pytest.raises(DockflowError):
        load_settings(settings.config_path)
    assert not settings.state.exists()


def test_direct_cli_reports_service_owner_without_mutating_state(settings):
    application = create_app(settings, execute=False)
    lock = settings.state / "owner.lock"
    runner = CliRunner()
    with TestClient(application) as client:
        owner_bytes = lock.read_bytes()
        owner = json.loads(owner_bytes)
        records = {
            path.name: path.read_bytes()
            for path in (settings.state / "records").glob("*.json")
        }
        result = runner.invoke(
            app,
            [
                "--config",
                str(settings.config_path),
                "--local",
                "--json",
                "experiments",
                "create",
                "competing-writer",
            ],
        )
        assert result.exit_code == 1, result.output
        error = json.loads(result.output)["error"]
        assert error["code"] == "CONFLICT"
        detail = error["details"][0]
        assert detail["owner"] == owner
        assert detail["owner_metadata_status"] == "valid"
        assert owner["mode"] == "service"
        assert owner["endpoint"] in error["message"]
        assert lock.read_bytes() == owner_bytes
        assert records == {
            path.name: path.read_bytes()
            for path in (settings.state / "records").glob("*.json")
        }
        assert not client.get("/dockflow/v1/experiments").json()["items"]
        schema = client.get("/dockflow/v1/openapi.json").json()
        detail_schema = schema["components"]["schemas"]["Error"]["properties"]["error"][
            "properties"
        ]["details"]["items"]
        assert set(detail) <= detail_schema["properties"].keys()
        assert set(owner) <= detail_schema["properties"]["owner"]["properties"].keys()
    result = runner.invoke(
        app,
        [
            "--config",
            str(settings.config_path),
            "--local",
            "experiments",
            "create",
            "after-service-stop",
        ],
    )
    assert result.exit_code == 0, result.output
    local_owner = json.loads(lock.read_bytes())
    assert local_owner["mode"] == "local"
    assert local_owner["owner_id"] != owner["owner_id"]


def test_service_refuses_direct_owner_before_initializing_project(settings):
    store = ControlStore(settings.state, settings.project_id)
    with store.owner():
        lock = settings.state / "owner.lock"
        owner_bytes = lock.read_bytes()
        with pytest.raises(DockflowError) as caught:
            with TestClient(create_app(settings, execute=False)):
                pytest.fail("Competing service became ready")
        assert caught.value.code == "CONFLICT"
        assert caught.value.details[0]["owner"]["mode"] == "local"
        assert lock.read_bytes() == owner_bytes
        assert not (settings.state / "project.json").exists()
        assert not (settings.metadata_directory / "mlmd.sqlite").exists()


def test_native_api_queue_idempotency_validation_paging_and_restart(settings):
    app = create_app(settings, execute=False)
    with TestClient(app) as client:
        assert client.get("/health/ready").status_code == 200
        refresh = client.post("/dockflow/v1/definitions/refresh", json={})
        assert refresh.status_code == 200, refresh.text
        definitions = client.get("/dockflow/v1/definitions").json()["items"]
        assert definitions[0]["pipeline_id"].startswith("pipeline_")
        request = {"definition_id": definitions[0]["definition_id"]}
        first = client.post(
            "/dockflow/v1/runs", json=request, headers={"Idempotency-Key": "repeat"}
        )
        assert first.status_code == 202, first.text
        run = first.json()
        assert (
            client.post(
                "/dockflow/v1/runs", json=request, headers={"Idempotency-Key": "repeat"}
            ).json()["run_id"]
            == run["run_id"]
        )
        conflict = client.post(
            "/dockflow/v1/runs",
            json={**request, "parameters": {"value": "changed"}},
            headers={"Idempotency-Key": "repeat"},
        )
        assert conflict.status_code == 409
        second = client.post("/dockflow/v1/runs", json=request)
        assert second.status_code == 202
        assert client.post("/dockflow/v1/runs", json=request).status_code == 429
        page = client.get("/dockflow/v1/runs?page_size=1").json()
        next_page = client.get(
            "/dockflow/v1/runs",
            params={"page_token": page["next_page_token"], "page_size": 1},
        ).json()
        assert page["items"][0]["run_id"] != next_page["items"][0]["run_id"]
        assert (
            client.get(
                "/dockflow/v1/runs",
                params={"page_token": page["next_page_token"] + "x"},
            ).status_code
            == 400
        )
        assert (
            client.post(f"/dockflow/v1/runs/{run['run_id']}/cancel", json={}).json()[
                "state"
            ]
            == "cancelled"
        )
        assert (
            client.post(
                "/dockflow/v1/metadata/rebuild", json={"apply": True}
            ).status_code
            == 409
        )
        spec = client.get("/dockflow/v1/openapi.json").json()
        assert (
            spec["openapi"] == "3.1.0" and "RunCreate" in spec["components"]["schemas"]
        )
    with TestClient(create_app(settings, execute=False)) as client:
        replay = client.post(
            "/dockflow/v1/runs", json=request, headers={"Idempotency-Key": "repeat"}
        )
        assert replay.status_code == 200 and replay.json()["run_id"] == run["run_id"]


def test_run_configuration_origins_survive_inspection_and_legacy_records(settings):
    application = create_app(settings, execute=False)
    with TestClient(application) as client:
        response = client.post(
            "/dockflow/v1/runs", json={"pipeline_spec": fixture_definition()}
        )
        assert response.status_code == 202, response.text
        run = response.json()
        url = f"/dockflow/v1/runs/{run['run_id']}"
        snapshot = run["effective_configuration"]
        assert snapshot["sources"]["service.queue_capacity"] == "file"
        assert snapshot["sources"]["execution.timeout_seconds"] == "default"
        assert snapshot["sources"]["metadata.directory"] == "derived"
        settings.sources["execution.timeout_seconds"] = "option"
        settings.execution["timeout_seconds"] = 999
        assert client.get(url).json()["effective_configuration"] == snapshot
        client.post(url + "/cancel", json={})
        spec = client.get("/dockflow/v1/openapi.json").json()
        resource = spec["components"]["schemas"]["Run"]["properties"]
        assert "sources" in resource["effective_configuration"]["properties"]
    runner = CliRunner()
    args = [
        "--config",
        str(settings.config_path),
        "--json",
        "runs",
        "show",
        run["run_id"],
    ]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["result"]["effective_configuration"] == snapshot
    store = ControlStore(
        settings.state, settings.project_id, settings.metadata_directory
    )
    with store.owner():
        store.initialize()
        legacy = store.get("runs", run["run_id"])
        legacy["effective_configuration"].pop("sources")
        store.put("runs", legacy)
    with TestClient(create_app(settings, execute=False)) as client:
        assert "sources" not in client.get(url).json()["effective_configuration"]


def test_api_errors_reject_ambiguous_json_and_numbers(settings):
    with TestClient(create_app(settings, execute=False)) as client:
        headers = {"content-type": "application/json"}
        for payload in [
            '{"display_name":"a","display_name":"b"}',
            '{"display_name":NaN}',
            '{"display_name":9007199254740992}',
            "[]",
        ]:
            response = client.post(
                "/dockflow/v1/experiments", content=payload, headers=headers
            )
            assert (
                response.status_code == 400
                and response.json()["error"]["code"] == "INVALID_ARGUMENT"
            )
        assert client.get("/dockflow/v1/runs?sort_by=evil").status_code == 400
        assert (
            client.post(
                "/dockflow/v1/runs",
                json={"pipeline_spec": fixture_definition(), "unknown": 1},
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/dockflow/v1/runs",
                json={
                    "pipeline_spec": fixture_definition(),
                    "parameters": {"value": True},
                },
            ).status_code
            == 400
        )


def test_cli_json_artifact_import_and_offline_validation(settings):
    source = settings.root / "inputs/sample.csv"
    source.parent.mkdir()
    source.write_text("example dataset")
    runner = CliRunner()
    prefix = ["--config", str(settings.config_path), "--json"]
    result = runner.invoke(app, prefix + ["definitions", "validate", "test"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["result"]["valid"]
    assert not settings.state.exists()
    imported = runner.invoke(
        app,
        prefix
        + ["artifacts", "import", "--uri", source.as_uri(), "--type", "system.Dataset"],
    )
    assert imported.exit_code == 0, imported.output
    artifact = json.loads(imported.stdout)["result"]
    assert artifact["ownership"] == "managed" and artifact["origin"] == "external"
    bad = runner.invoke(app, prefix + ["run", "test", "--no-wait"])
    assert bad.exit_code == 2 and not bad.stdout
    assert json.loads(bad.stderr)["error"]["code"] == "INVALID_ARGUMENT"


@pytest.mark.parametrize("direct_managed_root", [False, True])
def test_kfp_wire_views_filters_and_version_reference(settings, direct_managed_root):
    if direct_managed_root:
        settings = load_settings(
            settings.config_path, overrides={"artifacts.managed_root": "data/artifacts"}
        )
    with TestClient(create_app(settings, execute=False)) as client:
        assert client.get("/apis/v2beta1/healthz").json() == {
            "multi_user": False,
            "pipeline_store": "database",
        }
        client.post("/dockflow/v1/definitions/refresh", json={})
        created = client.post(
            "/apis/v2beta1/experiments", json={"display_name": "demo"}
        ).json()
        assert created["storage_state"] == "AVAILABLE"
        predicate = json.dumps(
            {
                "predicates": [
                    {"key": "display_name", "operation": 1, "stringValue": "demo"}
                ]
            }
        )
        page = client.get(
            "/apis/v2beta1/experiments", params={"filter": predicate}
        ).json()
        assert page["total_size"] == 1
        pipeline = client.get("/apis/v2beta1/pipelines").json()["pipelines"][0]
        versions = client.get(
            f"/apis/v2beta1/pipelines/{pipeline['pipeline_id']}/versions"
        ).json()
        version = versions["pipeline_versions"][0]
        response = client.post(
            "/apis/v2beta1/runs",
            json={
                "pipeline_version_reference": {
                    "pipeline_id": pipeline["pipeline_id"],
                    "pipeline_version_id": version["pipeline_version_id"],
                },
                "runtime_config": {
                    "pipeline_root": str(
                        settings.artifacts.get(
                            "root", settings.artifacts["managed_root"]
                        )
                    )
                },
            },
        )
        assert response.status_code == 200, response.text
        run = response.json()
        assert run["state"] == "PENDING"
        assert (
            client.post(f"/apis/v2beta1/runs/{run['run_id']}:terminate", json={}).json()
            == {}
        )
        assert (
            client.get(f"/apis/v2beta1/runs/{run['run_id']}").json()["state"]
            == "CANCELED"
        )
        rejected = client.post(
            "/apis/v2beta1/runs",
            json={"pipeline_spec": fixture_definition(), "service_account": "bad"},
        )
        assert rejected.status_code == 400 and rejected.json()["code"] == 3
        assert client.delete(f"/apis/v2beta1/runs/{run['run_id']}").status_code == 501


def test_log_pages_are_bounded_and_reconstruct_unicode(settings):
    core = Core(settings)
    text = "abcdefé🦆\n" * 10000
    with core.store.owner():
        core.initialize()
        run, _ = core.submit({"pipeline_spec": fixture_definition()})
        core.store.log(run["run_id"], text, stream="stdout")
        core.cancel(run["run_id"])
        cursor, chunks = None, []
        for _ in range(1000):
            page = core.logs(run["run_id"], cursor=cursor, limit_bytes=1024)
            assert sum(len(entry["text"].encode()) for entry in page["entries"]) <= 1024
            chunks.extend(entry["text"] for entry in page["entries"])
            cursor = page["next_cursor"]
            if page["terminal"]:
                break
        else:
            pytest.fail("Log paging made no progress")
        assert "".join(chunks) == text
        another, _ = core.submit({"pipeline_spec": fixture_definition()})
        with pytest.raises(DockflowError, match="cursor"):
            core.logs(another["run_id"], cursor=cursor)


def test_registered_definition_symlink_rejects_before_normalization(settings):
    original = settings.root / "pipeline.json"
    target = settings.root / "actual.json"
    original.rename(target)
    original.symlink_to(target.name)
    with pytest.raises(DockflowError, match="symlinks"):
        load_settings(settings.config_path)
    assert not settings.state.exists()
