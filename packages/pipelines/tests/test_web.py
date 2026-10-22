"""Browser shell, API inspection and same-origin mutation contract coverage."""

import json
from html.parser import HTMLParser
from importlib.resources import files
from urllib.parse import urljoin

import pytest
from dockflow_pipelines.config import load_settings
from dockflow_pipelines.metadata import new_id, utc_now
from dockflow_pipelines.service import create_app
from dockflow_pipelines.web import ASSETS
from fastapi.testclient import TestClient
from test_interfaces import fixture_definition

TOKEN = "web-contract-private-token"
AUTH = {"Authorization": "Bearer " + TOKEN}
API = "/dockflow/v1"


@pytest.fixture
def settings(tmp_path):
    (tmp_path / "pipeline.json").write_text(json.dumps(fixture_definition()))
    (tmp_path / "token").write_text(TOKEN)
    (tmp_path / "inputs").mkdir()
    config = tmp_path / "pipelines.toml"
    config.write_text(
        'schema_version=1\n[project]\nid="web-contract"\n'
        '[definitions.pipelines]\nexample="pipeline.json"\n'
        '[artifacts]\nexternal_roots=["inputs"]\n'
        '[service]\ntoken_file="token"\n'
    )
    return load_settings(config)


@pytest.fixture
def served(settings):
    app = create_app(settings, execute=False)
    with TestClient(app) as client:
        yield app, client


def accepted_snapshot(core):
    """Compare authoritative state, avoiding SQLite's read-side connection files."""
    return {
        str(path.relative_to(core.settings.state)): path.read_bytes()
        for path in core.settings.state.rglob("*")
        if path.is_file() and not path.is_relative_to(core.settings.metadata_directory)
    }


def seed_execution_records(core):
    """Persist controlled execution observations without starting any containers."""
    definition = core.resolve("example")
    source = core.settings.root / "inputs" / "dataset.csv"
    source.write_text("feature,label\n1,0\n")
    dataset = core.artifacts.register(
        source.as_uri(),
        {"schema_title": "system.Dataset", "schema_version": "0.0.1"},
        managed=True,
    )
    runs, tasks, attempts = [], [], []
    for index in range(3):
        run, _ = core.submit({"definition_id": definition["definition_id"]})
        run = core.store.put("runs", {**run, "state": "succeeded"})
        task_id, attempt_id = new_id("task"), new_id("attempt")
        task = core.store.put(
            "tasks",
            {
                "task_id": task_id,
                "run_id": run["run_id"],
                "definition_id": definition["definition_id"],
                "component_id": definition["component_ids"]["comp-echo"],
                "name": "echo",
                "state": "reused" if index == 2 else "succeeded",
                "created_at": utc_now(),
                "inputs": {"dataset": dataset["artifact_id"]},
                "outputs": {},
                "attempt_ids": [] if index == 2 else [attempt_id],
                "reuse": {"producer_attempt_id": attempts[0]["attempt_id"]}
                if index == 2
                else {"reason": "no_compatible_available_result", "rejections": []},
                "error": None,
            },
        )
        if index != 2:
            attempts.append(
                core.store.put(
                    "attempts",
                    {
                        "attempt_id": attempt_id,
                        "run_id": run["run_id"],
                        "task_id": task_id,
                        "state": "succeeded",
                        "created_at": utc_now(),
                        "inputs": {"dataset": dataset["artifact_id"]},
                        "outputs": {},
                        "error": None,
                    },
                )
            )
        runs.append(core.store.put("runs", {**run, "task_ids": [task_id]}))
        tasks.append(task)
    return definition, dataset, runs, tasks, attempts


def test_public_shell_and_docs_do_not_disclose_authenticated_project_data(served):
    app, client = served
    original = accepted_snapshot(app.state.core)
    for path in ("/ui/", API + "/docs"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert TOKEN not in response.text
        assert app.state.core.settings.project_id not in response.text
        assert "example" not in response.text
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        csp = response.headers["content-security-policy"]
        assert "script-src 'self'" in csp and "object-src 'none'" in csp
        assert "frame-ancestors 'none'" in csp
        assert "unsafe-eval" not in csp
        head = client.head(path)
        assert head.status_code == 200 and head.content == b""
    for path in (API + "/pipelines", API + "/openapi.json", API + "/capabilities"):
        response = client.get(path)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHENTICATED"
        assert TOKEN not in response.text
        assert client.get(path, headers=AUTH).status_code == 200
    assert client.post("/ui/", json={}).status_code == 401
    assert client.post("/ui/", json={}, headers=AUTH).status_code == 405
    assert accepted_snapshot(app.state.core) == original


@pytest.mark.parametrize("root_path", ["", "/prefix"])
@pytest.mark.parametrize(
    "host",
    [
        "testserver/ui/?",
        "testserver/health/live?",
        "testserver/health/ready#",
        "testserver\\ui\\?",
        "user@testserver",
        "testserver:invalid",
        "testserver:65536",
        "test server",
    ],
)
def test_malformed_host_cannot_bypass_authentication(settings, root_path, host):
    app = create_app(settings, execute=False)
    with TestClient(app, root_path=root_path) as client:
        original = accepted_snapshot(app.state.core)
        requests = [
            ("GET", API + "/experiments", {}),
            ("GET", API + "/openapi.json", {}),
            ("POST", API + "/experiments", {"json": {"display_name": "blocked"}}),
            (
                "POST",
                "/apis/v2beta1/pipelines/upload",
                {
                    "files": {
                        "uploadfile": (
                            "pipeline.json",
                            json.dumps(fixture_definition()),
                        )
                    }
                },
            ),
        ]
        for method, path, arguments in requests:
            response = client.request(
                method, root_path + path, headers={"Host": host}, **arguments
            )
            assert response.status_code == 400
        # Validation also applies with a correct token, before any mutation.
        response = client.post(
            root_path + API + "/experiments",
            json={"display_name": "blocked-authenticated"},
            headers={**AUTH, "Host": host},
        )
        assert response.status_code == 400
        assert accepted_snapshot(app.state.core) == original


def test_duplicate_host_headers_are_rejected(served):
    app, client = served
    original = accepted_snapshot(app.state.core)
    response = client.post(
        API + "/experiments",
        json={"display_name": "blocked"},
        headers=[("Host", "testserver"), ("Host", "testserver/ui/?")],
    )
    assert response.status_code == 400
    assert accepted_snapshot(app.state.core) == original


def test_missing_host_header_is_rejected(settings):
    app = create_app(settings, execute=False)

    async def without_host(scope, receive, send):
        # TestClient synthesizes a Host header, so remove it at the ASGI boundary.
        if scope["type"] == "http":
            scope = {
                **scope,
                "headers": [
                    (key, value) for key, value in scope["headers"] if key != b"host"
                ],
            }
        await app(scope, receive, send)

    with TestClient(without_host) as client:
        assert client.get("/health/live").status_code == 400


@pytest.mark.parametrize(
    "host", ["localhost", "127.0.0.1:8080", "[::1]:8080", "api.example"]
)
def test_valid_hosts_preserve_public_routes_and_token_protection(served, host):
    _, client = served
    headers = {"Host": host}
    for path in ("/health/live", "/health/ready", "/ui/", API + "/docs"):
        assert client.get(path, headers=headers).status_code == 200
    assert client.get(API + "/experiments", headers=headers).status_code == 401
    assert (
        client.get(API + "/experiments", headers={**headers, **AUTH}).status_code == 200
    )


def test_all_packaged_assets_have_expected_types_and_no_external_dependencies(served):
    _, client = served
    for name, content_type in ASSETS.items():
        response = client.get("/ui/assets/" + name)
        assert response.status_code == 200, name
        assert response.headers["content-type"].startswith(content_type)
        assert response.headers["x-content-type-options"] == "nosniff"
        assert (
            response.content
            == files("dockflow_pipelines").joinpath("static", name).read_bytes()
        )
        assert client.head("/ui/assets/" + name).content == b""

    class Dependencies(HTMLParser):
        def __init__(self):
            super().__init__()
            self.urls = []

        def handle_starttag(self, tag, attrs):
            attributes = dict(attrs)
            if tag == "script":
                self.urls.append(attributes.get("src", ""))
            if tag == "link" and attributes.get("rel") == "stylesheet":
                self.urls.append(attributes.get("href", ""))

    for path in ("/ui/", API + "/docs"):
        parser = Dependencies()
        parser.feed(client.get(path).text)
        assert parser.urls
        assert all(
            url and not url.startswith(("http:", "https:", "//", "data:"))
            for url in parser.urls
        )


@pytest.mark.parametrize(
    "path",
    [
        "/ui/assets/metadata.py",
        "/ui/assets/index.html",
        "/ui/assets/%2e%2e%2fmetadata.py",
        "/ui/assets/%2e%2e%2f%2e%2e%2fpyproject.toml",
        "/ui/assets/.env",
    ],
)
def test_asset_routing_never_serves_arbitrary_package_or_host_files(served, path):
    _, client = served
    response = client.get(path, headers=AUTH)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_cross_origin_mutations_are_rejected_before_acceptance(served):
    app, client = served
    original = accepted_snapshot(app.state.core)
    for origin in ("https://untrusted.example", "null", "http://testserver.evil"):
        response = client.post(
            API + "/experiments",
            json={"display_name": "foreign"},
            headers={**AUTH, "Origin": origin},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"
        assert "access-control-allow-origin" not in response.headers
    assert accepted_snapshot(app.state.core) == original
    assert (
        client.post(
            API + "/experiments",
            json={"display_name": "same-origin"},
            headers={**AUTH, "Origin": "http://testserver"},
        ).status_code
        == 201
    )
    assert (
        client.post(
            API + "/experiments",
            json={"display_name": "non-browser-client"},
            headers=AUTH,
        ).status_code
        == 201
    )


def test_new_collection_filters_and_pagination_preserve_read_only_inspection(served):
    app, client = served
    with app.state.core.mutex:
        definition, _, runs, tasks, attempts = seed_execution_records(app.state.core)
    original = accepted_snapshot(app.state.core)
    pipeline_id = definition["pipeline_id"]
    pipelines = client.get(API + "/pipelines", headers=AUTH).json()["items"]
    assert [item["pipeline_id"] for item in pipelines] == [pipeline_id]
    assert (
        client.get(API + "/pipelines/" + pipeline_id, headers=AUTH).status_code == 200
    )
    for collection, filters, key, expected in (
        ("pipelines", {"name": "example"}, "pipeline_id", [pipeline_id]),
        (
            "definitions",
            {"pipeline_id": pipeline_id},
            "definition_id",
            [definition["definition_id"]],
        ),
        (
            "components",
            {"definition_id": definition["definition_id"]},
            "component_id",
            list(definition["component_ids"].values()),
        ),
        ("tasks", {"run_id": runs[0]["run_id"]}, "task_id", [tasks[0]["task_id"]]),
        ("tasks", {"state": "reused"}, "task_id", [tasks[2]["task_id"]]),
        (
            "attempts",
            {"task_id": tasks[0]["task_id"]},
            "attempt_id",
            [attempts[0]["attempt_id"]],
        ),
    ):
        response = client.get(API + "/" + collection, params=filters, headers=AUTH)
        assert response.status_code == 200, response.text
        assert [item[key] for item in response.json()["items"]] == expected
    first = client.get(API + "/tasks", params={"page_size": 2}, headers=AUTH).json()
    second = client.get(
        API + "/tasks",
        params={"page_size": 2, "page_token": first["next_page_token"]},
        headers=AUTH,
    ).json()
    assert len(first["items"]) == 2 and len(second["items"]) == 1
    assert second["next_page_token"] is None
    assert {item["task_id"] for item in first["items"] + second["items"]} == {
        item["task_id"] for item in tasks
    }
    mismatch = client.get(
        API + "/tasks",
        params={"state": "reused", "page_token": first["next_page_token"]},
        headers=AUTH,
    )
    assert mismatch.status_code == 400
    assert accepted_snapshot(app.state.core) == original


@pytest.mark.parametrize(
    "path,query",
    [
        ("tasks", "state=publishing"),
        ("attempts", "state=reused"),
        ("attempts", "state=pending"),
        ("tasks", "state=unknown"),
        ("tasks", "page_size=0"),
        ("attempts", "page_size=201"),
        ("pipelines", "page_size=one"),
        ("tasks", "run_id=one&run_id=two"),
        ("attempts", "unknown=true"),
        ("definitions", "kind=unknown"),
    ],
)
def test_inspection_rejects_invalid_filters_and_ambiguous_queries(served, path, query):
    app, client = served
    original = accepted_snapshot(app.state.core)
    response = client.get(API + "/" + path + "?" + query, headers=AUTH)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_ARGUMENT"
    assert accepted_snapshot(app.state.core) == original


def test_artifact_lineage_pages_actual_consumers_without_inventing_producers(served):
    app, client = served
    with app.state.core.mutex:
        _, dataset, _, tasks, _ = seed_execution_records(app.state.core)
    original = accepted_snapshot(app.state.core)
    path = API + "/artifacts/" + dataset["artifact_id"] + "/lineage"
    first = client.get(path, params={"page_size": 2}, headers=AUTH)
    assert first.status_code == 200, first.text
    page = first.json()
    assert page["artifact_id"] == dataset["artifact_id"]
    assert page["producer"] is None
    last = client.get(
        path,
        params={"page_size": 2, "page_token": page["next_page_token"]},
        headers=AUTH,
    ).json()
    assert last["next_page_token"] is None
    consumers = page["items"] + last["items"]
    assert {item["task_id"] for item in consumers} == {
        item["task_id"] for item in tasks
    }
    reused = next(item for item in consumers if item["state"] == "reused")
    assert reused["attempt_ids"] == []
    assert client.get(path + "?page_size=one", headers=AUTH).status_code == 400
    assert (
        client.get(path + "?page_size=1&page_size=2", headers=AUTH).status_code == 400
    )
    assert client.get(path + "?unknown=true", headers=AUTH).status_code == 400
    assert (
        client.get(
            API + "/artifacts/" + new_id("artifact") + "/lineage", headers=AUTH
        ).status_code
        == 404
    )
    assert accepted_snapshot(app.state.core) == original


def test_reused_outputs_keep_the_original_artifact_producer(served):
    app, client = served
    core = app.state.core
    with core.mutex:
        definition, _, runs, tasks, attempts = seed_execution_records(core)
        producer = {
            "run_id": runs[0]["run_id"],
            "task_id": tasks[0]["task_id"],
            "attempt_id": attempts[0]["attempt_id"],
            "definition_id": definition["definition_id"],
            "output_name": "metrics",
            "pipeline_name": "web-test",
            "task_name": "train",
        }
        metrics = core.artifacts.publish(
            None,
            {"schema_title": "system.Metrics", "schema_version": "0.0.1"},
            producer,
            {"accuracy": 0.93},
        )
        core.store.commit_output_set(
            producer["run_id"],
            producer["task_id"],
            producer["attempt_id"],
            {"metrics": metrics},
            {},
        )
        core.store.put(
            "tasks",
            {**tasks[2], "outputs": {"metrics": metrics["artifact_id"]}},
        )
    original = accepted_snapshot(core)
    response = client.get(
        API + "/artifacts/" + metrics["artifact_id"] + "/lineage", headers=AUTH
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "artifact_id": metrics["artifact_id"],
        "producer": producer,
        "items": [],
        "next_page_token": None,
    }
    reused = client.get(API + "/tasks/" + tasks[2]["task_id"], headers=AUTH).json()
    assert reused["attempt_ids"] == []
    assert reused["outputs"]["metrics"] == metrics["artifact_id"]
    assert reused["reuse"]["producer_attempt_id"] == producer["attempt_id"]
    assert accepted_snapshot(core) == original


def test_live_openapi_describes_browser_inspection_resources_and_queries(served):
    _, client = served
    response = client.get(API + "/openapi.json", headers=AUTH)
    assert response.status_code == 200
    schema = response.json()

    def resolve(value):
        while "$ref" in value:
            target = value["$ref"]
            assert target.startswith("#/components/schemas/")
            value = schema["components"]["schemas"][target.rsplit("/", 1)[1]]
        return value

    for path, identifier, filters in (
        ("pipelines", "pipeline_id", {"name"}),
        ("tasks", "task_id", {"run_id", "state", "input_artifact_id"}),
        ("attempts", "attempt_id", {"run_id", "task_id", "state"}),
    ):
        operation = schema["paths"][API + "/" + path]["get"]
        query = {
            item["name"] for item in operation["parameters"] if item["in"] == "query"
        }
        assert filters | {"page_size", "page_token"} <= query
        result = resolve(
            operation["responses"]["200"]["content"]["application/json"]["schema"]
        )
        assert {"items", "next_page_token"} <= set(result["required"])
        item = resolve(result["properties"]["items"]["items"])
        assert identifier in item["properties"]
    operation = schema["paths"][API + "/artifacts/{artifact_id}/lineage"]["get"]
    result = resolve(
        operation["responses"]["200"]["content"]["application/json"]["schema"]
    )
    assert {"artifact_id", "producer", "items", "next_page_token"} <= set(
        result["required"]
    )
    assert "task_id" in resolve(result["properties"]["items"]["items"])["properties"]


def test_browser_shell_respects_an_explicit_proxy_root_path(settings):
    app = create_app(settings, execute=False)
    with TestClient(app, root_path="/prefix") as client:
        for path in ("/prefix/", "/prefix/ui"):
            response = client.get(path, follow_redirects=False)
            assert response.status_code in {302, 307, 308}
            assert urljoin(str(response.url), response.headers["location"]).endswith(
                "/prefix/ui/"
            )
        assert client.get("/prefix/ui/").status_code == 200
        assert client.get("/prefix/ui/assets/api.js").status_code == 200
        assert client.get("/prefix" + API + "/docs").status_code == 200
        assert client.get("/prefix" + API + "/pipelines").status_code == 401
        assert (
            client.get("/prefix" + API + "/pipelines", headers=AUTH).status_code == 200
        )
        for path in ("/health/live", "/health/ready"):
            assert client.get("/prefix" + path).status_code == 200
        unauthorized = client.get("/prefix/apis/v2beta1/pipelines")
        assert unauthorized.status_code == 401
        assert unauthorized.json()["code"] == 16
        assert "error" not in unauthorized.json()
        uploaded = client.post(
            "/prefix/apis/v2beta1/pipelines/upload",
            params={"name": "through-proxy"},
            files={
                "uploadfile": (
                    "compiled.json",
                    json.dumps(fixture_definition()),
                    "application/json",
                )
            },
            headers=AUTH,
        )
        assert uploaded.status_code == 200, uploaded.text
        assert uploaded.json()["pipeline_id"].startswith("pipeline_")
