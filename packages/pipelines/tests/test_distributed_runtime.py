"""Independent PostgreSQL services execute concurrently over common S3 storage."""

import json
import os
import signal
import socket
import subprocess
import sys
import time
import uuid

import httpx
import pytest
from dockflow_pipelines.config import load_settings
from dockflow_pipelines.metadata import ControlStore

pytestmark = [
    pytest.mark.docker,
    pytest.mark.postgresql,
    pytest.mark.s3,
    pytest.mark.skipif(
        os.environ.get("DOCKFLOW_TEST_DOCKER") != "1"
        or not os.environ.get("DOCKFLOW_TEST_STATE_POSTGRES_DSN")
        or not os.environ.get("DOCKFLOW_TEST_CACHE_S3_ENDPOINT"),
        reason="Requires real Docker, disposable PostgreSQL and shared S3 providers",
    ),
]


def document():
    parameters = {"value": {"parameterType": "STRING"}}
    return {
        "pipelineInfo": {"name": "distributed-runtime"},
        "schemaVersion": "2.1.0",
        "sdkVersion": "kfp-2.17.0",
        "components": {
            "comp-produce": {
                "executorLabel": "exec-produce",
                "inputDefinitions": {"parameters": parameters},
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
            }
        },
        "deploymentSpec": {
            "executors": {
                "exec-produce": {
                    "container": {
                        "image": "python:3.13-slim",
                        "command": [
                            "python",
                            "-c",
                            "import pathlib,sys,time; print('distributed task started',flush=True); time.sleep(6); p=pathlib.Path(sys.argv[1]); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(sys.argv[2]); print('distributed task finished',flush=True)",
                        ],
                        "args": [
                            "{{$.outputs.artifacts['dataset'].path}}",
                            "{{$.inputs.parameters['value']}}",
                        ],
                    }
                }
            }
        },
        "root": {
            "inputDefinitions": {"parameters": parameters},
            "dag": {
                "tasks": {
                    "produce": {
                        "componentRef": {"name": "comp-produce"},
                        "inputs": {
                            "parameters": {
                                "value": {"componentInputParameter": "value"}
                            }
                        },
                        "cachingOptions": {"enableCache": True},
                    }
                }
            },
        },
    }


def wait_until(predicate, *, seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("Distributed runtime condition was not reached")


@pytest.mark.parametrize(
    "outcome", ["success", "cancel", "owner_death", "direct", "shared_key"]
)
def test_isolated_services_concurrent_runs_and_scoped_recovery(tmp_path, outcome):
    import boto3

    project = "dockflow-distributed-" + uuid.uuid4().hex
    bucket = "dockflow-distributed-" + uuid.uuid4().hex
    endpoint = os.environ["DOCKFLOW_TEST_CACHE_S3_ENDPOINT"]
    client = boto3.client("s3", endpoint_url=endpoint)
    client.create_bucket(Bucket=bucket)
    processes, logs, configurations, endpoints = [], [], [], []

    def start(index):
        root = tmp_path / f"environment-{index}"
        root.mkdir()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        config = root / "project.toml"
        config.write_text(
            f'schema_version=1\n[project]\nid="{project}"\n'
            '[state]\nbackend="postgresql"\ndsn_env="DOCKFLOW_TEST_STATE_POSTGRES_DSN"\n'
            "[execution]\nrun_lease_seconds=20\nrun_heartbeat_seconds=0.5\nshutdown_grace_seconds=1\n"
            '[images]\npull_policy="never"\n'
            f'[artifacts]\nbackend="s3"\nendpoint={json.dumps(endpoint)}\nbucket="{bucket}"\nprefix="shared"\nallow_insecure_http=true\n'
            '[cache]\ntopology="shared"\nstorage_identity="distributed-runtime"\n'
        )
        log = (root / "service.log").open("w")
        logs.append(log)
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "dockflow_cli.main",
                "pipelines",
                "--config",
                str(config),
                "serve",
                "--port",
                str(port),
            ],
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        processes.append(process)
        configurations.append(config)
        url = f"http://127.0.0.1:{port}"
        endpoints.append(url)

        def ready():
            assert process.poll() is None, (root / "service.log").read_text()
            try:
                return httpx.get(url + "/health/ready", timeout=1).status_code == 200
            except httpx.TransportError:
                return False

        wait_until(ready)
        return url

    def submit(url, value):
        response = httpx.post(
            url + "/dockflow/v1/runs",
            json={"pipeline_spec": document(), "parameters": {"value": value}},
            timeout=15,
        )
        assert response.status_code == 202, response.text
        return response.json()

    def run(url, identifier):
        response = httpx.get(url + f"/dockflow/v1/runs/{identifier}")
        assert response.status_code == 200
        return response.json()

    def started(url, identifier):
        entries = httpx.get(url + f"/dockflow/v1/runs/{identifier}/logs").json()[
            "entries"
        ]
        return any("distributed task started" in entry["text"] for entry in entries)

    try:
        first_url = start(0)
        first = submit(first_url, "first")
        wait_until(lambda: started(first_url, first["run_id"]))
        # Startup of another service must leave the first host's live Run alone.
        second_url = start(1)
        assert run(second_url, first["run_id"])["state"] == "running"
        direct_process = None
        if outcome == "direct":
            script = r"""
import json,sys
from dockflow_pipelines.config import load_settings
from dockflow_pipelines.core import Core
core=Core(load_settings(sys.argv[1]))
with core.store.owner():
    core.initialize()
    run,_=core.submit({"pipeline_spec":json.loads(sys.argv[2]),"parameters":{"value":"second"}},reserve=True)
    print(run["run_id"],flush=True)
    result=core.execute(run)
    print(json.dumps({"state":result["state"]}),flush=True)
"""
            direct_log = (tmp_path / "direct.log").open("w")
            logs.append(direct_log)
            direct_process = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    script,
                    str(configurations[1]),
                    json.dumps(document()),
                ],
                stdout=subprocess.PIPE,
                stderr=direct_log,
                text=True,
                start_new_session=True,
            )
            processes.append(direct_process)
            identifier = direct_process.stdout.readline().strip()
            assert identifier.startswith("run_"), (tmp_path / "direct.log").read_text()
            second = run(second_url, identifier)
        else:
            second = submit(
                second_url, "first" if outcome == "shared_key" else "second"
            )
        if outcome == "shared_key":
            settings = load_settings(configurations[1])
            waiting_observer = ControlStore(
                settings.state, project, storage=settings.state_storage
            )
            wait_until(
                lambda: any(
                    task.get("run_id") == second["run_id"]
                    and task.get("disposition") == "cache_wait"
                    for task in waiting_observer.list("tasks")
                )
            )
        else:
            wait_until(lambda: started(second_url, second["run_id"]))
        assert run(second_url, first["run_id"])["state"] == "running"
        assert run(first_url, second["run_id"])["state"] == "running"
        if outcome == "cancel":
            response = httpx.post(
                first_url + f"/dockflow/v1/runs/{second['run_id']}/cancel", json={}
            )
            assert response.status_code == 200, response.text
        elif outcome == "owner_death":
            # Kill only the first service and worker group; its Docker container
            # survives and must be retired by recovery on this same daemon.
            os.killpg(processes[0].pid, signal.SIGKILL)
            processes[0].wait(timeout=10)
            from dockflow_pipelines.core import Core
            from dockflow_pipelines.service import Scheduler

            recovery = Core(load_settings(configurations[0]))
            with recovery.store.owner():
                recovery.initialize()
                with recovery.store.database.transaction() as connection:
                    recovery.store.database.execute(
                        connection,
                        "UPDATE dockflow_run_owners SET lease_expires_at=0 WHERE project_id=? AND run_id=?",
                        (project, first["run_id"]),
                    )
                Scheduler(recovery).reconcile()
                assert (
                    recovery.store.get("runs", first["run_id"])["state"]
                    == "interrupted"
                )
                assert (
                    recovery.store.get("runs", second["run_id"])["state"] == "running"
                )
        expected = "cancelled" if outcome == "cancel" else "succeeded"
        wait_until(lambda: run(second_url, second["run_id"])["state"] == expected)
        first_expected = "interrupted" if outcome == "owner_death" else "succeeded"
        wait_until(lambda: run(second_url, first["run_id"])["state"] == first_expected)
        settings = load_settings(configurations[1])
        observer = ControlStore(settings.state, project, storage=settings.state_storage)
        attempts = observer.list("attempts")
        expected_attempts = 1 if outcome == "shared_key" else 2
        assert len(attempts) == expected_attempts
        assert (
            len({attempt["container_id"] for attempt in attempts}) == expected_attempts
        )
        if direct_process is not None:
            output, _ = direct_process.communicate(timeout=15)
            assert direct_process.returncode == 0, (tmp_path / "direct.log").read_text()
            assert json.loads(output)["state"] == "succeeded"
        if outcome in {"success", "direct", "shared_key"}:
            third = submit(second_url, "first")
            wait_until(lambda: run(second_url, third["run_id"])["state"] == "succeeded")
            assert len(observer.list("attempts")) == expected_attempts
            reused = [
                task
                for task in observer.list("tasks")
                if task["run_id"] == third["run_id"]
            ]
            assert reused[0]["state"] == "reused"
            assert len(observer.list("artifacts")) == expected_attempts
        assert observer.check()["valid"]
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)
        for log in logs:
            log.close()
        # Retire any remaining labelled containers only for this test project.
        import docker

        docker_client = docker.from_env()
        try:
            for container in docker_client.containers.list(
                all=True, filters={"label": "dockflow.project=" + project}
            ):
                container.remove(force=True)
        finally:
            docker_client.close()
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
            keys = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if keys:
                client.delete_objects(Bucket=bucket, Delete={"Objects": keys})
        client.delete_bucket(Bucket=bucket)
