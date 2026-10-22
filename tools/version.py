#!/usr/bin/env python3
"""Check or synchronize package versions from the tracked VERSION authority."""

import argparse
import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEMBERS = [
    ROOT / "packages" / name / "pyproject.toml"
    for name in ("cli", "pipelines", "artifacts")
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Explicitly synchronize metadata; never invoked by builds",
    )
    arguments = parser.parse_args()
    version = (ROOT / "VERSION").read_text().strip()
    if not re.fullmatch(
        r"[0-9]+\.[0-9]+\.[0-9]+(?:(?:a|b|rc)[0-9]+)?(?:\.post[0-9]+)?(?:\.dev[0-9]+)?",
        version,
    ):
        parser.error("VERSION must contain a normalized numeric Python version")
    errors = []
    for path in MEMBERS:
        source = path.read_text()
        if arguments.sync:
            source = re.sub(
                r'(?m)^version = "[^"]+"$', f'version = "{version}"', source, count=1
            )
            source = re.sub(
                r'dockflow-cli==[^"\s]+', f"dockflow-cli=={version}", source
            )
            path.write_text(source)
        metadata = tomllib.loads(source)["project"]
        if metadata["version"] != version:
            errors.append(f"{metadata['name']}: project.version differs from VERSION")
        if (
            metadata["name"] == "dockflow-pipelines"
            and f"dockflow-cli=={version}" not in metadata["dependencies"]
        ):
            errors.append(
                "dockflow-pipelines must require the exact shared dockflow-cli version"
            )
    # The nonpackaged workspace advertises its development version to uv too.
    workspace = ROOT / "pyproject.toml"
    source = workspace.read_text()
    if arguments.sync:
        source = re.sub(
            r'(?m)^version = "[^"]+"$', f'version = "{version}"', source, count=1
        )
        workspace.write_text(source)
    if tomllib.loads(source)["project"]["version"] != version:
        errors.append("Workspace version differs from VERSION")
    dockerfile = ROOT / "deploy" / "Dockerfile"
    if dockerfile.exists():
        source = dockerfile.read_text()
        if arguments.sync:
            source = re.sub(
                r'org\.opencontainers\.image\.version="[^"]+"',
                f'org.opencontainers.image.version="{version}"',
                source,
            )
            dockerfile.write_text(source)
        match = re.search(r'org\.opencontainers\.image\.version="([^"]+)"', source)
        if match is None or match.group(1) != version:
            errors.append("Service image version label differs from VERSION")
    print(
        json.dumps(
            {
                "version": version,
                "synchronized": arguments.sync,
                "valid": not errors,
                "errors": errors,
            }
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
