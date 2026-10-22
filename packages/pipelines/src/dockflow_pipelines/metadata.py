"""Authoritative control records, durable commits, replay and recovery.

OS locking and MLMD projection are delegated to dedicated adapters. ControlStore
retains their coordination boundary and the accepted-record transaction order.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import os
import re
import shutil
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any

from .canonical import digest, json_bytes, loads, validate_json
from .errors import DockflowError
from .mlmd_index import MLMDIndex as MLMDIndex
from .ownership import OWNER_METADATA_MAX_BYTES as OWNER_METADATA_MAX_BYTES
from .ownership import StateOwnership
from .records import COLLECTIONS as COLLECTIONS
from .records import MAPPING_VERSION as MAPPING_VERSION
from .records import SCHEMA_VERSION as SCHEMA_VERSION
from .records import TERMINAL as TERMINAL
from .records import new_id as new_id
from .records import utc_now as utc_now


def _fsync_directory(path: Path) -> None:
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def atomic_write(path: Path, data: bytes, *, exclusive: bool = False) -> None:
    """Write and sync on the destination filesystem; never expose partial JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive and path.exists():
            if path.read_bytes() != data:
                raise DockflowError(
                    f"Conflicting immutable control record: {path.name}",
                    code="CONFLICT",
                    status=409,
                )
            return
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


class ControlStore:
    def __init__(
        self, state: Path, project_id: str, metadata_directory: Path | None = None
    ):
        self.state = Path(state).absolute()
        self.project_id = project_id
        self.metadata_directory = Path(metadata_directory or self.state / "db")
        self.index: MLMDIndex | None = None
        self._ownership = StateOwnership(self.state, self.project_id)
        self._owner_guard = threading.Lock()
        self._owner_depth = 0
        self._mutex = threading.RLock()
        self._sequence = 0

    @property
    def root(self) -> Path:
        return self.state

    @property
    def reconciliation_required(self) -> bool:
        path = self.state / "index-status.json"
        return path.exists() and bool(
            self.read("index-status.json").get("reconciliation_required")
        )

    def ensure_reconciled(self) -> None:
        if self.reconciliation_required:
            raise DockflowError(
                "Accepted control state requires MLMD reconciliation before dispatch",
                code="UNAVAILABLE",
                status=503,
            )

    def open_readonly_index(self) -> bool:
        """Attach an existing index for inspection without schema or project writes."""
        path = self.metadata_directory / "mlmd.sqlite"
        if not path.exists():
            if self.records():
                raise DockflowError(
                    "MLMD index is missing; rebuild it offline from the accepted control records",
                    code="NOT_FOUND",
                    status=404,
                )
            return False
        self.index = MLMDIndex(path, self.project_id, read_only=True)
        return True

    def require_owner(self) -> None:
        self._ownership.require_owner()

    @contextlib.contextmanager
    def owner(self, endpoint: str | None = None):
        """OS-backed exclusion; metadata is diagnostic, never a takeover token.

        Nested contexts on this shared coordinator retain the same acquisition,
        including across threads. The last context releases its stable lock inode.
        """
        with self._owner_guard:
            if not self._ownership.held:
                self._ownership.acquire(endpoint)
                try:
                    self._sequence = len(self.records())
                except BaseException:
                    self._ownership.release()
                    raise
            self._owner_depth += 1
        try:
            yield self
        finally:
            with self._owner_guard:
                self._owner_depth -= 1
                if self._owner_depth == 0:
                    self._ownership.release()

    def initialize(self, require_mlmd: bool = True) -> None:
        self.require_owner()
        project_path = self.state / "project.json"
        expected = {
            "schema_version": 1,
            "kind": "project",
            "project_id": self.project_id,
            "mapping_version": 1,
            "digest_format": "dockflow-json-v1",
        }
        if project_path.exists():
            project = self.read("project.json")
            if any(project.get(key) != value for key, value in expected.items()):
                raise DockflowError(
                    "Incompatible state schema or project identity",
                    code="CONFLICT",
                    status=409,
                )
        else:
            atomic_write(
                project_path,
                json_bytes({**expected, "created_at": utc_now()}),
                exclusive=True,
            )
        records = self.records()
        self._sequence = len(records)
        for record in records:
            self._project(record)
        self._recover_committed_outputs(records)
        if require_mlmd:
            self.index = MLMDIndex(
                self.metadata_directory / "mlmd.sqlite", self.project_id
            )
            self.reconcile_index()

    def _recover_committed_outputs(self, records: list[dict[str, Any]]) -> None:
        for record in records:
            if record["kind"] != "output_set":
                continue
            marker = record["payload"]["marker"]
            outputs = {
                name: value["artifact_id"] for name, value in marker["outputs"].items()
            }
            try:
                attempt = self.get("attempts", marker["attempt_id"])
                task = self.get("tasks", marker["task_id"])
            except DockflowError as exc:
                if exc.code == "NOT_FOUND":
                    continue
                raise
            if attempt.get("state") != "succeeded":
                self.put(
                    "attempts",
                    {
                        **attempt,
                        "state": "succeeded",
                        "publication_state": "committed",
                        "outputs": outputs,
                        "output_parameters": marker["parameters"],
                        "finished_at": marker["published_at"],
                        "reconciliation_required": False,
                        "recovered_from_output_set": True,
                    },
                )
            if task.get("state") != "succeeded":
                self.put(
                    "tasks",
                    {
                        **task,
                        "state": "succeeded",
                        "disposition": "executed",
                        "outputs": outputs,
                        "output_parameters": marker["parameters"],
                        "reconciliation_required": False,
                    },
                )

    def _path(self, relative: str | Path) -> Path:
        relative = Path(relative)
        if relative.is_absolute() or ".." in relative.parts:
            raise DockflowError("Invalid control-record path", code="INVALID_ARGUMENT")
        path = self.state / relative
        if not path.resolve().is_relative_to(self.state.resolve()):
            raise DockflowError(
                "Control path escapes state root", code="INVALID_ARGUMENT"
            )
        return path

    def read(self, relative: str | Path) -> dict[str, Any]:
        try:
            value = loads(self._path(relative).read_bytes())
        except FileNotFoundError as exc:
            raise DockflowError(
                f"Control record not found: {relative}", code="NOT_FOUND", status=404
            ) from exc
        except (ValueError, UnicodeError) as exc:
            raise DockflowError(
                f"Invalid control record: {relative}", code="CONFLICT", status=409
            ) from exc
        if not isinstance(value, dict):
            raise DockflowError(
                f"Control record is not an object: {relative}",
                code="CONFLICT",
                status=409,
            )
        return value

    def write(self, relative: str | Path, resource: dict[str, Any]) -> None:
        self.require_owner()
        atomic_write(self._path(relative), json_bytes(resource))

    def write_bytes(self, relative: str | Path, source: bytes) -> None:
        """Persist an exact accepted auxiliary snapshot, including it in replay."""
        self.require_owner()
        self._path(relative)
        self.append(
            "file_snapshot",
            {
                "path": str(relative),
                "base64": base64.b64encode(source).decode("ascii"),
                "sha256": hashlib.sha256(source).hexdigest(),
            },
        )

    def save_definition(
        self, resource: dict[str, Any], source: bytes
    ) -> dict[str, Any]:
        self.require_owner()
        definition_id = resource["definition_id"]
        source_digest = hashlib.sha256(source).hexdigest()
        if resource.get("sha256", source_digest) != source_digest:
            raise DockflowError(
                "Definition source digest mismatch", code="CONFLICT", status=409
            )
        self.write_bytes(Path("definitions") / definition_id / "source.yaml", source)
        return self.put("definitions", {**resource, "sha256": source_digest})

    def save_definition_source(self, definition_id: str, source: bytes) -> None:
        self._resource_path("definitions", {"definition_id": definition_id})
        self.write_bytes(Path("definitions") / definition_id / "source.yaml", source)

    def log(
        self,
        run_id: str,
        text: str,
        stream: str = "system",
        task_id: str | None = None,
        attempt_id: str | None = None,
    ) -> dict[str, Any]:
        if stream not in {"stdout", "stderr", "system"}:
            raise DockflowError("Invalid log stream")
        self.get("runs", run_id)
        if attempt_id and not task_id:
            raise DockflowError("Attempt logs require a task ID")
        text = "".join(
            "\ufffd" if 0xD800 <= ord(character) <= 0xDFFF else character
            for character in text
        )
        encoded = text.encode("utf-8")
        chunks: list[str] = []
        offset = 0
        while offset < len(encoded):
            end = min(offset + 16384, len(encoded))
            while end < len(encoded) and encoded[end] & 0xC0 == 0x80:
                end -= 1
            chunks.append(encoded[offset:end].decode("utf-8"))
            offset = end
        entry = {
            "timestamp": utc_now(),
            "run_id": run_id,
            "task_id": task_id,
            "attempt_id": attempt_id,
            "stream": stream,
            "text": "",
        }
        with self._mutex:
            for chunk in chunks or [""]:
                entry = {**entry, "text": chunk}
                record = self.append("log", entry)
            return {**entry, "sequence": record["sequence"]}

    def log_entries(self, run_id: str) -> list[dict[str, Any]]:
        self.get("runs", run_id)
        return [
            {**record["payload"], "sequence": record["sequence"]}
            for record in self.records()
            if record.get("event_kind") == "log"
            and record["payload"].get("run_id") == run_id
        ]

    def records(self) -> list[dict[str, Any]]:
        directory = self.state / "records"
        result = []
        if not directory.exists():
            return result
        stopped_runs: set[str] = set()
        committed_attempts: set[str] = set()
        registered_versions: dict[str, dict] = {}
        registered_components: dict[str, dict] = {}
        catalogs: dict[str, dict] = {}
        observed_ids: set[tuple[str, str]] = set()
        for expected, path in enumerate(sorted(directory.glob("*.json")), start=1):
            if path.name != f"{expected:020d}.json":
                raise DockflowError(
                    f"Accepted mutation sequence gap at {expected}",
                    code="CONFLICT",
                    status=409,
                )
            record = self.read(path.relative_to(self.state))
            if (
                record.get("schema_version") != 1
                or record.get("project_id") != self.project_id
                or record.get("sequence") != expected
            ):
                raise DockflowError(
                    f"Incompatible accepted mutation {path.name}",
                    code="CONFLICT",
                    status=409,
                )
            if record.get("kind") not in {
                "resource_put",
                "output_set",
                "stop_intent",
                "event",
                "cleanup",
                "file_snapshot",
            }:
                raise DockflowError(
                    f"Unknown accepted mutation kind: {record.get('kind')}",
                    code="CONFLICT",
                    status=409,
                )
            self._validate_record(record)
            if record.get("event_kind") == "pipeline_registration":
                resources = record["payload"]["resources"]
                catalog = resources[0]["resource"]
                version = resources[1]["resource"]
                previous = catalogs.get(catalog["pipeline_id"])
                previous_ids = previous.get("version_ids", []) if previous else []
                if (
                    catalog["version_ids"] != [*previous_ids, version["definition_id"]]
                    or previous is not None
                    and any(
                        previous.get(field) != catalog.get(field)
                        for field in (
                            "name",
                            "registration_origin",
                            "created_at",
                            "description",
                        )
                    )
                ):
                    raise DockflowError(
                        "Accepted registration changes catalog identity or version history",
                        "CONFLICT",
                        409,
                    )
                for item in resources[1:]:
                    collection, resource = item["collection"], item["resource"]
                    public_id = resource[f"{COLLECTIONS[collection]}_id"]
                    if (collection, public_id) in observed_ids:
                        raise DockflowError(
                            "Accepted registration reuses an immutable version/component ID",
                            "CONFLICT",
                            409,
                        )
                registered_versions[version["definition_id"]] = version
                registered_components.update(
                    {
                        item["resource"]["component_id"]: item["resource"]
                        for item in resources[2:]
                    }
                )
            for mutation in self._registration_records(record):
                if mutation["kind"] != "resource_put":
                    continue
                collection = mutation["payload"]["collection"]
                resource = mutation["payload"]["resource"]
                public_id = resource[f"{COLLECTIONS[collection]}_id"]
                protected = (
                    registered_versions
                    if collection == "definitions"
                    else registered_components
                    if collection == "components"
                    else {}
                )
                if public_id in protected and resource != protected[public_id]:
                    raise DockflowError(
                        "Accepted mutation rewrites an immutable registered version/component",
                        "CONFLICT",
                        409,
                    )
                if collection == "pipelines":
                    previous = catalogs.get(public_id)
                    if (
                        previous
                        and previous.get("registration_origin") == "api"
                        and record.get("event_kind") != "pipeline_registration"
                        and any(
                            resource.get(field) != previous.get(field)
                            for field in (
                                "name",
                                "registration_origin",
                                "version_ids",
                                "definition_id",
                                "default_version_id",
                                "created_at",
                                "description",
                            )
                        )
                    ):
                        raise DockflowError(
                            "Accepted mutation rewrites an uploaded catalog",
                            "CONFLICT",
                            409,
                        )
                    catalogs[public_id] = resource
                observed_ids.add((collection, public_id))
            if record["kind"] == "stop_intent":
                stopped_runs.add(record["payload"]["run_id"])
            elif record["kind"] == "output_set":
                marker = record["payload"]["marker"]
                if (
                    marker["run_id"] in stopped_runs
                    or marker["attempt_id"] in committed_attempts
                ):
                    raise DockflowError(
                        "Contradictory output-set acceptance ordering",
                        code="CONFLICT",
                        status=409,
                    )
                committed_attempts.add(marker["attempt_id"])
            result.append(record)
        return result

    def _validate_record(self, record: dict[str, Any]) -> None:
        try:
            payload = record["payload"]
            if not isinstance(payload, dict):
                raise ValueError("Mutation payload is not an object")
            if record["kind"] == "resource_put":
                self._resource_path(payload["collection"], payload["resource"])
            elif record["kind"] == "output_set":
                marker = payload["marker"]
                self.attempt_path(
                    marker["run_id"], marker["task_id"], marker["attempt_id"]
                )
                if (
                    marker["schema_version"] != 1
                    or marker["project_id"] != self.project_id
                    or marker["acceptance_sequence"] != record["sequence"]
                ):
                    raise ValueError("Output-set identity/schema/sequence mismatch")
                if set(marker["outputs"]) != set(payload["artifacts"]):
                    raise ValueError("Output-set named artifact bindings mismatch")
                for name, descriptor in payload["artifacts"].items():
                    self._resource_path("artifacts", descriptor)
                    binding = marker["outputs"][name]
                    if binding["artifact_id"] != descriptor["artifact_id"] or binding[
                        "descriptor_sha256"
                    ] != digest(descriptor):
                        raise ValueError("Committed descriptor digest mismatch")
                    producer = descriptor["producer"]
                    if (
                        any(
                            producer[key] != marker[key]
                            for key in ("run_id", "task_id", "attempt_id")
                        )
                        or producer["output_name"] != name
                    ):
                        raise ValueError("Committed artifact producer mismatch")
                validate_json(marker["parameters"])
            elif record["kind"] == "stop_intent":
                self._resource_path("runs", {"run_id": payload["run_id"]})
            elif record["kind"] == "file_snapshot":
                self._path(payload["path"])
                source = base64.b64decode(payload["base64"], validate=True)
                if hashlib.sha256(source).hexdigest() != payload["sha256"]:
                    raise ValueError("File snapshot digest mismatch")
            elif record.get("event_kind") == "pipeline_registration":
                from .definitions import load_definition

                resources = payload["resources"]
                if not isinstance(resources, list) or len(resources) < 2:
                    raise ValueError("Registration resources are missing")
                for mutation in self._registration_records(record):
                    self._validate_record(mutation)
                catalog = resources[0]["resource"]
                definition = resources[1]["resource"]
                if (
                    resources[0]["collection"] != "pipelines"
                    or resources[1]["collection"] != "definitions"
                    or catalog["definition_id"] != definition["definition_id"]
                    or catalog["pipeline_id"] != definition["pipeline_id"]
                    or definition["definition_id"] not in catalog["version_ids"]
                    or catalog.get("default_version_id") != definition["definition_id"]
                    or hashlib.sha256(
                        definition["source_text"].encode("utf-8")
                    ).hexdigest()
                    != definition["sha256"]
                    or payload["source"]["sha256"] != definition["sha256"]
                    or payload["source"]["path"]
                    != f"definitions/{definition['definition_id']}/source.yaml"
                ):
                    raise ValueError("Registration association mismatch")
                if {
                    item["resource"]["name"]: item["resource"]["component_id"]
                    for item in resources[2:]
                    if item["collection"] == "components"
                    and item["resource"]["definition_id"] == definition["definition_id"]
                } != definition["component_ids"] or any(
                    item["collection"] != "components" for item in resources[2:]
                ):
                    raise ValueError("Embedded component association mismatch")
                parsed = load_definition(definition["source_text"])
                if parsed.document != definition["pipeline_spec"]:
                    raise ValueError("Registered source and parsed pipeline differ")
                compiled = parsed.document.get("components", {}) or {
                    "root": parsed.root
                }
                executors = parsed.document.get("deploymentSpec", {}).get(
                    "executors", {}
                )
                if set(compiled) != set(definition["component_ids"]):
                    raise ValueError(
                        "Registered component keys differ from compiled source"
                    )
                for item in resources[2:]:
                    component = item["resource"]
                    original = compiled[component["name"]]
                    if component["compiled"] != original or component[
                        "executor"
                    ] != executors.get(original.get("executorLabel")):
                        raise ValueError(
                            "Registered component contract/executor differs from compiled source"
                        )
        except (KeyError, TypeError, ValueError) as exc:
            raise DockflowError(
                f"Invalid accepted mutation {record['sequence']}: {exc}",
                code="CONFLICT",
                status=409,
            ) from exc

    def append(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.require_owner()
        validate_json(payload)
        with self._mutex:
            record = {
                "schema_version": 1,
                "kind": kind
                if kind
                in {
                    "resource_put",
                    "output_set",
                    "stop_intent",
                    "cleanup",
                    "file_snapshot",
                }
                else "event",
                "event_kind": kind,
                "project_id": self.project_id,
                "sequence": self._sequence + 1,
                "timestamp": utc_now(),
                "payload": payload,
            }
            self._validate_record(record)
            atomic_write(
                self.state / "records" / f"{record['sequence']:020d}.json",
                json_bytes(record),
                exclusive=True,
            )
            self._sequence = record["sequence"]
            self._project(record)
            return record

    def _resource_path(self, collection: str, resource: dict[str, Any]) -> Path:
        kind = COLLECTIONS.get(collection)
        if kind is None:
            raise DockflowError(f"Unknown resource collection: {collection}")
        public_id = resource.get(f"{kind}_id", "")
        for field_kind in COLLECTIONS.values():
            value = resource.get(f"{field_kind}_id")
            if value is None and field_kind != kind:
                continue
            if not isinstance(value, str) or not re.fullmatch(
                rf"{field_kind}_[0-9a-f]{{8}}-[0-9a-f]{{4}}-4[0-9a-f]{{3}}-[89ab][0-9a-f]{{3}}-[0-9a-f]{{12}}",
                value,
            ):
                raise DockflowError(
                    f"Invalid {field_kind} public ID", code="INVALID_ARGUMENT"
                )
        if (
            resource.get("project_id", self.project_id) != self.project_id
            or resource.get("schema_version", 1) != 1
        ):
            raise DockflowError(
                "Resource project or schema mismatch", code="CONFLICT", status=409
            )
        # Canonical top-level query projections coexist with the specified nested
        # Run/Task/Attempt layout. Both are rebuilt from the same accepted journal.
        if collection == "runs":
            return Path("runs") / public_id / "run.json"
        if collection == "definitions":
            return Path("definitions") / public_id / "definition.json"
        return Path(collection) / f"{public_id}.json"

    def put(self, collection: str, resource: dict[str, Any]) -> dict[str, Any]:
        self.require_owner()
        value = {
            "schema_version": 1,
            "kind": COLLECTIONS[collection],
            "project_id": self.project_id,
            **resource,
        }
        if value["project_id"] != self.project_id or value["schema_version"] != 1:
            raise DockflowError(
                "Resource project or schema mismatch", code="CONFLICT", status=409
            )
        self._resource_path(collection, value)
        path = self._path(self._resource_path(collection, value))
        if collection in {"definitions", "components"} and path.exists():
            previous = self.read(path.relative_to(self.state))
            parent = (
                previous
                if collection == "definitions"
                else self.get("definitions", previous["definition_id"])
                if previous.get("definition_id")
                else {}
            )
            if parent.get("registration_origin") == "api" and previous != value:
                raise DockflowError(
                    "Uploaded versions and embedded components are immutable",
                    "CONFLICT",
                    409,
                )
        with self._mutex:
            pending_reconciliation = self.reconciliation_required
            record = self.append(
                "resource_put", {"collection": collection, "resource": value}
            )
            try:
                if self.index:
                    self.index.put(collection, value)
                    self.write(
                        "index-status.json",
                        {
                            "schema_version": 1,
                            "project_id": self.project_id,
                            "sequence": record["sequence"],
                            "reconciliation_required": pending_reconciliation,
                        },
                    )
            except Exception as exc:
                self.write(
                    "index-status.json",
                    {
                        "schema_version": 1,
                        "project_id": self.project_id,
                        "sequence": record["sequence"],
                        "reconciliation_required": True,
                    },
                )
                raise DockflowError(
                    f"Mutation accepted at sequence {record['sequence']}; MLMD reconciliation required. Do not repeat the computation.",
                    code="UNAVAILABLE",
                    status=503,
                ) from exc
        return value

    @staticmethod
    def _registration_records(record: dict[str, Any]) -> list[dict[str, Any]]:
        """Expand one accepted registration for projection and integrity checks."""
        if record.get("event_kind") != "pipeline_registration":
            return [record]
        return [
            {
                **record,
                "kind": "resource_put",
                "event_kind": "resource_put",
                "payload": mutation,
            }
            for mutation in record["payload"]["resources"]
        ] + [
            {
                **record,
                "kind": "file_snapshot",
                "event_kind": "file_snapshot",
                "payload": record["payload"]["source"],
            }
        ]

    def commit_registration(
        self, catalog: dict, definition: dict, components: list[dict], source: bytes
    ) -> dict:
        """Accept a whole registration once; replay never exposes a partial version."""
        self.require_owner()
        self.ensure_reconciled()
        for collection, resource in [
            ("definitions", definition),
            *(("components", item) for item in components),
        ]:
            if self._path(self._resource_path(collection, resource)).exists():
                raise DockflowError(
                    "Registration requires fresh version/component IDs", "CONFLICT", 409
                )
        resources = [
            {
                "collection": collection,
                "resource": {
                    "schema_version": 1,
                    "kind": COLLECTIONS[collection],
                    "project_id": self.project_id,
                    **resource,
                },
            }
            for collection, resource in [
                ("pipelines", catalog),
                ("definitions", definition),
                *(("components", component) for component in components),
            ]
        ]
        payload = {
            "resources": resources,
            "source": {
                "path": f"definitions/{definition['definition_id']}/source.yaml",
                "base64": base64.b64encode(source).decode("ascii"),
                "sha256": hashlib.sha256(source).hexdigest(),
            },
        }
        with self._mutex:
            # The durable event is the acceptance boundary. Both projection and
            # MLMD may be reconstructed from it after a process interruption.
            sequence = self._sequence
            try:
                self.append("pipeline_registration", payload)
                if self.index:
                    for mutation in resources:
                        self.index.put(mutation["collection"], mutation["resource"])
            except Exception as exc:
                if self._sequence == sequence:
                    raise
                self.write(
                    "index-status.json",
                    {
                        "schema_version": 1,
                        "project_id": self.project_id,
                        "sequence": self._sequence,
                        "reconciliation_required": True,
                    },
                )
                raise DockflowError(
                    f"Registration accepted: pipeline_id={catalog['pipeline_id']}, "
                    f"pipeline_version_id={definition['definition_id']}; "
                    "Control/index reconciliation required. Do not upload again.",
                    code="UNAVAILABLE",
                    status=503,
                ) from exc
        return resources[1]["resource"]

    def _project(self, record: dict[str, Any]) -> None:
        payload = record["payload"]
        if record.get("event_kind") == "pipeline_registration":
            for mutation in self._registration_records(record):
                self._project(mutation)
        elif record["kind"] == "resource_put":
            collection, resource = payload["collection"], payload["resource"]
            path = self._resource_path(collection, resource)
            atomic_write(self._path(path), json_bytes(resource))
            if collection == "tasks" and resource.get("run_id"):
                atomic_write(
                    self.state
                    / "runs"
                    / resource["run_id"]
                    / "tasks"
                    / resource["task_id"]
                    / "task.json",
                    json_bytes(resource),
                )
            elif (
                collection == "attempts"
                and resource.get("run_id")
                and resource.get("task_id")
            ):
                atomic_write(
                    self.attempt_path(
                        resource["run_id"], resource["task_id"], resource["attempt_id"]
                    )
                    / "execution.json",
                    json_bytes(resource),
                )
        elif record["kind"] == "output_set":
            marker = payload["marker"]
            atomic_write(
                self.attempt_path(
                    marker["run_id"], marker["task_id"], marker["attempt_id"]
                )
                / "output-set.json",
                json_bytes(marker),
                exclusive=True,
            )
            for descriptor in payload["artifacts"].values():
                atomic_write(
                    self._path(self._resource_path("artifacts", descriptor)),
                    json_bytes(descriptor),
                )
        elif record["kind"] == "file_snapshot":
            try:
                source = base64.b64decode(payload["base64"], validate=True)
            except (ValueError, KeyError) as exc:
                raise DockflowError(
                    "Invalid accepted file snapshot", code="CONFLICT", status=409
                ) from exc
            if hashlib.sha256(source).hexdigest() != payload["sha256"]:
                raise DockflowError(
                    "Accepted file snapshot digest mismatch",
                    code="CONFLICT",
                    status=409,
                )
            atomic_write(self._path(payload["path"]), source, exclusive=True)
        elif record.get("event_kind") == "log":
            if payload.get("attempt_id"):
                directory = (
                    self.attempt_path(
                        payload["run_id"], payload["task_id"], payload["attempt_id"]
                    )
                    / "logs"
                )
            else:
                directory = self.state / "runs" / payload["run_id"] / "logs"
            atomic_write(
                directory / f"{record['sequence']:020d}.json",
                json_bytes({**payload, "sequence": record["sequence"]}),
                exclusive=True,
            )

    def get(self, collection: str, public_id: str) -> dict[str, Any]:
        kind = COLLECTIONS.get(collection)
        if kind is None:
            raise DockflowError(f"Unknown resource collection: {collection}")
        return self.read(self._resource_path(collection, {f"{kind}_id": public_id}))

    def list(self, collection: str) -> list[dict[str, Any]]:
        if collection not in COLLECTIONS:
            raise DockflowError(f"Unknown resource collection: {collection}")
        if self.index:
            return self.index.list(collection)
        pattern = (
            "*/run.json"
            if collection == "runs"
            else "*/definition.json"
            if collection == "definitions"
            else "*.json"
        )
        return [
            self.read(path.relative_to(self.state))
            for path in sorted((self.state / collection).glob(pattern))
        ]

    def attempt_path(self, run_id: str, task_id: str, attempt_id: str) -> Path:
        for collection, value in (
            ("runs", run_id),
            ("tasks", task_id),
            ("attempts", attempt_id),
        ):
            self._resource_path(collection, {f"{COLLECTIONS[collection]}_id": value})
        return (
            self.state / "runs" / run_id / "tasks" / task_id / "attempts" / attempt_id
        )

    def commit_output_set(
        self,
        run_id: str,
        task_id: str,
        attempt_id: str,
        artifacts: dict[str, dict[str, Any]],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        self.require_owner()
        with self._mutex:
            marker_path = (
                self.attempt_path(run_id, task_id, attempt_id) / "output-set.json"
            )
            if marker_path.exists():
                marker = self.read(marker_path.relative_to(self.state))
                accepted = [
                    record["payload"]["marker"]
                    for record in self.records()
                    if record["kind"] == "output_set"
                    and record["payload"]["marker"]["attempt_id"] == attempt_id
                ]
                if accepted != [marker]:
                    raise DockflowError(
                        "Output-set marker differs from accepted history",
                        code="CONFLICT",
                        status=409,
                    )
                return marker
            stopped = any(
                record["kind"] == "stop_intent"
                and record["payload"].get("run_id") == run_id
                for record in self.records()
            )
            run = self.get("runs", run_id)
            if (
                stopped
                or run.get("stop_intent")
                or run.get("cancellation_requested")
                or run.get("interruption_requested")
                or run.get("state") in {"cancelling", "cancelled", "interrupted"}
            ):
                raise DockflowError(
                    "Stop intent prevents a new output-set commit",
                    code="CONFLICT",
                    status=409,
                )
            published_at = utc_now()
            artifact_ids = [item["artifact_id"] for item in artifacts.values()]
            if len(set(artifact_ids)) != len(artifact_ids):
                raise DockflowError(
                    "Each produced output requires a distinct artifact ID",
                    code="CONFLICT",
                    status=409,
                )
            for descriptor in artifacts.values():
                if (
                    descriptor != self.get("artifacts", descriptor["artifact_id"])
                    or descriptor.get("publication_state") != "staged"
                ):
                    raise DockflowError(
                        "Output descriptor differs from its durable staged snapshot",
                        code="CONFLICT",
                        status=409,
                    )
            committed = {
                name: {
                    **descriptor,
                    "publication_state": "committed",
                    "published_at": published_at,
                }
                for name, descriptor in artifacts.items()
            }
            marker = {
                "schema_version": 1,
                "kind": "output_set",
                "project_id": self.project_id,
                "run_id": run_id,
                "task_id": task_id,
                "attempt_id": attempt_id,
                "outputs": {
                    name: {
                        "artifact_id": descriptor["artifact_id"],
                        "descriptor_sha256": digest(descriptor),
                    }
                    for name, descriptor in committed.items()
                },
                "parameters": parameters,
                "acceptance_sequence": self._sequence + 1,
                "published_at": published_at,
            }
            self.append("output_set", {"marker": marker, "artifacts": committed})
            if self.index:
                try:
                    for descriptor in committed.values():
                        self.index.put("artifacts", descriptor)
                except Exception as exc:
                    self.write(
                        "index-status.json",
                        {
                            "schema_version": 1,
                            "project_id": self.project_id,
                            "reconciliation_required": True,
                            "sequence": marker["acceptance_sequence"],
                        },
                    )
                    raise DockflowError(
                        f"Output set committed for {attempt_id}; MLMD reconciliation required",
                        code="UNAVAILABLE",
                        status=503,
                    ) from exc
            return marker

    def verify_output_set(self, attempt_id: str) -> dict[str, Any]:
        """Verify the original committed snapshot independently of mutable pins."""
        try:
            attempt = self.get("attempts", attempt_id)
            accepted = [
                record["payload"]
                for record in self.records()
                if record["kind"] == "output_set"
                and record["payload"]["marker"]["attempt_id"] == attempt_id
            ]
            if len(accepted) != 1:
                return {
                    "valid": False,
                    "reason": "Attempt has no unique accepted output-set commit",
                }
            payload = accepted[0]
            marker = payload["marker"]
            actual = self.read(
                (
                    self.attempt_path(marker["run_id"], marker["task_id"], attempt_id)
                    / "output-set.json"
                ).relative_to(self.state)
            )
            if actual != marker:
                return {
                    "valid": False,
                    "reason": "Output-set marker differs from accepted snapshot",
                }
            outputs = {
                name: binding["artifact_id"]
                for name, binding in marker["outputs"].items()
            }
            if (
                attempt.get("outputs", {}) != outputs
                or attempt.get("output_parameters", {}) != marker["parameters"]
            ):
                return {
                    "valid": False,
                    "reason": "Attempt output bindings differ from committed snapshot",
                }
            for name, snapshot in payload["artifacts"].items():
                descriptor = self.get("artifacts", snapshot["artifact_id"])
                ignored = {"pinned", "availability", "availability_observed_at"}
                if {
                    key: value
                    for key, value in descriptor.items()
                    if key not in ignored
                } != {
                    key: value for key, value in snapshot.items() if key not in ignored
                }:
                    return {
                        "valid": False,
                        "reason": f"Committed output descriptor differs for {name}",
                    }
            return {"valid": True, "reason": None, "marker": marker}
        except DockflowError as exc:
            return {"valid": False, "reason": str(exc)}

    def reconcile_index(self) -> None:
        self.require_owner()
        if self.index is None:
            return
        # Replay current resources, preserving original producer references.
        for collection in (
            "pipelines",
            "components",
            "definitions",
            "experiments",
            "runs",
            "tasks",
            "artifacts",
            "attempts",
        ):
            pattern = (
                "*/run.json"
                if collection == "runs"
                else "*/definition.json"
                if collection == "definitions"
                else "*.json"
            )
            for path in sorted((self.state / collection).glob(pattern)):
                self.index.put(collection, self.read(path.relative_to(self.state)))
        self.write(
            "index-status.json",
            {
                "schema_version": 1,
                "project_id": self.project_id,
                "sequence": len(self.records()),
                "reconciliation_required": False,
            },
        )

    def check(
        self, verify_contents: bool = False, artifacts: Any = None
    ) -> dict[str, Any]:
        errors: list[dict[str, Any]] = []
        try:
            accepted_sequence = len(self.records())
            records = [
                mutation
                for record in self.records()
                for mutation in self._registration_records(record)
            ]
        except DockflowError as exc:
            return {
                "valid": False,
                "errors": [{"reason": str(exc)}],
                "content_verified": False,
            }
        accepted: dict[tuple[str, str], dict[str, Any]] = {}
        for record in records:
            if record["kind"] == "resource_put":
                resource = record["payload"]["resource"]
                collection = record["payload"]["collection"]
                accepted[(collection, resource[f"{COLLECTIONS[collection]}_id"])] = (
                    resource
                )
            elif record["kind"] == "output_set":
                marker = record["payload"]["marker"]
                try:
                    actual = self.read(
                        (
                            self.attempt_path(
                                marker["run_id"],
                                marker["task_id"],
                                marker["attempt_id"],
                            )
                            / "output-set.json"
                        ).relative_to(self.state)
                    )
                    if actual != marker:
                        errors.append(
                            {
                                "attempt_id": marker["attempt_id"],
                                "reason": "Output-set projection differs from accepted record",
                            }
                        )
                except DockflowError as exc:
                    errors.append(
                        {"attempt_id": marker["attempt_id"], "reason": str(exc)}
                    )
                for resource in record["payload"]["artifacts"].values():
                    accepted[("artifacts", resource["artifact_id"])] = resource
            elif record["kind"] == "file_snapshot":
                try:
                    actual_digest = hashlib.sha256(
                        self._path(record["payload"]["path"]).read_bytes()
                    ).hexdigest()
                    if actual_digest != record["payload"]["sha256"]:
                        errors.append(
                            {
                                "path": record["payload"]["path"],
                                "reason": "Accepted source snapshot digest mismatch",
                            }
                        )
                except OSError:
                    errors.append(
                        {
                            "path": record["payload"]["path"],
                            "reason": "Accepted source snapshot is missing or inaccessible",
                        }
                    )
        for record in records:
            if record["kind"] == "output_set":
                marker = record["payload"]["marker"]
                for collection, field in (
                    ("runs", "run_id"),
                    ("tasks", "task_id"),
                    ("attempts", "attempt_id"),
                ):
                    if (collection, marker[field]) not in accepted:
                        errors.append(
                            {
                                "resource_id": marker[field],
                                "reason": "Committed output set is missing an indispensable execution record",
                            }
                        )
        for (collection, public_id), resource in accepted.items():
            try:
                if self.get(collection, public_id) != resource:
                    errors.append(
                        {
                            "resource_id": public_id,
                            "reason": "Projection differs from accepted history",
                        }
                    )
            except DockflowError as exc:
                errors.append({"resource_id": public_id, "reason": str(exc)})
        if self.index:
            for collection in COLLECTIONS:
                indexed = {
                    item[f"{COLLECTIONS[collection]}_id"]: item
                    for item in self.index.list(collection)
                }
                for (kind, public_id), resource in accepted.items():
                    if kind == collection and indexed.get(public_id) != resource:
                        errors.append(
                            {
                                "resource_id": public_id,
                                "reason": "MLMD index differs from accepted history",
                            }
                        )
        availability = []
        if artifacts:
            availability = [
                artifacts.verify(public_id, verify_contents=verify_contents)
                for collection, public_id in accepted
                if collection == "artifacts"
            ]
        return {
            "valid": not errors,
            "project_id": self.project_id,
            "accepted_sequence": accepted_sequence,
            "errors": errors,
            "index_checked": self.index is not None,
            "content_verified": verify_contents and artifacts is not None,
            "availability": availability,
        }

    def rebuild(self, apply: bool = False) -> dict[str, Any]:
        records = self.records()
        report = {
            "project_id": self.project_id,
            "state_directory": str(self.state),
            "records": len(records),
            "apply": apply,
            "offline_required": True,
        }
        if not apply:
            return report
        self.require_owner()
        active = [
            run
            for run in self.list("runs")
            if run.get("state") not in TERMINAL and run.get("state") != "queued"
        ]
        if active:
            raise DockflowError(
                "Resolve active or uncertain executions before offline rebuild",
                code="CONFLICT",
                status=409,
            )
        required: set[tuple[str, str]] = set()
        present: set[tuple[str, str]] = set()
        for record in [
            mutation
            for accepted_record in records
            for mutation in self._registration_records(accepted_record)
        ]:
            if record["kind"] == "resource_put":
                collection = record["payload"]["collection"]
                present.add(
                    (
                        collection,
                        record["payload"]["resource"][f"{COLLECTIONS[collection]}_id"],
                    )
                )
            elif record["kind"] == "output_set":
                marker = record["payload"]["marker"]
                required.update(
                    (collection, marker[field])
                    for collection, field in (
                        ("runs", "run_id"),
                        ("tasks", "task_id"),
                        ("attempts", "attempt_id"),
                    )
                )
        if required - present:
            raise DockflowError(
                "Rebuild cannot invent missing committed execution records",
                code="CONFLICT",
                status=409,
            )
        # Refuse contradictory/missing authoritative marker records before replacing
        # an existing index; projections themselves are deliberately reconstructible.
        path = self.metadata_directory / "mlmd.sqlite"
        backup = path.with_name(f"mlmd.backup-{uuid.uuid4().hex}.sqlite")
        self.index = None
        backup_format = "sqlite"
        if path.exists():
            try:
                with (
                    sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as source,
                    sqlite3.connect(backup) as target,
                ):
                    source.backup(target)
            except sqlite3.DatabaseError:
                backup.unlink(missing_ok=True)
                backup = path.with_name(f"mlmd.corrupt-backup-{uuid.uuid4().hex}")
                backup.mkdir()
                for candidate in (
                    path,
                    *(
                        path.with_name(path.name + suffix)
                        for suffix in ("-wal", "-shm", "-journal")
                    ),
                ):
                    if candidate.exists():
                        shutil.copy2(candidate, backup / candidate.name)
                backup_format = "raw-corrupt-index"
        temporary = path.with_name(f"mlmd.rebuild-{uuid.uuid4().hex}.sqlite")
        retired = path.with_name(f"mlmd.retired-{uuid.uuid4().hex}")
        try:
            self.index = MLMDIndex(temporary, self.project_id)
            for record in records:
                self._project(record)
            self.reconcile_index()
            self.index = None
            retired.mkdir()
            for candidate in (
                path,
                *(
                    path.with_name(path.name + suffix)
                    for suffix in ("-wal", "-shm", "-journal")
                ),
            ):
                if candidate.exists():
                    os.replace(candidate, retired / candidate.name)
            try:
                os.replace(temporary, path)
                _fsync_directory(path.parent)
                self.index = MLMDIndex(path, self.project_id)
            except Exception:
                self.index = None
                for candidate in retired.iterdir():
                    os.replace(candidate, path.parent / candidate.name)
                raise
        except Exception:
            self.write(
                "index-status.json",
                {
                    "schema_version": 1,
                    "project_id": self.project_id,
                    "sequence": self._sequence,
                    "reconciliation_required": True,
                },
            )
            raise
        return {
            **report,
            "backup": str(backup) if backup.exists() else None,
            "backup_format": backup_format,
            "retired_index": str(retired),
            "rebuilt": True,
        }

    def clean(self, work_directory: Path, apply: bool = False) -> dict[str, Any]:
        root = Path(work_directory).resolve()
        protected: list[str] = []
        candidates: list[str] = []
        for run in self.list("runs"):
            run_id = run["run_id"]
            for candidate in (root / "runs" / run_id, root / "workspaces" / run_id):
                if not candidate.exists():
                    continue
                if run.get("state") not in TERMINAL:
                    protected.append(str(candidate))
                elif candidate.is_symlink() or not candidate.resolve().is_relative_to(
                    root
                ):
                    protected.append(str(candidate))
                else:
                    candidates.append(str(candidate))
        if apply:
            self.require_owner()
            if any(run.get("state") not in TERMINAL for run in self.list("runs")):
                raise DockflowError(
                    "Cleanup requires idle ownership", code="CONFLICT", status=409
                )
            for candidate in candidates:
                shutil.rmtree(candidate)
            self.append("cleanup", {"deleted": candidates, "work_directory": str(root)})
        return {
            "project_id": self.project_id,
            "state_directory": str(self.state),
            "work_directory": str(root),
            "apply": apply,
            "candidates": candidates,
            "protected": protected,
            "deleted_count": len(candidates) if apply else 0,
        }

    def backup(self, destination: Path, artifacts: Any) -> dict[str, Any]:
        """Make an offline, owner-exclusive snapshot with all managed contents.

        Restore targets the original configured roots; URI relocation is a
        separate migration. External reference contents are deliberately excluded.
        """
        self.require_owner()
        with self._mutex:
            if any(
                run.get("state") not in TERMINAL | {"queued"}
                for run in self.list("runs")
            ):
                raise DockflowError(
                    "Backup requires resolved, idle execution ownership",
                    code="CONFLICT",
                    status=409,
                )
            records = self.records()
            check = self.check()
            if not check["valid"]:
                raise DockflowError(
                    "Control history must pass metadata check before backup",
                    code="CONFLICT",
                    status=409,
                )
            for descriptor in artifacts.list():
                if (
                    descriptor.get("ownership") == "managed"
                    and artifacts.verify(descriptor["artifact_id"])["availability"]
                    != "available"
                ):
                    raise DockflowError(
                        "Managed contents must be available and intact before backup",
                        code="CONFLICT",
                        status=409,
                    )
            destination = Path(destination).absolute()
            roots = [
                self.state.resolve(),
                self.metadata_directory.resolve(),
            ]
            if artifacts.backend == "filesystem":
                roots.append(
                    Path(
                        artifacts.options.get("root", artifacts.managed_root)
                    ).resolve()
                )
            if destination.exists() or any(
                destination.resolve().is_relative_to(root) for root in roots
            ):
                raise DockflowError(
                    "Backup destination must be a new path outside state, metadata and artifact roots"
                )
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(
                f".{destination.name}.staging-{uuid.uuid4().hex}"
            )
            temporary.mkdir()
            try:
                shutil.copytree(
                    self.state,
                    temporary / "control",
                    ignore=shutil.ignore_patterns(
                        "owner.lock",
                        "mlmd.sqlite",
                        "mlmd.sqlite-wal",
                        "mlmd.sqlite-shm",
                    ),
                    symlinks=False,
                )
                database = self.metadata_directory / "mlmd.sqlite"
                if database.exists():
                    (temporary / "index").mkdir()
                    with (
                        sqlite3.connect(database) as source,
                        sqlite3.connect(temporary / "index" / "mlmd.sqlite") as target,
                    ):
                        source.backup(target)
                if artifacts.backend == "filesystem":
                    managed = artifacts.managed_root
                    if managed.exists():
                        # inventory validates links and special files before copying.
                        from .artifacts import inventory

                        inventory(managed)
                        shutil.copytree(managed, temporary / "managed", symlinks=False)
                else:
                    for descriptor in artifacts.list():
                        if descriptor["ownership"] != "managed":
                            continue
                        folder = temporary / "managed" / descriptor["artifact_id"]
                        folder.mkdir(parents=True)
                        if descriptor["payload_kind"] != "metadata":
                            artifacts._download_descriptor(
                                descriptor, folder / "payload"
                            )
                        atomic_write(folder / "artifact.json", json_bytes(descriptor))
                from .artifacts import inventory

                snapshot = inventory(temporary)
                manifest = {
                    "schema_version": 1,
                    "kind": "backup",
                    "project_id": self.project_id,
                    "accepted_sequence": len(records),
                    "created_at": utc_now(),
                    "state_directory": str(self.state),
                    "metadata_directory": str(self.metadata_directory),
                    "artifacts_backend": artifacts.backend,
                    "artifacts_root": str(artifacts.options["root"])
                    if artifacts.backend == "filesystem" and "root" in artifacts.options
                    else None,
                    "managed_root": str(artifacts.managed_root)
                    if artifacts.backend == "filesystem"
                    else None,
                    "artifact_bucket": artifacts.options.get("bucket"),
                    "artifact_prefix": artifacts.options.get("prefix", ""),
                    "external_references_included": False,
                    "snapshot": snapshot,
                }
                atomic_write(temporary / "backup.json", json_bytes(manifest))
                for directory, _, files in os.walk(temporary, topdown=False):
                    for name in files:
                        with (Path(directory) / name).open("rb") as stream:
                            os.fsync(stream.fileno())
                    _fsync_directory(Path(directory))
                os.rename(temporary, destination)
                _fsync_directory(destination.parent)
                return {"destination": str(destination), **manifest}
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)

    @staticmethod
    def verify_backup(source: Path) -> dict[str, Any]:
        from .artifacts import inventory

        source = Path(source)
        manifest = loads((source / "backup.json").read_bytes())
        if manifest.get("schema_version") != 1 or manifest.get("kind") != "backup":
            raise DockflowError(
                "Unsupported backup schema", code="CONFLICT", status=409
            )
        observed = inventory(source)
        entries = [
            entry for entry in observed["inventory"] if entry["path"] != "backup.json"
        ]
        expected = manifest["snapshot"]
        if (
            entries != expected["inventory"]
            or digest({"kind": "directory", "entries": entries})
            != expected["fingerprint"]["value"]
        ):
            raise DockflowError(
                "Backup contents differ from their recorded inventory",
                code="CONFLICT",
                status=409,
            )
        return {
            "valid": True,
            "project_id": manifest["project_id"],
            "accepted_sequence": manifest["accepted_sequence"],
            "external_references_included": False,
        }

    new_id = staticmethod(new_id)
    record = put
