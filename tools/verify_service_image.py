#!/usr/bin/env python3
"""Smoke-test the built service in an isolated, disposable Docker-in-Docker stack."""

import argparse
import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = "docker:29.1.3-dind@sha256:173f284a4299164772a90f52b373e73e087583c0963f1334c9995f190ef6f3f5"


def docker(*args: str, check: bool = True) -> str:
    result = subprocess.run(["docker", *args], text=True, capture_output=True)
    if check and result.returncode:
        # Avoid retaining host paths or arbitrary daemon diagnostics in receipts.
        raise RuntimeError(f"Docker {args[0]} failed (exit {result.returncode})")
    return result.stdout.strip()


def wait_for(probe, description: str, seconds: int = 120):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            value = probe()
            if value:
                return value
        except (OSError, RuntimeError):
            pass
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {description}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument(
        "--out", type=Path, default=ROOT / "dist/service-verification.json"
    )
    args = parser.parse_args()
    identity = json.loads(docker("image", "inspect", args.image))[0]
    prefix = f"dockflow-qualification-{uuid.uuid4().hex[:12]}"
    engine, service = f"{prefix}-engine", f"{prefix}-service"
    component = f"{prefix}-components:v1"
    volumes = {
        key: f"{prefix}-{key}" for key in ("state", "execution", "artifacts", "socket")
    }
    try:
        docker("network", "create", prefix)
        for volume in volumes.values():
            docker("volume", "create", volume)
        docker("pull", ENGINE)
        mounts = [
            item
            for key, target in (
                ("state", "/state"),
                ("execution", "/execution"),
                ("artifacts", "/artifacts"),
                ("socket", "/docker-socket"),
            )
            for item in ("--mount", f"type=volume,src={volumes[key]},dst={target}")
        ]
        docker(
            "run",
            "-d",
            "--name",
            engine,
            "--network",
            prefix,
            "--privileged",
            *mounts,
            "--entrypoint",
            "dockerd",
            ENGINE,
            "--host=unix:///docker-socket/docker.sock",
        )
        wait_for(
            lambda: docker(
                "exec",
                engine,
                "docker",
                "-H",
                "unix:///docker-socket/docker.sock",
                "info",
            ),
            "isolated Docker engine",
        )
        docker(
            "exec",
            engine,
            "chown",
            "10001:10001",
            "/state",
            "/execution",
            "/artifacts",
            "/docker-socket",
            "/docker-socket/docker.sock",
        )
        docker("build", "-t", component, str(ROOT / "examples/quickstart"))
        save = subprocess.Popen(["docker", "save", component], stdout=subprocess.PIPE)
        assert save.stdout is not None
        with save.stdout:
            load = subprocess.run(
                [
                    "docker",
                    "exec",
                    "-i",
                    engine,
                    "docker",
                    "-H",
                    "unix:///docker-socket/docker.sock",
                    "load",
                ],
                stdin=save.stdout,
                capture_output=True,
            )
        if save.wait() or load.returncode:
            raise RuntimeError(
                "Could not load the component image into the isolated engine"
            )
        with tempfile.TemporaryDirectory(prefix="dockflow-image-check-") as directory:
            config = Path(directory)
            config.chmod(0o755)
            definition = (
                ROOT / "examples/quickstart/orchestration/kfp/compiled/statistics.yaml"
            ).read_text()
            (config / "pipeline.yaml").write_text(
                definition.replace("dockflow-quickstart-components:v1", component)
            )
            (config / "dockflow.toml").write_text("""schema_version = 1
[project]
id = "release-qualification"
root = "/config"
[definitions.pipelines]
statistics = "pipeline.yaml"
[state]
directory = "/state"
[execution]
work_directory = "/execution"
[artifacts]
backend = "filesystem"
managed_root = "/artifacts"
[images]
pull_policy = "never"
""")
            docker(
                "run",
                "-d",
                "--name",
                service,
                "--network",
                prefix,
                "--group-add",
                "0",
                *mounts,
                "--mount",
                f"type=bind,src={config},dst=/config,readonly",
                "--env",
                "DOCKER_HOST=unix:///docker-socket/docker.sock",
                "--publish",
                "127.0.0.1::8080",
                args.image,
            )
            address = docker("port", service, "8080/tcp")
            endpoint = f"http://{address}"

            def request(path: str, data: dict | None = None):
                payload = None if data is None else json.dumps(data).encode()
                req = urllib.request.Request(
                    endpoint + path,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    raw = response.read()
                    return (
                        json.loads(raw)
                        if response.headers.get_content_type() == "application/json"
                        else raw
                    )

            wait_for(lambda: request("/health/ready"), "service readiness")
            assert b"<html" in request("/ui/").lower()
            assert request("/dockflow/v1/openapi.json")["openapi"].startswith("3.")
            request("/dockflow/v1/definitions/refresh", {})
            definitions = request("/dockflow/v1/definitions")["items"]
            definition_id = definitions[0]["definition_id"]
            run_ids = []
            for _ in range(2):
                run = request(
                    "/dockflow/v1/runs",
                    {
                        "definition_id": definition_id,
                        "parameters": {"count": 10},
                        "reuse": {"scope": "global"},
                    },
                )
                run_id = run["run_id"]
                run_ids.append(run_id)

                def completed(selected_run=run_id):
                    snapshot = request(f"/dockflow/v1/runs/{selected_run}")
                    return (
                        snapshot
                        if snapshot["state"]
                        in {"succeeded", "failed", "cancelled", "interrupted"}
                        else None
                    )

                result = wait_for(completed, "pipeline completion")
                assert result["state"] == "succeeded", "Image pipeline execution failed"
            artifacts = request("/dockflow/v1/artifacts")["items"]
            assert len(artifacts) == 2, (
                "Expected dataset and report without duplicate publications"
            )
            logs = request(f"/dockflow/v1/runs/{run_ids[0]}/logs")["entries"]
            assert any('"mean": 5.5' in entry["text"] for entry in logs)
            docker("restart", "--time", "45", service)
            # Docker may assign another ephemeral host port on restart.
            endpoint = f"http://{docker('port', service, '8080/tcp')}"
            wait_for(lambda: request("/health/ready"), "service restart")
            assert request(f"/dockflow/v1/runs/{run_ids[0]}")["state"] == "succeeded"
            assert len(request("/dockflow/v1/artifacts")["items"]) == 2
        receipt = {
            "schema_version": 1,
            "passed": True,
            "image_id": identity["Id"],
            "platform": f"{identity['Os']}/{identity['Architecture']}",
            "engine_image": ENGINE,
            "docker_server": json.loads(
                docker("version", "--format", "{{json .Server}}")
            )["Version"],
            "checks": [
                "non-root service readiness",
                "packaged UI and OpenAPI",
                "two-step execution",
                "artifact publication",
                "reuse without duplicate artifacts",
                "retained component logs",
                "restart with persistent history",
            ],
            "scope": "Disposable isolated Docker engine and filesystem artifacts; no Docker Desktop or ARM64 qualification",
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt, indent=2))
    except Exception:
        logs = subprocess.run(
            ["docker", "logs", "--tail", "40", service],
            capture_output=True,
            text=True,
        )
        print(logs.stdout + logs.stderr, file=sys.stderr)
        raise
    finally:
        for container in (service, engine):
            docker("rm", "--force", "--volumes", container, check=False)
        for volume in volumes.values():
            docker("volume", "rm", volume, check=False)
        docker("network", "rm", prefix, check=False)
        docker("image", "rm", component, check=False)


if __name__ == "__main__":
    main()
