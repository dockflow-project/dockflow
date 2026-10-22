import os
import subprocess
import sys
from importlib import metadata
from types import SimpleNamespace

import pytest
import typer
from dockflow_cli.main import create_app, main
from rich.text import Text
from typer.testing import CliRunner


class Entry:
    def __init__(self, name, value, loaded):
        self.name, self.value, self.loaded = name, value, loaded
        self.dist = SimpleNamespace(name="fixture-provider")

    def load(self):
        if isinstance(self.loaded, Exception):
            raise self.loaded
        return self.loaded


def test_cli_without_features_and_deterministic_registration(monkeypatch):
    monkeypatch.setattr(metadata, "entry_points", lambda **kwargs: [])
    result = CliRunner().invoke(create_app(), [])
    assert result.exit_code == 0 and "Install a Dockflow feature" in result.stdout
    plugins = []
    for name in ("zulu", "alpha"):
        plugin = typer.Typer(help=f"{name} description")
        plugin.command("ping")(lambda: typer.echo("pong"))
        plugins.append(Entry(name, name + ":app", plugin))
    monkeypatch.setattr(metadata, "entry_points", lambda **kwargs: plugins)
    app = create_app()
    help_text = CliRunner().invoke(app, ["--help"]).stdout
    assert help_text.index("alpha description") < help_text.index("zulu description")
    assert CliRunner().invoke(app, ["alpha", "ping"]).stdout.strip() == "pong"


@pytest.mark.parametrize(
    "entries",
    [
        [Entry("bad_name", "x:app", None)],
        [Entry("help", "x:app", None)],
        [Entry("same", "a:app", None), Entry("same", "b:app", None)],
        [Entry("broken", "x:app", ValueError("bad import"))],
        [Entry("broken", "x:app", object())],
    ],
)
def test_broken_providers_fail_with_identity(monkeypatch, entries):
    monkeypatch.setattr(metadata, "entry_points", lambda **kwargs: entries)
    with pytest.raises(RuntimeError, match="fixture-provider"):
        create_app()


def test_version_bypasses_discovery(monkeypatch, capsys):
    def forbidden(**kwargs):
        raise AssertionError("Version must not discover providers")

    monkeypatch.setattr(metadata, "entry_points", forbidden)
    monkeypatch.setattr(sys, "argv", ["dockflow", "--version"])
    main()
    assert capsys.readouterr().out.startswith("dockflow ")


@pytest.mark.parametrize("force_color", [False, True])
def test_nested_help_does_not_import_execution_dependencies(force_color):
    probe = """
import sys
class Guard:
 def find_spec(self, fullname, *args):
  if fullname.split('.')[0] in {'kfp','docker','ml_metadata','fastapi','boto3'}:
   raise AssertionError('Unexpected heavyweight import: '+fullname)
sys.meta_path.insert(0,Guard())
sys.argv=['dockflow','pipelines','run','--help']
from dockflow_cli.main import main
main()
"""
    environment = os.environ.copy()
    environment["TERM"] = "xterm-256color" if force_color else "dumb"
    environment["FORCE_COLOR"] = "1" if force_color else "0"
    if force_color:
        environment.pop("NO_COLOR", None)
    else:
        environment["NO_COLOR"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        env=environment,
    )
    assert result.returncode == 0, result.stderr
    assert "--parameter" in Text.from_ansi(result.stdout).plain
