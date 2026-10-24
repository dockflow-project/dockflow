"""Authoritative control records, durable commits, replay and recovery.

SQL transactions and execution ownership are delegated to a database adapter. ControlStore
retains their coordination boundary and the accepted-record transaction order.
"""

from __future__ import annotations

import base64
import contextlib
import functools
import hashlib
import os
import re
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any

from dockflow_database.errors import DockflowError

from .canonical import digest, json_bytes, loads, validate_json
from .lifecycle import merge_run, terminal_task
from .projections import DOMAINS, expected_rows, project_record
from .records import COLLECTIONS, TERMINAL, utc_now
from .state_database import StateDatabase


def _fsync_directory(path: Path) -> None:
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def atomic_write(path: Path, data: bytes) -> None:
    """Write and sync a backup manifest on the destination filesystem."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _project_mutation(method):
    @functools.wraps(method)
    def serialized(self, *args, **kwargs):
        with self._mutex, self.database.transaction():
            return method(self, *args, **kwargs)

    return serialized


def _maintenance_operation(method):
    @functools.wraps(method)
    def exclusive(self, *args, **kwargs):
        with self.database.maintenance():
            return method(self, *args, **kwargs)

    return exclusive


class ControlStore:
    def __init__(
        self,
        state: Path,
        project_id: str,
        *,
        storage: dict | None = None,
    ):
        self.state = Path(state).absolute()
        self.project_id = project_id
        self.database = StateDatabase(
            storage
            or {"backend": "sqlite", "database": str(self.state / "state.sqlite")},
            project_id,
        )
        self._owner_guard = threading.Lock()
        self._owner_depth = 0
        self._mutex = self.database.mutex

    @property
    def reconciliation_required(self) -> bool:
        status = self.project_metadata("reconciliation") or {}
        return self.database.poisoned or bool(status.get("reconciliation_required"))

    def ensure_reconciled(self) -> None:
        if self.reconciliation_required:
            raise DockflowError(
                "Accepted control state requires SQL projection reconciliation before dispatch",
                "UNAVAILABLE",
                503,
            )

    def project_metadata(self, name: str) -> dict | None:
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", name):
            raise DockflowError("Invalid project metadata name")
        return self.database.project_metadata(name)

    def set_project_metadata(self, name: str, value: dict, *, immutable=False) -> None:
        self.require_owner()
        self.project_metadata(name)
        self.database.set_project_metadata(name, value, immutable=immutable)

    def has_resource(self, collection: str, public_id: str) -> bool:
        self._validate_resource(
            collection, {f"{COLLECTIONS.get(collection, '')}_id": public_id}
        )
        return self.database.resource(collection, public_id) is not None

    def output_set(self, attempt_id: str) -> dict | None:
        self._validate_resource("attempts", {"attempt_id": attempt_id})
        return self.database.output_set(attempt_id)

    def has_output_set(self, attempt_id: str) -> bool:
        return self.output_set(attempt_id) is not None

    def definition_source(self, definition_id: str) -> bytes:
        self._validate_resource("definitions", {"definition_id": definition_id})
        return self.database.definition_source(definition_id)

    def attempt_log_snapshot(self, attempt_id: str, stream: str) -> bytes:
        self._validate_resource("attempts", {"attempt_id": attempt_id})
        if stream not in {"stdout", "stderr"}:
            raise DockflowError("Invalid retained log stream")
        return self.database.log_snapshot(attempt_id, stream)

    def snapshot_attempt_log(
        self, run_id: str, task_id: str, attempt_id: str, stream: str, source: bytes
    ) -> None:
        self.append(
            "attempt_log_snapshot",
            {
                "run_id": run_id,
                "task_id": task_id,
                "attempt_id": attempt_id,
                "stream": stream,
                "base64": base64.b64encode(source).decode("ascii"),
                "sha256": hashlib.sha256(source).hexdigest(),
            },
        )

    def require_owner(self) -> None:
        self.database.require_owner()

    @contextlib.contextmanager
    def owner(self, endpoint: str | None = None, *, exclusive: bool = False):
        """Database execution ownership; diagnostics never authorize takeover.

        Nested contexts on this shared coordinator retain the same acquisition,
        including across threads. The last context releases its stable lock inode.
        """
        with self._owner_guard:
            if not self.database.held:
                if (self.state / "project.json").exists() or (
                    self.state / "records"
                ).exists():
                    raise DockflowError(
                        "Legacy file-backed history is unsupported; select a fresh state directory",
                        "CONFLICT",
                        409,
                    )
                self.database.acquire(endpoint, exclusive=exclusive)
                try:
                    self.records()
                except BaseException:
                    self.database.release()
                    raise
            if exclusive and not self.database.exclusive:
                raise DockflowError(
                    "Exclusive ownership must be acquired before nesting",
                    "CONFLICT",
                    409,
                )
            self._owner_depth += 1
        try:
            yield self
        finally:
            with self._owner_guard:
                self._owner_depth -= 1
                if self._owner_depth == 0:
                    self.database.release()

    def run_owner(self, run_id, execution=None, *, recovering=False):
        from .run_ownership import owned_run

        execution = execution or {}
        return owned_run(
            self,
            run_id,
            execution.get("run_lease_seconds", 120.0),
            execution.get("run_heartbeat_seconds", 30.0),
            recovering=recovering,
        )

    def check_execution(self):
        if not self.database.adapter.concurrent_runs:
            return None
        try:
            with self.database.transaction():
                if self.database.run_claim is None:
                    raise DockflowError(
                        "Run execution requires a Run claim", "OWNERSHIP_LOST", 409
                    )
            return None
        except DockflowError:
            return "ownership_lost"

    @contextlib.contextmanager
    def stop_request(self, run_id):
        previous = getattr(self.database.local, "control_run", None)
        self.database.local.control_run = run_id
        try:
            with self.database.transaction():
                yield
        finally:
            self.database.local.control_run = previous

    def _guard_execution(self, kind, payload):
        if not self.database.adapter.concurrent_runs:
            return
        resource = payload.get("resource", {})
        claim = self.database.run_claim
        if (
            claim is not None
            and kind == "resource_put"
            and payload.get("collection") in {"tasks", "attempts"}
            and not resource.get("run_id")
        ):
            raise DockflowError(
                "Execution resources require their owning Run", "CONFLICT", 409
            )
        run_id = (
            payload.get("run_id")
            or resource.get("run_id")
            or payload.get("marker", {}).get("run_id")
        )
        if not run_id:
            return
        claim = self.database.run_claim
        if claim is not None:
            if run_id != claim.run_id:
                raise DockflowError(
                    "Run owner cannot mutate another Run", "CONFLICT", 409
                )
            return
        control = getattr(self.database.local, "control_run", None)
        if control == run_id and (
            kind == "stop_intent"
            or (kind == "resource_put" and payload.get("collection") == "runs")
        ):
            return
        row = self.database.execute(
            self.database.connection,
            "SELECT 1 FROM dockflow_run_owners WHERE project_id=? AND run_id=?",
            (self.project_id, run_id),
        ).fetchone()
        if row:
            raise DockflowError(
                "Execution mutation requires the current Run owner",
                "OWNERSHIP_LOST",
                409,
            )

    @_project_mutation
    def initialize(self) -> None:
        self.require_owner()
        expected = {
            "schema_version": 1,
            "kind": "project",
            "project_id": self.project_id,
            "mapping_version": 1,
            "digest_format": "dockflow-json-v1",
        }
        project = self.project_metadata("project")
        if project is not None:
            if any(project.get(key) != value for key, value in expected.items()):
                raise DockflowError(
                    "Incompatible state schema or project identity",
                    code="CONFLICT",
                    status=409,
                )
        else:
            if not self.database.project_empty():
                raise DockflowError(
                    "Project identity record is missing from nonempty database state",
                    "CONFLICT",
                    409,
                )
            self.set_project_metadata(
                "project", {**expected, "created_at": utc_now()}, immutable=True
            )
        if self.database.adapter.concurrent_runs:
            if self.database.current_sequence() != len(self.records()):
                raise DockflowError(
                    "Journal sequence counter differs from accepted history",
                    "CONFLICT",
                    409,
                )
            return
        with self._mutex, self.database.transaction():
            records = self.records()
            for record in records:
                self._project(record)
            self._recover_committed_outputs(records)
            self.mark_reconciled()

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
        self.save_definition_source(definition_id, source)
        return self.put("definitions", {**resource, "sha256": source_digest})

    def save_definition_source(self, definition_id: str, source: bytes) -> None:
        self._validate_resource("definitions", {"definition_id": definition_id})
        self.append(
            "definition_source",
            {
                "definition_id": definition_id,
                "base64": base64.b64encode(source).decode("ascii"),
                "sha256": hashlib.sha256(source).hexdigest(),
            },
        )

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
        return self.database.log_entries(run_id)

    def accepted_events(self, kind, *, run_id=None, attempt_id=None):
        records = [
            record
            for _, record in self.database.events(
                kind=kind, run_id=run_id, attempt_id=attempt_id
            )
        ]
        for record in records:
            self._validate_record(record)
        return records

    def has_stop_intent(self, run_id):
        return bool(self.database.events(kind="stop_intent", run_id=run_id))

    def records(self) -> list[dict[str, Any]]:
        with self.database.snapshot():
            return self._records()

    def _records(self) -> list[dict[str, Any]]:
        result = []
        events = self.database.events()
        stopped_runs: set[str] = set()
        committed_attempts: set[str] = set()
        registered_versions: dict[str, dict] = {}
        registered_components: dict[str, dict] = {}
        catalogs: dict[str, dict] = {}
        observed_ids: set[tuple[str, str]] = set()
        for expected, (sequence, record) in enumerate(events, start=1):
            if sequence != expected:
                raise DockflowError(
                    f"Accepted mutation sequence gap at {expected}",
                    code="CONFLICT",
                    status=409,
                )
            if (
                not isinstance(record, dict)
                or record.get("schema_version") != 1
                or record.get("project_id") != self.project_id
                or record.get("sequence") != expected
            ):
                raise DockflowError(
                    f"Incompatible accepted mutation {sequence}",
                    code="CONFLICT",
                    status=409,
                )
            if record.get("kind") not in {
                "resource_put",
                "output_set",
                "stop_intent",
                "event",
                "cleanup",
                "definition_source",
                "attempt_log_snapshot",
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
                self._validate_resource(payload["collection"], payload["resource"])
            elif record["kind"] == "output_set":
                marker = payload["marker"]
                self._validate_attempt_identity(
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
                    self._validate_resource("artifacts", descriptor)
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
                self._validate_resource("runs", {"run_id": payload["run_id"]})
            elif record["kind"] in {"definition_source", "attempt_log_snapshot"}:
                if record["kind"] == "definition_source":
                    self._validate_resource(
                        "definitions", {"definition_id": payload["definition_id"]}
                    )
                else:
                    self._validate_attempt_identity(
                        payload["run_id"], payload["task_id"], payload["attempt_id"]
                    )
                    if payload["stream"] not in {"stdout", "stderr"}:
                        raise ValueError("Invalid retained log stream")
                source = base64.b64decode(payload["base64"], validate=True)
                if hashlib.sha256(source).hexdigest() != payload["sha256"]:
                    raise ValueError("Snapshot digest mismatch")
            elif record.get("event_kind") == "cache_observation":
                self._validate_record({**record, "event_kind": "cache_import"})
                projected = payload["projected_artifact_ids"]
                if (
                    not isinstance(projected, list)
                    or len(set(projected)) != len(projected)
                    or not set(projected)
                    <= {
                        item["artifact_id"]
                        for item in payload["manifest"]["outputs"].values()
                    }
                ):
                    raise ValueError("Invalid cache observation projection")
            elif record.get("event_kind") == "cache_import":
                from .cache_storage import validate_manifest

                manifest = payload["manifest"]
                validate_manifest(
                    manifest,
                    manifest["storage_identity"],
                    manifest["producer"]["attempt_id"],
                )
                if payload["manifest_digest"] != digest(manifest):
                    raise ValueError("Imported cache manifest digest differs")
                for mutation in self._registration_records(record):
                    self._validate_record(mutation)
                if {
                    item["resource"]["artifact_id"]
                    for item in payload["resources"]
                    if item["collection"] == "artifacts"
                } != {item["artifact_id"] for item in manifest["outputs"].values()}:
                    raise ValueError("Imported cache artifact bindings differ")
                output_snapshots = {
                    item["artifact_id"]: item for item in manifest["outputs"].values()
                }
                producers = []
                for item in payload["resources"]:
                    resource = item["resource"]
                    if item["collection"] == "artifacts":
                        portable = {
                            key: value
                            for key, value in resource.items()
                            if key
                            not in {
                                "uri",
                                "descriptor_uri",
                                "content_uri",
                                "cache_origin",
                            }
                        }
                        if portable != output_snapshots[resource["artifact_id"]]:
                            raise ValueError(
                                "Imported descriptor differs from cache manifest"
                            )
                    elif item["collection"] == "attempts":
                        producers.append(resource)
                    else:
                        raise ValueError("Unexpected imported cache resource")
                if (
                    len(producers) != 1
                    or producers[0]["attempt_id"] != manifest["producer"]["attempt_id"]
                    or producers[0]["outputs"]
                    != {
                        name: item["artifact_id"]
                        for name, item in manifest["outputs"].items()
                    }
                    or producers[0]["output_parameters"] != manifest["parameters"]
                    or producers[0]["cache_manifest_digest"] != digest(manifest)
                ):
                    raise ValueError("Imported producer differs from cache manifest")
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
                    or payload["source"]["definition_id"] != definition["definition_id"]
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
        with self._mutex, self.database.transaction():
            self._guard_execution(kind, payload)
            sequence = self.database.allocate_sequence()
            record = {
                "schema_version": 1,
                "kind": kind
                if kind
                in {
                    "resource_put",
                    "output_set",
                    "stop_intent",
                    "cleanup",
                    "definition_source",
                    "attempt_log_snapshot",
                }
                else "event",
                "event_kind": kind,
                "project_id": self.project_id,
                "sequence": sequence,
                "timestamp": utc_now(),
                "payload": payload,
            }
            self._validate_record(record)
            self.database.append_event(record)
            try:
                self._project(record)
            except DockflowError:
                raise
            except Exception:
                raise DockflowError(
                    "Mutation rolled back before acceptance; SQL projection failed",
                    "UNAVAILABLE",
                    503,
                ) from None
            return record

    def _validate_resource(self, collection: str, resource: dict[str, Any]) -> str:
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
        if collection == "runs" and "execution_choices" in resource:
            from .execution_choices import ExecutionChoices

            ExecutionChoices.from_record(resource["execution_choices"])
        return public_id

    @_project_mutation
    def put(self, collection: str, resource: dict[str, Any]) -> dict[str, Any]:
        self.require_owner()
        public_id = self._validate_resource(collection, resource)
        if collection == "runs" and self.has_resource(collection, public_id):
            resource = merge_run(self.get("runs", public_id), resource)
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
        self._validate_resource(collection, value)
        if collection in {"definitions", "components"} and self.has_resource(
            collection, public_id
        ):
            previous = self.get(collection, public_id)
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
            self.append("resource_put", {"collection": collection, "resource": value})
        return value

    @_project_mutation
    def finish_run(self, run: dict, *, recovering=False):
        current = self.get("runs", run["run_id"])
        result = merge_run(current, run)
        if result.get("state") not in TERMINAL:
            raise DockflowError(
                "Run completion requires a terminal outcome", "CONFLICT", 409
            )
        tasks = self.database.queries.select("tasks", filters={"run_id": run["run_id"]})
        for task in tasks:
            attempts = self.database.queries.select(
                "attempts", filters={"task_id": task["task_id"]}
            )
            changed = terminal_task(
                task, attempts, result["state"], recovering=recovering
            )
            if changed is not None:
                self.put("tasks", changed)
        return self.put("runs", result)

    @staticmethod
    def _registration_records(record: dict[str, Any]) -> list[dict[str, Any]]:
        """Expand one accepted registration for projection and integrity checks."""
        if record.get("event_kind") == "cache_observation":
            return [
                {
                    **record,
                    "kind": "resource_put",
                    "event_kind": "resource_put",
                    "payload": item,
                }
                for item in record["payload"]["resources"]
                if item["collection"] == "artifacts"
                and item["resource"]["artifact_id"]
                in record["payload"]["projected_artifact_ids"]
            ]
        if record.get("event_kind") == "cache_import":
            return [
                {
                    **record,
                    "kind": "resource_put",
                    "event_kind": "resource_put",
                    "payload": mutation,
                }
                for mutation in record["payload"]["resources"]
            ]
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
                "kind": "definition_source",
                "event_kind": "definition_source",
                "payload": record["payload"]["source"],
            }
        ]

    @_project_mutation
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
            if self.has_resource(
                collection, self._validate_resource(collection, resource)
            ):
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
                "definition_id": definition["definition_id"],
                "base64": base64.b64encode(source).decode("ascii"),
                "sha256": hashlib.sha256(source).hexdigest(),
            },
        }
        self.append("pipeline_registration", payload)
        return resources[1]["resource"]

    def _project(self, record: dict[str, Any]) -> None:
        for projection in project_record(record, self._registration_records):
            value = projection.data
            identity = projection.identity
            if projection.table == "dockflow_state_resources":
                self.database.put_resource(identity[0], loads(value))
            elif projection.table == "dockflow_log_entries":
                self.database.put_log_entry(identity[0], loads(value))
            elif projection.table == "dockflow_definition_sources":
                self.database.put_definition_source(identity[0], value)
            elif projection.table == "dockflow_output_sets":
                self.database.put_output_set(loads(value))
            elif projection.table == "dockflow_cache_observations":
                self.database.put_cache_observation(identity[0], loads(value))
            elif projection.table == "dockflow_log_snapshots":
                self.database.put_log_snapshot(identity[0], identity[1], value)

    def get(self, collection: str, public_id: str) -> dict[str, Any]:
        kind = COLLECTIONS.get(collection)
        if kind is None:
            raise DockflowError(f"Unknown resource collection: {collection}")
        self._validate_resource(collection, {f"{kind}_id": public_id})
        resource = self.database.resource(collection, public_id)
        if resource is None:
            raise DockflowError(
                f"{kind.capitalize()} not found: {public_id}", "NOT_FOUND", 404
            )
        if self._validate_resource(collection, resource) != public_id:
            raise DockflowError(
                "Resource identity differs from its SQL key", "CONFLICT", 409
            )
        return resource

    def query(self, collection: str, **options) -> list[dict[str, Any]]:
        return self.database.queries.select(collection, **options)

    def list(self, collection: str) -> list[dict[str, Any]]:
        if collection not in COLLECTIONS:
            raise DockflowError(f"Unknown resource collection: {collection}")
        return self.database.resources(collection)

    def _validate_attempt_identity(
        self, run_id: str, task_id: str, attempt_id: str
    ) -> None:
        for collection, value in (
            ("runs", run_id),
            ("tasks", task_id),
            ("attempts", attempt_id),
        ):
            self._validate_resource(
                collection, {f"{COLLECTIONS[collection]}_id": value}
            )

    @_project_mutation
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
            self._validate_attempt_identity(run_id, task_id, attempt_id)
            marker = self.output_set(attempt_id)
            if marker is not None:
                accepted = [
                    record["payload"]["marker"]
                    for record in self.accepted_events(
                        "output_set", attempt_id=attempt_id
                    )
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
            stopped = self.has_stop_intent(run_id)
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
                "acceptance_sequence": self.database.current_sequence() + 1,
                "published_at": published_at,
            }
            self.append("output_set", {"marker": marker, "artifacts": committed})
            return marker

    def publish_cache_result(self, options: dict, ownership, manifest: dict) -> dict:
        """Serialize the cache commit with this Run's durable stop intent."""
        from .cache_registry import Registry

        self.require_owner()
        boundary = (
            self.database.transaction()
            if self.database.adapter.concurrent_runs
            else contextlib.nullcontext()
        )
        with self._mutex, boundary:
            run_id = manifest["producer"]["run_id"]
            run = self.get("runs", run_id)
            if (
                run.get("cancellation_requested")
                or run.get("interruption_requested")
                or run.get("state") in {"cancelling", "cancelled", "interrupted"}
                or self.has_stop_intent(run_id)
            ):
                raise DockflowError(
                    "Stop intent prevents new cache publication", "CONFLICT", 409
                )
            claim = self.database.run_claim
            if self.database.adapter.concurrent_runs:
                if claim is None or claim.run_id != run_id:
                    raise DockflowError(
                        "Cache publication requires Run ownership",
                        "OWNERSHIP_LOST",
                        409,
                    )
                options = {
                    **options,
                    "execution_claim": {
                        "run_id": run_id,
                        "owner_id": claim.owner_id,
                        "fence": claim.fence,
                    },
                }
            return Registry(
                options,
                self.project_id,
                before_commit=claim.check_local if claim else None,
            ).publish(ownership, manifest)

    @_project_mutation
    def import_cache_result(self, manifest: dict, descriptors: dict) -> dict:
        """Atomically retain verified remote producer facts, never a local attempt."""
        from .cache_storage import validate_manifest

        self.require_owner()
        self.ensure_reconciled()
        producer = manifest["producer"]
        attempt_id = producer["attempt_id"]
        validate_manifest(manifest, manifest["storage_identity"], attempt_id)
        existing = None
        try:
            existing = self.get("attempts", attempt_id)
        except DockflowError as exc:
            if exc.code != "NOT_FOUND":
                raise
        else:
            if existing.get("signature", {}).get("value") != manifest["signature"]:
                raise DockflowError(
                    "Cached producer conflicts with retained history", "CONFLICT", 409
                )
            if (
                self.verify_output_set(attempt_id)["valid"]
                and existing.get("outputs")
                == {name: value["artifact_id"] for name, value in descriptors.items()}
                and existing.get("output_parameters") == manifest["parameters"]
            ):
                return existing
            if existing.get("imported_cache_producer"):
                raise DockflowError(
                    "Retained cache provenance needs reconciliation", "CONFLICT", 409
                )
        source = {
            **(existing or {}),
            "schema_version": 1,
            "kind": "attempt",
            "project_id": self.project_id,
            **producer,
            "state": "succeeded",
            "publication_state": "committed",
            "signature": (existing or {}).get(
                "signature",
                {
                    "value": manifest["signature"],
                    "format": "dockflow-task-signature-v2",
                },
            ),
            "outputs": {
                name: item["artifact_id"] for name, item in descriptors.items()
            },
            "output_parameters": manifest["parameters"],
            "inputs": (existing or {}).get("inputs", {}),
            "error": None,
            "reconciliation_required": False,
            "imported_cache_producer": True,
            "cache_manifest_digest": digest(manifest),
            "finished_at": producer.get("finished_at"),
        }
        resources = [
            {"collection": "artifacts", "resource": value}
            for value in descriptors.values()
        ] + [{"collection": "attempts", "resource": source}]
        claim = self.database.run_claim
        if (
            existing is not None
            and self.database.adapter.concurrent_runs
            and (claim is None or claim.run_id != producer["run_id"])
        ):
            # Cache publication is already committed, but only the original Run
            # owner may advance its execution lifecycle. Retain a separate
            # immutable producer snapshot for consumers instead of overwriting it.
            observation = self.database.cache_observation(attempt_id)
            if observation is not None:
                if observation["manifest_digest"] != digest(manifest):
                    raise DockflowError(
                        "Cache observation conflicts with retained provenance",
                        "CONFLICT",
                        409,
                    )
                return next(
                    item["resource"]
                    for item in observation["resources"]
                    if item["collection"] == "attempts"
                )
            self.append(
                "cache_observation",
                {
                    "manifest": manifest,
                    "manifest_digest": digest(manifest),
                    "resources": resources,
                    "projected_artifact_ids": [
                        value["artifact_id"]
                        for value in descriptors.values()
                        if not self.has_resource("artifacts", value["artifact_id"])
                    ],
                },
            )
            return source
        self.append(
            "cache_import",
            {
                "manifest": manifest,
                "manifest_digest": digest(manifest),
                "resources": resources,
            },
        )
        return source

    def verify_output_set(self, attempt_id: str) -> dict[str, Any]:
        """Verify the original committed snapshot independently of mutable pins."""
        try:
            attempt = self.get("attempts", attempt_id)
            if attempt.get("imported_cache_producer"):
                imported = [
                    record["payload"]
                    for record in self.accepted_events(
                        "cache_import", attempt_id=attempt_id
                    )
                    if record.get("event_kind") == "cache_import"
                    and record["payload"]["manifest"]["producer"]["attempt_id"]
                    == attempt_id
                ]
                if (
                    len(imported) != 1
                    or imported[0]["manifest_digest"]
                    != attempt["cache_manifest_digest"]
                ):
                    return {
                        "valid": False,
                        "reason": "Imported cache provenance differs",
                    }
                manifest = imported[0]["manifest"]
                if (
                    attempt["outputs"]
                    != {
                        name: item["artifact_id"]
                        for name, item in manifest["outputs"].items()
                    }
                    or attempt["output_parameters"] != manifest["parameters"]
                ):
                    return {
                        "valid": False,
                        "reason": "Imported cache output bindings differ",
                    }
                for item in imported[0]["resources"]:
                    if item["collection"] != "artifacts":
                        continue
                    snapshot = item["resource"]
                    descriptor = self.get("artifacts", snapshot["artifact_id"])
                    ignored = {"pinned", "availability", "availability_observed_at"}
                    if {
                        key: value
                        for key, value in descriptor.items()
                        if key not in ignored
                    } != {
                        key: value
                        for key, value in snapshot.items()
                        if key not in ignored
                    }:
                        return {
                            "valid": False,
                            "reason": "Imported descriptor differs from committed cache binding",
                        }
                return {
                    "valid": True,
                    "reason": None,
                    "marker": {"parameters": manifest["parameters"]},
                }
            accepted = [
                record["payload"]
                for record in self.accepted_events("output_set", attempt_id=attempt_id)
                if record["kind"] == "output_set"
                and record["payload"]["marker"]["attempt_id"] == attempt_id
            ]
            observation = self.database.cache_observation(attempt_id)
            if not accepted and observation is not None:
                snapshots = [
                    record["payload"]
                    for record in self.accepted_events(
                        "cache_observation", attempt_id=attempt_id
                    )
                    if record.get("event_kind") == "cache_observation"
                    and record["payload"]["manifest"]["producer"]["attempt_id"]
                    == attempt_id
                ]
                valid = snapshots == [observation]
                return {
                    "valid": valid,
                    "reason": None
                    if valid
                    else "Cache observation differs from accepted provenance",
                    "marker": {"parameters": observation["manifest"]["parameters"]},
                }
            if len(accepted) != 1:
                return {
                    "valid": False,
                    "reason": "Attempt has no unique accepted output-set commit",
                }
            payload = accepted[0]
            marker = payload["marker"]
            actual = self.output_set(attempt_id)
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

    def mark_reconciled(self) -> None:
        self.set_project_metadata(
            "reconciliation",
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
        with self.database.snapshot():
            return self._check(verify_contents, artifacts)

    def _check(self, verify_contents: bool, artifacts: Any) -> dict[str, Any]:
        errors = []
        try:
            records = self.records()
            accepted_sequence = len(records)
            expected = expected_rows(records, self._registration_records)
            if self.database.current_sequence() != accepted_sequence:
                errors.append(
                    {"reason": "Journal sequence counter differs from accepted history"}
                )
            for table, (keys, columns) in DOMAINS.items():
                with self.database.reader() as connection:
                    rows = (
                        self.database.execute(
                            connection,
                            "SELECT "
                            + ",".join((*keys, *columns))
                            + f" FROM {table} WHERE project_id=?",
                            (self.project_id,),
                        ).fetchall()
                        if connection is not None
                        else []
                    )
                actual = {}
                for row in rows:
                    key = tuple(row[: len(keys)])
                    value = tuple(
                        value.encode()
                        if name == "value" and isinstance(value, str)
                        else bytes(value)
                        if name == "value" and isinstance(value, memoryview)
                        else value
                        for name, value in zip(columns, row[len(keys) :], strict=True)
                    )
                    actual[key] = value
                for identity in expected[table].keys() | actual.keys():
                    if expected[table].get(identity) != actual.get(identity):
                        missing = identity not in actual
                        reason = (
                            "Accepted source snapshot is missing or inaccessible"
                            if missing
                            and table
                            in {"dockflow_definition_sources", "dockflow_log_snapshots"}
                            else "Domain projection is missing, changed or orphaned"
                        )
                        errors.append({"table": table, "reason": reason})
            resources = {
                identity: loads(value[0])
                for identity, value in expected["dockflow_state_resources"].items()
            }
            for identity in resources:
                if self.database.internal_id(*identity) is None:
                    errors.append({"reason": "Resource numeric alias is missing"})
            for record in records:
                if record["kind"] == "output_set":
                    marker = record["payload"]["marker"]
                    if any(
                        (collection, marker[field]) not in resources
                        for collection, field in (
                            ("runs", "run_id"),
                            ("tasks", "task_id"),
                            ("attempts", "attempt_id"),
                        )
                    ):
                        errors.append(
                            {
                                "reason": "Committed output set is missing an indispensable execution record"
                            }
                        )
        except (DockflowError, ValueError, TypeError, KeyError) as exc:
            return {
                "valid": False,
                "errors": [
                    {
                        "reason": str(exc)
                        if isinstance(exc, DockflowError)
                        else "Invalid domain projection or accepted history"
                    }
                ],
                "content_verified": False,
                "projections_checked": True,
            }
        availability = []
        if artifacts:
            for collection, public_id in resources:
                if collection == "artifacts":
                    try:
                        availability.append(
                            artifacts.verify(public_id, verify_contents=verify_contents)
                        )
                    except DockflowError:
                        errors.append(
                            {"reason": "Artifact projection is invalid or inaccessible"}
                        )
        return {
            "valid": not errors,
            "project_id": self.project_id,
            "accepted_sequence": accepted_sequence,
            "errors": errors,
            "projections_checked": True,
            "content_verified": verify_contents and artifacts is not None,
            "availability": availability,
        }

    def rebuild(self, apply: bool = False) -> dict[str, Any]:
        records = self.records()
        report = {
            "project_id": self.project_id,
            "state_backend": self.database.backend,
            "records": len(records),
            "apply": apply,
            "offline_required": True,
        }
        if not apply:
            return report
        self.require_owner()
        with self.database.maintenance():
            records = self.records()
            report["records"] = len(records)
            return self._apply_rebuild(records, report)

    def _apply_rebuild(self, records, report):
        if self.database.current_sequence() != len(records):
            raise DockflowError(
                "Journal sequence counter differs; restore authoritative state before rebuilding",
                "CONFLICT",
                409,
            )

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
        with self._mutex, self.database.transaction():
            self.database.clear_projections()
            for record in records:
                self._project(record)
            self.mark_reconciled()
        return {
            **report,
            "rebuilt": True,
            "backup": None,
            "backup_format": "transactional-journal",
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
            with self.database.maintenance():
                return self._apply_clean(root, candidates, protected)
        return {
            "project_id": self.project_id,
            "state_backend": self.database.backend,
            "work_directory": str(root),
            "apply": False,
            "candidates": candidates,
            "protected": protected,
            "deleted_count": 0,
        }

    def _apply_clean(self, root, candidates, protected):
        apply = True
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
            "state_backend": self.database.backend,
            "work_directory": str(root),
            "apply": apply,
            "candidates": candidates,
            "protected": protected,
            "deleted_count": len(candidates) if apply else 0,
        }

    @_maintenance_operation
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
            roots = [self.state.resolve()]
            if self.database.backend == "sqlite":
                roots.append(Path(self.database.options["database"]).resolve())
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
                self.export_database(temporary / "state.sqlite")
                snapshot_database = StateDatabase(
                    {"backend": "sqlite", "database": str(temporary / "state.sqlite")},
                    self.project_id,
                )
                cache_manifests = snapshot_database.cache_manifests()
                for cache_manifest in cache_manifests:
                    artifacts.verify_cache(
                        cache_manifest, cache_manifest["storage_identity"]
                    )
                tokens = snapshot_database.cache_store_tokens()
                store_ids = snapshot_database.artifact_store_ids()
                identity = (
                    artifacts.storage_identity(create=False)
                    if tokens or store_ids
                    else None
                )
                if store_ids - {identity}:
                    raise DockflowError(
                        "Project publication records include additional artifact roots; back up all roots with the database together",
                        "CONFLICT",
                        409,
                    )
                if tokens and tokens != {identity}:
                    raise DockflowError(
                        "Backup artifact store identity differs from cache history",
                        "CONFLICT",
                        409,
                    )
                if artifacts.backend == "filesystem":
                    managed = artifacts.managed_root
                    if managed.exists():
                        # inventory validates links and special files before copying.
                        from .artifacts import inventory

                        inventory(managed)
                        shutil.copytree(managed, temporary / "managed", symlinks=False)
                else:
                    from .artifacts import _relative_path

                    prefix = artifacts.options.get("prefix", "").strip("/")
                    prefix = prefix + "/" if prefix else ""
                    client = artifacts._s3()
                    bucket = artifacts.options["bucket"]
                    for page in client.get_paginator("list_objects_v2").paginate(
                        Bucket=bucket, Prefix=prefix
                    ):
                        for item in page.get("Contents", []):
                            relative = str(_relative_path(item["Key"][len(prefix) :]))
                            target = temporary / "managed" / relative
                            target.parent.mkdir(parents=True, exist_ok=True)
                            client.download_file(bucket, item["Key"], str(target))
                from .artifacts import inventory

                _verify_publications(snapshot_database, temporary / "managed")
                snapshot = inventory(temporary)
                manifest = {
                    "schema_version": 1,
                    "kind": "backup",
                    "project_id": self.project_id,
                    "accepted_sequence": len(records),
                    "created_at": utc_now(),
                    "state_backend": self.database.backend,
                    "state_format": "dockflow-sql-v4",
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

    @_maintenance_operation
    def export_database(self, destination: Path) -> None:
        self.require_owner()
        target = StateDatabase(
            {"backend": "sqlite", "database": str(destination)}, self.project_id
        )
        target.acquire()
        try:
            target.copy_project(self.database)
            with target.transaction() as connection:
                connection.execute("DELETE FROM dockflow_state_owners")
            target.connection.execute("VACUUM")
        finally:
            target.release()

    @_maintenance_operation
    def import_database(self, source: Path) -> None:
        self.require_owner()
        if not self.database.project_empty(include_cache=True):
            raise DockflowError("Restore target project must be empty", "CONFLICT", 409)
        snapshot = StateDatabase(
            {"backend": "sqlite", "database": str(source)}, self.project_id
        )
        project = snapshot.project_metadata("project")
        if project is None:
            raise DockflowError("Backup project identity is missing", "CONFLICT", 409)
        if project.get("project_id") != self.project_id:
            raise DockflowError("Backup project identity mismatch", "CONFLICT", 409)
        with self.database.transaction():
            self.database.copy_project(snapshot)
            for record in self.records():
                self._project(record)

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
        if manifest.get("state_format") != "dockflow-sql-v4":
            raise DockflowError("Unsupported backup state format", "CONFLICT", 409)
        snapshot = StateDatabase(
            {"backend": "sqlite", "database": str(source.absolute() / "state.sqlite")},
            manifest["project_id"],
        )
        _verify_publications(snapshot, source.absolute() / "managed")
        return {
            "valid": True,
            "project_id": manifest["project_id"],
            "accepted_sequence": manifest["accepted_sequence"],
            "external_references_included": False,
        }


def _verify_publications(snapshot: StateDatabase, managed: Path) -> None:
    """Validate standalone publication bytes against their SQL completion records."""
    from dockflow_artifacts import ArtifactError, Publisher

    destinations = snapshot.publication_destinations()
    if not destinations:
        return
    publisher = Publisher(
        managed.absolute(), database=snapshot.adapter, project_id=snapshot.project_id
    )
    try:
        for destination in destinations:
            publisher.verify(destination)
    except ArtifactError:
        raise DockflowError(
            "Backup publication contents differ from SQL manifests", "CONFLICT", 409
        ) from None
