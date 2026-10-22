"""The independently installed feature is discovered by the shared host."""

import subprocess
import sys
from importlib import metadata

from rich.text import Text


def test_real_pipeline_registration_and_nested_help():
    entries = metadata.entry_points(group="dockflow_cli.modules")
    assert any(
        entry.name == "pipelines" and entry.value == "dockflow_pipelines.cli:app"
        for entry in entries
    )
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "dockflow_cli.main",
            "pipelines",
            "artifacts",
            "import",
            "--help",
        ],
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0
    help_text = Text.from_ansi(process.stdout).plain
    assert "--uri" in help_text and "--type" in help_text
    assert "Traceback" not in process.stderr
