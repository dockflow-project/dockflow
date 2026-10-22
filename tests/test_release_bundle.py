"""Publication refuses changed bytes, provenance and conflicting immutable files."""

import importlib.util
import json
import subprocess
import urllib.error
from io import BytesIO
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "release", Path(__file__).resolve().parents[1] / "tools/release.py"
)
assert SPEC is not None and SPEC.loader is not None
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
COMMIT = "a" * 40
IMAGE_ID = "sha256:" + "b" * 64


def write_manifest(directory, data):
    path = directory / "manifest.json"
    path.write_text(json.dumps(data))
    return release.sha256(path)


@pytest.fixture
def candidate(tmp_path):
    paths = release.package_paths("0.1.0")
    for relative in paths | {
        "image.tar.gz",
        "release-notes.md",
        "runtime-overrides.txt",
    }:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative)
    (tmp_path / "verification.json").write_text(
        json.dumps(
            {
                "version": "0.1.0",
                "source": {"commit": COMMIT, "state": "clean"},
                "artifacts": [
                    {
                        "filename": Path(path).name,
                        "sha256": release.sha256(tmp_path / path),
                    }
                    for path in paths
                ],
            }
        )
    )
    (tmp_path / "service-verification.json").write_text(
        json.dumps({"passed": True, "image_id": IMAGE_ID})
    )
    data = {
        "schema_version": 1,
        "version": "0.1.0",
        "commit": COMMIT,
        "repository": release.REPOSITORY,
        "specification": "specs-0.1.0",
        "implementation": "imp-0.1.0",
        "image": {
            "id": IMAGE_ID,
            "reference": release.IMAGE + ":0.1.0",
            "platform": "linux/amd64",
        },
        "files": {
            path.relative_to(tmp_path).as_posix(): release.sha256(path)
            for path in tmp_path.rglob("*")
            if path.is_file()
        },
    }
    digest = write_manifest(tmp_path, data)
    return tmp_path, data, digest


def test_exact_verified_bundle_passes(candidate):
    directory, data, digest = candidate
    assert release.verify(directory, digest, COMMIT) == data


def test_changed_manifest_requires_new_approval(candidate):
    directory, data, digest = candidate
    data["commit"] = "c" * 40
    write_manifest(directory, data)
    with pytest.raises(ValueError, match="hash differs"):
        release.verify(directory, digest, COMMIT)


@pytest.mark.parametrize("mutation", ["changed", "extra", "missing", "symlink"])
def test_altered_bundle_rejected(candidate, mutation):
    directory, _, digest = candidate
    path = directory / "image.tar.gz"
    if mutation == "changed":
        path.write_bytes(b"different image")
    elif mutation == "extra":
        (directory / "extra.whl").write_bytes(b"unexpected")
    elif mutation == "missing":
        path.unlink()
    else:
        path.unlink()
        try:
            path.symlink_to(directory / "release-notes.md")
        except OSError:
            pytest.skip("Symlink creation is not available")
    with pytest.raises(ValueError):
        release.verify(directory, digest, COMMIT)


@pytest.mark.parametrize(
    "field,value",
    [
        ("commit", "c" * 40),
        ("repository", "another/project"),
        ("version", "0.1.0.dev0"),
        ("implementation", "unaccepted-development"),
    ],
)
def test_wrong_source_or_release_identity_rejected(candidate, field, value):
    directory, data, _ = candidate
    data[field] = value
    digest = write_manifest(directory, data)
    with pytest.raises(ValueError):
        release.verify(directory, digest, COMMIT)


def test_path_traversal_in_inventory_rejected(candidate):
    directory, data, _ = candidate
    data["files"]["../outside"] = "c" * 64
    digest = write_manifest(directory, data)
    with pytest.raises(ValueError, match="inventory"):
        release.verify(directory, digest, COMMIT)


@pytest.mark.parametrize("receipt", ["verification.json", "service-verification.json"])
def test_checks_must_identify_the_same_artifacts(candidate, receipt):
    directory, data, _ = candidate
    path = directory / receipt
    evidence = json.loads(path.read_text())
    if receipt == "verification.json":
        evidence["artifacts"][0]["sha256"] = "c" * 64
    else:
        evidence["image_id"] = "sha256:" + "c" * 64
    path.write_text(json.dumps(evidence))
    data["files"][receipt] = release.sha256(path)
    digest = write_manifest(directory, data)
    with pytest.raises(ValueError):
        release.verify(directory, digest, COMMIT)


def test_annotated_tags_must_bind_exact_source(candidate, monkeypatch):
    directory, _, digest = candidate
    monkeypatch.setattr(
        release, "command", lambda *args: "tag" if args[1] == "cat-file" else "c" * 40
    )
    with pytest.raises(ValueError, match="Tag differs"):
        release.verify(directory, digest, COMMIT, tags=True)


@pytest.fixture
def tagged_repository(tmp_path, monkeypatch):
    def git(*args):
        return subprocess.check_output(
            ["git", "-c", "commit.gpgsign=false", *args], cwd=tmp_path, text=True
        ).strip()

    git("init", "--initial-branch=main")
    git("config", "user.name", "Test contributor")
    git("config", "user.email", "test@example.invalid")
    specs = tmp_path / ".macrostates/specs"
    specs.mkdir(parents=True)
    (specs / "main.md").write_text("unchanged contract\n")
    git("add", ".")
    git("commit", "-m", "Initial contract")
    baseline = git("rev-parse", "HEAD")
    git("tag", "-a", "specs-0.1.0", "-m", "Initial specification")
    (tmp_path / "implementation.py").write_text("# Security maintenance\n")
    git("add", ".")
    git("commit", "-m", "Patch implementation")
    for tag in ("v0.1.1", "imp-0.1.1"):
        git("tag", "-a", tag, "-m", tag)
    monkeypatch.setattr(release, "ROOT", tmp_path)
    return git, baseline


def test_patch_release_reuses_unchanged_ancestral_specification(tagged_repository):
    git, _ = tagged_repository
    release.verify_tags("0.1.1", "specs-0.1.0", "imp-0.1.1", git("rev-parse", "HEAD"))


def test_reused_specification_rejects_changed_tree(tagged_repository):
    git, _ = tagged_repository
    (release.ROOT / ".macrostates/specs/main.md").write_text("changed contract\n")
    git("add", ".")
    git("commit", "-m", "Change contract")
    commit = git("rev-parse", "HEAD")
    for tag in ("v0.1.1", "imp-0.1.1"):
        git("tag", "-d", tag)
        git("tag", "-a", tag, "-m", tag)
    with pytest.raises(ValueError, match="Specification tree differs"):
        release.verify_tags("0.1.1", "specs-0.1.0", "imp-0.1.1", commit)


def test_specification_must_belong_to_release_history(tagged_repository):
    git, _ = tagged_repository
    commit = git("rev-parse", "HEAD")
    git("checkout", "--orphan", "unrelated")
    git("commit", "-m", "Unrelated history")
    git("tag", "-d", "specs-0.1.0")
    git("tag", "-a", "specs-0.1.0", "-m", "Unrelated specification")
    with pytest.raises(ValueError, match="not an ancestor"):
        release.verify_tags("0.1.1", "specs-0.1.0", "imp-0.1.1", commit)


def test_specification_tag_must_still_be_annotated(tagged_repository):
    git, baseline = tagged_repository
    git("tag", "-d", "specs-0.1.0")
    git("tag", "specs-0.1.0", baseline)
    with pytest.raises(ValueError, match="annotated tag"):
        release.verify_tags(
            "0.1.1", "specs-0.1.0", "imp-0.1.1", git("rev-parse", "HEAD")
        )


def test_implementation_tag_cannot_reuse_older_source(tagged_repository):
    git, baseline = tagged_repository
    git("tag", "-d", "imp-0.1.1")
    git("tag", "-a", "imp-0.1.1", baseline, "-m", "Older implementation")
    with pytest.raises(ValueError, match="Tag differs"):
        release.verify_tags(
            "0.1.1", "specs-0.1.0", "imp-0.1.1", git("rev-parse", "HEAD")
        )


def test_pypi_absence_allowed_before_upload_but_not_after(candidate, monkeypatch):
    directory, _, _ = candidate

    def absent(url, **kwargs):
        raise urllib.error.HTTPError(url, 404, "Not found", {}, None)

    monkeypatch.setattr(release.urllib.request, "urlopen", absent)
    release.pypi(directory, complete=False)
    with pytest.raises(ValueError, match="incomplete"):
        release.pypi(directory, complete=True)


def test_pypi_matching_partial_files_can_be_resumed(candidate, monkeypatch):
    directory, data, _ = candidate

    def response(url, **kwargs):
        package = url.split("/")[-3].removeprefix("dockflow-")
        path = next(
            path for path in data["files"] if path.startswith(f"packages/{package}/")
        )
        return BytesIO(
            json.dumps(
                {
                    "urls": [
                        {
                            "filename": Path(path).name,
                            "digests": {"sha256": data["files"][path]},
                        }
                    ]
                }
            ).encode()
        )

    monkeypatch.setattr(release.urllib.request, "urlopen", response)
    release.pypi(directory, complete=False)
    with pytest.raises(ValueError, match="incomplete"):
        release.pypi(directory, complete=True)


def test_pypi_conflicting_immutable_upload_blocks_resume(candidate, monkeypatch):
    directory, _, _ = candidate
    monkeypatch.setattr(
        release.urllib.request,
        "urlopen",
        lambda *args, **kwargs: BytesIO(
            json.dumps(
                {
                    "urls": [
                        {
                            "filename": "dockflow_cli-0.1.0-py3-none-any.whl",
                            "digests": {"sha256": "c" * 64},
                        }
                    ],
                }
            ).encode()
        ),
    )
    with pytest.raises(ValueError, match="conflict"):
        release.pypi(directory, complete=False)


@pytest.mark.parametrize(
    "field,value",
    [
        ("head_sha", "c" * 40),
        ("head_branch", "feature"),
        ("event", "pull_request"),
        ("conclusion", "failure"),
        ("path", ".github/workflows/ci.yaml"),
    ],
)
def test_candidate_run_must_be_manual_successful_main_build(monkeypatch, field, value):
    run = {
        "head_sha": COMMIT,
        "head_branch": "main",
        "event": "workflow_dispatch",
        "conclusion": "success",
        "path": ".github/workflows/release-candidate.yaml",
        "repository": {"full_name": release.REPOSITORY},
        "head_repository": {"full_name": release.REPOSITORY},
    }
    run[field] = value
    monkeypatch.setattr(
        release,
        "command",
        lambda *args: COMMIT if args[0] == "git" else json.dumps(run),
    )
    with pytest.raises(ValueError, match="successful manual build"):
        release.github("123")
