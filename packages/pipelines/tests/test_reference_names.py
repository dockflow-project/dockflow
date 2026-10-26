"""Authoritative human context, bounded deduplicated reads and native admission."""

import json

import pytest
from dockflow_core.errors import DockflowError
from dockflow_pipelines.config import load_settings
from dockflow_pipelines.records import new_id
from dockflow_pipelines.service import create_app
from fastapi.testclient import TestClient
from test_interfaces import fixture_definition
from test_web import AUTH, accepted_snapshot, seed_execution_records

URL = "/dockflow/v1/ui/reference-names"


@pytest.fixture
def served(tmp_path):
    (tmp_path / "pipeline.json").write_text(json.dumps(fixture_definition()))
    (tmp_path / "token").write_text(AUTH["Authorization"].removeprefix("Bearer "))
    (tmp_path / "inputs").mkdir()
    config = tmp_path / "pipelines.toml"
    config.write_text(
        'schema_version=1\n[project]\nid="reference-tests"\n[definitions.pipelines]\nexample="pipeline.json"\n[artifacts]\nexternal_roots=["inputs"]\n[service]\ntoken_file="token"\n'
    )
    app = create_app(load_settings(config), execute=False)
    with TestClient(app) as client:
        yield app, client


def lookup(client, *references):
    return client.post(
        URL,
        headers=AUTH,
        json={
            "references": [
                {"collection": collection, "id": identity}
                for collection, identity in references
            ]
        },
    )


def test_names_are_component_pipeline_and_experiment_not_invocation(served):
    app, client = served
    core = app.state.core
    definition, _, runs, tasks, attempts = seed_execution_records(core)
    experiment = core.create_experiment("Human experiment <b>literal</b>", "")
    custom, _ = core.submit(
        {
            "definition_id": definition["definition_id"],
            "display_name": "Morning invocation",
        }
    )
    refs = [
        ("tasks", tasks[0]["task_id"]),
        ("attempts", attempts[0]["attempt_id"]),
        ("runs", custom["run_id"]),
        ("definitions", definition["definition_id"]),
        ("pipelines", definition["pipeline_id"]),
        ("experiments", experiment["experiment_id"]),
        ("components", tasks[0]["component_id"]),
    ]
    before = accepted_snapshot(core)
    response = lookup(client, *refs)
    assert response.status_code == 200, response.text
    values = response.json()["items"]
    assert [item["collection"] for item in values] == [item[0] for item in refs]
    assert [values[i]["name"] for i in [0, 1, 6]] == ["comp-echo"] * 3
    assert values[0]["name"] != tasks[0]["name"]
    assert values[2]["name"] == definition["pipeline_spec"]["pipelineInfo"]["name"]
    assert values[2]["name"] != custom["display_name"]
    assert values[3]["name"] == values[2]["name"]
    assert values[5]["name"] == experiment["display_name"]
    assert all(item["available"] for item in values)
    assert accepted_snapshot(core) == before
    assert response.headers["cache-control"] == "no-store"


def test_deduplicated_requests_dependencies_and_no_catalog_scan(served, monkeypatch):
    app, client = served
    core = app.state.core
    _, _, _, tasks, attempts = seed_execution_records(core)
    original = core.store.get
    seen = []

    def observed(collection, identifier):
        seen.append((collection, identifier))
        return original(collection, identifier)

    def forbidden(*args, **kwargs):
        pytest.fail("Must not enumerate catalogs")

    monkeypatch.setattr(core.store, "get", observed)
    monkeypatch.setattr(core.store, "list", forbidden)
    monkeypatch.setattr(core, "page", forbidden)
    response = lookup(
        client,
        *(
            [("attempts", attempts[0]["attempt_id"]), ("tasks", tasks[0]["task_id"])]
            * 100
        ),
    )
    assert response.status_code == 200
    assert len(response.json()["items"]) == 2
    assert len(seen) == len(set(seen)) == 3


def test_unavailable_retired_context_is_null_without_breaking_other_items(
    served, monkeypatch
):
    app, client = served
    core = app.state.core
    definition, _, _, tasks, _ = seed_execution_records(core)
    original = core.store.get

    def retired(collection, identifier):
        if collection == "components":
            raise DockflowError("Retired", "GONE", 410)
        return original(collection, identifier)

    monkeypatch.setattr(core.store, "get", retired)
    response = lookup(
        client,
        ("tasks", tasks[0]["task_id"]),
        ("runs", new_id("run")),
        ("definitions", definition["definition_id"]),
    )
    items = response.json()["items"]
    assert items[0]["name"] is items[1]["name"] is None
    assert not items[0]["available"] and not items[1]["available"]
    assert items[2]["available"] and "comp-echo" not in response.text


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"references": []},
        {"references": [{}]},
        {"references": "wrong"},
        {"references": [{"collection": "unknown", "id": "a"}]},
        {"references": [{"collection": [], "id": "a"}]},
        {"references": [{"collection": "runs", "id": "../file"}]},
        {"references": [{"collection": "runs", "id": []}]},
        {"references": [{"collection": "runs", "id": new_id("task")}]},
        {"references": [{"collection": "runs", "id": new_id("run"), "extra": 1}]},
        {"references": [{"collection": "runs", "id": new_id("run")}] * 201},
        {"references": [], "extra": True},
    ],
)
def test_strict_schema(served, body):
    _, client = served
    assert client.post(URL, headers=AUTH, json=body).status_code == 400


def test_auth_origin_queries_and_execution_read_availability(served):
    app, client = served
    experiment = app.state.core.create_experiment("Reference test", "")
    body = {
        "references": [{"collection": "experiments", "id": experiment["experiment_id"]}]
    }
    assert client.post(URL, json=body).status_code == 401
    assert (
        client.post(
            URL, json=body, headers={**AUTH, "Origin": "https://other.invalid"}
        ).status_code
        == 403
    )
    assert client.post(URL + "?unknown=1", json=body, headers=AUTH).status_code == 400
    before = accepted_snapshot(app.state.core)
    app.state.scheduler.active_run = "busy"
    try:
        assert client.post(URL, json=body, headers=AUTH).status_code == 200
    finally:
        app.state.scheduler.active_run = None
    assert accepted_snapshot(app.state.core) == before


def test_openapi_bounded_request_and_response(served):
    _, client = served
    schema = client.get("/dockflow/v1/openapi.json", headers=AUTH).json()
    assert (
        schema["components"]["schemas"]["ReferenceNamesRequest"]["properties"][
            "references"
        ]["maxItems"]
        == 200
    )
    response = schema["paths"][URL]["post"]["responses"]["200"]
    assert response["content"]["application/json"]["schema"]["$ref"].endswith(
        "ReferenceNames"
    )
