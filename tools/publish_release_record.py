#!/usr/bin/env python3
"""Publish a verified saved image and immutable GitHub release assets in Actions."""

import argparse
import json
import os
import subprocess
from pathlib import Path

from release import REPOSITORY, command, require, sha256, verify


def existing_release(tag: str) -> dict | None:
    response = subprocess.run(
        ["gh", "api", f"repos/{REPOSITORY}/releases/tags/{tag}"],
        capture_output=True,
        text=True,
    )
    if response.returncode == 0:
        return json.loads(response.stdout)
    # Fail closed on authentication/network/rate-limit errors.
    require("HTTP 404" in response.stderr, "Could not inspect existing GitHub release")
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    args = parser.parse_args()
    require(
        os.environ.get("GITHUB_ACTIONS") == "true",
        "Publication is restricted to GitHub Actions",
    )
    require(
        os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
        and os.environ.get("GITHUB_REF") == "refs/heads/main",
        "Publication requires canonical main",
    )
    data = verify(
        args.directory,
        os.environ["MANIFEST_SHA256"],
        os.environ["GITHUB_SHA"],
        tags=True,
    )
    token = os.environ["GH_TOKEN"]
    subprocess.run(
        [
            "docker",
            "login",
            "ghcr.io",
            "--username",
            os.environ["GITHUB_ACTOR"],
            "--password-stdin",
        ],
        input=token,
        text=True,
        check=True,
        capture_output=True,
    )
    image = data["image"]["reference"]
    try:
        pull = subprocess.run(["docker", "pull", image], capture_output=True, text=True)
        if pull.returncode == 0:
            require(
                command("docker", "image", "inspect", "--format", "{{.Id}}", image)
                == data["image"]["id"],
                "Refusing to replace a published image with different contents",
            )
        else:
            require(
                any(
                    message in pull.stderr.lower()
                    for message in ("manifest unknown", "name unknown", "not found")
                ),
                "Could not establish that the image tag is absent",
            )
        command("docker", "load", "--input", str(args.directory / "image.tar.gz"))
        require(
            command(
                "docker", "image", "inspect", "--format", "{{.Id}}", data["image"]["id"]
            )
            == data["image"]["id"],
            "Loaded image identity differs",
        )
        command("docker", "tag", data["image"]["id"], image)
        command("docker", "push", image)
        # Pull the published tag back and bind its registry digest to the tested ID.
        command("docker", "pull", image)
        result = json.loads(command("docker", "image", "inspect", image))[0]
        require(result["Id"] == data["image"]["id"], "Published image ID differs")
        repository = image.rsplit(":", 1)[0]
        digest = next(
            value
            for value in result["RepoDigests"]
            if value.startswith(repository + "@")
        )
    finally:
        subprocess.run(
            ["docker", "logout", "ghcr.io"], check=False, capture_output=True
        )
    publication = args.directory.parent / "published-image.json"
    publication.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "version": data["version"],
                "commit": data["commit"],
                "specification": data["specification"],
                "implementation": data["implementation"],
                "image": digest,
                "image_id": data["image"]["id"],
                "manifest_sha256": os.environ["MANIFEST_SHA256"],
            },
            indent=2,
        )
        + "\n"
    )
    tag = f"v{data['version']}"
    release = existing_release(tag)
    if release is None:
        command(
            "gh",
            "release",
            "create",
            tag,
            "--repo",
            REPOSITORY,
            "--verify-tag",
            "--draft",
            "--title",
            f"Dockflow {data['version']}",
            "--notes-file",
            str(args.directory / "release-notes.md"),
        )
        release = existing_release(tag)
    assert release is not None
    assets = {item["name"]: item for item in release["assets"]}
    paths = [path for path in args.directory.rglob("*") if path.is_file()] + [
        publication
    ]
    for path in paths:
        previous = assets.get(path.name)
        if previous:
            require(
                previous.get("digest") == "sha256:" + sha256(path),
                f"Existing release asset differs or has no verifiable digest: {path.name}",
            )
        else:
            command("gh", "release", "upload", tag, str(path), "--repo", REPOSITORY)
    current = existing_release(tag)
    assert current is not None
    current_assets = {item["name"]: item for item in current["assets"]}
    require(
        all(
            current_assets[path.name].get("digest") == "sha256:" + sha256(path)
            for path in paths
        ),
        "Uploaded release asset verification failed",
    )
    if current["draft"]:
        command(
            "gh",
            "release",
            "edit",
            tag,
            "--repo",
            REPOSITORY,
            "--draft=false",
            "--latest",
        )
    print(f"Published {tag}: {digest}")


if __name__ == "__main__":
    main()
