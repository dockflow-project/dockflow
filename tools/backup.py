#!/usr/bin/env python3
"""Offline owner-exclusive backup, verification and explicit restore."""

import argparse
import json
import shutil
from pathlib import Path

from dockflow_database.errors import DockflowError
from dockflow_pipelines.artifacts import ArtifactStore
from dockflow_pipelines.canonical import loads
from dockflow_pipelines.config import load_settings
from dockflow_pipelines.metadata import ControlStore


def restore(source: Path, config: Path, apply: bool) -> dict:
    ControlStore.verify_backup(source)
    manifest = loads((source / "backup.json").read_bytes())
    settings = load_settings(config)
    if manifest["project_id"] != settings.project_id:
        raise DockflowError("Backup project ID differs from configuration")
    if manifest.get("state_format") != "dockflow-sql-v4":
        raise DockflowError(
            "Unsupported backup state format; SQL state backup required"
        )
    matches = {
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
            "Restore requires the original managed artifact locations; relocation needs a separate migration"
        )
    report = {
        "schema_version": 1,
        "project_id": settings.project_id,
        "apply": apply,
        "backup": str(source),
        "external_references_restored": False,
    }
    if not apply:
        return report
    control = ControlStore(
        settings.state,
        settings.project_id,
        storage=settings.state_storage,
    )
    artifacts = ArtifactStore(control, settings.artifacts)
    with control.owner(exclusive=True):
        if not control.database.project_empty(include_cache=True):
            raise DockflowError("Restore target project must be empty")
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
        if artifacts.backend == "filesystem":
            if (source / "managed").exists():
                shutil.copytree(source / "managed", managed, dirs_exist_ok=True)
        else:
            managed_source = source / "managed"
            for payload in managed_source.rglob("*"):
                if payload.is_file():
                    relative = payload.relative_to(managed_source).as_posix()
                    artifacts._s3().upload_file(
                        str(payload),
                        settings.artifacts["bucket"],
                        artifacts.object_key(relative),
                    )
        with control.database.transaction():
            control.import_database(source / "state.sqlite")
            control.initialize()
            check = control.check(verify_contents=True, artifacts=artifacts)
            if not check["valid"]:
                raise DockflowError("Restored database failed verification")
            tokens = control.database.cache_store_tokens()
            if tokens and tokens != {artifacts.storage_identity(create=False)}:
                raise DockflowError(
                    "Restored artifact store identity differs from cache history"
                )
            for cache_manifest in control.database.cache_manifests():
                artifacts.verify_cache(
                    cache_manifest, cache_manifest["storage_identity"]
                )
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
                settings.state,
                settings.project_id,
                storage=settings.state_storage,
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
