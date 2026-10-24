"""Filesystem layout choices are explicit, isolated and resolved before I/O."""

import json

import pytest
from dockflow_database.errors import DockflowError
from dockflow_pipelines.config import load_settings


def config(tmp_path, artifacts="", other=""):
    path = tmp_path / "project.toml"
    path.write_text(
        'schema_version=1\n[project]\nid="layout-test"\n'
        f"{other}\n[artifacts]\n{artifacts}\n"
    )
    return path


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ("", "artifacts/managed"),
        ('root="old-store"', "old-store/managed"),
        ('managed_root="data/artifacts"', "data/artifacts"),
    ],
)
def test_managed_directory_resolves_from_project_not_cwd(
    tmp_path, monkeypatch, options, expected
):
    path = config(tmp_path, options)
    monkeypatch.chdir(tmp_path.parent)
    settings = load_settings(path)
    assert settings.artifacts["managed_root"] == tmp_path / expected
    assert not (tmp_path / expected).exists()
    assert not settings.state.exists()


def test_managed_directory_environment_and_option_precedence(tmp_path, monkeypatch):
    path = config(tmp_path, 'managed_root="file-store"')
    monkeypatch.setenv("DOCKFLOW_PIPELINES_ARTIFACTS_MANAGED_ROOT", "env-store")
    settings = load_settings(path)
    assert settings.artifacts["managed_root"] == tmp_path / "env-store"
    assert settings.sources["artifacts.managed_root"] == "environment"
    settings = load_settings(path, overrides={"artifacts.managed_root": "option-store"})
    assert settings.artifacts["managed_root"] == tmp_path / "option-store"
    assert settings.sources["artifacts.managed_root"] == "option"
    assert settings.effective()["artifacts"]["managed_root"] == str(
        tmp_path / "option-store"
    )


@pytest.mark.parametrize(
    ("options", "other"),
    [
        ('root="old"\nmanaged_root="new"', ""),
        ('managed_root=""', ""),
        ("managed_root=42", ""),
        ('managed_root=".dockflow"', ""),
        ('managed_root="."', ""),
        ('managed_root="work/output"', '[execution]\nwork_directory="work"'),
        ('managed_root="data"', '[execution]\nwork_directory="data/work"'),
        ('managed_root="data"\nexternal_roots=["data/external"]', ""),
        ('managed_root="data/artifacts"\nexternal_roots=["data"]', ""),
        ('managed_root="index/artifacts"', '[metadata]\ndirectory="index"'),
        ('managed_root="data"', '[metadata]\ndirectory="data/index"'),
        (
            'backend="s3"\nendpoint="https://storage.example"\nbucket="test"\n'
            'managed_root="data/artifacts"',
            "",
        ),
    ],
)
def test_invalid_managed_directory_fails_without_mutation(tmp_path, options, other):
    path = config(tmp_path, options, other)
    before = list(tmp_path.iterdir())
    with pytest.raises(DockflowError):
        load_settings(path)
    assert list(tmp_path.iterdir()) == before


def test_environment_does_not_silently_replace_a_different_layout(
    tmp_path, monkeypatch
):
    path = config(tmp_path, 'root="old"')
    monkeypatch.setenv("DOCKFLOW_PIPELINES_ARTIFACTS_MANAGED_ROOT", "new")
    with pytest.raises(DockflowError, match="not both"):
        load_settings(path)
    monkeypatch.setenv("DOCKFLOW_PIPELINES_ARTIFACTS_MANAGED_ROOT", "")
    with pytest.raises(DockflowError, match="cannot be empty"):
        load_settings(path)


def test_effective_snapshot_retains_complete_nonsecret_origins(tmp_path, monkeypatch):
    token = tmp_path / "secret.txt"
    token.write_text("private-test-token")
    path = config(
        tmp_path,
        other='[state]\ndirectory="control"\n[service]\ntoken_file="secret.txt"',
    )
    monkeypatch.setenv("DOCKFLOW_PIPELINES_TIMEOUT_SECONDS", "12")
    settings = load_settings(path, overrides={"service.port": 8090})
    snapshot = settings.effective()
    origins = snapshot["sources"]
    assert origins["project.id"] == "file"
    assert origins["execution.timeout_seconds"] == "environment"
    assert origins["service.port"] == "option"
    assert origins["reuse.scope"] == "default"
    assert origins["state.database"] == "derived"
    assert origins["execution.work_directory"] == "derived"
    assert origins["artifacts.root"] == "default"
    assert origins["artifacts.managed_root"] == "derived"
    assert origins["config_path"] == "option"
    assert snapshot["state_storage"]["database"] == str(
        tmp_path / "control/state.sqlite"
    )
    assert snapshot["work_directory"] == str(tmp_path / "control/work")
    assert snapshot["execution"]["timeout_seconds"] == 12
    assert snapshot["service"]["port"] == 8090
    assert token.read_text() not in json.dumps(snapshot)
    snapshot["sources"]["service.port"] = "file"
    assert settings.sources["service.port"] == "option"
    assert not settings.state.exists()


def test_config_selection_and_explicit_derived_fields(tmp_path, monkeypatch):
    path = config(
        tmp_path,
        'managed_root="published"',
        '[state]\ndatabase="index/state.sqlite"\n[execution]\nwork_directory="work"',
    )
    monkeypatch.setenv("DOCKFLOW_PIPELINES_CONFIG", str(path))
    sources = load_settings().effective()["sources"]
    assert sources["config_path"] == "environment"
    for key in (
        "state.database",
        "execution.work_directory",
        "artifacts.managed_root",
    ):
        assert sources[key] == "file"
    assert "artifacts.root" not in sources
    monkeypatch.delenv("DOCKFLOW_PIPELINES_CONFIG")
    path.rename(tmp_path / ".dockflow-pipelines.toml")
    monkeypatch.chdir(tmp_path)
    assert load_settings().effective()["sources"]["config_path"] == "discovery"


@pytest.mark.parametrize(
    "fields",
    [
        "run_lease_seconds=0",
        "run_lease_seconds=nan",
        "run_heartbeat_seconds=inf",
        "run_heartbeat_seconds=true",
        'run_lease_seconds="120"',
        "run_lease_seconds=40\nrun_heartbeat_seconds=30",
    ],
)
def test_invalid_run_lease_policy_is_side_effect_free(tmp_path, fields):
    path = config(tmp_path, other="[execution]\n" + fields)
    with pytest.raises(DockflowError):
        load_settings(path)
    assert list(tmp_path.iterdir()) == [path]


def test_backend_selects_coordination_and_lease_environment_overrides(
    tmp_path, monkeypatch
):
    path = config(
        tmp_path,
        other='[state]\nbackend="postgresql"\ndsn_env="DOCKFLOW_TEST_CONNECTION"',
    )
    monkeypatch.setenv("DOCKFLOW_PIPELINES_RUN_LEASE_SECONDS", "60")
    monkeypatch.setenv("DOCKFLOW_PIPELINES_RUN_HEARTBEAT_SECONDS", "15")
    settings = load_settings(path)
    assert settings.execution["run_lease_seconds"] == 60
    assert settings.execution["run_heartbeat_seconds"] == 15
    assert settings.sources["execution.run_lease_seconds"] == "environment"
    assert settings.cache["database"] == settings.state_storage
    assert list(tmp_path.iterdir()) == [path]
