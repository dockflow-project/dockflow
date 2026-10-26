"""Real SQL filtering, bounded recency and authenticated suggestion contracts."""

import pytest
from dockflow_pipelines.records import new_id
from test_web import AUTH, accepted_snapshot, seed_execution_records

pytest_plugins = ["test_reference_names"]

URL = "/dockflow/v1/ui/filter-options"


def options(client, collection, search="", **extra):
    return client.get(
        URL, params={"collection": collection, "search": search, **extra}, headers=AUTH
    )


def test_recent_limit_id_name_matching_and_read_only(served):
    app, client = served
    core = app.state.core
    for i in range(14):
        core.store.put(
            "experiments",
            {
                "experiment_id": new_id("experiment"),
                "display_name": f"Dataset {i:02}",
                "created_at": f"2026-01-{i + 1:02}T00:00:00Z",
            },
        )
    before = accepted_snapshot(core)
    response = options(client, "experiments")
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert response.json()["remaining_count"] == 4
    assert [item["name"] for item in items] == [
        f"Dataset {i:02}" for i in range(13, 3, -1)
    ]
    assert response.headers["cache-control"] == "no-store"
    target = items[3]
    assert options(client, "experiments", target["id"][12:]).json()["items"] == [target]
    assert options(client, "experiments", "dAtAsEt 10").json()["items"] == [target]
    assert options(client, "experiments", "%").json()["items"] == []
    assert options(client, "experiments", "_not_a_wildcard_").json()["items"] == []
    page = client.get(
        "/dockflow/v1/experiments", params={"search": target["id"]}, headers=AUTH
    )
    assert [r["experiment_id"] for r in page.json()["items"]] == [target["id"]]
    assert accepted_snapshot(core) == before


def test_workload_execution_time_names_and_retirement(served):
    app, client = served
    core = app.state.core
    definition, _, runs, tasks, attempts = seed_execution_records(core)
    for i, run in enumerate(runs):
        core.store.put(
            "runs",
            {
                **run,
                "display_name": f"Invocation {i}",
                "started_at": f"2026-01-0{6 - i}T00:00:00Z",
            },
        )
    items = options(client, "runs").json()["items"]
    assert [item["id"] for item in items] == [r["run_id"] for r in runs]
    pipeline_name = definition["pipeline_spec"]["pipelineInfo"]["name"]
    assert len(options(client, "runs", pipeline_name).json()["items"]) == 3
    assert len(options(client, "runs", "Invocation 1").json()["items"]) == 1
    assert len(options(client, "attempts", "comp-echo").json()["items"]) == len(
        attempts
    )
    assert len(options(client, "tasks", "comp-echo").json()["items"]) == len(tasks)
    for collection, identifier in (
        ("runs", runs[0]["run_id"]),
        ("attempts", attempts[0]["attempt_id"]),
    ):
        page = client.get(
            "/dockflow/v1/" + collection, params={"search": identifier}, headers=AUTH
        ).json()
        assert len(page["items"]) == 1
    core.store.put("runs", {**runs[2], "deleted_at": "2026-02-01T00:00:00Z"})
    assert runs[2]["run_id"] not in [
        item["id"] for item in options(client, "runs").json()["items"]
    ]
    core.store.put(
        "components",
        {
            **core.store.get("components", tasks[0]["component_id"]),
            "retiring_plan_id": "plan",
        },
    )
    assert options(client, "attempts", "comp-echo").json()["items"] == []


@pytest.mark.parametrize(
    "collection",
    [
        "pipelines",
        "definitions",
        "components",
        "experiments",
        "artifacts",
        "runs",
        "tasks",
        "attempts",
    ],
)
def test_all_collections_use_shared_search_without_mutation(served, collection):
    app, client = served
    seed_execution_records(app.state.core)
    before = accepted_snapshot(app.state.core)
    response = options(client, collection)
    assert response.status_code == 200, response.text
    assert response.json()["items"]
    item = response.json()["items"][0]
    assert options(client, collection, item["id"]).json()["items"] == [item]
    assert accepted_snapshot(app.state.core) == before


def test_type_options_and_bad_requests(served):
    app, client = served
    seed_execution_records(app.state.core)
    assert (
        options(client, "artifacts", "data", field="type").json()["items"][0]["value"]
        == "system.Dataset"
    )
    assert client.get(URL, params={"collection": "runs"}).status_code == 401
    for query in (
        "collection=nope",
        "collection=runs&field=type",
        "collection=runs&x=1",
        "collection=runs&search=a&search=b",
        "collection=runs&search=" + "x" * 257,
        "search=a",
    ):
        assert client.get(URL + "?" + query, headers=AUTH).status_code == 400
    schema = client.get("/dockflow/v1/openapi.json", headers=AUTH).json()
    operation = schema["paths"][URL]["get"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/FilterOptions")


def test_ties_filter_bound_pagination_and_project_isolation(served):
    app, client = served
    core = app.state.core
    records = [
        core.store.put(
            "experiments",
            {
                "experiment_id": new_id("experiment"),
                "display_name": f"Shared {i}",
                "created_at": "2026-01-01T00:00:00Z",
            },
        )
        for i in range(3)
    ]
    suggestions = options(client, "experiments", "Shared").json()["items"]
    assert [item["id"] for item in suggestions] == sorted(
        record["experiment_id"] for record in records
    )
    query = {"search": "Shared", "page_size": 2}
    first = client.get("/dockflow/v1/experiments", params=query, headers=AUTH).json()
    second = client.get(
        "/dockflow/v1/experiments",
        params={**query, "page_token": first["next_page_token"]},
        headers=AUTH,
    ).json()
    assert len(first["items"]) == 2 and len(second["items"]) == 1
    assert (
        client.get(
            "/dockflow/v1/experiments",
            params={
                **query,
                "search": "Changed",
                "page_token": first["next_page_token"],
            },
            headers=AUTH,
        ).status_code
        == 400
    )
    assert (
        len(
            client.get(
                "/dockflow/v1/experiments",
                params={"name": "Shared 0", "search": "Shared"},
                headers=AUTH,
            ).json()["items"]
        )
        == 1
    )
    db = core.store.database
    with db.transaction() as connection:
        db.execute(
            connection,
            "INSERT INTO dockflow_state_resources(project_id,collection,public_id,value) VALUES(?,?,?,?)",
            (
                "other-project",
                "experiments",
                new_id("experiment"),
                '{"display_name":"Invisible foreign name","created_at":"2099-01-01T00:00:00Z"}',
            ),
        )
    assert (
        options(client, "experiments", "Invisible foreign name").json()["items"] == []
    )
    assert len(options(client, "experiments").json()["items"]) == 3


def test_dependent_options_count_only_selected_live_parents(served):
    app, client = served
    core = app.state.core
    definition, _, runs, tasks, _ = seed_execution_records(core)
    other = core.store.put(
        "definitions",
        {**definition, "definition_id": new_id("definition"), "name": "Other version"},
    )
    core.store.put(
        "definitions",
        {**definition, "definition_id": new_id("definition"), "name": "Unused version"},
    )
    component = core.store.put(
        "components",
        {
            **core.store.get("components", tasks[0]["component_id"]),
            "component_id": new_id("component"),
            "definition_id": other["definition_id"],
            "name": "Other component",
        },
    )
    first = core.create_experiment("First scope", "")
    second = core.create_experiment("Second scope", "")
    for parent, selected in ((first, definition), (second, other)):
        core.store.put(
            "runs",
            {
                **runs[0],
                "run_id": new_id("run"),
                "experiment_id": parent["experiment_id"],
                "definition_id": selected["definition_id"],
            },
        )
    before = accepted_snapshot(core)
    result = options(client, "components", definition_id=other["definition_id"]).json()
    assert [r["id"] for r in result["items"]] == [component["component_id"]]
    assert result["remaining_count"] == 0
    result = options(client, "definitions", experiment_id=first["experiment_id"]).json()
    assert [r["id"] for r in result["items"]] == [definition["definition_id"]]
    assert (
        len(
            options(
                client,
                "runs",
                experiment_id=second["experiment_id"],
                definition_id=other["definition_id"],
            ).json()["items"]
        )
        == 1
    )
    assert (
        options(
            client,
            "runs",
            experiment_id=first["experiment_id"],
            definition_id=other["definition_id"],
        ).json()["items"]
        == []
    )
    assert [
        r["id"]
        for r in options(client, "tasks", run_id=runs[0]["run_id"]).json()["items"]
    ] == [tasks[0]["task_id"]]
    assert (
        len(
            options(
                client,
                "attempts",
                run_id=runs[0]["run_id"],
                task_id=tasks[0]["task_id"],
            ).json()["items"]
        )
        == 1
    )
    assert (
        options(
            client, "attempts", run_id=runs[0]["run_id"], task_id=tasks[1]["task_id"]
        ).json()["items"]
        == []
    )
    assert accepted_snapshot(core) == before
    core.store.put("experiments", {**first, "deleted_at": "2026-02-01T00:00:00Z"})
    assert options(
        client, "definitions", experiment_id=first["experiment_id"]
    ).json() == {"items": [], "remaining_count": 0}
    for collection, scopes in (
        ("pipelines", {"experiment_id": second["experiment_id"]}),
        ("components", {"definition_id": "bad"}),
        ("tasks", {"experiment_id": second["experiment_id"]}),
    ):
        assert options(client, collection, **scopes).status_code == 400


def test_remaining_count_for_distinct_types(served):
    app, client = served
    core = app.state.core
    _, artifact, _, _, _ = seed_execution_records(core)
    for i in range(14):
        core.store.put(
            "artifacts",
            {
                **artifact,
                "artifact_id": new_id("artifact"),
                "type": {
                    "schema_title": f"custom.Type{i:02}",
                    "schema_version": "0.0.1",
                },
            },
        )
    core.store.put(
        "artifacts",
        {
            **artifact,
            "artifact_id": new_id("artifact"),
            "type": {"schema_title": "custom.Type00", "schema_version": "0.0.1"},
        },
    )
    response = options(client, "artifacts", "custom.", field="type").json()
    assert len(response["items"]) == 10 and response["remaining_count"] == 4
    assert (
        options(client, "artifacts", "Type00", field="type").json()["remaining_count"]
        == 0
    )
