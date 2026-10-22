#!/usr/bin/env python3
"""Offline owner-exclusive backup, verification and explicit restore."""

import argparse
import json
import shutil
from pathlib import Path

from dockflow_pipelines.artifacts import ArtifactStore
from dockflow_pipelines.canonical import loads
from dockflow_pipelines.config import load_settings
from dockflow_pipelines.errors import DockflowError
from dockflow_pipelines.metadata import ControlStore


def restore(source: Path, config: Path, apply: bool) -> dict:
    ControlStore.verify_backup(source)
    manifest = loads((source / "backup.json").read_bytes())
    settings = load_settings(config)
    if manifest["project_id"] != settings.project_id:
        raise DockflowError("Backup project ID differs from configuration")
    matches = {
        "state_directory": str(settings.state),
        "metadata_directory": str(settings.metadata_directory),
        "artifacts_backend": settings.artifacts["backend"],
    }
    if settings.artifacts["backend"] == "filesystem":
        # Schema-1 backups predating managed_root stored only its parent.
        original_managed = manifest.get("managed_root")
        if original_managed is None and manifest.get("artifacts_root"):
            original_managed = str(Path(manifest["artifacts_root"]) / "managed")
        matches["managed_root"] = str(settings.artifacts["managed_root"])
        manifest["managed_root"] = original_managed
    else:
        matches["artifact_bucket"] = settings.artifacts["bucket"]
        matches["artifact_prefix"] = settings.artifacts.get("prefix", "")
    if any(manifest.get(key) != value for key, value in matches.items()):
        raise DockflowError(
            "Restore requires the original configured state, metadata and artifact locations; relocation needs a separate migration"
        )
    report = {
        "schema_version": 1,
        "project_id": settings.project_id,
        "apply": apply,
        "state_directory": str(settings.state),
        "metadata_directory": str(settings.metadata_directory),
        "backup": str(source),
        "external_references_restored": False,
    }
    if not apply:
        return report
    control = ControlStore(
        settings.state, settings.project_id, settings.metadata_directory
    )
    artifacts = ArtifactStore(control, settings.artifacts)
    with control.owner():
        if any(path.name != "owner.lock" for path in settings.state.iterdir()):
            raise DockflowError(
                "Restore target state must be empty. Preserve existing state separately before restoring."
            )
        if settings.metadata_directory.exists() and any(
            settings.metadata_directory.iterdir()
        ):
            raise DockflowError("Restore target metadata directory must be empty")
        managed = artifacts.managed_root
        if (
            artifacts.backend == "filesystem"
            and managed.exists()
            and any(managed.iterdir())
        ):
            raise DockflowError(
                "Restore target managed artifact directory must be empty"
            )
        if artifacts.backend == "s3":
            # The entire configured root now contains pipeline directories plus
            # recovery metadata. Do not restore over any unrelated contents.
            prefix = settings.artifacts.get("prefix", "").strip("/")
            prefix = prefix + "/" if prefix else ""
            existing = {
                item["Key"]
                for page in artifacts._s3()
                .get_paginator("list_objects_v2")
                .paginate(Bucket=settings.artifacts["bucket"], Prefix=prefix)
                for item in page.get("Contents", [])
            }
            # Existing objects are also refused, so restore cannot overwrite a
            # different dataset. A provider-volume restore is an alternative.
            if existing:
                raise DockflowError("S3 managed restore prefix must be empty")
        shutil.copytree(source / "control", settings.state, dirs_exist_ok=True)
        index = source / "index" / "mlmd.sqlite"
        if index.exists():
            settings.metadata_directory.mkdir(parents=True, exist_ok=True)
            shutil.copy2(index, settings.metadata_directory / "mlmd.sqlite")
        if artifacts.backend == "filesystem":
            if (source / "managed").exists():
                shutil.copytree(source / "managed", managed, dirs_exist_ok=True)
        else:
            for folder in (source / "managed").glob("artifact_*"):
                descriptor = loads((folder / "artifact.json").read_bytes())
                content_path, recovery_path = artifacts.managed_paths(descriptor)
                key = artifacts.object_key(content_path)
                client = artifacts._s3()
                bucket = settings.artifacts["bucket"]
                if descriptor["payload_kind"] == "file":
                    client.upload_file(str(folder / "payload"), bucket, key)
                elif descriptor["payload_kind"] == "directory":
                    for entry in descriptor["inventory"]:
                        if entry["kind"] == "file":
                            client.upload_file(
                                str(folder / "payload" / entry["path"]),
                                bucket,
                                key + "/" + entry["path"],
                            )
                client.upload_file(
                    str(folder / "artifact.json"),
                    bucket,
                    artifacts.object_key(recovery_path),
                )
        control.initialize()
        check = control.check(verify_contents=True, artifacts=artifacts)
        if not check["valid"]:
            raise DockflowError(
                "Restored control records failed verification",
                details=[{"field": "backup", "reason": str(check["errors"])}],
            )
        return {**report, "restored": True, "check": check}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup")
    backup.add_argument("--config", type=Path, required=True)
    backup.add_argument("destination", type=Path)
    verify = commands.add_parser("verify")
    verify.add_argument("source", type=Path)
    restore_parser = commands.add_parser("restore")
    restore_parser.add_argument("--config", type=Path, required=True)
    restore_parser.add_argument("--apply", action="store_true")
    restore_parser.add_argument("source", type=Path)
    arguments = parser.parse_args()
    try:
        if arguments.command == "verify":
            result = ControlStore.verify_backup(arguments.source)
        elif arguments.command == "restore":
            result = restore(
                arguments.source.resolve(), arguments.config, arguments.apply
            )
        else:
            settings = load_settings(arguments.config)
            control = ControlStore(
                settings.state, settings.project_id, settings.metadata_directory
            )
            artifacts = ArtifactStore(control, settings.artifacts)
            with control.owner():
                control.initialize()
                result = control.backup(arguments.destination, artifacts)
        print(json.dumps(result, indent=2))
        return 0
    except (DockflowError, OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
