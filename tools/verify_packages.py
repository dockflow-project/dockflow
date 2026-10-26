#!/usr/bin/env python3
"""Build, inspect, clean-install and independently rebuild all distributions."""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from email.parser import BytesParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source_provenance(root: Path) -> dict:
    """Report observable checkout state without inferring release acceptance."""
    source = {
        "commit": None,
        "branch": None,
        "dirty": None,
        "state": "unavailable",
        "note": (
            "Observed Git checkout state only; acceptance and publication "
            "are not determined by package verification."
        ),
    }
    # Do not attribute an archive to a caller-selected repository/index, or let
    # read-only inspection refresh the index. No personal Git identity is read.
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    environment["GIT_OPTIONAL_LOCKS"] = "0"

    def git(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=root,
            env=environment,
            text=True,
            capture_output=True,
        )

    try:
        top = git("rev-parse", "--show-toplevel")
        if top.returncode:
            source["reason"] = "checkout_unavailable"
            return source
        if Path(top.stdout.strip()).resolve() != root.resolve():
            source["reason"] = "checkout_not_at_project_root"
            return source

        commit = git("rev-parse", "--verify", "HEAD^{commit}")
        branch = git("symbolic-ref", "--quiet", "HEAD")
        status = git("status", "--porcelain")
        if commit.returncode == 0:
            source["commit"] = commit.stdout.strip()
        if branch.returncode == 0:
            source["branch"] = branch.stdout.strip().removeprefix("refs/heads/")
        if status.returncode == 0:
            source["dirty"] = bool(status.stdout.strip())
        else:
            source["reason"] = "git_status_failed"
            return source
        if branch.returncode not in {0, 1}:
            source["reason"] = "git_branch_failed"
            return source
        if commit.returncode == 0:
            source["state"] = "dirty" if source["dirty"] else "clean"
        elif (
            branch.returncode == 0
            and git("show-ref", "--verify", "--quiet", branch.stdout.strip()).returncode
            == 1
        ):
            source["state"] = "unborn"
        else:
            source["reason"] = "git_head_unresolved"
    except OSError:
        source["reason"] = "git_execution_failed"
    return source


def run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(
            f"Command failed: {command[0]} {' '.join(command[1:3])}\n{result.stdout}\n{result.stderr}"
        )
    return result.stdout


def python_path(environment: Path) -> Path:
    return environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def wheel_check(path: Path, version: str) -> dict:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        metadata = BytesParser().parsebytes(
            archive.read(
                next(name for name in names if name.endswith(".dist-info/METADATA"))
            )
        )
        wheel_metadata = BytesParser().parsebytes(
            archive.read(
                next(name for name in names if name.endswith(".dist-info/WHEEL"))
            )
        )
        if metadata["Version"] != version:
            raise RuntimeError(f"Wheel version mismatch: {path.name}")
        if not any(name.endswith("/licenses/LICENSE") for name in names):
            raise RuntimeError(f"License missing from wheel: {path.name}")
        dependencies = metadata.get_all("Requires-Dist", [])
        if any(
            "file:" in value or "workspace" in value or " @ " in value
            for value in dependencies
        ):
            raise RuntimeError(
                "Published dependency metadata contains a checkout source"
            )
        if (
            metadata["Name"] == "dockflow-pipelines"
            and f"dockflow-cli=={version}" not in dependencies
        ):
            raise RuntimeError(
                "Pipelines wheel does not require the exact shared CLI version"
            )
        if (
            metadata["Name"]
            in {"dockflow-cli", "dockflow-pipelines", "dockflow-artifacts"}
            and f"dockflow-core=={version}" not in dependencies
        ):
            raise RuntimeError("Wheel does not require the exact shared Core version")
        if (
            metadata["Name"] == "dockflow-pipelines"
            and f"dockflow-artifacts=={version}" not in dependencies
        ):
            raise RuntimeError(
                "Pipelines wheel does not require the exact Artifacts version"
            )
        if metadata["Name"] == "dockflow-cli" and not any(
            name.endswith(".dist-info/entry_points.txt") for name in names
        ):
            raise RuntimeError("CLI console entry point missing")
        if metadata["Name"] == "dockflow-pipelines":
            expected_assets = {
                "index.html",
                "api-docs.html",
                "styles.css",
                "app.js",
                "cleanup.js",
                "contents.js",
                "references.js",
                "autocomplete.js",
                "api.js",
                "dom.js",
                "forms.js",
                "views.js",
                "graph.js",
                "json.js",
                "logs.js",
                "api-docs.js",
            }
            missing = expected_assets - {
                name.removeprefix("dockflow_pipelines/static/")
                for name in names
                if name.startswith("dockflow_pipelines/static/")
            }
            if missing:
                raise RuntimeError(
                    f"Browser assets missing from wheel: {sorted(missing)}"
                )
        return {
            "filename": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "name": metadata["Name"],
            "version": metadata["Version"],
            "dependencies": dependencies,
            "build_backend_generator": wheel_metadata["Generator"],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--uv", default=os.environ.get("DOCKFLOW_UV") or shutil.which("uv")
    )
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "dist")
    parser.add_argument(
        "--existing",
        action="store_true",
        help="Verify existing wheels/sdists without rebuilding the release candidates",
    )
    arguments = parser.parse_args()
    if not arguments.uv:
        parser.error("Install uv or pass --uv /path/to/uv")
    uv = str(arguments.uv)
    out = arguments.out_dir.resolve()
    version = (ROOT / "VERSION").read_text().strip()
    run([sys.executable, str(ROOT / "tools/version.py")], ROOT)
    # PEP 517 isolation honors the backend compatibility range even when the
    # invoking uv frontend is a newer version with a different built-in backend.
    if not arguments.existing:
        run(
            [
                uv,
                "build",
                "--all-packages",
                "--force-pep517",
                "--out-dir",
                str(out),
                "--python",
                arguments.python,
            ],
            ROOT,
        )
    wheels = [
        out / f"dockflow_{name}-{version}-py3-none-any.whl"
        for name in ("cli", "pipelines", "artifacts", "core")
    ]
    receipts = [wheel_check(path, version) for path in wheels]
    with tempfile.TemporaryDirectory(prefix="dockflow-package-check-") as directory:
        temporary = Path(directory)
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("DOCKFLOW_PIPELINES_")
            and key not in {"PYTHONPATH", "VIRTUAL_ENV"}
        }
        for label, packages in (
            ("core", wheels[3:]),
            ("cli", wheels[:1] + wheels[3:]),
            ("artifacts", wheels[2:]),
            ("combined", wheels),
        ):
            environment = temporary / label
            run(
                [uv, "venv", "--python", arguments.python, str(environment)],
                temporary,
                env,
            )
            python = str(python_path(environment))
            run(
                [uv, "pip", "install", "--python", python, *map(str, packages)],
                temporary,
                env,
            )
            if label == "core":
                run(
                    [
                        python,
                        "-c",
                        "import importlib.util; import dockflow_core; assert all(importlib.util.find_spec(name) is None for name in ('dockflow_cli','dockflow_pipelines','dockflow_artifacts','psycopg'))",
                    ],
                    temporary,
                    env,
                )
                continue
            if label == "artifacts":
                run(
                    [
                        python,
                        "-c",
                        "import sys, importlib.util; import dockflow_artifacts; "
                        "assert all(importlib.util.find_spec(name) is None for name "
                        "in ('kfp','boto3','dockflow_cli','dockflow_pipelines')); "
                        "assert not any(name in sys.modules for name in ('kfp','boto3'))",
                    ],
                    temporary,
                    env,
                )
                continue
            console = environment / (
                "Scripts/dockflow.exe" if os.name == "nt" else "bin/dockflow"
            )
            if (
                run([str(console), "--version"], temporary, env).strip()
                != f"dockflow {version}"
            ):
                raise RuntimeError("Installed console reports an unexpected version")
            run([str(console)], temporary, env)
            run([str(console), "--help"], temporary, env)
            if label == "combined":
                run([str(console), "pipelines", "--help"], temporary, env)
                run([str(console), "pipelines", "run", "--help"], temporary, env)
                code = "import importlib.util; assert all(importlib.util.find_spec(name) is None for name in ('kfp','docker','ml_metadata','fastapi','boto3','psycopg')); import importlib.metadata as m; assert any(p.name=='pipelines' for p in m.entry_points(group='dockflow_cli.modules'))"
            else:
                code = "import importlib.metadata as m; assert not list(m.entry_points(group='dockflow_cli.modules'))"
            run([python, "-c", code], temporary, env)
        for name in ("cli", "pipelines", "artifacts", "core"):
            source_archive = out / f"dockflow_{name}-{version}.tar.gz"
            extraction = temporary / f"source-{name}"
            extraction.mkdir()
            with tarfile.open(source_archive) as archive:
                archive.extractall(extraction, filter="data")
            checkout = next(extraction.iterdir())
            if not (checkout / "LICENSE").is_file():
                raise RuntimeError(
                    "License missing from standalone source distribution"
                )
            rebuild = temporary / f"rebuilt-{name}"
            run(
                [
                    uv,
                    "build",
                    str(checkout),
                    "--wheel",
                    "--force-pep517",
                    "--no-sources",
                    "--out-dir",
                    str(rebuild),
                    "--python",
                    arguments.python,
                ],
                temporary,
                env,
            )
            wheel_check(next(rebuild.glob("*.whl")), version)
            receipts.append(
                {
                    "filename": source_archive.name,
                    "sha256": hashlib.sha256(source_archive.read_bytes()).hexdigest(),
                    "standalone_rebuild": True,
                }
            )
    receipt = {
        "schema_version": 1,
        "version": version,
        "python": sys.version.split()[0],
        "uv": run([uv, "--version"], ROOT).strip(),
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "libc": platform.libc_ver(),
        },
        "source": source_provenance(ROOT),
        "clean_install": [
            "core-only",
            "cli-only",
            "artifacts-only",
            "combined-base",
        ],
        "runtime_extras_absent_from_base": True,
        "artifacts": receipts,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "verification.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
