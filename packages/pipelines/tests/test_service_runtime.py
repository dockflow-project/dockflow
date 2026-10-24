"""Real owner/worker execution through the native API and pinned KFP SDK."""

import json
import os
import socket
import subprocess
import sys
import time
import uuid
from copy import deepcopy

import httpx
import pytest

pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(
        os.environ.get("DOCKFLOW_TEST_DOCKER") != "1",
        reason="Set DOCKFLOW_TEST_DOCKER=1",
    ),
]


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_isolated_service_workers_kfp_sdk_and_restart(tmp_path, backend):
    if backend == "postgresql" and not os.environ.get(
        "DOCKFLOW_TEST_STATE_POSTGRES_DSN"
    ):
        pytest.skip("Requires disposable PostgreSQL execution-state database")
    import kfp

    document = {
        "pipelineInfo": {"name": "service-fixture"},
        "schemaVersion": "2.1.0",
        "sdkVersion": "kfp-2.17.0",
        "components": {"comp-echo": {"executorLabel": "exec-echo"}},
        "deploymentSpec": {
            "executors": {
                "exec-echo": {
                    "container": {
                        "image": "python:3.13-slim",
                        "command": [
                            "python",
                            "-c",
                            "import time; print('durable service execution', flush=True); "
                            "time.sleep(2); print('service tail', flush=True)",
                        ],
                    }
                }
            }
        },
        "root": {"dag": {"tasks": {"echo": {"componentRef": {"name": "comp-echo"}}}}},
    }
    package = tmp_path / "pipeline.yaml"
    package.write_text(json.dumps(document))
    config = tmp_path / "config.toml"
    project_id = "service-runtime-fixture-" + uuid.uuid4().hex
    state_configuration = (
        '[state]\nbackend="postgresql"\ndsn_env="DOCKFLOW_TEST_STATE_POSTGRES_DSN"\n'
        if backend == "postgresql"
        else ""
    )
    config.write_text(
        f'schema_version=1\n[project]\nid="{project_id}"\n{state_configuration}[definitions.pipelines]\necho="pipeline.yaml"\n[images]\npull_policy="never"\n'
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    endpoint = f"http://127.0.0.1:{port}"
    command = [
        sys.executable,
        "-m",
        "dockflow_cli.main",
        "pipelines",
        "--config",
        str(config),
        "serve",
        "--port",
        str(port),
    ]

    def start(log):
        process = subprocess.Popen(command, stdout=log, stderr=log)
        for _ in range(200):
            if process.poll() is not None:
                raise AssertionError((tmp_path / "service.log").read_text())
            try:
                if httpx.get(endpoint + "/health/ready", timeout=1).status_code == 200:
                    return process
            except httpx.TransportError:
                pass
            time.sleep(0.05)
        process.terminate()
        raise AssertionError("Service never became ready")

    with (tmp_path / "service.log").open("w") as log:
        process = start(log)
        try:
            assert (
                httpx.post(
                    endpoint + "/dockflow/v1/definitions/refresh", json={}
                ).status_code
                == 200
            )
            client = kfp.Client(host=endpoint, existing_token="")
            experiment = client.create_experiment("sdk-contract")
            assert (
                client.get_experiment(experiment_name="sdk-contract").experiment_id
                == experiment.experiment_id
            )
            first = client.create_run_from_pipeline_package(
                str(package), experiment_name="sdk-contract"
            )
            for _ in range(150):
                page = httpx.get(
                    endpoint + f"/dockflow/v1/runs/{first.run_id}/logs"
                ).json()
                if any(
                    "durable service execution" in e["text"] for e in page["entries"]
                ):
                    observed = httpx.get(
                        endpoint + f"/dockflow/v1/runs/{first.run_id}"
                    ).json()
                    assert observed["state"] == "running"
                    assert not page["terminal"]
                    break
                time.sleep(0.05)
            else:
                pytest.fail("Service did not publish logs while the task was running")
            completed = client.wait_for_run_completion(
                first.run_id, timeout=45, sleep_duration=1
            )
            assert completed.state == "SUCCEEDED", (
                tmp_path / "service.log"
            ).read_text()
            assert httpx.get(endpoint + "/health/ready").status_code == 200
            pipelines = client.list_pipelines().pipelines
            version = client.list_pipeline_versions(
                pipelines[0].pipeline_id
            ).pipeline_versions[0]
            second = client.run_pipeline(
                experiment.experiment_id,
                "registered-sdk-run",
                pipeline_id=pipelines[0].pipeline_id,
                version_id=version.pipeline_version_id,
            )
            assert (
                client.wait_for_run_completion(
                    second.run_id, timeout=45, sleep_duration=1
                ).state
                == "SUCCEEDED"
            )
            entries = httpx.get(
                endpoint + f"/dockflow/v1/runs/{first.run_id}/logs"
            ).json()["entries"]
            assert "durable service execution" in "".join(
                item["text"] for item in entries
            )
            assert (
                client.list_runs(experiment_id=experiment.experiment_id).total_size == 2
            )
            uploaded = client.upload_pipeline(
                str(package), pipeline_name="uploaded-sdk-pipeline"
            )
            original_version = client.list_pipeline_versions(
                uploaded.pipeline_id
            ).pipeline_versions[0]
            updated_document = deepcopy(document)
            updated_document["deploymentSpec"]["executors"]["exec-echo"]["container"][
                "command"
            ][2] = "print('uploaded version execution')"
            updated_package = tmp_path / "updated-pipeline.yaml"
            updated_package.write_text(json.dumps(updated_document))
            uploaded_version = client.upload_pipeline_version(
                str(updated_package),
                pipeline_id=uploaded.pipeline_id,
                pipeline_version_name="uploaded-v2",
            )
            assert (
                uploaded_version.pipeline_version_id
                != original_version.pipeline_version_id
            )
            registered_run = client.run_pipeline(
                experiment.experiment_id,
                "uploaded-version-sdk-run",
                pipeline_id=uploaded.pipeline_id,
                version_id=uploaded_version.pipeline_version_id,
            )
            assert (
                client.wait_for_run_completion(
                    registered_run.run_id, timeout=45, sleep_duration=1
                ).state
                == "SUCCEEDED"
            )
            registered_logs = httpx.get(
                endpoint + f"/dockflow/v1/runs/{registered_run.run_id}/logs"
            ).json()["entries"]
            assert "uploaded version execution" in "".join(
                entry["text"] for entry in registered_logs
            )
        finally:
            process.terminate()
            process.wait(timeout=40)
        process = start(log)
        try:
            assert (
                httpx.get(endpoint + f"/dockflow/v1/runs/{first.run_id}").json()[
                    "state"
                ]
                == "succeeded"
            )
            assert httpx.get(endpoint + "/health/ready").status_code == 200
            client = kfp.Client(host=endpoint, existing_token="")
            assert (
                client.get_pipeline(uploaded.pipeline_id).display_name
                == "uploaded-sdk-pipeline"
            )
            versions = client.list_pipeline_versions(
                uploaded.pipeline_id
            ).pipeline_versions
            assert {version.pipeline_version_id for version in versions} == {
                original_version.pipeline_version_id,
                uploaded_version.pipeline_version_id,
            }
            original_snapshot = client.get_pipeline_version(
                uploaded.pipeline_id, original_version.pipeline_version_id
            )
            assert original_snapshot.pipeline_spec == document
            assert client.get_run(registered_run.run_id).state == "SUCCEEDED"
        finally:
            process.terminate()
            process.wait(timeout=40)
