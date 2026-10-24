"""The host and a container must contend on one bind-mounted state lock."""

import json
import os
from pathlib import Path

import pytest
from dockflow_pipelines.metadata import ControlStore

pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(
        os.environ.get("DOCKFLOW_TEST_DOCKER") != "1" or os.name != "posix",
        reason="Requires an enabled Linux Docker daemon and POSIX host",
    ),
]


def test_host_and_bind_mounted_container_share_owner_lock(tmp_path):
    import docker

    source = Path(__file__).resolve().parents[1] / "src"
    state = tmp_path / "state"
    store = ControlStore(state, "bind-mount-owner-test")
    script = """
import json
from pathlib import Path
from dockflow_database.errors import DockflowError
from dockflow_pipelines.metadata import ControlStore
store = ControlStore(Path('/shared-state'), 'bind-mount-owner-test')
try:
    with store.owner():
        print(json.dumps({'acquired': store.database.owner_metadata()}))
except DockflowError as error:
    print(json.dumps({'error': error.as_dict()}))
"""
    client = docker.from_env()
    try:
        # Image preparation is explicit; this test must not pull an image.
        client.images.get("python:3.13-slim")

        def probe():
            output = client.containers.run(
                "python:3.13-slim",
                ["python", "-c", script],
                environment={
                    "PYTHONPATH": "/opt/dockflow:/opt/dockflow-database",
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
                volumes={
                    str(source): {"bind": "/opt/dockflow", "mode": "ro"},
                    str(source.parents[1] / "database/src"): {
                        "bind": "/opt/dockflow-database",
                        "mode": "ro",
                    },
                    str(state): {"bind": "/shared-state", "mode": "rw"},
                },
                user=f"{os.getuid()}:{os.getgid()}",
                network_disabled=True,
                remove=True,
            )
            return json.loads(output)

        with store.owner(endpoint="http://127.0.0.1:8080"):
            lock = state / "state.sqlite"
            identity = store.database.owner_metadata()
            inode = lock.stat().st_ino
            error = probe()["error"]
            assert error["code"] == "CONFLICT"
            detail = error["details"][0]
            assert detail["owner"] == identity
            assert lock.stat().st_ino == inode

        acquired = probe()["acquired"]
        assert acquired["owner_id"] != identity["owner_id"]
        assert acquired["mode"] == "local"
        assert acquired["pid"] == 1
        assert lock.stat().st_ino == inode
        assert store.database.owner_metadata() == acquired
        with store.owner():
            assert store.database.owner_metadata()["owner_id"] != acquired["owner_id"]
    finally:
        client.close()
