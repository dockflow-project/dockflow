"""Infrastructure remains lazy across the persistence adapter boundaries."""

import subprocess
import sys

from dockflow_pipelines.errors import DockflowError
from dockflow_pipelines.metadata import ControlStore


def test_core_construction_and_validation_work_without_runtime_dependencies(tmp_path):
    config = tmp_path / "pipelines.toml"
    config.write_text('schema_version = 1\n[project]\nid = "lazy-boundaries"\n')
    script = r"""
import importlib.abc
import sys

blocked = {"ml_metadata", "kfp", "docker", "boto3", "fastapi", "uvicorn"}

class NoRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in blocked:
            raise AssertionError(f"Unexpected runtime import: {fullname}")

sys.meta_path.insert(0, NoRuntime())
from dockflow_pipelines.config import load_settings
from dockflow_pipelines.core import Core
from dockflow_pipelines.metadata import MLMDIndex, new_id, utc_now
from dockflow_pipelines.ownership import StateOwnership

core = Core(load_settings(sys.argv[1]))
result = core.validate({"pipeline_spec": {
    "pipelineInfo": {"name": "offline-validation"},
    "schemaVersion": "2.1.0",
    "sdkVersion": "kfp-2.17.0",
    "root": {"executorLabel": "exec-noop"},
    "deploymentSpec": {"executors": {"exec-noop": {"container": {
        "image": "example.invalid/noop:1", "command": ["true"]
    }}}}
}})
assert result["valid"] is True
assert not any(name.split(".")[0] in blocked for name in sys.modules)
assert not core.settings.state.exists()
assert not core.settings.work_directory.exists()
assert not core.settings.artifacts["root"].exists()
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(config)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == [config]


def test_missing_mlmd_reports_installation_error_before_creating_index(tmp_path):
    script = r"""
import importlib.abc
import sys
from pathlib import Path

class NoMLMD(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] == "ml_metadata":
            raise ModuleNotFoundError("MLMD intentionally unavailable")

sys.meta_path.insert(0, NoMLMD())
from dockflow_pipelines.errors import DockflowError
from dockflow_pipelines.metadata import MLMDIndex

try:
    MLMDIndex(Path(sys.argv[1]) / "absent" / "mlmd.sqlite", "lazy-boundaries")
except DockflowError as error:
    assert (error.code, error.status) == ("UNAVAILABLE", 503)
    assert "dockflow-pipelines[runtime]" in error.message
else:
    raise AssertionError("A missing native runtime was silently bypassed")
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert not list(tmp_path.iterdir())


def test_failed_journal_inspection_releases_ownership_for_a_clean_retry(
    tmp_path, monkeypatch
):
    store = ControlStore(tmp_path / "state", "lazy-boundaries")

    def unreadable_records():
        raise DockflowError("Corrupt accepted record", code="CONFLICT", status=409)

    with monkeypatch.context() as patch:
        patch.setattr(store, "records", unreadable_records)
        try:
            with store.owner():
                raise AssertionError("Journal failure did not block ownership setup")
        except DockflowError as error:
            assert error.message == "Corrupt accepted record"
    assert not (store.state / "project.json").exists()
    inode = (store.state / "owner.lock").stat().st_ino
    contender = ControlStore(store.state, "lazy-boundaries")
    with contender.owner():
        contender.initialize(require_mlmd=False)
    assert (store.state / "owner.lock").stat().st_ino == inode
    with store.owner():
        store.require_owner()
