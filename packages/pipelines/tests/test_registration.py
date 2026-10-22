"""Uploaded catalog identity, strict multipart admission and durable recovery."""

import contextlib
import copy
import json
import socket
import threading
import time
from pathlib import Path

import pytest
import yaml
from dockflow_pipelines.cli import file_request
from dockflow_pipelines.config import load_settings
from dockflow_pipelines.core import Core, checked_definition
from dockflow_pipelines.errors import DockflowError
from dockflow_pipelines.metadata import ControlStore
from dockflow_pipelines.service import create_app
from fastapi.testclient import TestClient
from test_interfaces import fixture_definition

UPLOAD = "/apis/v2beta1/pipelines/upload"
VERSION = UPLOAD + "_version"


@pytest.fixture
def settings(tmp_path):
    (tmp_path / "pipeline.yaml").write_text(yaml.safe_dump(fixture_definition()))
    path = tmp_path / ".dockflow-pipelines.toml"
    path.write_text(
        'schema_version=1\n[project]\nid="registration-tests"\n'
        '[definitions.pipelines]\nconfigured="pipeline.yaml"\n'
        "[service]\nqueue_capacity=20\n"
    )
    return load_settings(path)


def upload(client, name=None, *, source=None, path=UPLOAD, **params):
    if name is not None:
        params["name"] = name
    return client.post(
        path,
        params=params,
        files={
            "uploadfile": (
                "../../ignored.yaml",
                source or yaml.safe_dump(fixture_definition()),
                "application/yaml",
            )
        },
    )


def versions(client, pipeline_id):
    response = client.get(f"/apis/v2beta1/pipelines/{pipeline_id}/versions")
    assert response.status_code == 200, response.text
    return response.json()["pipeline_versions"]


def test_versions_have_distinct_immutable_associations_and_survive_refresh_restart(
    settings,
):
    source = "# exact uploaded bytes\n" + yaml.safe_dump(fixture_definition())
    app = create_app(settings, execute=False)
    with TestClient(app) as client:
        first = upload(
            client, "remote", source=source, description="pipeline description"
        )
        assert first.status_code == 200, first.text
        assert first.headers["content-type"] == "application/json; charset=utf-8"
        pipeline_id = first.json()["pipeline_id"]
        initial = versions(client, pipeline_id)[0]
        original = app.state.core.store.get(
            "definitions", initial["pipeline_version_id"]
        )
        assert original["source_text"] == source
        assert original["registration_origin"] == "api"
        assert original["version_name"] == "remote"
        assert original["description"] == "pipeline description"
        assert not app.state.core.store.list("runs")
        assert not app.state.core.store.list("attempts")

        second = upload(
            client,
            "v2",
            source=source,
            path=VERSION,
            pipelineid=pipeline_id,
            description="second",
        )
        assert second.status_code == 200, second.text
        newest = second.json()["pipeline_version_id"]
        other = upload(client, "other", source=source).json()["pipeline_id"]
        other_version = versions(client, other)[0]["pipeline_version_id"]
        configured = app.state.core.resolve("configured")
        inline = app.state.core.snapshot(checked_definition(source))
        ids = {
            initial["pipeline_version_id"],
            newest,
            other_version,
            configured["definition_id"],
            inline["definition_id"],
        }
        assert len(ids) == 5
        assert (
            app.state.core.store.get("definitions", initial["pipeline_version_id"])
            == original
        )
        components = [
            app.state.core.store.get("definitions", value)["component_ids"]["comp-echo"]
            for value in ids
        ]
        assert len(set(components)) == 5
        assert (
            app.state.core.resolve("remote", persist=False)["definition_id"] == newest
        )
        assert file_request("remote", settings, None) == {"definition_id": newest}
        assert app.state.core.registrations_unchanged()
        assert (
            client.post("/dockflow/v1/definitions/refresh", json={}).json()[
                "diagnostics"
            ]
            == []
        )
        assert app.state.core.resolve("remote")["definition_id"] == newest
        catalog = app.state.core.store.get("pipelines", pipeline_id)
        assert catalog["default_version_id"] == newest
        assert catalog["registration_origin"] == "api"
        old_view = client.get(
            f"/dockflow/v1/definitions/{initial['pipeline_version_id']}"
        ).json()
        assert old_view["default_version_id"] == newest
        assert old_view["version_name"] == "remote"
        assert (
            client.get("/dockflow/v1/definitions/remote").json()["definition_id"]
            == newest
        )

        # A default submission binds the latest accepted snapshot exactly once.
        run = client.post(
            "/apis/v2beta1/runs",
            json={"pipeline_version_reference": {"pipeline_id": pipeline_id}},
        )
        assert run.status_code == 200, run.text
        assert run.json()["pipeline_version_id"] == newest
        assert (
            client.get(f"/apis/v2beta1/pipelines/{other}/versions/{newest}").status_code
            == 404
        )
        wrong = client.post(
            "/apis/v2beta1/runs",
            json={
                "pipeline_version_reference": {
                    "pipeline_id": other,
                    "pipeline_version_id": newest,
                }
            },
        )
        assert wrong.status_code == 400
        assert app.state.core.store.check()["valid"]
        # Lose projections deliberately: startup replay must restore their exact bytes.
        (settings.state / "definitions" / newest / "source.yaml").unlink()
        (settings.state / "definitions" / newest / "definition.json").unlink()

    with TestClient(create_app(settings, execute=False)) as client:
        assert {
            item["pipeline_version_id"] for item in versions(client, pipeline_id)
        } == {initial["pipeline_version_id"], newest}
        assert (
            client.get(f"/dockflow/v1/definitions/{newest}").json()["source_text"]
            == source
        )
        assert (
            settings.state / "definitions" / newest / "source.yaml"
        ).read_bytes() == source.encode()
        assert (
            Core(settings).resolve("remote", persist=False)["definition_id"] == newest
        )
        assert client.post("/dockflow/v1/metadata/check", json={}).json()["valid"]


def test_required_runtime_inputs_are_unbound_at_registration_and_name_defaults(
    settings,
):
    definition = fixture_definition()
    del definition["root"]["inputDefinitions"]["parameters"]["value"]["defaultValue"]
    with TestClient(create_app(settings, execute=False)) as client:
        response = upload(client, source=json.dumps(definition))
        assert response.status_code == 200, response.text
        assert response.json()["display_name"] == "test-pipeline"
        pipeline_id = response.json()["pipeline_id"]
        missing = client.post(
            "/apis/v2beta1/runs",
            json={"pipeline_version_reference": {"pipeline_id": pipeline_id}},
        )
        assert missing.status_code == 400
        supplied = client.post(
            "/apis/v2beta1/runs",
            json={
                "pipeline_version_reference": {"pipeline_id": pipeline_id},
                "runtime_config": {"parameters": {"value": "bound at run"}},
            },
        )
        assert supplied.status_code == 200
        assert upload(client, "名前 with spaces").status_code == 200


@pytest.mark.parametrize(
    "params,status",
    [
        ({"name": ""}, 400),
        ({"name": " "}, 400),
        ({"name": "x" * 257}, 400),
        ({"description": "x" * 4097}, 400),
        ({"name": "one", "display_name": "two"}, 400),
        ({"namespace": "other"}, 422),
        ({"tags": "{}"}, 400),
        ({"url": "https://example.test/pipeline.yaml"}, 400),
    ],
)
def test_query_validation_precedes_registration_without_partial_records(
    settings, params, status
):
    app = create_app(settings, execute=False)
    with TestClient(app) as client:
        before = len(app.state.core.store.records())
        response = upload(client, **params)
        assert response.status_code == status, response.text
        assert response.json()["code"] == 3
        assert len(app.state.core.store.records()) == before


def test_duplicates_collisions_and_version_validation_do_not_mutate_catalog(settings):
    app = create_app(settings, execute=False)
    with TestClient(app) as client:
        assert upload(client, "configured").status_code == 409
        pipeline_id = upload(client, "remote").json()["pipeline_id"]
        before = len(app.state.core.store.records())
        assert upload(client, "remote").status_code == 409
        assert (
            upload(client, "remote", path=VERSION, pipelineid=pipeline_id).status_code
            == 409
        )
        assert upload(client, "new", path=VERSION).status_code == 400
        assert upload(client, path=VERSION, pipelineid=pipeline_id).status_code == 400
        assert (
            upload(
                client, "new", path=VERSION, pipelineid=pipeline_id, namespace=""
            ).status_code
            == 400
        )
        configured_id = next(
            item["pipeline_id"]
            for item in app.state.core.store.list("pipelines")
            if item["name"] == "configured"
        )
        assert (
            upload(client, "new", path=VERSION, pipelineid=configured_id).status_code
            == 409
        )
        response = client.post(
            UPLOAD + "?name=a&name=b",
            files={
                "uploadfile": ("pipeline.yaml", yaml.safe_dump(fixture_definition()))
            },
        )
        assert response.status_code == 400
        assert len(app.state.core.store.records()) == before
        equal = upload(client, "alias", display_name="alias", namespace="")
        assert equal.status_code == 200


@pytest.mark.parametrize(
    "source,status",
    [
        (b"\xff", 400),
        (b"", 400),
        (b"not a compiled object", 400),
        (b"pipelineInfo: {}\npipelineInfo: {}", 400),
        (b"PK\x03\x04example", 422),
        (b"\x1f\x8bexample", 422),
        (
            json.dumps({**fixture_definition(), "sdkVersion": "kfp-2.16.0"}).encode(),
            422,
        ),
    ],
)
def test_invalid_uploaded_content_never_creates_resources(settings, source, status):
    app = create_app(settings, execute=False)
    with TestClient(app) as client:
        before = len(app.state.core.store.records())
        response = client.post(UPLOAD, files={"uploadfile": ("pipeline.yaml", source)})
        assert response.status_code == status, response.text
        assert len(app.state.core.store.records()) == before


@pytest.mark.parametrize(
    "files,data",
    [
        ([("other", ("p.yaml", "x"))], None),
        ([("uploadfile", ("p.yaml", "x")), ("uploadfile", ("p.yaml", "x"))], None),
        ([("uploadfile", ("p.yaml", "x"))], {"name": "extra"}),
        (None, {"uploadfile": "plain text"}),
    ],
)
def test_strict_multipart_parts(settings, files, data):
    with TestClient(create_app(settings, execute=False)) as client:
        response = client.post(UPLOAD, files=files, data=data)
        assert response.status_code == 400, response.text


def test_malformed_multipart_and_non_upload_routes(settings):
    with TestClient(create_app(settings, execute=False)) as client:
        payloads = [
            ("multipart/form-data", b"missing boundary"),
            (
                "multipart/form-data; boundary=x",
                b'--x\r\nContent-Disposition: form-data; name="uploadfile"; filename="p.yaml"\r\n\r\ntruncated',
            ),
            ("multipart/form-data; boundary=x", b"--x\r\nbroken header\r\n\r\n"),
            ("application/json", b"{}"),
        ]
        for content_type, content in payloads:
            response = client.post(
                UPLOAD, content=content, headers={"content-type": content_type}
            )
            assert response.status_code == 400, response.text
        for path in (
            "/dockflow/v1/experiments",
            "/apis/v2beta1/experiments",
            "/apis/v2beta1/pipelines/other",
        ):
            response = client.post(path, files={"uploadfile": ("p.yaml", "x")})
            assert response.status_code == 400


def test_upload_authentication_and_streamed_body_limit(settings):
    token = settings.root / "token"
    token.write_text("test-secret")
    settings.service.update(token_file=token, request_max_bytes=512)
    with TestClient(create_app(settings, execute=False)) as client:
        assert upload(client, "unauthorized").status_code == 401
        headers = {
            "authorization": "Bearer test-secret",
            "content-type": "multipart/form-data; boundary=x",
        }
        response = client.post(
            UPLOAD, content=iter([b"x" * 300, b"x" * 300]), headers=headers
        )
        assert response.status_code == 413
        assert response.json()["code"] == 8
        response = client.post(
            UPLOAD, content=b"x", headers={**headers, "content-length": "513"}
        )
        assert response.status_code == 413


def test_accepted_registration_index_failure_recovers_as_one_event(
    settings, monkeypatch
):
    core = Core(settings)
    with core.store.owner():
        core.initialize()
        before = len(core.store.records())

        def fail(*args):
            raise RuntimeError("injected index failure")

        monkeypatch.setattr(core.store.index, "put", fail)
        with pytest.raises(
            DockflowError,
            match="Registration accepted: pipeline_id=.*pipeline_version_id=",
        ) as error:
            core.upload_pipeline(json.dumps(fixture_definition()), "recoverable")
        assert error.value.status == 503
        records = core.store.records()
        assert len(records) == before + 1
        assert records[-1]["event_kind"] == "pipeline_registration"
        assert core.store.reconciliation_required
        with pytest.raises(DockflowError, match="reconciliation"):
            core.upload_pipeline(json.dumps(fixture_definition()), "blocked")
    with TestClient(create_app(settings, execute=False)) as client:
        pipelines = client.get("/apis/v2beta1/pipelines").json()["pipelines"]
        recovered = next(
            item for item in pipelines if item["display_name"] == "recoverable"
        )
        assert len(versions(client, recovered["pipeline_id"])) == 1
        assert upload(client, "recoverable").status_code == 409
        assert client.post("/dockflow/v1/metadata/check", json={}).json()["valid"]


def test_partial_projection_failure_replays_complete_accepted_registration(
    settings, monkeypatch
):
    core = Core(settings)
    with core.store.owner():
        core.initialize()
        original = core.store._project

        def fail_after_catalog(record):
            if record.get("event_kind") == "pipeline_registration":
                original(core.store._registration_records(record)[0])
                raise OSError("injected projection interruption")
            original(record)

        monkeypatch.setattr(core.store, "_project", fail_after_catalog)
        with pytest.raises(DockflowError, match="Registration accepted"):
            core.upload_pipeline(json.dumps(fixture_definition()), "recoverable")
    with TestClient(create_app(settings, execute=False)) as client:
        pipeline_id = client.get("/apis/v2beta1/pipelines").json()["pipelines"][0][
            "pipeline_id"
        ]
        assert len(versions(client, pipeline_id)) == 1
        assert client.post("/dockflow/v1/metadata/check", json={}).json()["valid"]


def test_readiness_immediately_reports_accepted_registration_hold(
    settings, monkeypatch
):
    app = create_app(settings, execute=False)
    with TestClient(app) as client:
        assert client.get("/health/ready").status_code == 200

        def fail(*args):
            raise RuntimeError("injected index failure")

        monkeypatch.setattr(app.state.core.store.index, "put", fail)
        response = upload(client, "accepted")
        assert response.status_code == 503
        assert "pipeline_id=" in response.json()["message"]
        readiness = client.get("/health/ready")
        assert readiness.status_code == 503
        assert readiness.json()["checks"]["reconciliation_required"]


def test_config_origin_refresh_and_same_name_conflict_do_not_move_api_version(settings):
    app = create_app(settings, execute=False)
    with TestClient(app) as client:
        pipeline_id = upload(client, "remote").json()["pipeline_id"]
        original = copy.deepcopy(app.state.core.resolve("remote"))
        settings.definitions["pipelines"]["remote"] = Path(
            settings.root / "pipeline.yaml"
        )
        report = app.state.core.refresh()
        assert any(item["name"] == "remote" for item in report["diagnostics"])
        assert app.state.core.store.get("pipelines", pipeline_id)["available"]
        assert (
            app.state.core.store.get("definitions", original["definition_id"])
            == original
        )
        del settings.definitions["pipelines"]["remote"]
        settings.definitions["pipelines"].clear()
        app.state.core.refresh()
        assert (
            app.state.core.resolve("remote")["definition_id"]
            == original["definition_id"]
        )


@pytest.mark.parametrize(
    "tamper",
    [
        "definition_id",
        "component_id",
        "compiled",
        "executor",
        "pipeline_spec",
        "history",
    ],
)
def test_replay_rejects_reparented_ids_or_changed_compiled_snapshots(settings, tamper):
    core = Core(settings)
    with core.store.owner():
        core.store.initialize(require_mlmd=False)
        first_catalog, first = core.upload_pipeline(
            json.dumps(fixture_definition()), "first"
        )
        second_catalog, second = core.upload_pipeline(
            json.dumps(fixture_definition()), "second"
        )
        events = [
            item
            for item in core.store.records()
            if item.get("event_kind") == "pipeline_registration"
        ]
    event = events[1]
    resources = event["payload"]["resources"]
    catalog, version, component = [item["resource"] for item in resources]
    if tamper == "definition_id":
        catalog["definition_id"] = catalog["default_version_id"] = first[
            "definition_id"
        ]
        catalog["version_ids"] = [first["definition_id"]]
        version["definition_id"] = component["definition_id"] = first["definition_id"]
        event["payload"]["source"]["path"] = (
            f"definitions/{first['definition_id']}/source.yaml"
        )
    elif tamper == "component_id":
        version["component_ids"]["comp-echo"] = first["component_ids"]["comp-echo"]
        component["component_id"] = first["component_ids"]["comp-echo"]
    elif tamper == "compiled":
        component["compiled"]["inputDefinitions"]["parameters"]["value"][
            "parameterType"
        ] = "BOOLEAN"
    elif tamper == "executor":
        component["executor"]["container"]["image"] = "unaccepted:image"
    elif tamper == "pipeline_spec":
        version["pipeline_spec"]["pipelineInfo"]["name"] = "unaccepted-name"
    else:
        catalog["version_ids"].insert(0, first["definition_id"])
    path = settings.state / "records" / f"{event['sequence']:020d}.json"
    path.write_text(json.dumps(event))
    store = ControlStore(settings.state, settings.project_id)
    with pytest.raises(DockflowError) as error, store.owner():
        store.initialize(require_mlmd=False)
    assert error.value.status == 409
    # The corruption is rejected before overwriting either retained association.
    assert (
        core.store.get("definitions", first["definition_id"])["pipeline_id"]
        == first_catalog["pipeline_id"]
    )
    assert (
        core.store.get("definitions", second["definition_id"])["pipeline_id"]
        == second_catalog["pipeline_id"]
    )


def test_uploaded_definitions_and_embedded_components_cannot_be_rewritten(settings):
    core = Core(settings)
    with core.store.owner():
        core.store.initialize(require_mlmd=False)
        _, version = core.upload_pipeline(json.dumps(fixture_definition()), "immutable")
        component = core.store.get("components", version["component_ids"]["comp-echo"])
        before = len(core.store.records())
        with pytest.raises(DockflowError, match="immutable"):
            core.store.put("definitions", {**version, "description": "changed"})
        with pytest.raises(DockflowError, match="immutable"):
            core.store.put("components", {**component, "executor": {}})
        assert len(core.store.records()) == before


@contextlib.contextmanager
def real_http_service(settings):
    """Exercise the upstream SDK transport without starting an execution worker."""
    import httpx
    import uvicorn

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        endpoint = f"http://127.0.0.1:{listener.getsockname()[1]}"
        server = uvicorn.Server(
            uvicorn.Config(create_app(settings, execute=False), log_level="error")
        )
        thread = threading.Thread(
            target=server.run, kwargs={"sockets": [listener]}, daemon=True
        )
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                try:
                    if (
                        httpx.get(endpoint + "/health/ready", timeout=0.2).status_code
                        == 200
                    ):
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.02)
            else:
                pytest.fail("The isolated upload API did not become ready")
            yield endpoint
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive()


def test_official_sdk_over_http_rejects_invalid_uploads_and_retains_registered_ids(
    settings,
):
    import httpx
    import kfp
    from kfp_server_api.exceptions import ApiException

    package = settings.root / "pipeline.yaml"
    with real_http_service(settings) as endpoint:
        sdk = kfp.Client(host=endpoint)
        pipeline = sdk.upload_pipeline(
            str(package), pipeline_name="SDK remote", description="uploaded over HTTP"
        )
        pipeline_id = pipeline.pipeline_id
        assert sdk.get_pipeline_id("SDK remote") == pipeline_id
        initial = sdk.list_pipeline_versions(pipeline_id).pipeline_versions[0]
        version = sdk.upload_pipeline_version(
            str(package),
            "second",
            pipeline_id=pipeline_id,
            description="version description",
        )
        for name in ("SDK remote", "configured"):
            with pytest.raises(ApiException) as error:
                sdk.upload_pipeline(str(package), pipeline_name=name)
            assert error.value.status == 409
            assert json.loads(error.value.body)["code"] == 9
        with pytest.raises(ApiException) as error:
            sdk.upload_pipeline_version(str(package), "second", pipeline_id=pipeline_id)
        assert error.value.status == 409
        with pytest.raises(ApiException) as error:
            sdk._upload_api.upload_pipeline(
                str(package), name="namespaced", namespace="other"
            )
        assert error.value.status == 422
        invalid = settings.root / "invalid.yaml"
        invalid.write_text(
            "plain Python or another source is not a compiled PipelineSpec"
        )
        with pytest.raises(ApiException) as error:
            sdk.upload_pipeline(str(invalid), pipeline_name="invalid")
        assert error.value.status == 400
        assert (
            httpx.post(
                endpoint + "/dockflow/v1/definitions/refresh", json={}
            ).status_code
            == 200
        )
        old = sdk.get_pipeline_version(pipeline_id, initial.pipeline_version_id)
        assert old.display_name == "SDK remote"
        assert old.pipeline_spec == initial.pipeline_spec
        native = httpx.get(
            endpoint + f"/dockflow/v1/definitions/{initial.pipeline_version_id}"
        ).json()
        assert native["default_version_id"] == version.pipeline_version_id
    with real_http_service(settings) as endpoint:
        sdk = kfp.Client(host=endpoint)
        assert sdk.get_pipeline_id("SDK remote") == pipeline_id
        actual = sdk.list_pipeline_versions(pipeline_id).pipeline_versions
        assert {item.pipeline_version_id for item in actual} == {
            initial.pipeline_version_id,
            version.pipeline_version_id,
        }
        assert (
            sdk.get_pipeline_version(
                pipeline_id, version.pipeline_version_id
            ).description
            == "version description"
        )
