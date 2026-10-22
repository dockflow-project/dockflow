"""Lazy ML Metadata projection of accepted Dockflow control records.

MLMD is a rebuildable query and lineage index. Durable acceptance, record replay,
and output-set commitment remain owned by ControlStore, not this adapter.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from .canonical import json_bytes, loads
from .errors import DockflowError
from .records import COLLECTIONS, MAPPING_VERSION


class MLMDIndex:
    """Lazy optional-native dependency boundary; this is the only query index."""

    def __init__(self, path: Path, project_id: str, *, read_only: bool = False):
        self.read_only = read_only
        try:
            module = importlib.import_module(
                "ml_metadata.metadata_store.metadata_store"
            )
            self.pb = importlib.import_module("ml_metadata.proto.metadata_store_pb2")
            self.mlmd_errors = importlib.import_module("ml_metadata.errors")
        except (ImportError, OSError) as exc:
            raise DockflowError(
                "MLMD runtime is unavailable. Install dockflow-pipelines[runtime] "
                "with a supported Python/native runtime (CPython 3.12 or 3.13).",
                code="UNAVAILABLE",
                status=503,
            ) from exc
        if read_only:
            if not path.is_file():
                raise DockflowError(
                    "MLMD index is missing", code="NOT_FOUND", status=404
                )
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
        config = self.pb.ConnectionConfig()
        config.sqlite.filename_uri = str(path)
        config.sqlite.connection_mode = (
            self.pb.SqliteMetadataSourceConfig.READONLY
            if read_only
            else self.pb.SqliteMetadataSourceConfig.READWRITE_OPENCREATE
        )
        try:
            self.store = module.MetadataStore(config, enable_upgrade_migration=False)
        except Exception as exc:
            raise DockflowError(
                "MLMD index cannot be opened; use an offline metadata rebuild to recover its index from accepted records",
                code="CONFLICT",
                status=409,
            ) from exc
        self.project_id = project_id
        if read_only:
            try:
                self.context_types = {
                    kind: self.store.get_context_type(f"dockflow.v1.{kind}").id
                    for kind in (
                        "project",
                        "pipeline",
                        "component",
                        "definition",
                        "experiment",
                        "run",
                        "task",
                    )
                }
                self.artifact_type = self.store.get_artifact_type(
                    "dockflow.v1.artifact"
                ).id
                self.execution_type = self.store.get_execution_type(
                    "dockflow.v1.attempt"
                ).id
                projects = self.store.get_contexts_by_type("dockflow.v1.project")
                if (
                    len(projects) != 1
                    or projects[0].name != project_id
                    or projects[0]
                    .custom_properties["dockflow_mapping_version"]
                    .int_value
                    != MAPPING_VERSION
                ):
                    raise ValueError("Project identity or mapping version mismatch")
            except Exception as exc:
                raise DockflowError(
                    "MLMD index identity or mapping is incompatible",
                    code="CONFLICT",
                    status=409,
                ) from exc
            return
        self.context_types = {
            kind: self.store.put_context_type(
                self.pb.ContextType(name=f"dockflow.v1.{kind}")
            )
            for kind in (
                "project",
                "pipeline",
                "component",
                "definition",
                "experiment",
                "run",
                "task",
            )
        }
        self.artifact_type = self.store.put_artifact_type(
            self.pb.ArtifactType(name="dockflow.v1.artifact")
        )
        self.execution_type = self.store.put_execution_type(
            self.pb.ExecutionType(name="dockflow.v1.attempt")
        )
        projects = self.store.get_contexts_by_type("dockflow.v1.project")
        if any(project.name != project_id for project in projects):
            raise DockflowError(
                "MLMD index belongs to a different project", code="CONFLICT", status=409
            )
        self._context("project", {"project_id": project_id, "schema_version": 1})

    def _context(self, kind: str, resource: dict[str, Any]) -> Any:
        public_id = resource[f"{kind}_id"]
        node = self.store.get_context_by_type_and_name(f"dockflow.v1.{kind}", public_id)
        if node is None:
            node = self.pb.Context(type_id=self.context_types[kind], name=public_id)
        node.custom_properties["dockflow_resource_json"].string_value = json_bytes(
            resource
        ).decode()
        node.custom_properties["dockflow_project_id"].string_value = self.project_id
        node.custom_properties["dockflow_mapping_version"].int_value = MAPPING_VERSION
        node.id = self.store.put_contexts([node])[0]
        return node

    def _contexts(self, resource: dict[str, Any]) -> list[Any]:
        nodes = [
            self.store.get_context_by_type_and_name(
                "dockflow.v1.project", self.project_id
            )
        ]
        for kind in (
            "pipeline",
            "component",
            "definition",
            "experiment",
            "run",
            "task",
        ):
            public_id = resource.get(f"{kind}_id")
            if public_id:
                node = self.store.get_context_by_type_and_name(
                    f"dockflow.v1.{kind}", public_id
                )
                if node:
                    nodes.append(node)
        return [node for node in nodes if node is not None]

    def put(self, collection: str, resource: dict[str, Any]) -> None:
        if self.read_only:
            raise DockflowError(
                "Read-only MLMD inspection cannot mutate its index",
                code="CONFLICT",
                status=409,
            )
        kind = COLLECTIONS[collection]
        if kind not in {"attempt", "artifact"}:
            node = self._context(kind, resource)
            parent_fields = {
                "pipeline": (),
                "component": () if resource.get("registration") else ("definition_id",),
                "definition": ("pipeline_id",),
                "experiment": (),
                "run": ("pipeline_id", "definition_id", "experiment_id"),
                "task": ("run_id", "definition_id", "component_id"),
            }[kind]
            # Catalog registrations point at their current definition, while a
            # definition belongs to a catalog. Only the ownership direction is
            # a parent edge; treating every foreign key as a parent forms cycles.
            parents = {key: resource[key] for key in parent_fields if resource.get(key)}
            for parent in self._contexts(parents):
                if parent.id != node.id:
                    try:
                        self.store.put_parent_contexts(
                            [
                                self.pb.ParentContext(
                                    parent_id=parent.id, child_id=node.id
                                )
                            ]
                        )
                    except self.mlmd_errors.AlreadyExistsError:
                        pass
            if (
                kind in {"pipeline", "component"}
                and resource.get("registration")
                and resource.get("definition_id")
            ):
                definition = self.store.get_context_by_type_and_name(
                    "dockflow.v1.definition", resource["definition_id"]
                )
                if definition:
                    try:
                        self.store.put_parent_contexts(
                            [
                                self.pb.ParentContext(
                                    parent_id=node.id, child_id=definition.id
                                )
                            ]
                        )
                    except self.mlmd_errors.AlreadyExistsError:
                        pass
            return
        if kind == "artifact":
            node = self.store.get_artifact_by_type_and_name(
                "dockflow.v1.artifact", resource["artifact_id"]
            )
            if node is None:
                node = self.pb.Artifact(
                    type_id=self.artifact_type, name=resource["artifact_id"]
                )
            node.uri = resource.get("content_uri") or resource.get("descriptor_uri", "")
            node.state = (
                self.pb.Artifact.LIVE
                if resource.get("publication_state") == "committed"
                else self.pb.Artifact.PENDING
            )
            node.custom_properties["dockflow_resource_json"].string_value = json_bytes(
                resource
            ).decode()
            node.id = self.store.put_artifacts([node])[0]
            contexts = self._contexts({**resource, **(resource.get("producer") or {})})
            self.store.put_attributions_and_associations(
                [
                    self.pb.Attribution(context_id=context.id, artifact_id=node.id)
                    for context in contexts
                ],
                [],
            )
            return
        node = self.store.get_execution_by_type_and_name(
            "dockflow.v1.attempt", resource["attempt_id"]
        )
        if node is None:
            node = self.pb.Execution(
                type_id=self.execution_type, name=resource["attempt_id"]
            )
        node.last_known_state = {
            "succeeded": self.pb.Execution.COMPLETE,
            "failed": self.pb.Execution.FAILED,
            "cancelled": self.pb.Execution.CANCELED,
            "interrupted": self.pb.Execution.FAILED,
        }.get(str(resource.get("state", "running")), self.pb.Execution.RUNNING)
        node.custom_properties["dockflow_resource_json"].string_value = json_bytes(
            resource
        ).decode()
        node.id = self.store.put_executions([node])[0]
        self.store.put_attributions_and_associations(
            [],
            [
                self.pb.Association(context_id=context.id, execution_id=node.id)
                for context in self._contexts(resource)
            ],
        )
        existing = self.store.get_events_by_execution_ids([node.id])
        keys = {
            (
                event.artifact_id,
                event.type,
                tuple(step.key for step in event.path.steps),
            )
            for event in existing
        }
        for field, event_type in (
            ("inputs", self.pb.Event.INPUT),
            ("outputs", self.pb.Event.OUTPUT),
        ):
            for name, value in resource.get(field, {}).items():
                public_id = (
                    value.get("artifact_id") if isinstance(value, dict) else value
                )
                artifact = self.store.get_artifact_by_type_and_name(
                    "dockflow.v1.artifact", public_id
                )
                if artifact is None:
                    raise DockflowError(
                        f"Dangling MLMD binding: {public_id}",
                        code="CONFLICT",
                        status=409,
                    )
                if (artifact.id, event_type, (name,)) not in keys:
                    event = self.pb.Event(
                        execution_id=node.id, artifact_id=artifact.id, type=event_type
                    )
                    event.path.steps.add().key = name
                    self.store.put_events([event])

    def list(self, collection: str) -> list[dict[str, Any]]:
        kind = COLLECTIONS[collection]
        if kind == "artifact":
            nodes = self.store.get_artifacts_by_type("dockflow.v1.artifact")
        elif kind == "attempt":
            nodes = self.store.get_executions_by_type("dockflow.v1.attempt")
        else:
            nodes = self.store.get_contexts_by_type(f"dockflow.v1.{kind}")
        return [
            loads(node.custom_properties["dockflow_resource_json"].string_value)
            for node in nodes
        ]
