#!/usr/bin/env python3
"""Prepare and verify immutable release bundles; never build or upload packages."""

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "dockflow-project/dockflow"
IMAGE = "ghcr.io/dockflow-project/dockflow-pipelines"
PACKAGES = ("cli", "pipelines", "artifacts")


def command(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_tags(version: str, specification: str, implementation: str, commit: str):
    for tag in (f"v{version}", specification, implementation):
        require(
            command("git", "cat-file", "-t", f"refs/tags/{tag}") == "tag",
            f"Release requires an annotated tag: {tag}",
        )
    for tag in (f"v{version}", implementation):
        require(
            command("git", "rev-parse", f"refs/tags/{tag}^{{commit}}") == commit,
            f"Tag differs from publication source: {tag}",
        )
    baseline = command("git", "rev-parse", f"refs/tags/{specification}^{{commit}}")
    # An unchanged contract keeps its original immutable tag. Require both
    # ancestry and byte-identical specification trees, never just a version label.
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", baseline, commit], cwd=ROOT
    )
    require(ancestor.returncode == 0, "Specification baseline is not an ancestor")
    require(
        command("git", "rev-parse", f"{baseline}:.macrostates/specs")
        == command("git", "rev-parse", f"{commit}:.macrostates/specs"),
        "Specification tree differs from the reused baseline",
    )


def package_paths(version: str) -> set[str]:
    return {
        f"packages/{name}/dockflow_{name}-{version}{suffix}"
        for name in PACKAGES
        for suffix in ("-py3-none-any.whl", ".tar.gz")
    }


def source() -> dict:
    # Only preparation needs PyYAML (already a workspace dependency).
    import yaml

    version = (ROOT / "VERSION").read_text().strip()
    require(
        bool(re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", version)),
        "Release VERSION must be a stable X.Y.Z",
    )
    require(
        not command("git", "status", "--porcelain"), "Release checkout must be clean"
    )
    workflows = ROOT / ".macrostates/implementation/workflows"
    require(not list(workflows.glob("*.md")), "Release requires closed workflows")
    release = yaml.safe_load(
        (ROOT / ".macrostates/implementation/release.yaml").read_text()
    )
    composition = yaml.safe_load(
        (ROOT / ".macrostates/specs/composition.yaml").read_text()
    )
    require(release["schema_version"] == 2, "Unsupported baseline declaration")
    require(
        release["specification"] == composition["project"]["version"],
        "Candidate must use the current specification baseline",
    )
    return {
        "version": version,
        "commit": command("git", "rev-parse", "HEAD"),
        "specification": release["specification"],
        "implementation": release["version"],
    }


def bundle(directory: Path, distributions: Path, image: str) -> dict:
    identity = source()
    require(not directory.exists(), "Refusing to overwrite an existing candidate")
    verification = json.loads((distributions / "verification.json").read_text())
    require(
        verification["version"] == identity["version"], "Verification version differs"
    )
    require(
        verification["source"]["commit"] == identity["commit"]
        and verification["source"]["state"] == "clean",
        "Verification source differs",
    )
    inspected = json.loads(command("docker", "image", "inspect", image))[0]
    labels = inspected["Config"]["Labels"]
    for label, value in {
        "org.opencontainers.image.version": identity["version"],
        "org.opencontainers.image.revision": identity["commit"],
        "io.macrostates.specification": identity["specification"],
        "io.macrostates.implementation": identity["implementation"],
    }.items():
        require(labels.get(label) == value, f"Image label differs: {label}")
    require(
        inspected["Os"] == "linux" and inspected["Architecture"] == "amd64",
        "Only the qualified linux/amd64 image can be released",
    )
    require(inspected["Config"]["User"] == "10001:10001", "Image must run as non-root")
    directory.mkdir(parents=True)
    for relative in package_paths(identity["version"]):
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(distributions / target.name, target)
    shutil.copyfile(
        distributions / "verification.json", directory / "verification.json"
    )
    shutil.copyfile(ROOT / "CHANGELOG.md", directory / "release-notes.md")
    shutil.copyfile(
        ROOT / "tools/runtime-overrides.txt", directory / "runtime-overrides.txt"
    )
    shutil.copyfile(
        distributions / "service-verification.json",
        directory / "service-verification.json",
    )
    # Keep the tested image itself: publishing loads this archive, never rebuilds it.
    with (directory / "image.tar.gz").open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as zipped:
            process = subprocess.Popen(
                ["docker", "image", "save", image], stdout=subprocess.PIPE
            )
            assert process.stdout is not None
            with process.stdout:
                shutil.copyfileobj(process.stdout, zipped)
            require(process.wait() == 0, "Could not save candidate image")
    manifest = {
        "schema_version": 1,
        **identity,
        "repository": REPOSITORY,
        "image": {
            "reference": f"{IMAGE}:{identity['version']}",
            "id": inspected["Id"],
            "platform": "linux/amd64",
        },
        "files": {
            str(path.relative_to(directory)): sha256(path)
            for path in sorted(directory.rglob("*"))
            if path.is_file()
        },
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    verify(directory, sha256(directory / "manifest.json"), identity["commit"])
    return manifest


def verify(
    directory: Path, expected_hash: str, commit: str, tags: bool = False
) -> dict:
    require(
        bool(re.fullmatch(r"[a-f0-9]{64}", expected_hash)), "Invalid manifest SHA-256"
    )
    require(
        sha256(directory / "manifest.json") == expected_hash,
        "Manifest hash differs from approval",
    )
    data = json.loads((directory / "manifest.json").read_text())
    require(
        data["schema_version"] == 1 and data["repository"] == REPOSITORY,
        "Unexpected release bundle identity",
    )
    require(
        bool(re.fullmatch(r"[a-f0-9]{40}", commit)) and data["commit"] == commit,
        "Candidate source differs from publication source",
    )
    version = data["version"]
    require(
        bool(re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", version)),
        "Invalid stable release version",
    )
    for field, prefix in (("specification", "specs"), ("implementation", "imp")):
        require(
            bool(re.fullmatch(rf"{prefix}-\d+\.\d+\.\d+", data[field])),
            f"Invalid {field} reference",
        )
    require(
        data["image"]["reference"] == f"{IMAGE}:{version}"
        and data["image"]["platform"] == "linux/amd64"
        and bool(re.fullmatch(r"sha256:[a-f0-9]{64}", data["image"]["id"])),
        "Unexpected image identity",
    )
    expected = package_paths(version) | {
        "image.tar.gz",
        "verification.json",
        "service-verification.json",
        "release-notes.md",
        "runtime-overrides.txt",
    }
    require(set(data["files"]) == expected, "Candidate file inventory differs")
    actual = set()
    for path in directory.rglob("*"):
        require(not path.is_symlink(), "Symlinks are forbidden in release bundles")
        require(path.is_file() or path.is_dir(), "Special file in release bundle")
        if path.is_file():
            actual.add(path.relative_to(directory).as_posix())
    require(
        actual == expected | {"manifest.json"}, "Unexpected or missing bundle files"
    )
    for relative, digest in data["files"].items():
        require(
            sha256(directory / relative) == digest,
            f"Candidate bytes differ: {relative}",
        )
    receipt = json.loads((directory / "verification.json").read_text())
    require(
        receipt["version"] == version
        and receipt["source"]["state"] == "clean"
        and receipt["source"]["commit"] == commit,
        "Package verification provenance differs",
    )
    hashes = {item["filename"]: item["sha256"] for item in receipt["artifacts"]}
    require(
        len(hashes) == 6 and len(receipt["artifacts"]) == 6,
        "Expected verification of six distributions",
    )
    require(
        all(
            hashes.get(Path(path).name) == data["files"][path]
            for path in package_paths(version)
        ),
        "Package verification hashes differ",
    )
    smoke = json.loads((directory / "service-verification.json").read_text())
    require(
        smoke["image_id"] == data["image"]["id"] and smoke["passed"] is True,
        "Service qualification does not identify the candidate image",
    )
    if tags:
        verify_tags(version, data["specification"], data["implementation"], commit)
    return data


def pypi(directory: Path, complete: bool) -> None:
    data = json.loads((directory / "manifest.json").read_text())
    version = data["version"]
    for name in PACKAGES:
        url = f"https://pypi.org/pypi/dockflow-{name}/{version}/json"
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                files = json.load(response)["urls"]
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
            files = []
        expected = {
            Path(path).name: digest
            for path, digest in data["files"].items()
            if path.startswith(f"packages/{name}/")
        }
        actual = {item["filename"]: item["digests"]["sha256"] for item in files}
        require(
            all(
                filename in expected and expected[filename] == digest
                for filename, digest in actual.items()
            ),
            f"Published dockflow-{name} files conflict with this candidate",
        )
        require(
            not any(item.get("yanked") for item in files), "Existing release is yanked"
        )
        if complete:
            require(actual == expected, f"dockflow-{name} publication is incomplete")


def github(run_id: str) -> None:
    require(bool(re.fullmatch(r"[1-9]\d*", run_id)), "Invalid candidate run ID")
    run = json.loads(command("gh", "api", f"repos/{REPOSITORY}/actions/runs/{run_id}"))
    require(
        run["path"] == ".github/workflows/release-candidate.yaml"
        and run["event"] == "workflow_dispatch"
        and run["head_branch"] == "main"
        and run["conclusion"] == "success"
        and run["repository"]["full_name"] == REPOSITORY
        and run["head_repository"]["full_name"] == REPOSITORY
        and run["head_sha"] == command("git", "rev-parse", "HEAD"),
        "Candidate must be a successful manual build of this exact main commit",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    info = sub.add_parser("source")
    info.add_argument("--output", type=Path)
    build = sub.add_parser("bundle")
    build.add_argument("--directory", type=Path, required=True)
    build.add_argument("--distributions", type=Path, default=ROOT / "dist")
    build.add_argument("--image", required=True)
    check = sub.add_parser("verify")
    check.add_argument("--directory", type=Path, required=True)
    check.add_argument("--sha256", required=True)
    check.add_argument("--commit", required=True)
    check.add_argument("--tags", action="store_true")
    remote = sub.add_parser("pypi")
    remote.add_argument("--directory", type=Path, required=True)
    remote.add_argument("--complete", action="store_true")
    hosted = sub.add_parser("github")
    hosted.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if args.action == "source":
        identity = source()
        print(json.dumps(identity))
        if args.output:
            with args.output.open("a") as stream:
                stream.writelines(f"{key}={value}\n" for key, value in identity.items())
    elif args.action == "bundle":
        bundle(args.directory, args.distributions, args.image)
        digest = sha256(args.directory / "manifest.json")
        print(f"Release manifest SHA-256: {digest}")
        if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
            with Path(summary).open("a") as stream:
                stream.write(
                    f"Candidate run: {os.environ['GITHUB_RUN_ID']}\n\n"
                    f"Manifest SHA-256: `{digest}`\n\n"
                    "Review all artifacts before manually starting Publish.\n"
                )
    elif args.action == "verify":
        verify(args.directory, args.sha256, args.commit, args.tags)
        print("Candidate hashes, inventory and provenance verified")
    elif args.action == "pypi":
        pypi(args.directory, args.complete)
        print("PyPI file identities verified")
    else:
        github(args.run_id)


if __name__ == "__main__":
    main()
