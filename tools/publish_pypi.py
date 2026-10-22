#!/usr/bin/env python3
"""Run the upstream PyPA publisher in the CA-corrected, prebuilt runtime."""

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

IMAGE = "dockflow-pypi-publisher:ca-fixed"
# Pass short-lived OIDC credentials by environment name, never command-line value.
FORWARDED = (
    "ACTIONS_ID_TOKEN_REQUEST_URL",
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
    "GITHUB_ACTIONS",
    "GITHUB_REPOSITORY",
    "GITHUB_REPOSITORY_OWNER",
    "GITHUB_WORKFLOW_REF",
    "GITHUB_WORKFLOW_SHA",
    "GITHUB_RUN_ID",
    "GITHUB_RUN_ATTEMPT",
    "GITHUB_SHA",
    "GITHUB_REF",
    "GITHUB_EVENT_NAME",
    "GITHUB_SERVER_URL",
    "RUNNER_ENVIRONMENT",
)


def publish(packages: Path, *, check_only: bool = False) -> None:
    if not check_only and (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("GITHUB_REPOSITORY") != "dockflow-project/dockflow"
        or os.environ.get("GITHUB_REF") != "refs/heads/main"
        or os.environ.get("GITHUB_WORKFLOW_REF")
        != "dockflow-project/dockflow/.github/workflows/publish.yaml@refs/heads/main"
        or not all(os.environ.get(name) for name in FORWARDED[:2])
    ):
        raise ValueError("Publishing requires the protected canonical main workflow")
    files = sorted(packages.iterdir())
    if (
        len(files) != 2
        or {p.suffix for p in files} != {".whl", ".gz"}
        or any(
            p.is_symlink()
            or not p.is_file()
            or not (p.name.endswith(".whl") or p.name.endswith(".tar.gz"))
            for p in files
        )
    ):
        raise ValueError("Expected exactly one verified wheel and one source archive")
    # Upstream writes attestations alongside distributions. Never change the
    # immutable candidate directory when preparing these auxiliary files.
    staging = Path(__file__).resolve().parents[1] / "tmp"
    staging.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="dockflow-publish-", dir=staging
    ) as directory:
        workspace = Path(directory)
        (workspace / "packages").mkdir()
        for path in files:
            shutil.copyfile(path, workspace / "packages" / path.name)
        # Upstream runs as root; this single capability permits access to the
        # runner-owned private staging directory without making it world-writable.
        command = [
            "docker",
            "run",
            "--rm",
            "--cap-drop",
            "ALL",
            "--cap-add",
            "DAC_OVERRIDE",
            "--security-opt",
            "no-new-privileges",
            "--mount",
            f"type=bind,src={workspace},dst=/github/workspace",
            "--workdir",
            "/github/workspace",
        ]
        if check_only:
            command += ["--network", "none", "--entrypoint", "twine", IMAGE, "check"]
            command += [f"packages/{p.name}" for p in files]
        else:
            for name in FORWARDED:
                command += ["--env", name]
            for key, value in {
                "INPUT_USER": "__token__",
                "INPUT_PASSWORD": "",
                "INPUT_REPOSITORY_URL": "https://upload.pypi.org/legacy/",
                "INPUT_PACKAGES_DIR": "packages/",
                "INPUT_VERIFY_METADATA": "true",
                "INPUT_SKIP_EXISTING": "true",
                "INPUT_PRINT_HASH": "true",
                "INPUT_ATTESTATIONS": "true",
                "INPUT_VERBOSE": "false",
                "DEBUG": "",
                "GITHUB_STEP_SUMMARY": "/github/workspace/summary.md",
            }.items():
                command += ["--env", f"{key}={value}"]
            command += [IMAGE]
        subprocess.run(command, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packages", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    publish(args.packages, check_only=args.check_only)


if __name__ == "__main__":
    main()
