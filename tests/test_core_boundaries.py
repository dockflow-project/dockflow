"""Dependency direction and import isolation are public packaging contracts."""

import ast
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_core_has_no_domain_imports_or_schema_objects():
    for path in (ROOT / "packages/core/src/dockflow_core").glob("*.py"):
        tree = ast.parse(path.read_text())
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert not any(
                    token in node.value
                    for token in (
                        "dockflow_pipelines",
                        "dockflow_artifacts",
                        "dockflow_cli",
                        "dockflow_run_owners",
                        "dockflow_artifact_records",
                        "df_cache_",
                    )
                ), path.name
        assert not any(
            name.startswith("dockflow_") and name.split(".")[0] != "dockflow_core"
            for name in imports
        ), path.name


def test_each_consumer_requires_core_and_core_requires_no_consumer():
    version = (ROOT / "VERSION").read_text().strip()
    for name in ("cli", "artifacts", "pipelines"):
        project = tomllib.loads((ROOT / f"packages/{name}/pyproject.toml").read_text())[
            "project"
        ]
        assert f"dockflow-core=={version}" in project["dependencies"]
    core = tomllib.loads((ROOT / "packages/core/pyproject.toml").read_text())["project"]
    assert core["dependencies"] == []
    assert set(core["optional-dependencies"]) == {"postgresql"}


def test_all_core_modules_import_without_consumers_or_optional_drivers(tmp_path):
    code = """
import importlib.abc, pkgutil, sys
class Blocked(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {
            'dockflow_pipelines', 'dockflow_artifacts', 'dockflow_cli',
            'psycopg', 'docker', 'kfp', 'boto3', 'fastapi', 'typer',
        }:
            raise AssertionError('unexpected dependency: ' + fullname)
sys.meta_path.insert(0, Blocked())
import dockflow_core
for module in pkgutil.walk_packages(dockflow_core.__path__, dockflow_core.__name__ + '.'):
    __import__(module.name)
"""
    subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path, check=True, capture_output=True
    )
    assert list(tmp_path.iterdir()) == []
