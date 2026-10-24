"""Application operations shared by the direct CLI and HTTP service."""

from __future__ import annotations

import base64
import contextlib
import functools
import hashlib
import hmac
import json
import re
import secrets
import sys
import threading
from collections.abc import Callable
from importlib import metadata
from pathlib import Path
from typing import Any

from dockflow_database.errors import DockflowError

from .canonical import digest, loads, validate_json
from .config import Settings
from .definitions import (
    Definition,
    DefinitionError,
    UnsupportedCapability,
    load_definition,
    validate_parameters,
    validate_selection,
)
from .execution_choices import ExecutionChoices
from .records import TERMINAL

RUN_FIELDS = {
    "definition_id",
    "pipeline_spec",
    "source_text",
    "display_name",
    "experiment_id",
    "description",
    "parameters",
    "inputs",
    "selection",
    "bindings",
    "use_executions",
    "reuse",
}


def only_fields(value: dict, allowed: set[str], name: str = "request") -> None:
    if not isinstance(value, dict) or set(value) - allowed:
        unknown = sorted(set(value) - allowed) if isinstance(value, dict) else []
        raise DockflowError(f"Invalid {name}; unknown fields: {unknown}")


def checked_definition(source) -> Definition:
    try:
        return load_definition(source)
    except UnsupportedCapability as exc:
        raise DockflowError(str(exc), "UNSUPPORTED_CAPABILITY", 422) from exc
    except (DefinitionError, OSError, ValueError, TypeError) as exc:
        raise DockflowError(str(exc)) from exc


def capabilities(settings: Settings | None = None) -> dict:
    from .reuse import ADAPTER

    versions = {}
    for package in ("dockflow-pipelines", "kfp", "ml-metadata", "docker"):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    return {
        "schema_version": 1,
        "project_id": settings.project_id if settings else None,
        "versions": versions,
        "profile": "dockflow-kfp-2.17-v1",
        "adapter": ADAPTER,
        "compiled_cache_default": False,
        "condition_grammar": {
            "references": "inputs.parameter_values['name'] or inputs.parameter_values[\"name\"]",
            "literals": "scalar JSON literals",
            "casts": ["int", "double", "string", "bool"],
            "operators": [
                "==",
                "!=",
                "<",
                "<=",
                ">",
                ">=",
                "!",
                "&&",
                "||",
                "parentheses",
            ],
        },
        "task_identity": "POSIX execution-owner UID/GID with attempt-local HOME unless component supplies HOME",
        "ir_schema_version": "2.1.0",
        "qualification": "bounded initial milestone; see version-specific release evidence",
        "features": [
            "compiled_ir",
            "static_dag",
            "nested_dag",
            "importer",
            "scalar_conditions",
            "artifacts",
            "reuse",
            "partial_selection",
            "pipeline_uploads",
            "web_interface",
            "coordinated_artifact_cache",
            "database_execution_state",
            "concurrent_postgresql_runs",
        ],
        "backends": {
            "execution": "KFP DockerRunner",
            "metadata": ["sqlite", "postgresql"],
            "artifacts": ["filesystem", "s3"],
            "cache": ["sqlite", "postgresql"],
        },
        "limits": {
            "active_runs": 1,
            "active_runs_scope": "project"
            if settings is None or settings.state_storage["backend"] == "sqlite"
            else "coordinator",
            "task_parallelism": 1,
            "queue_capacity": settings.service["queue_capacity"] if settings else 100,
        },
        "kfp_api": {
            "version": "2.17.0 v2beta1",
            "qualification": "documented client subset",
        },
        "limitations": [
            "No loops, accelerators, Kubernetes platform plugins, managed-output URI overrides or artifact payload uploads",
            "Execution qualification is limited to Linux x86-64; no full KFP parity claim",
        ],
    }


def _project_mutation(method):
    @functools.wraps(method)
    def serialized(self, *args, **kwargs):
        with self.mutex, self.store.database.transaction():
            return method(self, *args, **kwargs)

    return serialized


class Core:
    def __init__(self, settings: Settings):
        from .artifacts import ArtifactStore
        from .metadata import ControlStore

        self.settings = settings
        self.store = ControlStore(
            settings.state,
            settings.project_id,
            storage=settings.state_storage,
        )
        settings.cache["database"] = dict(self.store.database.options)
        self.artifacts = ArtifactStore(self.store, settings.artifacts)
        self.mutex = threading.RLock()

    def initialize(self) -> None:
        self.store.initialize()
        from .cache_registry import Registry

        self.settings.cache["storage_token"] = self.artifacts.storage_identity()
        Registry(self.settings.cache, self.settings.project_id).initialize()
        with self.store.database.transaction():
            if self.store.project_metadata("pagination") is None:
                self.store.set_project_metadata(
                    "pagination",
                    {"schema_version": 1, "key": secrets.token_hex(32)},
                )

    def _definition(self, request: dict) -> Definition:
        if ("definition_id" in request) == ("pipeline_spec" in request):
            raise DockflowError(
                "Exactly one of definition_id or pipeline_spec is required"
            )
        if "source_text" in request and "pipeline_spec" not in request:
            raise DockflowError("source_text requires pipeline_spec")
        if "definition_id" in request:
            record = self.store.get("definitions", request["definition_id"])
            return checked_definition(record["source_text"])
        if not isinstance(request["pipeline_spec"], dict):
            raise DockflowError("pipeline_spec must be an object")
        definition = checked_definition(
            request.get("source_text", request["pipeline_spec"])
        )
        parsed = checked_definition(request["pipeline_spec"])
        if digest(definition.document) != digest(parsed.document):
            raise DockflowError("source_text does not match pipeline_spec")
        return definition

    def validate(self, request: dict) -> dict:
        only_fields(
            request,
            {"definition_id", "pipeline_spec", "source_text", "parameters", "inputs"},
        )
        definition = self._definition(request)
        try:
            parameters = validate_parameters(definition, request.get("parameters", {}))
            self._inputs(definition, request.get("inputs", {}))
        except (ValueError, TypeError) as exc:
            raise DockflowError(str(exc)) from exc
        return {
            "valid": True,
            "diagnostics": [],
            "required_capabilities": definition.to_record().get("profile"),
            "parameters": parameters,
        }

    @_project_mutation
    def snapshot(
        self,
        definition: Definition,
        name: str | None = None,
        pipeline_id: str | None = None,
        registration_origin: str | None = None,
    ) -> dict:
        existing = self.store.database.queries.select(
            "definitions",
            filters={
                "sha256": definition.sha256,
                "profile": definition.to_record().get("profile"),
                "pipeline_id": pipeline_id,
                "name": name,
                "registration_origin": registration_origin,
            },
            limit=1,
        )
        if existing:
            return existing[0]
        record, components = self._snapshot_records(
            definition, name, pipeline_id, registration_origin
        )
        self.store.save_definition_source(record["definition_id"], definition.raw_bytes)
        for component in components:
            self.store.put("components", component)
        return self.store.put("definitions", record)

    def _snapshot_records(
        self,
        definition: Definition,
        name: str | None,
        pipeline_id: str | None,
        registration_origin: str | None,
    ) -> tuple[dict, list[dict]]:
        from .records import new_id, utc_now

        record = {
            **definition.to_record(),
            "definition_id": new_id("definition"),
            "name": name,
            "pipeline_id": pipeline_id,
            "registration_origin": registration_origin,
            "version_name": None,
            "description": "",
            "created_at": utc_now(),
        }
        component_ids = {}
        components = []
        all_components = definition.document.get("components", {}) or {
            "root": definition.document["root"]
        }
        for key, component in all_components.items():
            component_ids[key] = new_id("component")
            components.append(
                {
                    "component_id": component_ids[key],
                    "definition_id": record["definition_id"],
                    "name": key,
                    "created_at": record["created_at"],
                    "compiled": component,
                    "executor": definition.document.get("deploymentSpec", {})
                    .get("executors", {})
                    .get(component.get("executorLabel")),
                    "available": True,
                }
            )
        return {**record, "component_ids": component_ids}, components

    def upload_pipeline(
        self,
        source: str,
        name: str | None,
        description: str = "",
        pipeline_id: str | None = None,
    ) -> tuple[dict, dict]:
        """Validate first, then accept a catalog/version and its exact source once."""
        from .records import new_id, utc_now

        definition = checked_definition(source)
        if not isinstance(description, str) or len(description) > 4096:
            raise DockflowError("description must contain at most 4096 characters")
        if name is None and pipeline_id is None:
            name = definition.name
        if not isinstance(name, str) or not name.strip() or len(name) > 256:
            raise DockflowError(
                "name/display_name must contain 1–256 nonblank characters"
            )
        with self.mutex, self.store.database.transaction():
            self.store.ensure_reconciled()
            if pipeline_id is None:
                if name in self.settings.definitions["pipelines"] or any(
                    item.get("registration") and item["name"] == name
                    for item in self.store.database.queries.select(
                        "pipelines",
                        filters={"name": name, "registration": True},
                        limit=1,
                    )
                ):
                    raise DockflowError("Pipeline name already exists", "CONFLICT", 409)
                catalog = {
                    "pipeline_id": new_id("pipeline"),
                    "name": name,
                    "description": description,
                    "created_at": utc_now(),
                    "registration": True,
                    "registration_origin": "api",
                    "version_ids": [],
                }
            else:
                catalog = self.store.get("pipelines", pipeline_id)
                if catalog.get("registration_origin") != "api":
                    raise DockflowError(
                        "Configured pipelines cannot receive uploaded versions",
                        "CONFLICT",
                        409,
                    )
                if any(
                    item.get("version_name") == name
                    for item in self.store.database.queries.select(
                        "definitions",
                        filters={"pipeline_id": pipeline_id, "sort_name": name},
                        limit=1,
                    )
                ):
                    raise DockflowError(
                        "Pipeline version name already exists", "CONFLICT", 409
                    )
            snapshot, components = self._snapshot_records(
                definition, catalog["name"], catalog["pipeline_id"], "api"
            )
            snapshot.update(version_name=name, description=description)
            catalog = {
                **catalog,
                "definition_id": snapshot["definition_id"],
                "default_version_id": snapshot["definition_id"],
                "available": True,
                "version_ids": [*catalog["version_ids"], snapshot["definition_id"]],
            }
            accepted = self.store.commit_registration(
                catalog, snapshot, components, definition.raw_bytes
            )
            return self.store.get("pipelines", catalog["pipeline_id"]), accepted

    @_project_mutation
    def refresh(self, name: str | None = None) -> dict:
        from .records import new_id, utc_now

        report = {"added": [], "updated": [], "unavailable": [], "diagnostics": []}
        for collection in ("pipelines", "components"):
            registrations = self.settings.definitions[collection]
            catalogs = {
                item["name"]: item
                for item in self.store.query(
                    collection,
                    filters={
                        "registration": True,
                        "registration_origin": "configuration",
                        **({"name": name} if name is not None else {}),
                    },
                )
            }
            for alias in sorted(set(catalogs) | set(registrations)):
                if name is not None and alias != name:
                    continue
                catalog = catalogs.get(alias)
                filename = registrations.get(alias)
                try:
                    if filename is None:
                        raise DockflowError("Registration removed from configuration")
                    definition = checked_definition(filename)
                    if catalog is None:
                        if any(
                            item.get("registration") and item["name"] == alias
                            for item in self.store.query(
                                collection,
                                filters={"name": alias, "registration": True},
                                limit=1,
                            )
                        ):
                            raise DockflowError(
                                "Name conflicts with an API registration",
                                "CONFLICT",
                                409,
                            )
                        catalog = {
                            f"{collection[:-1]}_id": new_id(collection[:-1]),
                            "name": alias,
                            "created_at": utc_now(),
                            "registration": True,
                            "registration_origin": "configuration",
                        }
                    snapshot = self.snapshot(
                        definition, alias, catalog.get("pipeline_id"), "configuration"
                    )
                    previous = catalog.get("definition_id")
                    if previous == snapshot["definition_id"] and catalog.get(
                        "available"
                    ):
                        continue
                    catalog = self.store.put(
                        collection,
                        {
                            **catalog,
                            "definition_id": snapshot["definition_id"],
                            "default_version_id": snapshot["definition_id"],
                            "available": True,
                        },
                    )
                    report["added" if previous is None else "updated"].append(
                        snapshot["definition_id"]
                    )
                except (DockflowError, OSError) as exc:
                    report["diagnostics"].append({"name": alias, "reason": str(exc)})
                    if catalog:
                        self.store.put(collection, {**catalog, "available": False})
                        report["unavailable"].append(catalog.get("definition_id"))
        return report

    def registrations_unchanged(self) -> bool:
        """Check active catalog sources without mutating during active work."""
        for collection in ("pipelines", "components"):
            registrations = self.settings.definitions[collection]
            catalogs = {
                item["name"]: item
                for item in self.store.query(
                    collection,
                    filters={
                        "registration": True,
                        "registration_origin": "configuration",
                    },
                )
                if item.get("available")
            }
            if set(catalogs) != set(registrations):
                return False
            for name, filename in registrations.items():
                try:
                    definition = checked_definition(filename)
                    if (
                        self.store.get("definitions", catalogs[name]["definition_id"])[
                            "sha256"
                        ]
                        != definition.sha256
                    ):
                        return False
                except (DockflowError, OSError):
                    return False
        return True

    def resolve(self, operand: str, *, persist: bool = True) -> dict:
        if operand.startswith("definition_"):
            return self.store.get("definitions", operand)
        filename = Path(operand)
        is_file = (
            filename.is_absolute()
            or operand.startswith(("./", "../"))
            or filename.suffix in {".yaml", ".yml", ".json"}
        )
        if is_file:
            definition = checked_definition(filename)
            return self.snapshot(definition) if persist else definition.to_record()
        if operand not in self.settings.definitions["pipelines"]:
            catalog = next(
                (
                    item
                    for item in self.store.database.queries.select(
                        "pipelines",
                        filters={"name": operand, "registration": True},
                        limit=1,
                    )
                ),
                None,
            )
            if catalog is not None:
                if not catalog.get("available"):
                    raise DockflowError(
                        f"Pipeline registration is unavailable: {operand}",
                        "CONFLICT",
                        409,
                    )
                return self.store.get("definitions", catalog["definition_id"])
            raise DockflowError(
                f"Unknown pipeline registration: {operand}", "NOT_FOUND", 404
            )
        if not persist:
            return checked_definition(
                self.settings.definitions["pipelines"][operand]
            ).to_record()
        report = self.refresh(operand)
        if report["diagnostics"]:
            raise DockflowError(
                f"Definition {operand}: {report['diagnostics'][0]['reason']}"
            )
        catalog = next(
            item
            for item in self.store.database.queries.select(
                "pipelines", filters={"name": operand, "registration": True}, limit=1
            )
        )
        return self.store.get("definitions", catalog["definition_id"])

    def definition_view(self, record: dict) -> dict:
        """Add the current catalog pointer without changing an immutable version."""
        default_version_id = None
        if record.get("pipeline_id"):
            default_version_id = self.store.get("pipelines", record["pipeline_id"]).get(
                "default_version_id"
            )
        return {**record, "default_version_id": default_version_id}

    def _inputs(self, definition: Definition, inputs: dict) -> dict:
        if not isinstance(inputs, dict):
            raise DockflowError("inputs must be an object")
        contracts = definition.root.get("inputDefinitions", {}).get("artifacts", {})
        if set(inputs) - set(contracts):
            raise DockflowError("Unknown root artifact inputs")
        for name, contract in contracts.items():
            if name not in inputs:
                if contract.get("isOptional"):
                    continue
                raise DockflowError(f"Missing artifact input: {name}")
            artifact = self.artifacts.get(inputs[name])
            expected = contract["artifactType"]
            actual = artifact["type"]
            if expected["schemaTitle"] != "system.Artifact" and (
                actual["schema_title"] != expected["schemaTitle"]
                or actual["schema_version"] != expected.get("schemaVersion", "0.0.1")
            ):
                raise DockflowError(f"Artifact type mismatch for {name}")
            observation = self.artifacts.verify(artifact["artifact_id"])
            if observation["availability"] != "available":
                raise DockflowError(
                    f"Input artifact {name} is {observation['availability']}"
                )
        return inputs

    @_project_mutation
    def create_experiment(self, name: str, description: str = "") -> dict:
        from .records import new_id, utc_now

        if (
            not isinstance(name, str)
            or not 1 <= len(name) <= 256
            or not isinstance(description, str)
            or len(description) > 4096
        ):
            raise DockflowError("Invalid experiment name or description")
        if self.store.database.queries.count(
            "experiments", filters={"sort_name": name}
        ):
            raise DockflowError(
                "Experiment display_name already exists", "CONFLICT", 409
            )
        return self.store.put(
            "experiments",
            {
                "experiment_id": new_id("experiment"),
                "display_name": name,
                "description": description,
                "created_at": utc_now(),
                "last_run_created_at": None,
            },
        )

    def submit(
        self,
        request: dict,
        idempotency_key: str | None = None,
        *,
        reserve: bool = False,
    ) -> tuple[dict, bool]:
        from .records import new_id, utc_now

        self.store.ensure_reconciled()
        only_fields(request, RUN_FIELDS)
        validate_json(request)
        submitted_request_digest = digest(request)
        if idempotency_key is not None and (
            not isinstance(idempotency_key, str)
            or not re.fullmatch(r"[\x20-\x7e]{1,128}", idempotency_key)
        ):
            raise DockflowError(
                "Idempotency-Key must be 1–128 printable ASCII characters"
            )
        if idempotency_key:
            prior = self.store.database.queries.select(
                "runs", filters={"idempotency_key": idempotency_key}, limit=1
            )
            previous = prior[0] if prior else None
            if (
                previous
                and previous.get("submitted_request_digest") == submitted_request_digest
            ):
                return previous, True
        definition = self._definition(request)
        try:
            parameters = validate_parameters(definition, request.get("parameters", {}))
            selected = validate_selection(definition, request.get("selection"))
        except (ValueError, TypeError) as exc:
            raise DockflowError(str(exc)) from exc
        inputs = self._inputs(definition, request.get("inputs", {}))
        for field in ("bindings", "use_executions"):
            if not isinstance(request.get(field, {}), dict):
                raise DockflowError(f"{field} must be an object")
        for binding, artifact_id in request.get("bindings", {}).items():
            task, sep, input_name = binding.rpartition(".")
            if (
                not sep
                or task not in definition.tasks
                or input_name
                not in definition.tasks[task]
                .component.get("inputDefinitions", {})
                .get("artifacts", {})
            ):
                raise DockflowError(f"Unknown task input binding: {binding}")
            observation = self.artifacts.verify(artifact_id)
            if observation["availability"] != "available":
                raise DockflowError(
                    f"Historical input is {observation['availability']}"
                )
        for task, attempt_id in request.get("use_executions", {}).items():
            if task not in definition.tasks:
                raise DockflowError(f"Unknown historical task selector: {task}")
            if self.store.get("attempts", attempt_id)["state"] != "succeeded":
                raise DockflowError("Historical attempt must have succeeded")
        reuse = request.get("reuse", {})
        only_fields(reuse, {"scope", "key"}, "reuse")
        scope = reuse.get("scope", self.settings.reuse["scope"])
        if scope not in {"global", "keyed", "run", "none"}:
            raise DockflowError("Invalid reuse scope")
        resolved_reuse = {"scope": scope}
        if scope == "keyed":
            key = reuse.get("key", self.settings.reuse.get("scope_key"))
            if not isinstance(key, str) or not key:
                raise DockflowError("Keyed reuse requires a nonempty key")
            resolved_reuse["key"] = key
        elif "key" in reuse:
            raise DockflowError("reuse.key is valid only for keyed scope")
        description = request.get("description", "")
        display_name = request.get("display_name", definition.name)
        if (
            not isinstance(description, str)
            or len(description) > 4096
            or not isinstance(display_name, str)
            or not display_name
            or len(display_name) > 256
        ):
            raise DockflowError("Invalid display_name or description")
        normalized = {
            **request,
            "pipeline_spec": definition.document,
            "parameters": parameters,
            "inputs": inputs,
            "reuse": resolved_reuse,
            "description": description,
            "display_name": display_name,
            "selection": request.get("selection", {"mode": "full"}),
            "bindings": request.get("bindings", {}),
            "use_executions": request.get("use_executions", {}),
        }
        normalized.pop("definition_id", None)
        normalized.pop("source_text", None)
        from .engine import validate_invocation

        try:
            plan = validate_invocation(
                definition,
                {**normalized, "definition_sha256": definition.sha256},
                self.settings,
                self.store,
                self.artifacts,
            )
        except UnsupportedCapability as exc:
            raise DockflowError(str(exc), "UNSUPPORTED_CAPABILITY", 422) from exc
        except (DefinitionError, ValueError, TypeError) as exc:
            raise DockflowError(str(exc)) from exc
        request_digest = digest(normalized)
        with self.mutex, self.store.database.transaction():
            if idempotency_key:
                prior = self.store.database.queries.select(
                    "runs", filters={"idempotency_key": idempotency_key}, limit=1
                )
                if prior:
                    previous = prior[0]
                    if previous["request_digest"] != request_digest:
                        raise DockflowError(
                            "Idempotency key was used for a different request",
                            "CONFLICT",
                            409,
                        )
                    return previous, True
            if (
                self.store.database.queries.count("runs", filters={"state": "queued"})
                >= self.settings.service["queue_capacity"]
            ):
                raise DockflowError("The service queue is full", "QUEUE_FULL", 429)
            experiment_id = request.get("experiment_id")
            if experiment_id:
                experiment = self.store.get("experiments", experiment_id)
            else:
                defaults = self.store.database.queries.select(
                    "experiments", filters={"sort_name": "Default"}, limit=1
                )
                experiment = (
                    defaults[0] if defaults else self.create_experiment("Default")
                )
            snapshot = (
                self.store.get("definitions", request["definition_id"])
                if "definition_id" in request
                else self.snapshot(definition)
            )
            now = utc_now()
            run = {
                **normalized,
                "run_id": new_id("run"),
                "project_id": self.settings.project_id,
                "definition_id": snapshot["definition_id"],
                "experiment_id": experiment["experiment_id"],
                "definition_sha256": definition.sha256,
                "component_ids": snapshot.get("component_ids", {}),
                "state": "queued",
                "created_at": now,
                "started_at": None,
                "finished_at": None,
                "task_ids": [],
                "outputs": {},
                "error": None,
                "idempotency_key": idempotency_key,
                "request_digest": request_digest,
                "submitted_request_digest": submitted_request_digest,
                "source_text": definition.raw_bytes.decode("utf-8"),
                "effective_configuration": self.settings.effective(),
                "execution_choices": ExecutionChoices.capture(
                    self.settings, plan["task_policies"]
                ).to_record(),
                "selected_tasks": sorted(selected),
                "resolved_plan": plan,
                "acceptance_sequence": self.store.database.current_sequence() + 1,
            }
            run = self.store.put("runs", run)
            if reserve:
                from .run_ownership import reserve as reserve_run

                reserve_run(
                    self.store,
                    run["run_id"],
                    self.settings.execution["run_lease_seconds"],
                )
            self.store.put("experiments", {**experiment, "last_run_created_at": now})
            return run, False

    def cancel(self, run_id: str, *, interruption: bool = False) -> dict:
        from .records import utc_now

        with self.mutex, self.store.stop_request(run_id):
            run = self.store.get("runs", run_id)
            if run["state"] in TERMINAL:
                return run
            self.store.append(
                "stop_intent",
                {
                    "run_id": run_id,
                    "reason": "interrupted" if interruption else "cancelled",
                },
            )
            changes: dict[str, Any] = {
                "stop_intent": True,
                "interruption_requested"
                if interruption
                else "cancellation_requested": True,
            }
            if run["state"] == "queued":
                changes.update(
                    state="interrupted" if interruption else "cancelled",
                    finished_at=utc_now(),
                )
            else:
                changes["state"] = "cancelling"
            return self.store.put("runs", {**run, **changes})

    def execute(
        self, run: dict, *, on_log: Callable[[str, str], None] | None = None
    ) -> dict:
        from .engine import execute_run

        with contextlib.redirect_stdout(sys.stderr):
            return execute_run(
                self.store, self.artifacts, self.settings, run, on_log=on_log
            )

    def page(
        self,
        collection: str,
        *,
        page_size: int = 50,
        page_token: str | None = None,
        filters: dict | None = None,
        sort_by: str = "created_at desc",
    ) -> dict:
        if not 1 <= page_size <= 200:
            raise DockflowError("page_size must be between 1 and 200")
        filters = {
            key: value for key, value in (filters or {}).items() if value is not None
        }
        query = {"collection": collection, "filters": filters, "sort_by": sort_by}
        pagination = self.store.project_metadata("pagination")
        key = (
            bytes.fromhex(pagination["key"])
            if pagination is not None
            else hashlib.sha256(self.settings.project_id.encode()).digest()
        )
        boundary = None
        if page_token:
            try:
                raw, signature = page_token.split(".")
                if not hmac.compare_digest(
                    hmac.new(key, raw.encode(), "sha256").hexdigest(), signature
                ):
                    raise ValueError("signature")
                token = loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
                if (
                    token["project"] != self.settings.project_id
                    or token["query"] != query
                ):
                    raise ValueError("query")
                boundary = token["boundary"]
            except (ValueError, KeyError, TypeError) as exc:
                raise DockflowError("Invalid or mismatched page token") from exc
        items = self.store.database.queries.select(
            collection,
            filters=filters,
            sort_by=sort_by,
            boundary=boundary,
            limit=page_size + 1,
        )
        id_key = {
            "definitions": "definition",
            "components": "component",
            "runs": "run",
            "artifacts": "artifact",
            "experiments": "experiment",
            "pipelines": "pipeline",
            "tasks": "task",
            "attempts": "attempt",
        }[collection] + "_id"
        sort_field = sort_by.split()[0]
        if sort_field == "display_name" and collection in {"pipelines", "definitions"}:
            sort_field = "name"

        def sort_value(item):
            if collection == "definitions" and sort_field == "name":
                return item.get("version_name") or item.get("name") or ""
            return item.get(sort_field) or ""

        selected = items[:page_size]
        next_token = None
        if len(items) > page_size:
            item = selected[-1]
            raw = (
                base64.urlsafe_b64encode(
                    json.dumps(
                        {
                            "project": self.settings.project_id,
                            "query": query,
                            "boundary": [sort_value(item), item[id_key]],
                        },
                        separators=(",", ":"),
                    ).encode()
                )
                .decode()
                .rstrip("=")
            )
            next_token = raw + "." + hmac.new(key, raw.encode(), "sha256").hexdigest()
        return {"items": selected, "next_page_token": next_token}

    def logs(
        self,
        run_id: str,
        task_id: str | None = None,
        attempt_id: str | None = None,
        cursor: str | None = None,
        limit_bytes: int = 65536,
    ) -> dict:
        run = self.store.get("runs", run_id)
        if not 1 <= limit_bytes <= 65536:
            raise DockflowError("limit_bytes must be between 1 and 65536")
        if task_id and self.store.get("tasks", task_id)["run_id"] != run_id:
            raise DockflowError("Task does not belong to Run")
        if attempt_id:
            attempt = self.store.get("attempts", attempt_id)
            if attempt["run_id"] != run_id or (
                task_id and attempt["task_id"] != task_id
            ):
                raise DockflowError("Attempt does not belong to requested Run/Task")
        context = {"run_id": run_id, "task_id": task_id, "attempt_id": attempt_id}
        try:
            position = (
                loads(base64.urlsafe_b64decode(cursor))
                if cursor
                else {**context, "sequence": 0, "offset": 0}
            )
            if any(position.get(key) != value for key, value in context.items()) or any(
                type(position.get(key)) is not int or position[key] < 0
                for key in ("sequence", "offset")
            ):
                raise ValueError("mismatched cursor")
        except (ValueError, UnicodeError, TypeError, AttributeError) as exc:
            raise DockflowError("Invalid log cursor") from exc
        entries = self.store.database.log_entries(
            run_id,
            sequence=position["sequence"],
            offset=position["offset"],
            task_id=task_id,
            attempt_id=attempt_id,
            limit=257,
        )
        matches = entries[:256]
        result, used = [], 0
        drained = len(entries) <= 256
        for entry in matches:
            offset = (
                position["offset"] if entry["sequence"] == position["sequence"] else 0
            )
            payload = entry["text"].encode()[offset:]
            fragment = payload[: limit_bytes - used].decode("utf-8", "ignore")
            if payload and not fragment:
                if not result:
                    raise DockflowError(
                        "limit_bytes cannot hold the next UTF-8 character; increase the limit"
                    )
                drained = False
                break
            consumed = len(fragment.encode())
            result.append({**entry, "text": fragment})
            used += consumed
            position = {
                **context,
                "sequence": entry["sequence"],
                "offset": offset + consumed if consumed < len(payload) else 0,
            }
            if consumed < len(payload):
                drained = False
                break
        return {
            "entries": result,
            "next_cursor": base64.urlsafe_b64encode(
                json.dumps(position, separators=(",", ":")).encode()
            ).decode(),
            "terminal": run["state"] in TERMINAL and drained,
        }
