"""Package receipts distinguish observed source state from release authority."""

import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "verify_packages", Path(__file__).resolve().parents[1] / "tools/verify_packages.py"
)
assert SPEC is not None and SPEC.loader is not None
verification = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verification)


def git(root: Path, *arguments: str) -> str:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    environment.update(
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_AUTHOR_NAME="Fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="Fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
    )
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    if shutil.which("git") is None:
        pytest.skip("Git is required for disposable source-state fixtures")
    git(tmp_path, "init", "--initial-branch=qualification")
    return tmp_path


@pytest.fixture
def committed(repository: Path) -> Path:
    (repository / "source.txt").write_text("original\n")
    git(repository, "add", "source.txt")
    git(repository, "-c", "commit.gpgsign=false", "commit", "-m", "Fixture")
    return repository


def test_unborn_checkout_has_no_invented_commit(repository: Path):
    source = verification.source_provenance(repository)
    assert source["state"] == "unborn"
    assert source["commit"] is None
    assert source["branch"] == "qualification"
    assert source["dirty"] is False
    assert "not determined" in source["note"]


def test_clean_committed_checkout(committed: Path):
    source = verification.source_provenance(committed)
    assert source["state"] == "clean"
    assert source["commit"] == git(committed, "rev-parse", "HEAD")
    assert source["branch"] == "qualification"
    assert source["dirty"] is False
    assert "Uncommitted" not in source["note"]


@pytest.mark.parametrize("filename", ["source.txt", "untracked.txt"])
def test_modified_and_untracked_files_make_checkout_dirty(
    committed: Path, filename: str
):
    (committed / filename).write_text("changed\n")
    source = verification.source_provenance(committed)
    assert source["state"] == "dirty"
    assert source["dirty"] is True
    assert source["commit"] == git(committed, "rev-parse", "HEAD")


def test_detached_head_preserves_commit_without_inventing_branch(committed: Path):
    git(committed, "checkout", "--detach")
    source = verification.source_provenance(committed)
    assert source["state"] == "clean"
    assert source["commit"] == git(committed, "rev-parse", "HEAD")
    assert source["branch"] is None
    assert source["dirty"] is False


def test_nested_archive_is_not_attributed_to_parent_repository(committed: Path):
    archive = committed / "unpacked-source"
    archive.mkdir()
    source = verification.source_provenance(archive)
    assert source["state"] == "unavailable"
    assert source["reason"] == "checkout_not_at_project_root"
    assert source["commit"] is None
    assert source["branch"] is None
    assert source["dirty"] is None


def test_directory_without_git_metadata(tmp_path: Path):
    source = verification.source_provenance(tmp_path)
    assert source["state"] == "unavailable"
    assert source["commit"] is None
    assert source["branch"] is None
    assert source["dirty"] is None


@pytest.mark.parametrize("error", [FileNotFoundError, PermissionError])
def test_unavailable_git_is_not_reported_as_a_clean_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: type[OSError]
):
    def unavailable(*args, **kwargs):
        raise error("synthetic execution failure")

    monkeypatch.setattr(verification.subprocess, "run", unavailable)
    source = verification.source_provenance(tmp_path)
    assert source["state"] == "unavailable"
    assert source["reason"] == "git_execution_failed"
    assert source["dirty"] is None


@pytest.mark.parametrize(
    ("command", "reason"),
    [
        (("status", "--porcelain"), "git_status_failed"),
        (("symbolic-ref", "--quiet", "HEAD"), "git_branch_failed"),
        (("rev-parse", "--verify", "HEAD^{commit}"), "git_head_unresolved"),
    ],
)
def test_git_errors_do_not_invent_clean_or_unborn_state(
    committed: Path, monkeypatch: pytest.MonkeyPatch, command: tuple, reason: str
):
    actual_run = subprocess.run

    def fail_selected(arguments, **kwargs):
        if tuple(arguments[1:]) == command:
            return subprocess.CompletedProcess(arguments, 128, "", "synthetic error")
        return actual_run(arguments, **kwargs)

    monkeypatch.setattr(verification.subprocess, "run", fail_selected)
    source = verification.source_provenance(committed)
    assert source["state"] == "unavailable"
    assert source["reason"] == reason
    if reason == "git_status_failed":
        assert source["dirty"] is None
    if reason == "git_head_unresolved":
        assert source["commit"] is None


def test_caller_git_environment_cannot_change_provenance(
    committed: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("GIT_DIR", str(committed / "absent"))
    monkeypatch.setenv("GIT_WORK_TREE", str(committed.parent))
    monkeypatch.setenv("GIT_INDEX_FILE", str(committed / "other-index"))
    source = verification.source_provenance(committed)
    assert source["state"] == "clean"
    assert source["commit"] == git(committed, "rev-parse", "HEAD")
    assert not (committed / "other-index").exists()
