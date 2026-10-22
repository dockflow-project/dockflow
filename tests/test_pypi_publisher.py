"""The patched publisher preserves candidate files and gates credential use."""

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "publisher", Path(__file__).resolve().parents[1] / "tools/publish_pypi.py"
)
assert SPEC and SPEC.loader
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)


@pytest.fixture
def packages(tmp_path):
    folder = tmp_path / "packages"
    folder.mkdir()
    for name in ("example-1.0-py3-none-any.whl", "example-1.0.tar.gz"):
        (folder / name).write_bytes(b"verified bytes")
    return folder


def test_upload_refuses_unprotected_context(packages, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(ValueError, match="protected canonical main"):
        publisher.publish(packages)


def test_validation_has_no_network_or_credentials(packages, monkeypatch):
    commands = []
    monkeypatch.setattr(
        publisher.subprocess, "run", lambda cmd, **kw: commands.append(cmd)
    )
    publisher.publish(packages, check_only=True)
    cmd = commands[0]
    assert "none" in cmd and "--network" in cmd
    assert "--env" not in cmd and "check" in cmd


def test_upload_uses_oidc_names_and_separate_writable_copy(packages, monkeypatch):
    env = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": "dockflow-project/dockflow",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_WORKFLOW_REF": "dockflow-project/dockflow/.github/workflows/publish.yaml@refs/heads/main",
        "ACTIONS_ID_TOKEN_REQUEST_URL": "https://oidc.invalid/",
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "synthetic-test-secret",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    def run(cmd, **kwargs):
        assert "synthetic-test-secret" not in " ".join(cmd)
        assert "ACTIONS_ID_TOKEN_REQUEST_TOKEN" in cmd
        assert "INPUT_ATTESTATIONS=true" in cmd
        assert "INPUT_SKIP_EXISTING=true" in cmd
        mount = cmd[cmd.index("--mount") + 1]
        staged = Path(mount.split("src=", 1)[1].split(",dst=", 1)[0]) / "packages"
        assert staged != packages
        assert [p.name for p in sorted(staged.iterdir())] == [
            p.name for p in sorted(packages.iterdir())
        ]
        (staged / "example.publish.attestation").write_text("generated")

    monkeypatch.setattr(publisher.subprocess, "run", run)
    publisher.publish(packages)
    assert len(list(packages.iterdir())) == 2
    assert all(p.read_bytes() == b"verified bytes" for p in packages.iterdir())
