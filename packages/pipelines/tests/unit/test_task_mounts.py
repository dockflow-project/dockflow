"""Only owner configuration can add explicit task storage/configuration mounts."""

import re

import pytest
from dockflow_pipelines.config import load_settings
from dockflow_pipelines.definitions import DefinitionError
from dockflow_pipelines.errors import DockflowError
from dockflow_pipelines.executor import resource_limits, task_volumes


def test_mounts_are_normalized_and_part_of_execution_signature(tmp_path):
    config = tmp_path / ".dockflow-pipelines.toml"
    config.write_text("""
schema_version=1
[project]
id="mount-test"
[[execution.task_mounts]]
source="data/published"
read_only=false
[[execution.task_mounts]]
source="secrets/config.json"
target="/etc/artifacts/config.json"
""")
    settings = load_settings(config)
    mounts = settings.execution["task_mounts"]
    assert (
        mounts[0]["source"] == mounts[0]["target"] == str(tmp_path / "data/published")
    )
    assert mounts[1]["read_only"] is True
    assert mounts[1]["target"] == "/etc/artifacts/config.json"
    assert resource_limits({}, settings.execution)["dockflow_mounts"] == mounts


@pytest.mark.parametrize("target", ["/", "../relative", "/unsafe/../path", "C:/data"])
def test_invalid_mount_target_rejected(tmp_path, target):
    config = tmp_path / "config.toml"
    config.write_text(f"""
schema_version=1
[project]
id="mount-test"
[[execution.task_mounts]]
source="data"
target="{target}"
""")
    with pytest.raises(DockflowError):
        load_settings(config)


def test_transport_preserves_runtime_mount_and_rejects_overlap(tmp_path):
    root = tmp_path / "runtime"
    root.mkdir()
    source = tmp_path / "config.json"
    source.write_text("{}")
    base = {str(root): {"bind": str(root), "mode": "rw"}}
    configured = [
        {
            "source": str(source),
            "target": "/etc/artifacts/config.json",
            "read_only": True,
        }
    ]
    volumes = task_volumes(base, configured)
    assert volumes[str(source)]["mode"] == "ro"
    assert volumes[str(root)] == base[str(root)]
    configured[0]["target"] = str(root / "shadow")
    with pytest.raises(DefinitionError):
        task_volumes(base, configured)
    configured[0]["source"] = str(tmp_path / "missing")
    configured[0]["target"] = "/etc/artifacts/config.json"
    with pytest.raises(DefinitionError, match=re.escape(str(tmp_path / "missing"))):
        task_volumes(base, configured)
