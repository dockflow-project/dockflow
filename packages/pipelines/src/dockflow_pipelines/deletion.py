"""Dependency-protected retirement and exact managed-storage deletion plans.

SQL records intent before touching storage. Project maintenance excludes every
cooperating coordinator/publisher; storage identity and object identities fence
retries. No operation removes journal, publication or cache fencing history.
"""

from __future__ import annotations

import contextlib
import os
import stat
import time
import uuid
from datetime import UTC, datetime
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from dockflow_core.canonical import digest, loads
from dockflow_core.errors import DockflowError
from dockflow_core.time import utc_now

from .records import COLLECTIONS, TERMINAL

PLAN_SECONDS = 1800
CLASSES = {
    "execution_artifact",
    "manual_artifact",
    "publication",
    "retained_file",
    "orphan",
    "protected",
    "unknown",
}


def manual(artifact: dict) -> bool:
    return (
        artifact.get("creation_origin") == "manual"
        or not artifact.get("producer")
        or artifact.get("origin") == "external"
    )


def relative(value: str) -> str:
    if not isinstance(value, str) or "\\" in value or any(ord(c) < 32 for c in value):
        raise DockflowError("Storage prefix must be a relative path")
    if value.startswith("/") or any(p in {".", ".."} for p in value.split("/")):
        raise DockflowError("Storage prefix must remain inside the managed root")
    return value.strip("/")


def contains(parent: str, child: str) -> bool:
    return not parent or child == parent or child.startswith(parent + "/")


def identifiers(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from identifiers(item)
    elif isinstance(value, list):
        for item in value:
            yield from identifiers(item)
    elif isinstance(value, str):
        yield value


class Deletions:
    def __init__(self, core):
        self.core = core
        self.store = core.store
        self.db = core.store.database
        self.artifacts = core.artifacts

    def _save(self, kind: str, value: dict):
        self.store.set_project_metadata(kind + "_" + value[kind + "_id"], value)
        return value

    def _load(self, kind: str, identity: str) -> dict:
        try:
            uuid.UUID(identity)
        except (ValueError, TypeError, AttributeError):
            raise DockflowError("Invalid " + kind + " identity") from None
        value = self.store.project_metadata(kind + "_" + identity)
        if value is None:
            raise DockflowError(kind.capitalize() + " not found", "NOT_FOUND", 404)
        return value

    def resources(self) -> dict[str, dict[str, dict]]:
        result: dict[str, dict[str, dict]] = {name: {} for name in COLLECTIONS}
        with self.db.reader() as connection:
            rows = (
                self.db.execute(
                    connection,
                    "SELECT collection,public_id,value FROM dockflow_state_resources WHERE project_id=?",
                    (self.store.project_id,),
                ).fetchall()
                if connection is not None
                else []
            )
            output_sets = (
                self.db.execute(
                    connection,
                    "SELECT attempt_id,value FROM dockflow_output_sets WHERE project_id=?",
                    (self.store.project_id,),
                ).fetchall()
                if connection is not None
                else []
            )
        for collection, identity, value in rows:
            result[collection][identity] = loads(value)
        result["output_sets"] = {
            identity: loads(value) for identity, value in output_sets
        }
        return result

    def _live(self, value: dict) -> bool:
        return not value.get("deleted_at") and not value.get("retiring_plan_id")

    def _idle(self):
        if any(
            self._live(run)
            and (run.get("state") not in TERMINAL or run.get("reconciliation_required"))
            for run in self.resources()["runs"].values()
        ):
            raise DockflowError(
                "Deletion requires an idle project with no queued or unresolved Runs",
                "CONFLICT",
                409,
            )
        with self.db.reader() as connection:
            active = self.db.execute(
                connection,
                "SELECT 1 FROM df_cache_attempts WHERE scope_id IN (SELECT scope_id FROM df_cache_scopes WHERE project_id=?) AND state IN ('RUNNING','VALIDATING') LIMIT 1",
                (self.store.project_id,),
            ).fetchone()
        if active:
            raise DockflowError(
                "An unfinished cache publication protects storage", "CONFLICT", 409
            )

    def _cache(self):
        with self.db.reader() as connection:
            return [
                dict(
                    zip(
                        ("artifact_id", "scope_id", "cache_key", "state", "manifest"),
                        row,
                        strict=True,
                    )
                )
                for row in self.db.execute(
                    connection,
                    "SELECT artifact_id,scope_id,cache_key,state,manifest FROM df_cache_artifacts WHERE scope_id IN (SELECT scope_id FROM df_cache_scopes WHERE project_id=?)",
                    (self.store.project_id,),
                ).fetchall()
            ]

    def blockers(self, artifact: dict, resources=None) -> list[str]:
        resources = resources or self.resources()
        identity = artifact["artifact_id"]
        reasons = []
        if artifact.get("pinned"):
            reasons.append("Artifact is pinned; explicitly unpin it first")
        for attempt_id, marker in resources.get("output_sets", {}).items():
            if identity in set(identifiers(marker.get("outputs", {}))) and any(
                self._live(
                    resources[collection].get(marker[field], {"deleted_at": True})
                )
                for collection, field in (
                    ("runs", "run_id"),
                    ("tasks", "task_id"),
                    ("attempts", "attempt_id"),
                )
            ):
                reasons.append(
                    "Committed output set remains needed by retained execution history: "
                    + attempt_id
                )
        for collection in ("runs", "tasks", "attempts"):
            for key, resource in resources[collection].items():
                if not self._live(resource):
                    continue
                bound = {
                    field: resource.get(field)
                    for field in (
                        "inputs",
                        "outputs",
                        "bindings",
                        "parameters",
                        "use_executions",
                    )
                }
                if identity in set(identifiers(bound)):
                    reasons.append(f"Referenced by {collection}/{key}")
                # Importer parameters may bind a URI rather than an artifact ID.
                uri = artifact.get("content_uri")
                if uri and uri in set(identifiers(resource.get("parameters", {}))):
                    reasons.append(f"Storage URI referenced by {collection}/{key}")
        return sorted(set(reasons))

    def _path(self, artifact):
        uri = artifact.get("content_uri")
        if not uri:
            return None
        parsed = urlsplit(uri)
        if self.artifacts.backend == "filesystem":
            if parsed.scheme != "file":
                return None
            from pathlib import Path

            try:
                return (
                    Path(unquote(parsed.path))
                    .relative_to(self.artifacts.managed_root)
                    .as_posix()
                )
            except ValueError:
                return None
        if parsed.scheme != "s3" or parsed.netloc != self.artifacts.options["bucket"]:
            return None
        key = unquote(parsed.path).lstrip("/")
        prefix = self.artifacts.options.get("prefix", "").strip("/")
        if prefix and not key.startswith(prefix + "/"):
            return None
        return key[len(prefix) + 1 :] if prefix else key

    def _publication_records(self, storage_id):
        with self.db.reader() as connection:
            return [
                (project, namespace, key, loads(value))
                for project, namespace, key, value in self.db.execute(
                    connection,
                    "SELECT project_id,namespace,record_key,value FROM dockflow_artifact_records WHERE storage_id=?",
                    (storage_id,),
                ).fetchall()
            ]

    @contextlib.contextmanager
    def _parent(self, key):
        """Open every ancestor without symlinks and stay on the root device."""
        root = self.artifacts.managed_root
        descriptors = []
        try:
            descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            descriptors.append(descriptor)
            device = os.fstat(descriptor).st_dev
            parts = PurePosixPath(relative(key)).parts
            if not parts:
                raise DockflowError("The storage root cannot be deleted")
            for part in parts[:-1]:
                descriptor = os.open(
                    part,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=descriptor,
                )
                descriptors.append(descriptor)
                if os.fstat(descriptor).st_dev != device:
                    raise DockflowError(
                        "Storage deletion cannot cross filesystem mounts",
                        "CONFLICT",
                        409,
                    )
            yield descriptor, parts[-1], device
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    def _identity(self, key, version_id=None):
        if self.artifacts.backend == "filesystem":
            with self._parent(key) as (parent, name, device):
                observed = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if not stat.S_ISREG(observed.st_mode) or observed.st_dev != device:
                    raise DockflowError(
                        "Only regular files on the managed filesystem may be deleted",
                        "CONFLICT",
                        409,
                    )
                return {
                    "device": str(observed.st_dev),
                    "inode": str(observed.st_ino),
                    "size_bytes": observed.st_size,
                    "mtime_ns": str(observed.st_mtime_ns),
                    "ctime_ns": str(observed.st_ctime_ns),
                }
        try:
            value = self.artifacts._s3().head_object(
                Bucket=self.artifacts.options["bucket"],
                Key=self._object_key(key),
                **({"VersionId": version_id} if version_id else {}),
            )
        except Exception as exc:
            code = str(getattr(exc, "response", {}).get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NoSuchVersion", "NotFound"}:
                raise FileNotFoundError(key) from None
            raise DockflowError(
                "Cannot inspect object identity", "ARTIFACT_UNAVAILABLE", 503
            ) from None
        return {
            "etag": value.get("ETag"),
            "version_id": value.get("VersionId") or version_id,
            "size_bytes": value["ContentLength"],
            "last_modified": value["LastModified"].isoformat(),
        }

    def _object_key(self, key):
        relative(key)
        prefix = self.artifacts.options.get("prefix", "").strip("/")
        return prefix + "/" + key if prefix else key

    def _files(self, prefix):
        if self.artifacts.backend == "filesystem":
            root = self.artifacts.managed_root
            if not root.exists():
                return
            root_device = root.stat().st_dev

            def unavailable(error):
                raise error

            for directory, folders, names in os.walk(
                root, followlinks=False, onerror=unavailable
            ):
                from pathlib import Path

                base = Path(directory)
                for folder in list(folders):
                    path = base / folder
                    value = path.lstat()
                    if path.is_symlink() or value.st_dev != root_device:
                        folders.remove(folder)
                        key = path.relative_to(root).as_posix()
                        if contains(prefix, key):
                            yield key, None, "Symlink or mounted directory"
                for name in names:
                    key = (base / name).relative_to(root).as_posix()
                    if not contains(prefix, key):
                        continue
                    try:
                        yield key, self._identity(key), None
                    except (DockflowError, OSError):
                        yield key, None, "Nonregular or inaccessible file"
            return
        client = self.artifacts._s3()
        versioning = client.get_bucket_versioning(
            Bucket=self.artifacts.options["bucket"]
        )
        if versioning.get("Status") == "Enabled":
            for page in client.get_paginator("list_object_versions").paginate(
                Bucket=self.artifacts.options["bucket"], Prefix=self._object_key(prefix)
            ):
                base = self.artifacts.options.get("prefix", "").strip("/")
                for value in page.get("Versions", []):
                    key = value["Key"][len(base) + 1 :] if base else value["Key"]
                    if contains(prefix, key):
                        yield key, self._identity(key, value["VersionId"]), None
            return
        token = None
        while True:
            arguments = {
                "Bucket": self.artifacts.options["bucket"],
                "Prefix": self._object_key(prefix),
            }
            if token:
                arguments["ContinuationToken"] = token
            page = client.list_objects_v2(**arguments)
            for value in page.get("Contents", []):
                base = self.artifacts.options.get("prefix", "").strip("/")
                key = value["Key"][len(base) + 1 :] if base else value["Key"]
                if contains(prefix, key):
                    yield key, self._identity(key), None
            if not page.get("IsTruncated"):
                break
            following = page.get("NextContinuationToken")
            if not following or following == token:
                raise DockflowError(
                    "Incomplete object listing; rescan before cleanup",
                    "UNAVAILABLE",
                    503,
                )
            token = following

    def _inventory(self, prefix=""):
        prefix = relative(prefix)
        storage_id = self.artifacts.storage_identity(create=False)
        resources = self.resources()
        descriptors = resources["artifacts"]
        cache = self._cache()
        publications = self._publication_records(storage_id)
        dependencies = {
            identity: self.blockers(value, resources)
            for identity, value in descriptors.items()
            if self._live(value)
        }
        with self.db.reader() as connection:
            jobs = [
                loads(row[0])
                for row in self.db.execute(
                    connection,
                    "SELECT value FROM dockflow_project_metadata WHERE project_id=? AND name LIKE ?",
                    (self.store.project_id, "plan_%"),
                ).fetchall()
            ]
        # A cache-only committed output remains owned even without a catalog row.
        cache_paths = []
        for entry in cache:
            manifest = loads(entry["manifest"])
            for descriptor in manifest.get("outputs", {}).values():
                path = descriptor.get("managed_path")
                if path:
                    cache_paths.append((path, descriptor["artifact_id"]))
        rows = []
        for key, identity, error in self._files(prefix):
            owners = [
                value
                for value in descriptors.values()
                if (path := self._path(value)) is not None
                and (
                    key == path
                    or value.get("payload_kind") == "directory"
                    and contains(path, key)
                )
            ]
            live = [value for value in owners if self._live(value)]
            reasons = [error] if error else []
            classification = "orphan"
            if owners:
                classification = (
                    "manual_artifact"
                    if any(manual(value) for value in live)
                    else "execution_artifact"
                    if live
                    else "retained_file"
                )
                for value in live:
                    reasons.extend(dependencies[value["artifact_id"]])
                    if value.get("ownership") != "managed":
                        reasons.append("External reference storage cannot be deleted")
                if any(value.get("retiring_plan_id") for value in owners):
                    reasons.append("A pending deletion job owns this file")
                if not any(value.get("ownership") == "managed" for value in owners):
                    reasons.append("External source files cannot be deleted")
            for project, namespace, destination, value in publications:
                if namespace == "pipeline-descriptors":
                    path = value.get("managed_path")
                    if (
                        path
                        and contains(path, key)
                        and value.get("artifact_id") not in descriptors
                    ):
                        classification = "publication"
                        reasons.append(
                            "Retained publication descriptor without a catalog entry"
                        )
                elif namespace == "pipeline-claims" and contains(destination, key):
                    if value.get("artifact_id") not in descriptors:
                        classification = "publication"
                        reasons.append("Publication claim protects this location")
                elif (
                    namespace in {"publication-claims", "publication-manifests"}
                    and "destination" in value
                    and contains(destination, key)
                ):
                    classification = "publication"
                    reasons.append(
                        "Standalone manual publication; explicit publisher retirement is required"
                    )
                if project != self.store.project_id and contains(destination, key):
                    classification = "unknown"
                    reasons.append("Storage contains another project's publication")
            if any(
                contains(path, key) and artifact_id not in descriptors
                for path, artifact_id in cache_paths
            ):
                classification = "publication"
                reasons.append("Committed cache publication without a catalog entry")
            if (
                not key
                or key == ".dockflow/storage.json"
                or key.startswith(".dockflow/")
                and not owners
                and classification == "orphan"
            ):
                classification = "protected"
                reasons.append("Reserved storage metadata")
            if error:
                classification = "unknown"
            pending = [
                job["plan_id"]
                for job in jobs
                if job["state"] in {"deleting", "partial"}
                and any(
                    row["path"] == key and row["id"] not in job["completed"]
                    for row in job["rows"]
                )
            ]
            if pending:
                reasons.append("Pending deletion job: " + ", ".join(pending))
            rows.append(
                {
                    "id": digest(
                        {
                            "path": key,
                            "version_id": identity.get("version_id")
                            if identity
                            else None,
                        }
                    ),
                    "path": key,
                    "size_bytes": identity["size_bytes"] if identity else None,
                    "identity": identity,
                    "classification": classification,
                    "artifact_ids": sorted(value["artifact_id"] for value in owners),
                    "blockers": sorted(set(reasons)),
                    "eligible": not reasons,
                    "pending_plan_ids": pending,
                }
            )
        rows.sort(key=lambda row: row["path"])
        location = (
            str(self.artifacts.managed_root)
            if self.artifacts.backend == "filesystem"
            else "s3://"
            + self.artifacts.options["bucket"]
            + "/"
            + self.artifacts.options.get("prefix", "").strip("/")
        )
        return {
            "storage_id": storage_id,
            "location": location,
            "prefix": prefix,
            "rows": rows,
        }

    @staticmethod
    def totals(rows, selected=()):
        selected = set(selected)
        return {
            "selected_bytes": sum(
                row["size_bytes"] or 0 for row in rows if row["id"] in selected
            ),
            "orphan_bytes": sum(
                row["size_bytes"] or 0
                for row in rows
                if row["classification"] == "orphan" and row["eligible"]
            ),
            "artifact_bytes": sum(
                row["size_bytes"] or 0 for row in rows if row["artifact_ids"]
            ),
            "protected_artifact_bytes": sum(
                row["size_bytes"] or 0
                for row in rows
                if row["artifact_ids"] and not row["eligible"]
            ),
            "unknown_size_count": sum(row["size_bytes"] is None for row in rows),
            "file_count": len(rows),
        }

    def scan(self, values: dict) -> dict:
        self.store.require_owner()
        scan = {
            "scan_id": str(uuid.uuid4()),
            "created_at": utc_now(),
            "state": "scanning",
            "prefix": relative(values.get("prefix", "")),
            "rows": [],
            "errors": [],
        }
        self._save("scan", scan)
        try:
            scan.update(self._inventory(scan["prefix"]), state="complete")
        except Exception:
            scan.update(
                state="failed",
                errors=["Inventory was incomplete; check storage access and retry"],
            )
            self._save("scan", scan)
            raise
        scan["totals"] = self.totals(scan["rows"])
        self._save("scan", scan)
        return self.scan_show({"scan_id": scan["scan_id"]})

    def scan_show(self, values: dict) -> dict:
        scan = self._load("scan", values["scan_id"])
        page_size = values.get("page_size", 50)
        if type(page_size) is not int or not 1 <= page_size <= 200:
            raise DockflowError("page_size must be between 1 and 200")
        try:
            offset = int(values.get("page_token") or 0)
            if offset < 0:
                raise ValueError
        except (TypeError, ValueError):
            raise DockflowError("Invalid scan page token") from None
        selected = (
            self._selection(scan, values, expand=True)
            if values.get("selected") or values.get("orphans")
            else []
        )
        rows = scan["rows"]
        if values.get("classification"):
            if values["classification"] not in CLASSES:
                raise DockflowError("Unknown storage classification")
            rows = [
                row for row in rows if row["classification"] == values["classification"]
            ]
        if values.get("artifact_id"):
            rows = [row for row in rows if values["artifact_id"] in row["artifact_ids"]]
        return {
            **{key: value for key, value in scan.items() if key != "rows"},
            "items": rows[offset : offset + page_size],
            "next_page_token": str(offset + page_size)
            if offset + page_size < len(rows)
            else None,
            "totals": self.totals(scan["rows"], [row["id"] for row in selected]),
            "selected_ids": [row["id"] for row in selected],
            "selection_groups": {
                identity: [
                    row["id"] for row in selected if identity in row["artifact_ids"]
                ]
                for identity in {
                    identity for row in selected for identity in row["artifact_ids"]
                }
            },
            "retention": self.retention_status(),
        }

    def _selection(self, scan, values, *, expand):
        selected = values.get("selected", [])
        if not isinstance(selected, list) or not all(
            isinstance(item, str) for item in selected
        ):
            raise DockflowError("selected must be an array of scan row IDs")
        if values.get("orphans"):
            selected = [
                row["id"]
                for row in scan["rows"]
                if row["classification"] == "orphan" and row["eligible"]
            ]
        by_id = {row["id"]: row for row in scan["rows"]}
        if set(selected) - by_id.keys():
            raise DockflowError("Selection contains unknown scan row IDs")
        chosen = {key: by_id[key] for key in selected}
        if expand:
            owners = {
                identity for row in chosen.values() for identity in row["artifact_ids"]
            }
            # Expand repeatedly for overlapping artifact aliases.
            while True:
                previous = set(chosen)
                chosen.update(
                    {
                        row["id"]: row
                        for row in scan["rows"]
                        if owners.intersection(row["artifact_ids"])
                    }
                )
                owners.update(
                    identity
                    for row in chosen.values()
                    for identity in row["artifact_ids"]
                )
                if previous == set(chosen):
                    break
        return sorted(chosen.values(), key=lambda row: row["path"])

    def _targets(self, requested, resources):
        targets = set()
        for target in requested:
            if (
                not isinstance(target, dict)
                or set(target) != {"collection", "id"}
                or not isinstance(target["collection"], str)
                or target["collection"] not in {"runs", "attempts", "artifacts"}
                or not isinstance(target["id"], str)
            ):
                raise DockflowError(
                    "Deletion targets require collection runs/attempts/artifacts and id"
                )
            collection, identity = target["collection"], target["id"]
            if identity not in resources[collection] or not self._live(
                resources[collection][identity]
            ):
                raise DockflowError("Deletion target does not exist", "NOT_FOUND", 404)
            targets.add((collection, identity))
            if collection == "runs":
                targets.update(
                    (kind, key)
                    for kind in ("tasks", "attempts")
                    for key, resource in resources[kind].items()
                    if resource.get("run_id") == identity and self._live(resource)
                )
        return targets

    def _target_blockers(self, targets, resources):
        reasons = []
        attempt_ids = {key for kind, key in targets if kind == "attempts"}
        for collection, identity in targets:
            value = resources[collection][identity]
            if collection == "artifacts":
                reasons.extend(self.blockers(value, resources))
                continue
            if collection in {"runs", "attempts"} and (
                value.get("state") not in TERMINAL
                or value.get("reconciliation_required")
            ):
                reasons.append(
                    f"{collection}/{identity} is not terminal and reconciled"
                )
        for collection in ("runs", "tasks", "attempts"):
            for identity, value in resources[collection].items():
                if (collection, identity) in targets or not self._live(value):
                    continue
                references = {
                    "use_executions": value.get("use_executions"),
                    "reuse": value.get("reuse"),
                }
                if attempt_ids.intersection(identifiers(references)):
                    reasons.append(
                        f"Retained {collection}/{identity} selects this execution"
                    )
        return sorted(set(reasons))

    def plan(self, values: dict) -> dict:
        self.store.require_owner()
        resources = self.resources()
        requested = values.get("targets", [])
        if not isinstance(requested, list):
            raise DockflowError("targets must be an array")
        targets = self._targets(requested, resources)
        if any(kind == "artifacts" for kind, _ in targets) and any(
            kind != "artifacts" for kind, _ in targets
        ):
            raise DockflowError(
                "Delete Runs/executions before separately deleting artifacts"
            )
        rows = []
        blockers = self._target_blockers(targets, resources)
        scan_id = values.get("scan_id")
        delete_files = values.get("delete_files", False)
        if type(delete_files) is not bool:
            raise DockflowError("delete_files must be boolean")
        storage_id = self.artifacts.storage_identity(create=False)
        if scan_id:
            scan = self._load("scan", scan_id)
            if scan["state"] != "complete" or scan.get("storage_id") != storage_id:
                raise DockflowError(
                    "Only a complete scan of the current store can be used",
                    "CONFLICT",
                    409,
                )
            rows = self._selection(scan, values, expand=True)
            delete_files = True
            targets.update(
                ("artifacts", identity)
                for row in rows
                for identity in row["artifact_ids"]
                if identity in resources["artifacts"]
                and self._live(resources["artifacts"][identity])
            )
            blockers.extend(self._target_blockers(targets, resources))
        elif delete_files:
            if any(kind != "artifacts" for kind, _ in targets):
                raise DockflowError(
                    "Run/execution deletion does not implicitly delete artifact files"
                )
            scan = self._inventory()
            identities = {identity for _, identity in targets}
            rows = [
                row
                for row in scan["rows"]
                if identities.intersection(row["artifact_ids"])
            ]
            # Every alias to selected bytes must pass the same gate.
            targets.update(
                ("artifacts", identity)
                for row in rows
                for identity in row["artifact_ids"]
                if self._live(resources["artifacts"][identity])
            )
            blockers.extend(self._target_blockers(targets, resources))
            for _, identity in targets:
                if resources["artifacts"][identity].get("ownership") != "managed":
                    blockers.append("External source files cannot be deleted")
        for row in rows:
            blockers.extend(row["blockers"])
            if row["classification"] in {"publication", "protected", "unknown"}:
                blockers.append("Selection contains protected or unknown owned data")
        if not targets and not rows:
            raise DockflowError("Deletion selection is empty")
        # A selected directory must be represented completely, even when a scan
        # was scoped to a child prefix. Never silently delete a partial artifact.
        if rows and any(row["artifact_ids"] for row in rows):
            full = self._inventory()
            identities = {key for kind, key in targets if kind == "artifacts"}
            complete = [
                row
                for row in full["rows"]
                if identities.intersection(row["artifact_ids"])
            ]
            if {row["id"] for row in complete} - {row["id"] for row in rows}:
                blockers.append(
                    "Selection omits files of a directory artifact; scan the complete managed root"
                )
        now = utc_now()
        plan = {
            "plan_id": str(uuid.uuid4()),
            "project_id": self.store.project_id,
            "storage_id": storage_id,
            "location": str(self.artifacts.managed_root)
            if self.artifacts.backend == "filesystem"
            else "s3://"
            + self.artifacts.options["bucket"]
            + "/"
            + self.artifacts.options.get("prefix", "").strip("/"),
            "created_at": now,
            "expires_at": time.time() + PLAN_SECONDS,
            "state": "planned",
            "delete_files": delete_files,
            "targets": [
                {"collection": kind, "id": key} for kind, key in sorted(targets)
            ],
            "target_digests": {
                kind + "/" + key: digest(resources[kind][key]) for kind, key in targets
            },
            "rows": rows,
            "blockers": sorted(set(blockers)),
            "estimated_bytes": sum(row["size_bytes"] or 0 for row in rows),
            "completed": [],
            "failures": [],
            "scan_id": scan_id,
        }
        self._save("plan", plan)
        return plan

    def show(self, values: dict) -> dict:
        return self._load("plan", values["plan_id"])

    def _invalidate(self, targets):
        artifacts = {key for kind, key in targets if kind == "artifacts"}
        attempts = {key for kind, key in targets if kind == "attempts"}
        for entry in self._cache():
            manifest = loads(entry["manifest"])
            if not (
                artifacts.intersection(
                    value["artifact_id"]
                    for value in manifest.get("outputs", {}).values()
                )
                or manifest.get("producer", {}).get("attempt_id") in attempts
            ):
                continue
            now = time.time()
            self.db.execute(
                self.db.connection,
                "UPDATE df_cache_artifacts SET state='INVALID',invalidated_at=?,invalidation_reason=? WHERE artifact_id=? AND scope_id=?",
                (
                    now,
                    "Explicit Dockflow retirement",
                    entry["artifact_id"],
                    entry["scope_id"],
                ),
            )
            self.db.execute(
                self.db.connection,
                "UPDATE df_cache_entries SET published_artifact_id=NULL,generation=generation+1,revision=revision+1,updated_at=? WHERE scope_id=? AND cache_key=? AND published_artifact_id=?",
                (now, entry["scope_id"], entry["cache_key"], entry["artifact_id"]),
            )

    def _retire(self, plan, resources, *, completed=False):
        values = []
        for target in plan["targets"]:
            collection, identity = target["collection"], target["id"]
            value = dict(resources[collection][identity])
            if completed:
                value.pop("retiring_plan_id", None)
                value.update(
                    deleted_at=utc_now(),
                    deletion_plan_id=plan["plan_id"],
                    deletion_reason=plan.get("reason", "explicit"),
                )
                if collection == "artifacts":
                    value["storage_files_deleted"] = plan["delete_files"]
            else:
                value["retiring_plan_id"] = plan["plan_id"]
            values.append({"collection": collection, "resource": value})
        if values:
            self.store.append(
                "resource_retirement", {"plan_id": plan["plan_id"], "resources": values}
            )
            project = self.store.project_metadata("project")
            if project and project.get("mapping_version") == 1:
                self.store.set_project_metadata(
                    "project", {**project, "mapping_version": 2}
                )

    def _delete(self, row):
        key = row["path"]
        if self.artifacts.backend == "filesystem":
            with self._parent(key) as (parent, name, _):
                if self._identity(key) != row["identity"]:
                    raise DockflowError("File changed since planning", "CONFLICT", 409)
                os.unlink(name, dir_fd=parent)
                os.fsync(parent)
            return
        condition = (
            {"VersionId": row["identity"]["version_id"]}
            if row["identity"].get("version_id")
            else {"IfMatch": row["identity"]["etag"]}
        )
        self.artifacts._s3().delete_object(
            Bucket=self.artifacts.options["bucket"],
            Key=self._object_key(key),
            **condition,
        )

    def _qualify_conditional_delete(self, client):
        """Probe only a fresh reserved object, never a user's artifact."""
        key = self._object_key(".dockflow/deletion-probes/" + uuid.uuid4().hex)
        bucket = self.artifacts.options["bucket"]
        client.put_object(
            Bucket=bucket, Key=key, Body=b"dockflow-delete-capability", IfNoneMatch="*"
        )
        try:
            try:
                client.delete_object(
                    Bucket=bucket, Key=key, IfMatch='"deliberately-mismatched-etag"'
                )
            except Exception as exc:
                code = str(
                    getattr(exc, "response", {}).get("Error", {}).get("Code", "")
                )
                if code in {"412", "PreconditionFailed"}:
                    return
                raise DockflowError(
                    "Cannot qualify conditional storage deletion; no selected files were deleted",
                    "ARTIFACT_UNAVAILABLE",
                    503,
                ) from None
            raise DockflowError(
                "This S3 provider ignores conditional deletion. Enable bucket versioning before using storage cleanup",
                "UNSUPPORTED_STORAGE",
                409,
            )
        finally:
            client.delete_object(Bucket=bucket, Key=key)

    def apply(self, values: dict, *, automatic: bool = False) -> dict:
        plan = self._load("plan", values["plan_id"])
        if plan["delete_files"] and (
            not automatic and values.get("confirmation") != "DANGER"
        ):
            raise DockflowError(
                "Type DANGER to confirm deletion of storage files",
                "CONFIRMATION_REQUIRED",
                409,
            )
        if plan["state"] == "completed":
            return plan
        if plan["blockers"]:
            raise DockflowError(
                "Deletion is blocked: " + "; ".join(plan["blockers"]), "CONFLICT", 409
            )
        with self.db.maintenance():
            self._idle()
            if not self.store.check()["valid"]:
                raise DockflowError(
                    "Metadata integrity must be repaired before deletion",
                    "CONFLICT",
                    409,
                )
            if self.artifacts.storage_identity(create=False) != plan["storage_id"]:
                raise DockflowError("Artifact store identity changed", "CONFLICT", 409)
            if plan["delete_files"] and self.artifacts.backend == "s3":
                client = self.artifacts._s3()
                versioning = client.get_bucket_versioning(
                    Bucket=self.artifacts.options["bucket"]
                )
                if versioning.get("Status") == "Suspended":
                    raise DockflowError(
                        "Storage deletion requires enabled versioning or an unversioned bucket; suspended versioning is unsupported",
                        "CONFLICT",
                        409,
                    )
                if versioning.get("Status") != "Enabled":
                    self._qualify_conditional_delete(client)
                elif any(not row["identity"].get("version_id") for row in plan["rows"]):
                    raise DockflowError(
                        "Bucket versioning changed after scanning; create a new scan and plan",
                        "CONFLICT",
                        409,
                    )
                try:
                    lock = client.get_object_lock_configuration(
                        Bucket=self.artifacts.options["bucket"]
                    )
                except Exception as exc:
                    code = str(
                        getattr(exc, "response", {}).get("Error", {}).get("Code", "")
                    )
                    if code not in {
                        "ObjectLockConfigurationNotFoundError",
                        "NoSuchObjectLockConfiguration",
                        "404",
                        "NotFound",
                    }:
                        raise DockflowError(
                            "Cannot verify object-lock configuration; deletion refused",
                            "ARTIFACT_UNAVAILABLE",
                            503,
                        ) from None
                    lock = {}
                if (
                    lock.get("ObjectLockConfiguration", {}).get("ObjectLockEnabled")
                    == "Enabled"
                ):
                    raise DockflowError(
                        "Object-lock buckets cannot be cleaned", "CONFLICT", 409
                    )
            resources = self.resources()
            targets = {
                (target["collection"], target["id"]) for target in plan["targets"]
            }
            if plan["state"] == "planned":
                if time.time() > plan["expires_at"]:
                    raise DockflowError(
                        "Deletion plan expired; create a new plan", "CONFLICT", 409
                    )
                if any(
                    digest(resources[kind][key])
                    != plan["target_digests"][kind + "/" + key]
                    for kind, key in targets
                ):
                    raise DockflowError(
                        "Resource changed since planning; create a new plan",
                        "CONFLICT",
                        409,
                    )
                blocked = self._target_blockers(targets, resources)
                if plan["rows"]:
                    current = self._inventory()
                    by_path = {row["id"]: row for row in current["rows"]}
                    artifact_ids = {key for kind, key in targets if kind == "artifacts"}
                    planned_ids = {row["id"] for row in plan["rows"]}
                    if any(
                        artifact_ids.intersection(row["artifact_ids"])
                        and row["id"] not in planned_ids
                        for row in current["rows"]
                    ):
                        blocked.append(
                            "Artifact gained files or object versions after planning"
                        )
                    for row in plan["rows"]:
                        observed = by_path.get(row["id"])
                        if (
                            observed is None
                            or observed["identity"] != row["identity"]
                            or not observed["eligible"]
                            or observed["artifact_ids"] != row["artifact_ids"]
                            or observed["classification"] != row["classification"]
                        ):
                            blocked.append(
                                "Storage ownership or file identity changed: "
                                + row["path"]
                            )
                if blocked:
                    raise DockflowError(
                        "Deletion plan is stale: " + "; ".join(blocked), "CONFLICT", 409
                    )
                with self.db.transaction():
                    self._invalidate(targets)
                    self._retire(plan, resources)
                    plan["state"] = "deleting"
                    self._save("plan", plan)
            else:
                # A resumable job owns only its original objects. New aliases,
                # publications or replacement files must not be removed on retry.
                current = {row["id"]: row for row in self._inventory()["rows"]}
                for row in plan["rows"]:
                    if row["id"] in plan["completed"]:
                        continue
                    observed = current.get(row["id"])
                    if observed is None:
                        continue
                    other_blockers = [
                        reason
                        for reason in observed["blockers"]
                        if reason != "A pending deletion job owns this file"
                        and not reason.startswith("Pending deletion job:")
                    ]
                    if (
                        observed["artifact_ids"] != row["artifact_ids"]
                        or other_blockers
                        or set(observed.get("pending_plan_ids", [])) - {plan["plan_id"]}
                    ):
                        raise DockflowError(
                            "Storage ownership changed while deletion was pending; remaining files were preserved",
                            "CONFLICT",
                            409,
                        )
            failures = []
            for row in plan["rows"]:
                if row["id"] in plan["completed"]:
                    continue
                try:
                    try:
                        observed = self._identity(
                            row["path"], row["identity"].get("version_id")
                        )
                    except FileNotFoundError:
                        observed = None
                    if observed is not None:
                        if observed != row["identity"]:
                            raise DockflowError(
                                "Object changed since planning", "CONFLICT", 409
                            )
                        self._delete(row)
                    plan["completed"].append(row["id"])
                    self._save("plan", plan)
                except Exception as exc:
                    failures.append(
                        {
                            "path": row["path"],
                            "reason": exc.message
                            if isinstance(exc, DockflowError)
                            else "Storage deletion failed; inspect permissions/provider and retry this plan",
                        }
                    )
            plan["failures"] = failures
            plan["state"] = "partial" if failures else "completed"
            if not failures:
                with self.db.transaction():
                    self._retire(plan, self.resources(), completed=True)
                    plan["finished_at"] = utc_now()
                    self.store.append(
                        "storage_deletion",
                        {
                            "plan_id": plan["plan_id"],
                            "file_count": len(plan["completed"]),
                            "estimated_bytes": plan["estimated_bytes"],
                        },
                    )
                    self._save("plan", plan)
            else:
                self._save("plan", plan)
            return plan

    def retention_status(self) -> dict:
        last = self.store.project_metadata("retention_status") or {}
        return {
            "days": self.core.settings.artifacts.get("retention_days", -1),
            "interval_seconds": self.core.settings.artifacts.get(
                "retention_interval_seconds", 3600
            ),
            **last,
        }

    def retention(self, values: dict, *, automatic: bool = False) -> dict:
        days = self.core.settings.artifacts.get("retention_days", -1)
        result = {
            "days": days,
            "enabled": days > 0,
            "eligible_artifact_ids": [],
            "estimated_bytes": 0,
            "blocked": [],
            "checked_at": utc_now(),
        }
        if days < 0:
            return result
        cutoff = time.time() - days * 86400
        resources = self.resources()
        for identity, value in resources["artifacts"].items():
            if (
                not self._live(value)
                or manual(value)
                or value.get("ownership") != "managed"
                or value.get("publication_state") != "committed"
            ):
                continue
            try:
                published = datetime.fromisoformat(
                    value["published_at"].replace("Z", "+00:00")
                )
                if published.tzinfo is None or published.timestamp() > cutoff:
                    continue
            except (KeyError, ValueError, TypeError):
                continue
            blocked = self.blockers(value, resources)
            path = self._path(value)
            for other_id, other in resources["artifacts"].items():
                other_path = self._path(other)
                if (
                    other_id != identity
                    and path is not None
                    and other_path is not None
                    and (contains(path, other_path) or contains(other_path, path))
                    and (
                        manual(other)
                        and self._live(other)
                        or other.get("deleted_at")
                        and not other.get("storage_files_deleted")
                    )
                ):
                    blocked.append(
                        "Storage is shared with a manual artifact or explicitly retained files"
                    )
            if blocked:
                result["blocked"].append({"artifact_id": identity, "reasons": blocked})
            else:
                result["eligible_artifact_ids"].append(identity)
        if result["eligible_artifact_ids"]:
            plan = self.plan(
                {
                    "targets": [
                        {"collection": "artifacts", "id": key}
                        for key in result["eligible_artifact_ids"]
                    ],
                    "delete_files": True,
                }
            )
            plan["reason"] = "retention"
            self._save("plan", plan)
            result.update(
                plan_id=plan["plan_id"], estimated_bytes=plan["estimated_bytes"]
            )
            if values.get("apply"):
                result["job"] = self.apply(
                    {
                        "plan_id": plan["plan_id"],
                        "confirmation": values.get("confirmation"),
                    },
                    automatic=automatic,
                )
        result["next_check_at"] = datetime.fromtimestamp(
            time.time()
            + self.core.settings.artifacts.get("retention_interval_seconds", 3600),
            UTC,
        ).isoformat()
        self.store.set_project_metadata("retention_status", result)
        return result


def operate(core, action: str, values: dict) -> dict:
    for field in (
        "prefix",
        "scan_id",
        "plan_id",
        "classification",
        "artifact_id",
        "page_token",
        "confirmation",
    ):
        if (
            field in values
            and values[field] is not None
            and not isinstance(values[field], str)
        ):
            raise DockflowError(field + " must be a string")
    for field in ("apply", "delete_files", "orphans"):
        if field in values and type(values[field]) is not bool:
            raise DockflowError(field + " must be boolean")
    required = {
        "storage.show": {"scan_id"},
        "deletions.show": {"plan_id"},
        "deletions.apply": {"plan_id"},
    }
    if not required.get(action, set()) <= values.keys():
        raise DockflowError("Missing required deletion/scan identity")
    service = Deletions(core)
    actions = {
        "storage.scan": service.scan,
        "storage.show": service.scan_show,
        "deletions.plan": service.plan,
        "deletions.show": service.show,
        "deletions.apply": service.apply,
        "retention": service.retention,
    }
    return actions[action](values)
