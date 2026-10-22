"""Native DockerRunner acceptance probes (explicitly enabled with DOCKFLOW_TEST_DOCKER)."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from dockflow_pipelines.artifacts import ArtifactStore
from dockflow_pipelines.definitions import load_definition
from dockflow_pipelines.engine import execute_run
from dockflow_pipelines.metadata import ControlStore, new_id

pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(
        os.environ.get("DOCKFLOW_TEST_DOCKER") != "1",
        reason="Set DOCKFLOW_TEST_DOCKER=1 to run actual Docker tasks",
    ),
]


def pipeline():
    return {
        "pipelineInfo": {"name": "native-runtime-fixture"},
        "schemaVersion": "2.1.0",
        "sdkVersion": "kfp-2.17.0",
        "components": {
            "comp-prepare": {
                "executorLabel": "exec-prepare",
                "outputDefinitions": {
                    "artifacts": {
                        "dataset": {
                            "artifactType": {
                                "schemaTitle": "system.Dataset",
                                "schemaVersion": "0.0.1",
                            }
                        }
                    }
                },
            },
            "comp-train": {
                "executorLabel": "exec-train",
                "inputDefinitions": {
                    "parameters": {"factor": {"parameterType": "NUMBER_INTEGER"}},
                    "artifacts": {
                        "dataset": {
                            "artifactType": {
                                "schemaTitle": "system.Dataset",
                                "schemaVersion": "0.0.1",
                            }
                        }
                    },
                },
                "outputDefinitions": {
                    "parameters": {"score": {"parameterType": "NUMBER_INTEGER"}}
                },
            },
        },
        "deploymentSpec": {
            "executors": {
                "exec-prepare": {
                    "container": {
                        "image": "python:3.13-slim",
                        "command": [
                            "python",
                            "-c",
                            "import pathlib,sys; p=pathlib.Path(sys.argv[1]); p.parent.mkdir(parents=True,exist_ok=True); p.write_text('training data'); print('prepared')",
                        ],
                        "args": ["{{$.outputs.artifacts['dataset'].path}}"],
                    }
                },
                "exec-train": {
                    "container": {
                        "image": "python:3.13-slim",
                        "command": [
                            "python",
                            "-c",
                            "import pathlib,sys; p=pathlib.Path(sys.argv[3]); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(str(len(pathlib.Path(sys.argv[1]).read_text())*int(sys.argv[2]))); print('trained')",
                        ],
                        "args": [
                            "{{$.inputs.artifacts['dataset'].path}}",
                            "{{$.inputs.parameters['factor']}}",
                            "{{$.outputs.parameters['score'].output_file}}",
                        ],
                    }
                },
            }
        },
        "root": {
            "inputDefinitions": {
                "parameters": {
                    "factor": {"parameterType": "NUMBER_INTEGER", "defaultValue": 2.0}
                }
            },
            "outputDefinitions": {
                "parameters": {"score": {"parameterType": "NUMBER_INTEGER"}}
            },
            "dag": {
                "tasks": {
                    "prepare": {
                        "componentRef": {"name": "comp-prepare"},
                        "cachingOptions": {"enableCache": True},
                    },
                    "train": {
                        "componentRef": {"name": "comp-train"},
                        "cachingOptions": {"enableCache": True},
                        "inputs": {
                            "parameters": {
                                "factor": {"componentInputParameter": "factor"}
                            },
                            "artifacts": {
                                "dataset": {
                                    "taskOutputArtifact": {
                                        "producerTask": "prepare",
                                        "outputArtifactKey": "dataset",
                                    }
                                }
                            },
                        },
                    },
                },
                "outputs": {
                    "parameters": {
                        "score": {
                            "valueFromParameter": {
                                "producerSubtask": "train",
                                "outputParameterKey": "score",
                            }
                        }
                    }
                },
            },
        },
    }


@pytest.fixture
def runtime(tmp_path):
    settings = SimpleNamespace(
        project_id="runtime-fixture",
        state=tmp_path / "state",
        work_directory=tmp_path / "work",
        execution={"timeout_seconds": 0, "shutdown_grace_seconds": 1},
        images={"pull_policy": "never"},
        reuse={"scope": "global"},
        policies={},
    )
    store = ControlStore(settings.state, settings.project_id)
    with store.owner():
        store.initialize(require_mlmd=True)
        artifacts = ArtifactStore(
            store,
            {
                "backend": "filesystem",
                "root": tmp_path / "artifacts",
                "external_roots": [],
                "allowed_uri_prefixes": [],
            },
        )
        yield settings, store, artifacts


def submit(runtime, document=None, *, on_log=None, **overrides):
    settings, store, artifacts = runtime
    document = document or pipeline()
    definition = load_definition(document)
    definition_id = new_id("definition")
    store.put("definitions", {"definition_id": definition_id, **definition.to_record()})
    run = {
        "run_id": new_id("run"),
        "definition_id": definition_id,
        "pipeline_spec": document,
        "parameters": {"factor": 2},
        "inputs": {},
        "selection": {"mode": "full"},
        "bindings": {},
        "use_executions": {},
        "reuse": {"scope": "global"},
        "state": "queued",
        "task_ids": [],
        **overrides,
    }
    store.put("runs", run)
    return execute_run(store, artifacts, settings, run, on_log=on_log)


def test_foreground_logs_are_forwarded_only_after_persistence(runtime):
    _, store, _ = runtime
    document = pipeline()
    container = document["deploymentSpec"]["executors"]["exec-prepare"]["container"]
    container["command"][-1] += "; print('prepare warning', file=sys.stderr)"
    observed = []

    def on_log(stream, text):
        run = store.list("runs")[-1]
        last = store.log_entries(run["run_id"])[-1]
        assert (last["stream"], last["text"]) == (stream, text)
        observed.append((stream, text))

    run = submit(runtime, document, on_log=on_log)
    assert run["state"] == "succeeded", run.get("error")
    assert observed == [
        (entry["stream"], entry["text"]) for entry in store.log_entries(run["run_id"])
    ]
    assert any(stream == "stdout" and "prepared" in text for stream, text in observed)
    assert any(
        stream == "stderr" and "prepare warning" in text for stream, text in observed
    )


def test_logs_arrive_while_container_is_running_without_duplicates(runtime):
    import docker

    _, store, _ = runtime
    document = pipeline()
    container = document["deploymentSpec"]["executors"]["exec-prepare"]["container"]
    container["command"][-1] += (
        "; print('live-before-finish', flush=True); "
        "print('live-warning', file=sys.stderr, flush=True); "
        "import time; time.sleep(2); print('last-output', flush=True)"
    )
    witnessed = []
    client = docker.from_env()

    def on_log(stream, text):
        if "live-before-finish" in text or "live-warning" in text:
            attempt = store.list("attempts")[-1]
            running = client.containers.get(attempt["container_id"])
            assert running.attrs["State"]["Running"]
            assert attempt["state"] == "running"
            persisted = store.log_entries(attempt["run_id"])
            assert any(text == entry["text"] for entry in persisted)
            witnessed.append(stream)

    try:
        run = submit(runtime, document, on_log=on_log)
    finally:
        client.close()
    assert run["state"] == "succeeded", run.get("error")
    assert set(witnessed) == {"stdout", "stderr"}
    output = "".join(entry["text"] for entry in store.log_entries(run["run_id"]))
    for marker in ("live-before-finish", "live-warning", "last-output"):
        assert output.count(marker) == 1


def test_interrupt_during_live_output_saves_intent_and_stops_container(runtime):
    import docker

    _, store, _ = runtime
    document = pipeline()
    container = document["deploymentSpec"]["executors"]["exec-prepare"]["container"]
    container["command"] = [
        "python",
        "-c",
        "import time; print('ready-to-interrupt', flush=True); time.sleep(30)",
    ]
    interrupted = False

    def on_log(stream, text):
        nonlocal interrupted
        if "ready-to-interrupt" in text and not interrupted:
            interrupted = True
            raise KeyboardInterrupt

    run = submit(runtime, document, on_log=on_log)
    assert interrupted
    assert run["state"] == "interrupted", run.get("error")
    assert not run.get("reconciliation_required")
    assert any(r["event_kind"] == "stop_intent" for r in store.records())
    attempt = store.list("attempts")[-1]
    client = docker.from_env()
    try:
        assert not client.containers.get(attempt["container_id"]).attrs["State"][
            "Running"
        ]
    finally:
        client.close()
    text = "".join(e["text"] for e in store.log_entries(run["run_id"]))
    assert text.count("ready-to-interrupt") == 1
    assert attempt["publication_state"] != "committed"


def test_durable_publication_reuse_and_downstream_parameter_locality(runtime):
    settings, store, artifacts = runtime
    first = submit(runtime)
    assert first["state"] == "succeeded", first.get("error")
    assert first["output_parameters"]["score"] == 26
    first_tasks = {
        item["name"]: item
        for item in store.list("tasks")
        if item["run_id"] == first["run_id"]
    }
    producer = first_tasks["prepare"]["attempt_ids"][0]
    artifact_id = first_tasks["prepare"]["outputs"]["dataset"]
    original = artifacts.get(artifact_id)
    expected = (
        artifacts.managed_root
        / "native-runtime-fixture"
        / first["run_id"]
        / "prepare"
        / producer.removeprefix("attempt_")
        / "dataset"
    )
    assert original["content_uri"] == expected.as_uri()
    assert expected.read_text() == "training data"
    assert (
        store.attempt_path(first["run_id"], first_tasks["prepare"]["task_id"], producer)
        .joinpath("output-set.json")
        .is_file()
    )
    second = submit(runtime)
    assert second["state"] == "succeeded", second.get("error")
    second_tasks = [store.get("tasks", task_id) for task_id in second["task_ids"]]
    assert all(
        task["state"] == "reused" and not task["attempt_ids"] for task in second_tasks
    )
    assert artifacts.get(artifact_id)["content_uri"] == expected.as_uri()
    assert not (
        artifacts.managed_root / "native-runtime-fixture" / second["run_id"]
    ).exists()
    third = submit(runtime, parameters={"factor": 3})
    assert third["state"] == "succeeded", third.get("error")
    tasks = {
        store.get("tasks", tid)["name"]: store.get("tasks", tid)
        for tid in third["task_ids"]
    }
    assert tasks["prepare"]["state"] == "reused"
    assert tasks["train"]["state"] == "succeeded"
    assert third["output_parameters"]["score"] == 39
    assert store.log_entries(first["run_id"])


def test_nonzero_exit_is_never_inferred_as_success(runtime):
    doc = pipeline()
    doc["deploymentSpec"]["executors"]["exec-prepare"]["container"]["command"] = [
        "python",
        "-c",
        "import sys; print('intentional failure',file=sys.stderr); sys.exit(23)",
    ]
    failed = submit(runtime, doc)
    assert failed["state"] == "failed"
    _, store, _ = runtime
    attempts = [
        item for item in store.list("attempts") if item["run_id"] == failed["run_id"]
    ]
    assert len(attempts) == 1
    assert attempts[0]["exit_status"] == 23
    assert attempts[0]["publication_state"] != "committed"
    assert "intentional failure" in "".join(
        entry["text"] for entry in store.log_entries(failed["run_id"])
    )


def test_timeout_confirms_stop_and_commits_no_outputs(runtime):
    settings, store, _ = runtime
    settings.execution["timeout_seconds"] = 1
    doc = pipeline()
    doc["deploymentSpec"]["executors"]["exec-prepare"]["container"]["command"] = [
        "python",
        "-c",
        "import time; time.sleep(30)",
    ]
    failed = submit(runtime, doc, reuse={"scope": "none"})
    assert failed["state"] == "failed"
    assert "deadline_exceeded" in failed["error"]["message"]
    assert not failed.get("reconciliation_required")
    attempts = [
        item for item in store.list("attempts") if item["run_id"] == failed["run_id"]
    ]
    assert len(attempts) == 1 and not attempts[0].get("reconciliation_required")
    assert attempts[0]["publication_state"] != "committed"


def test_nested_conditions_oneof_and_external_importer(runtime, tmp_path):
    settings, store, artifacts = runtime
    external = tmp_path / "external"
    external.mkdir()
    data = external / "dataset.txt"
    data.write_text("training data")
    # Keep the provider's admission roots explicit rather than relying on host
    # paths being automatically visible in a service's namespace.
    artifacts = ArtifactStore(
        store,
        {
            "backend": "filesystem",
            "root": tmp_path / "artifacts",
            "external_roots": [external],
            "allowed_uri_prefixes": [],
        },
    )
    runtime = (settings, store, artifacts)
    doc = pipeline()
    del doc["components"]["comp-prepare"]
    del doc["deploymentSpec"]["executors"]["exec-prepare"]
    dataset_contract = {
        "artifactType": {"schemaTitle": "system.Dataset", "schemaVersion": "0.0.1"}
    }
    doc["components"]["comp-import"] = {
        "executorLabel": "exec-import",
        "outputDefinitions": {"artifacts": {"artifact": dataset_contract}},
    }
    doc["deploymentSpec"]["executors"]["exec-import"] = {
        "importer": {
            "artifactUri": {"constant": data.as_uri()},
            "typeSchema": dataset_contract["artifactType"],
            "reimport": False,
        }
    }
    branch_tasks = {}
    for name, condition in (
        ("yes", "int(inputs.parameter_values['factor']) >= 2"),
        ("no", "!(int(inputs.parameter_values['factor']) >= 2)"),
    ):
        branch_tasks[name] = {
            "componentRef": {"name": "comp-train"},
            "cachingOptions": {"enableCache": True},
            "triggerPolicy": {"condition": condition},
            "inputs": {
                "parameters": {"factor": {"componentInputParameter": "factor"}},
                "artifacts": {"dataset": {"componentInputArtifact": "dataset"}},
            },
        }
    doc["components"]["comp-choice"] = {
        "inputDefinitions": {
            "parameters": {"factor": {"parameterType": "NUMBER_INTEGER"}},
            "artifacts": {"dataset": dataset_contract},
        },
        "outputDefinitions": {
            "parameters": {"score": {"parameterType": "NUMBER_INTEGER"}}
        },
        "dag": {
            "tasks": branch_tasks,
            "outputs": {
                "parameters": {
                    "score": {
                        "valueFromOneof": {
                            "parameterSelectors": [
                                {
                                    "producerSubtask": "yes",
                                    "outputParameterKey": "score",
                                },
                                {
                                    "producerSubtask": "no",
                                    "outputParameterKey": "score",
                                },
                            ]
                        }
                    }
                }
            },
        },
    }
    doc["root"]["dag"] = {
        "tasks": {
            "import": {"componentRef": {"name": "comp-import"}},
            "choice": {
                "componentRef": {"name": "comp-choice"},
                "inputs": {
                    "parameters": {"factor": {"componentInputParameter": "factor"}},
                    "artifacts": {
                        "dataset": {
                            "taskOutputArtifact": {
                                "producerTask": "import",
                                "outputArtifactKey": "artifact",
                            }
                        }
                    },
                },
            },
        },
        "outputs": {
            "parameters": {
                "score": {
                    "valueFromParameter": {
                        "producerSubtask": "choice",
                        "outputParameterKey": "score",
                    }
                }
            }
        },
    }
    result = submit(runtime, doc)
    assert result["state"] == "succeeded", result.get("error")
    assert result["output_parameters"] == {"score": 26}
    records = {
        store.get("tasks", tid)["name"]: store.get("tasks", tid)
        for tid in result["task_ids"]
    }
    assert (
        records["import"]["disposition"] == "imported"
        and not records["import"]["attempt_ids"]
    )
    assert (
        records["choice/no"]["state"] == "skipped"
        and not records["choice/no"]["attempt_ids"]
    )
    assert records["choice/yes"]["state"] == "succeeded"
    imported = artifacts.get(records["import"]["outputs"]["artifact"])
    assert imported["origin"] == "external" and imported["producer"] is None


def test_partial_preflight_and_manual_input_choices(runtime):
    from dockflow_pipelines.definitions import DefinitionError
    from dockflow_pipelines.engine import validate_invocation

    settings, store, artifacts = runtime
    definition = load_definition(pipeline())
    request = {
        "parameters": {"factor": 3},
        "selection": {"mode": "tasks", "tasks": ["train"]},
    }
    with pytest.raises(DefinitionError, match="unresolved omitted"):
        validate_invocation(definition, request, settings, store, artifacts)
    first = submit(runtime)
    assert first["state"] == "succeeded", first.get("error")
    plan = validate_invocation(definition, request, settings, store, artifacts)
    assert "prepare" in plan["resolved_prerequisites"]
    partial = submit(runtime, parameters={"factor": 3}, selection=request["selection"])
    assert partial["state"] == "succeeded", partial.get("error")
    assert partial["output_parameters"]["score"] == 39


def test_primitive_directory_empty_directory_and_metadata_outputs(runtime):
    script = """import json,pathlib,sys
request=json.loads(sys.argv[1])
outputs=request['outputs']['artifacts']
dataset=pathlib.Path(outputs['dataset']['artifacts'][0]['uri'])
(dataset/'empty').mkdir(parents=True)
(dataset/'values.txt').write_text('1,2,3')
wire={'artifacts':{name:{'artifacts':[{'name':name,'uri':value['artifacts'][0]['uri'],'metadata':{'rows':3,'accuracy':0.75}}]} for name,value in outputs.items()}}
pathlib.Path(request['outputs']['outputFile']).write_text(json.dumps(wire))
"""
    contracts = {
        "dataset": {
            "artifactType": {"schemaTitle": "system.Dataset", "schemaVersion": "0.0.1"}
        },
        "metrics": {
            "artifactType": {"schemaTitle": "system.Metrics", "schemaVersion": "0.0.1"}
        },
    }
    doc = {
        "pipelineInfo": {"name": "compiled-primitive"},
        "schemaVersion": "2.1.0",
        "sdkVersion": "kfp-2.17.0",
        "root": {
            "executorLabel": "exec",
            "outputDefinitions": {"artifacts": contracts},
        },
        "deploymentSpec": {
            "executors": {
                "exec": {
                    "container": {
                        "image": "python:3.13-slim",
                        "command": ["python", "-c", script],
                        "args": ["{{$}}"],
                    }
                }
            }
        },
    }
    result = submit(runtime, doc, parameters={})
    assert result["state"] == "succeeded", result.get("error")
    _, store, artifacts = runtime
    task = store.get("tasks", result["task_ids"][0])
    assert task["name"] == "root"
    dataset = artifacts.get(result["outputs"]["dataset"])
    metrics = artifacts.get(result["outputs"]["metrics"])
    assert dataset["payload_kind"] == "directory"
    assert dataset["inventory"][0] == {"path": "empty", "kind": "directory"}
    assert metrics["payload_kind"] == "metadata" and metrics["content_uri"] is None
    assert metrics["metadata"]["accuracy"] == 0.75


def test_modified_input_copy_cannot_commit_outputs(runtime):
    doc = pipeline()
    script = "import pathlib,sys; p=pathlib.Path(sys.argv[1]); p.write_text('modified'); pathlib.Path(sys.argv[3]).write_text('1')"
    doc["deploymentSpec"]["executors"]["exec-train"]["container"]["command"] = [
        "python",
        "-c",
        script,
    ]
    result = submit(runtime, doc)
    assert result["state"] == "failed"
    assert "modified immutable input" in result["error"]["message"]
    _, store, artifacts = runtime
    records = {
        store.get("tasks", tid)["name"]: store.get("tasks", tid)
        for tid in result["task_ids"]
    }
    source = artifacts.get(records["prepare"]["outputs"]["dataset"])
    assert (
        Path(source["content_uri"].removeprefix("file://")).read_text()
        == "training data"
    )
    attempt = store.get("attempts", records["train"]["attempt_ids"][0])
    assert attempt["publication_state"] == "uncommitted"


def test_managed_importer_preserves_original_producing_artifact(runtime):
    first = submit(runtime)
    assert first["state"] == "succeeded", first.get("error")
    _, store, artifacts = runtime
    prep = next(
        store.get("tasks", tid)
        for tid in first["task_ids"]
        if store.get("tasks", tid)["name"] == "prepare"
    )
    original_id = prep["outputs"]["dataset"]
    original = artifacts.get(original_id)
    doc = pipeline()
    del doc["components"]["comp-prepare"]
    del doc["deploymentSpec"]["executors"]["exec-prepare"]
    typ = {"schemaTitle": "system.Dataset", "schemaVersion": "0.0.1"}
    doc["components"]["comp-import"] = {
        "executorLabel": "exec-import",
        "outputDefinitions": {"artifacts": {"dataset": {"artifactType": typ}}},
    }
    doc["deploymentSpec"]["executors"]["exec-import"] = {
        "importer": {
            "artifactUri": {"constant": original["content_uri"]},
            "typeSchema": typ,
            "reimport": False,
        }
    }
    doc["root"]["dag"]["tasks"]["prepare"] = {"componentRef": {"name": "comp-import"}}
    second = submit(runtime, doc, parameters={"factor": 3})
    assert second["state"] == "succeeded", second.get("error")
    imported = next(
        store.get("tasks", tid)
        for tid in second["task_ids"]
        if store.get("tasks", tid)["name"] == "prepare"
    )
    assert imported["outputs"]["dataset"] == original_id
    assert imported["import_event"]["source_artifact_id"] == original_id
    assert not imported["attempt_ids"]
    assert artifacts.get(original_id)["producer"] == original["producer"]
    assert artifacts.get(original_id)["origin"] == "produced"


def test_accepted_partial_plan_does_not_switch_to_newer_producer(runtime):
    from dockflow_pipelines.engine import validate_invocation

    settings, store, artifacts = runtime
    first = submit(runtime)
    assert first["state"] == "succeeded", first.get("error")
    first_prepare = next(
        store.get("tasks", tid)
        for tid in first["task_ids"]
        if store.get("tasks", tid)["name"] == "prepare"
    )
    request = {
        "parameters": {"factor": 3},
        "selection": {"mode": "tasks", "tasks": ["train"]},
    }
    plan = validate_invocation(
        load_definition(pipeline()), request, settings, store, artifacts
    )
    assert (
        plan["resolved_prerequisites"]["prepare"]["attempt_id"]
        == first_prepare["attempt_ids"][0]
    )
    later_document = pipeline()
    later_document["root"]["dag"]["tasks"]["prepare"]["cachingOptions"][
        "enableCache"
    ] = False
    later = submit(runtime, later_document)
    assert later["state"] == "succeeded", later.get("error")
    accepted = submit(
        runtime,
        parameters=request["parameters"],
        selection=request["selection"],
        resolved_plan=plan,
    )
    assert accepted["state"] == "succeeded", accepted.get("error")
    chosen = next(
        store.get("tasks", tid)
        for tid in accepted["task_ids"]
        if store.get("tasks", tid)["name"] == "prepare"
    )
    assert chosen["reuse"]["producer_attempt_id"] == first_prepare["attempt_ids"][0]
    assert chosen["reuse"]["reason"] == "equivalent_committed_result"
    Path(
        artifacts.get(first_prepare["outputs"]["dataset"])["content_uri"].removeprefix(
            "file://"
        )
    ).unlink()
    unavailable = submit(
        runtime,
        parameters=request["parameters"],
        selection=request["selection"],
        resolved_plan=plan,
    )
    assert unavailable["state"] == "failed"
    assert "Accepted historical producer" in unavailable["error"]["message"]
    assert not [
        attempt
        for attempt in store.list("attempts")
        if attempt["run_id"] == unavailable["run_id"]
    ]


def test_accepted_policy_snapshot_survives_file_edits(runtime, tmp_path):
    import json

    from dockflow_pipelines.engine import validate_invocation

    settings, store, artifacts = runtime
    doc = pipeline()
    doc["root"]["dag"]["tasks"]["prepare"]["retryPolicy"] = {"maxRetryCount": 1}
    definition = load_definition(doc)
    policy_file = tmp_path / "policy.json"
    policy_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "definition_sha256": definition.sha256,
                "tasks": {"prepare": {"retry_safe": True}},
            }
        )
    )
    settings.policies["file"] = policy_file
    plan = validate_invocation(
        definition, {"parameters": {"factor": 2}}, settings, store, artifacts
    )
    policy_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "definition_sha256": "0" * 64,
                "tasks": {"prepare": {"retry_safe": False}},
            }
        )
    )
    accepted = submit(runtime, doc, resolved_plan=plan)
    assert accepted["state"] == "succeeded", accepted.get("error")
    prepare = next(
        store.get("tasks", tid)
        for tid in accepted["task_ids"]
        if store.get("tasks", tid)["name"] == "prepare"
    )
    assert prepare["policy"]["retry_safe"] is True
