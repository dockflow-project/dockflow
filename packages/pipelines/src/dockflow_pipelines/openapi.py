"""Native OpenAPI 3.1 schemas for the data-only API boundary."""

from copy import deepcopy
from typing import Any

from fastapi.openapi.utils import get_openapi


def enhance_openapi(app):
    def document():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            routes=app.routes,
            openapi_version="3.1.0",
        )

        def obj(properties, required=()):
            return {
                "type": "object",
                "properties": properties,
                "required": list(required),
                "additionalProperties": False,
            }

        string = {"type": "string"}
        mapping = {"type": "object", "additionalProperties": True}
        identifier_map = {"type": "object", "additionalProperties": string}
        selection = {
            "oneOf": [
                obj({"mode": {"const": "full"}}, ["mode"]),
                obj({"mode": {"const": "from"}, "task": string}, ["mode", "task"]),
                obj(
                    {
                        "mode": {"const": "tasks"},
                        "tasks": {
                            "type": "array",
                            "minItems": 1,
                            "uniqueItems": True,
                            "items": string,
                        },
                    },
                    ["mode", "tasks"],
                ),
            ]
        }
        reuse = obj(
            {
                "scope": {"enum": ["global", "keyed", "run", "none"]},
                "key": {"type": "string", "minLength": 1},
            }
        )
        definition_fields = {
            "definition_id": string,
            "pipeline_spec": mapping,
            "source_text": string,
        }
        run_create = obj(
            {
                **definition_fields,
                "display_name": {"type": "string", "minLength": 1, "maxLength": 256},
                "experiment_id": string,
                "description": {"type": "string", "maxLength": 4096, "default": ""},
                "parameters": mapping,
                "inputs": identifier_map,
                "selection": selection,
                "bindings": identifier_map,
                "use_executions": identifier_map,
                "reuse": reuse,
            }
        )
        run_create["oneOf"] = [
            {"required": ["definition_id"], "not": {"required": ["pipeline_spec"]}},
            {"required": ["pipeline_spec"], "not": {"required": ["definition_id"]}},
        ]
        validation = obj(
            {**definition_fields, "parameters": mapping, "inputs": identifier_map}
        )
        validation["oneOf"] = run_create["oneOf"]
        artifact_type = obj(
            {"schema_title": string, "schema_version": string},
            ["schema_title", "schema_version"],
        )
        owner = obj(
            {
                "schema_version": {"const": 1},
                "owner_id": {"type": "string", "format": "uuid"},
                "project_id": string,
                "hostname": string,
                "pid": {"type": "integer", "minimum": 1},
                "mode": {"enum": ["local", "service"]},
                "acquired_at": {"type": "string", "format": "date-time"},
                "endpoint": {"type": ["string", "null"]},
            }
        )
        ownership_detail = obj(
            {
                "field": string,
                "reason": string,
                "owner_metadata_status": {
                    "enum": [
                        "valid",
                        "malformed",
                        "oversized",
                        "unavailable",
                        "unsupported_schema",
                    ]
                },
                "owner": owner,
            },
            ["field", "reason"],
        )
        definitions = {
            "FilterOptions": obj(
                {
                    "remaining_count": {"type": "integer", "minimum": 0},
                    "items": {
                        "type": "array",
                        "maxItems": 10,
                        "items": obj(
                            {
                                "id": string,
                                "name": string,
                                "value": string,
                                "recent_at": string,
                            },
                            ["id", "name", "value", "recent_at"],
                        ),
                    },
                },
                ["items", "remaining_count"],
            ),
            "ReferenceNamesRequest": obj(
                {
                    "references": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 200,
                        "items": obj(
                            {
                                "collection": {
                                    "enum": [
                                        "runs",
                                        "tasks",
                                        "attempts",
                                        "pipelines",
                                        "definitions",
                                        "components",
                                        "experiments",
                                    ]
                                },
                                "id": string,
                            },
                            ["collection", "id"],
                        ),
                    },
                },
                ["references"],
            ),
            "ReferenceNames": obj(
                {
                    "items": {
                        "type": "array",
                        "items": obj(
                            {
                                "collection": string,
                                "id": string,
                                "name": {"type": ["string", "null"]},
                                "available": {"type": "boolean"},
                            },
                            ["collection", "id", "name", "available"],
                        ),
                    }
                },
                ["items"],
            ),
            "RunCreate": run_create,
            "ValidationRequest": validation,
            "ArtifactCreate": obj(
                {
                    "operation": {"enum": ["register", "import"]},
                    "uri": {"type": "string", "format": "uri"},
                    "type": artifact_type,
                    "version": string,
                    "metadata": mapping,
                },
                ["operation", "uri", "type"],
            ),
            "ArtifactUploadOptions": obj(
                {
                    "type": artifact_type,
                    "metadata": mapping,
                    "version": {"type": "string", "minLength": 1, "maxLength": 256},
                    "archive_mode": {"enum": ["keep", "extract"], "default": "keep"},
                },
                ["type"],
            ),
            "ExperimentCreate": obj(
                {
                    "display_name": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 256,
                    },
                    "description": {"type": "string", "maxLength": 4096},
                },
                ["display_name"],
            ),
            "CacheInvalidate": obj(
                {
                    "artifact_id": string,
                    "reason": {"type": "string", "minLength": 1, "maxLength": 256},
                },
                ["artifact_id", "reason"],
            ),
            "CacheReset": obj(
                {
                    "revision": {"type": "integer", "minimum": 0},
                    "reason": {"type": "string", "minLength": 1, "maxLength": 256},
                },
                ["revision", "reason"],
            ),
            "MaintenanceRequest": obj({"apply": {"type": "boolean", "default": False}}),
            "MetadataCheck": obj(
                {"verify_contents": {"type": "boolean", "default": False}}
            ),
            "Empty": obj({}),
            "Error": obj(
                {
                    "error": obj(
                        {
                            "code": string,
                            "message": string,
                            "details": {
                                "type": "array",
                                "items": ownership_detail,
                            },
                            "request_id": string,
                        },
                        ["code", "message", "details", "request_id"],
                    )
                },
                ["error"],
            ),
        }
        definitions.update(
            {
                "StorageScanRequest": obj({"prefix": string}),
                "StorageScanQuery": obj(
                    {
                        "scan_id": string,
                        "page_size": {"type": "integer", "minimum": 1, "maximum": 200},
                        "page_token": {"type": ["string", "null"]},
                        "selected": {
                            "type": "array",
                            "items": string,
                            "uniqueItems": True,
                        },
                        "orphans": {"type": "boolean"},
                        "classification": {"type": ["string", "null"]},
                        "artifact_id": {"type": ["string", "null"]},
                    },
                    ["scan_id"],
                ),
                "DeletionPlanRequest": obj(
                    {
                        "targets": {
                            "type": "array",
                            "items": obj(
                                {
                                    "collection": {
                                        "enum": ["runs", "attempts", "artifacts"]
                                    },
                                    "id": string,
                                },
                                ["collection", "id"],
                            ),
                        },
                        "scan_id": string,
                        "selected": {
                            "type": "array",
                            "items": string,
                            "uniqueItems": True,
                        },
                        "orphans": {"type": "boolean"},
                        "delete_files": {"type": "boolean", "default": False},
                    }
                ),
                "DeletionQuery": obj({"plan_id": string}, ["plan_id"]),
                "DeletionApply": obj(
                    {
                        "plan_id": string,
                        "confirmation": {
                            "type": ["string", "null"],
                            "description": "Exact DANGER is mandatory for manual storage deletion.",
                        },
                    },
                    ["plan_id"],
                ),
                "RetentionRequest": obj(
                    {
                        "apply": {"type": "boolean", "default": False},
                        "confirmation": {"type": ["string", "null"]},
                    }
                ),
                "StorageRow": obj(
                    {
                        "id": string,
                        "path": string,
                        "size_bytes": {"type": ["integer", "null"]},
                        "identity": {"type": ["object", "null"]},
                        "classification": {
                            "enum": [
                                "execution_artifact",
                                "manual_artifact",
                                "publication",
                                "retained_file",
                                "orphan",
                                "protected",
                                "unknown",
                            ]
                        },
                        "artifact_ids": {"type": "array", "items": string},
                        "blockers": {"type": "array", "items": string},
                        "eligible": {"type": "boolean"},
                        "pending_plan_ids": {"type": "array", "items": string},
                    },
                    [
                        "id",
                        "path",
                        "size_bytes",
                        "identity",
                        "classification",
                        "artifact_ids",
                        "blockers",
                        "eligible",
                    ],
                ),
                "DeletionPlan": {
                    "type": "object",
                    "properties": {
                        "plan_id": string,
                        "state": {
                            "enum": ["planned", "deleting", "partial", "completed"]
                        },
                        "targets": {"type": "array", "items": mapping},
                        "rows": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/StorageRow"},
                        },
                        "delete_files": {"type": "boolean"},
                        "estimated_bytes": {"type": "integer"},
                        "blockers": {"type": "array", "items": string},
                        "completed": {"type": "array", "items": string},
                        "failures": {"type": "array", "items": mapping},
                    },
                    "required": [
                        "plan_id",
                        "state",
                        "targets",
                        "rows",
                        "delete_files",
                        "estimated_bytes",
                        "blockers",
                        "completed",
                        "failures",
                    ],
                    "additionalProperties": True,
                },
                "StorageScanPage": {
                    "type": "object",
                    "properties": {
                        "scan_id": string,
                        "state": {"enum": ["scanning", "complete", "failed"]},
                        "items": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/StorageRow"},
                        },
                        "next_page_token": {"type": ["string", "null"]},
                        "totals": mapping,
                        "selected_ids": {"type": "array", "items": string},
                        "retention": mapping,
                    },
                    "required": [
                        "scan_id",
                        "state",
                        "items",
                        "next_page_token",
                        "totals",
                        "selected_ids",
                        "retention",
                    ],
                    "additionalProperties": True,
                },
            }
        )
        definitions["JsonPreviewNode"] = obj(
            {
                "kind": {
                    "enum": ["object", "array", "string", "number", "boolean", "null"]
                },
                "value": {
                    "type": ["string", "boolean", "null"],
                    "description": "Strings/keys are JSON-escaped display literals; numbers retain exact lexical spelling.",
                },
                "children": {
                    "type": "array",
                    "items": obj(
                        {
                            "key": string,
                            "node": {"$ref": "#/components/schemas/JsonPreviewNode"},
                        },
                        ["key", "node"],
                    ),
                },
            },
            ["kind"],
        )
        definitions["ArtifactContents"] = obj(
            {
                "artifact_id": string,
                "path": string,
                "name": string,
                "format": {
                    "enum": ["directory", "csv", "json", "image", "text", "unsupported"]
                },
                "size_bytes": {"type": "integer", "minimum": 0},
                "next_page_token": {"type": ["string", "null"]},
                "checksum_verified": {"type": "boolean"},
                "message": string,
                "items": {
                    "type": "array",
                    "items": obj(
                        {
                            "name": string,
                            "path": string,
                            "kind": {"enum": ["file", "directory"]},
                            "size_bytes": {"type": ["integer", "null"]},
                        },
                        ["name", "path", "kind", "size_bytes"],
                    ),
                },
                "total_entries": {"type": "integer", "minimum": 0},
                "columns": {"type": "array", "items": string},
                "rows": {"type": "array", "items": {"type": "array", "items": string}},
                "first_row": {"type": "integer", "minimum": 0},
                "last_row": {"type": "integer", "minimum": 0},
                "delimiter": string,
                "tree": {"$ref": "#/components/schemas/JsonPreviewNode"},
                "mime_type": {
                    "enum": ["image/png", "image/jpeg", "image/gif", "image/webp"]
                },
                "base64": {"type": "string", "contentEncoding": "base64"},
                "width": {"type": "integer", "minimum": 1, "maximum": 16384},
                "height": {"type": "integer", "minimum": 1, "maximum": 16384},
                "text": string,
                "truncated": {"type": "boolean"},
            },
            [
                "artifact_id",
                "path",
                "format",
                "size_bytes",
                "next_page_token",
                "checksum_verified",
                "message",
            ],
        )
        resources = {
            "Pipeline": (
                "pipeline_id name definition_id available created_at",
                {
                    "available": {"type": "boolean"},
                    "registration_origin": {"enum": ["configuration", "api"]},
                    "default_version_id": {"type": ["string", "null"]},
                    "description": string,
                    "version_ids": {"type": "array", "items": string},
                },
            ),
            "Run": (
                "run_id project_id definition_id experiment_id display_name state created_at started_at finished_at parameters inputs selection bindings use_executions reuse task_ids outputs execution_choices effective_configuration error",
                {
                    "state": {
                        "enum": [
                            "queued",
                            "running",
                            "cancelling",
                            "succeeded",
                            "failed",
                            "cancelled",
                            "interrupted",
                        ]
                    },
                    "parameters": mapping,
                    "inputs": identifier_map,
                    "selection": selection,
                    "bindings": identifier_map,
                    "use_executions": identifier_map,
                    "reuse": reuse,
                    "task_ids": {"type": "array", "items": string},
                    "outputs": identifier_map,
                    "execution_choices": {
                        "type": "object",
                        "description": "Versioned immutable execution settings admitted with this Run; coordinator access and local paths remain deployment settings.",
                    },
                    "effective_configuration": {
                        "type": "object",
                        "description": "Non-secret settings and winning setting origins captured at admission.",
                        "properties": {
                            "sources": {
                                "type": "object",
                                "description": "TOML setting paths map to their winning origin; config_path records file selection. No credential values are included.",
                                "additionalProperties": {
                                    "enum": [
                                        "file",
                                        "environment",
                                        "option",
                                        "default",
                                        "derived",
                                        "discovery",
                                    ],
                                },
                            },
                        },
                        "additionalProperties": True,
                    },
                    "error": {"type": ["object", "null"]},
                },
            ),
            "Task": (
                "task_id run_id name component_id definition_id state inputs outputs attempt_ids error",
                {
                    "inputs": identifier_map,
                    "outputs": identifier_map,
                    "attempt_ids": {"type": "array", "items": string},
                    "error": {"type": ["object", "null"]},
                },
            ),
            "Attempt": ("attempt_id task_id run_id state", {}),
            "Artifact": (
                "artifact_id type version metadata origin uri fingerprint availability publication_state producer created_at pinned",
                {
                    "type": artifact_type,
                    "metadata": mapping,
                    "fingerprint": mapping,
                    "producer": {"type": ["object", "null"]},
                    "pinned": {"type": "boolean"},
                    "upload": obj(
                        {
                            "filename": string,
                            "archive_mode": {"enum": ["keep", "extract"]},
                        },
                        ["filename", "archive_mode"],
                    ),
                },
            ),
            "Definition": (
                "definition_id kind name sha256 created_at available pipeline_spec compatibility_diagnostics pipeline_id registration_origin version_name description default_version_id",
                {
                    "available": {"type": "boolean"},
                    "pipeline_spec": mapping,
                    "compatibility_diagnostics": {"type": "array", "items": mapping},
                    "pipeline_id": {"type": ["string", "null"]},
                    "default_version_id": {"type": ["string", "null"]},
                    "registration_origin": {"enum": ["configuration", "api", None]},
                    "version_name": {"type": ["string", "null"]},
                },
            ),
            "Component": (
                "component_id definition_id name created_at available compiled executor",
                {
                    "available": {"type": "boolean"},
                    "compiled": mapping,
                    "executor": {"type": ["object", "null"]},
                },
            ),
            "Experiment": (
                "experiment_id display_name description created_at last_run_created_at",
                {},
            ),
        }
        for name, (fields, specialized) in resources.items():
            properties: dict[str, Any] = {
                field: deepcopy(string) for field in fields.split()
            }
            for field in (
                "started_at",
                "finished_at",
                "last_run_created_at",
                "version",
                "name",
                "component_id",
            ):
                if field in properties:
                    properties[field] = {"type": ["string", "null"]}
            properties.update(specialized)
            definitions[name] = {
                "type": "object",
                "properties": properties,
                "required": fields.split(),
                "additionalProperties": True,
            }
        schema.setdefault("components", {}).setdefault("schemas", {}).update(
            definitions
        )
        bodies = {
            "/ui/reference-names": "ReferenceNamesRequest",
            "/storage/scan": "StorageScanRequest",
            "/storage/scan/show": "StorageScanQuery",
            "/deletions/plan": "DeletionPlanRequest",
            "/deletions/show": "DeletionQuery",
            "/deletions/apply": "DeletionApply",
            "/retention": "RetentionRequest",
            "/runs": "RunCreate",
            "/definitions/validate": "ValidationRequest",
            "/definitions/refresh": "Empty",
            "/artifacts": "ArtifactCreate",
            "/experiments": "ExperimentCreate",
            "/metadata/check": "MetadataCheck",
            "/metadata/rebuild": "MaintenanceRequest",
            "/clean": "MaintenanceRequest",
            "/cache/{key}/invalidate": "CacheInvalidate",
            "/cache/{key}/reset": "CacheReset",
        }
        resource_names = {
            "pipelines": "Pipeline",
            "runs": "Run",
            "tasks": "Task",
            "attempts": "Attempt",
            "definitions": "Definition",
            "components": "Component",
            "artifacts": "Artifact",
            "experiments": "Experiment",
        }
        definitions["LogPage"] = obj(
            {
                "entries": {
                    "type": "array",
                    "items": obj(
                        {
                            "sequence": {"type": "integer"},
                            "timestamp": string,
                            "run_id": string,
                            "task_id": {"type": ["string", "null"]},
                            "attempt_id": {"type": ["string", "null"]},
                            "stream": {"enum": ["stdout", "stderr", "system"]},
                            "text": string,
                        },
                        [
                            "sequence",
                            "timestamp",
                            "run_id",
                            "task_id",
                            "attempt_id",
                            "stream",
                            "text",
                        ],
                    ),
                },
                "next_cursor": string,
                "terminal": {"type": "boolean"},
            },
            ["entries", "next_cursor", "terminal"],
        )
        schema["components"]["schemas"].update(definitions)
        schema["components"]["schemas"]["ArtifactLineage"] = obj(
            {
                "artifact_id": string,
                "producer": {"type": ["object", "null"]},
                "deleted_producer_ids": {"type": "array", "items": string},
                "items": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/Task"},
                },
                "next_page_token": {"type": ["string", "null"]},
            },
            ["artifact_id", "producer", "items", "next_page_token"],
        )
        schema["components"]["securitySchemes"] = {
            "BearerAuth": {"type": "http", "scheme": "bearer"}
        }
        native_filters = {
            "pipelines": ["name"],
            "definitions": ["name", "pipeline_id", "kind"],
            "components": ["name", "definition_id"],
            "runs": ["state", "experiment_id", "definition_id"],
            "tasks": ["state", "run_id", "input_artifact_id"],
            "attempts": ["state", "run_id", "task_id"],
            "artifacts": ["type", "availability"],
            "experiments": ["name"],
        }
        for fields in native_filters.values():
            fields.append("search")
        for upload_name in ("upload", "upload_version"):
            operation = schema["paths"][f"/apis/v2beta1/pipelines/{upload_name}"][
                "post"
            ]
            operation["summary"] = (
                "Upload a compiled pipeline"
                if upload_name == "upload"
                else "Upload an immutable pipeline version"
            )
            operation["description"] = (
                "Exactly one uploadfile part containing raw UTF-8 compiled KFP 2.17 YAML/JSON. The service request byte limit includes multipart overhead. Archives, URL fetching and tags are unsupported."
            )
            operation["requestBody"] = {
                "required": True,
                "content": {
                    "multipart/form-data": {
                        "schema": obj(
                            {"uploadfile": {"type": "string", "format": "binary"}},
                            ["uploadfile"],
                        )
                    }
                },
            }
            fields = [
                "name",
                "display_name",
                "description",
                "pipelineid" if upload_name == "upload_version" else "namespace",
            ]
            operation["parameters"] = [
                {
                    "name": field,
                    "in": "query",
                    "required": field == "pipelineid",
                    "schema": string,
                }
                for field in fields
            ]
            for status in (400, 401, 404, 409, 413, 422, 500, 503):
                operation["responses"][str(status)] = {
                    "description": "KFP google.rpc.Status error"
                }
        for path, methods in schema["paths"].items():
            if not path.startswith("/dockflow/v1/"):
                continue
            for method, operation in methods.items():
                if method not in {"get", "post"}:
                    continue
                operation["security"] = (
                    [{"BearerAuth": []}]
                    if app.state.core.settings.service.get("token_file")
                    else [{}, {"BearerAuth": []}]
                )
                operation.setdefault(
                    "description",
                    "Uses the service's configured bearer token when authentication is enabled.",
                )
                for status in (400, 401, 403, 404, 409, 410, 413, 422, 429, 500, 503):
                    operation.setdefault("responses", {})[str(status)] = {
                        "description": "Dockflow error",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    }
                if method == "post":
                    model = bodies.get(path.removeprefix("/dockflow/v1"), "Empty")
                    operation["requestBody"] = {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": f"#/components/schemas/{model}"}
                            }
                        },
                    }
                segments = path.removeprefix("/dockflow/v1/").split("/")
                collection = segments[0]
                model = resource_names.get(collection)
                success = None
                statuses = ["200"]
                if method == "get" and (
                    len(segments) == 1 or path.endswith("/lineage")
                ):
                    operation["parameters"] = (
                        [
                            *operation.get("parameters", []),
                            {
                                "name": "page_size",
                                "in": "query",
                                "schema": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "maximum": 200,
                                    "default": 50,
                                },
                            },
                            {"name": "page_token", "in": "query", "schema": string},
                            *[
                                {
                                    "name": field,
                                    "in": "query",
                                    "schema": string,
                                    "description": "Case-insensitive literal ID/name substring (maximum 256 characters)."
                                    if field == "search"
                                    else "Exact equality filter.",
                                }
                                for field in native_filters.get(collection, [])
                                if not path.endswith("/lineage")
                            ],
                        ]
                        if model
                        else operation.get("parameters", [])
                    )
                if path.endswith("/contents"):
                    success = {"$ref": "#/components/schemas/ArtifactContents"}
                    operation["parameters"] = [
                        *operation.get("parameters", []),
                        {
                            "name": "path",
                            "in": "query",
                            "schema": {
                                "type": "string",
                                "maxLength": 4096,
                                "default": "",
                            },
                        },
                        {
                            "name": "format",
                            "in": "query",
                            "schema": {
                                "enum": ["auto", "csv", "json", "image", "text"],
                                "default": "auto",
                            },
                        },
                        {
                            "name": "page_size",
                            "in": "query",
                            "schema": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 200,
                                "default": 50,
                            },
                        },
                        {
                            "name": "page_token",
                            "in": "query",
                            "schema": {"type": "string", "maxLength": 4096},
                        },
                    ]
                elif path.endswith("/lineage"):
                    success = {"$ref": "#/components/schemas/ArtifactLineage"}
                elif path.endswith("/logs"):
                    success = {"$ref": "#/components/schemas/LogPage"}
                    operation["parameters"] = [
                        *operation.get("parameters", []),
                        *[
                            {"name": field, "in": "query", "schema": string}
                            for field in ("task_id", "attempt_id", "cursor")
                        ],
                        {
                            "name": "limit_bytes",
                            "in": "query",
                            "schema": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 65536,
                                "default": 65536,
                            },
                        },
                    ]
                elif model and method == "get" and len(segments) == 1:
                    success = obj(
                        {
                            "items": {
                                "type": "array",
                                "items": {"$ref": f"#/components/schemas/{model}"},
                            },
                            "next_page_token": {"type": ["string", "null"]},
                        },
                        ["items", "next_page_token"],
                    )
                elif model and (
                    method == "get"
                    or len(segments) == 1
                    or segments[-1] in {"pin", "unpin", "cancel"}
                ):
                    success = {"$ref": f"#/components/schemas/{model}"}
                    if method == "post" and len(segments) == 1:
                        statuses = ["200", "202"] if collection == "runs" else ["201"]
                if path == "/dockflow/v1/artifacts/upload" and method == "post":
                    operation["description"] = (
                        "Upload and register one manual managed artifact. Exactly one uploadfile "
                        "file and one options text field containing an ArtifactUploadOptions JSON "
                        "object. No query arguments. The service request byte limit includes "
                        "multipart overhead. ZIP keep preserves bytes; extract creates a directory "
                        "(256 MiB expanded, 10,000 entries, 32 path levels). No automatic retries."
                    )
                    operation["requestBody"] = {
                        "required": True,
                        "content": {
                            "multipart/form-data": {
                                "schema": obj(
                                    {
                                        "uploadfile": {
                                            "type": "string",
                                            "format": "binary",
                                        },
                                        "options": {
                                            "type": "string",
                                            "contentMediaType": "application/json",
                                            "contentSchema": {
                                                "$ref": "#/components/schemas/ArtifactUploadOptions"
                                            },
                                            "description": "JSON text conforming to ArtifactUploadOptions (maximum 64 KiB).",
                                        },
                                    },
                                    ["uploadfile", "options"],
                                )
                            }
                        },
                    }
                    success = {"$ref": "#/components/schemas/Artifact"}
                    statuses = ["201"]
                if path == "/dockflow/v1/ui/reference-names":
                    success = {"$ref": "#/components/schemas/ReferenceNames"}
                    operation["description"] = (
                        "Read-only project-scoped name lookup for 1–200 requested references; unavailable/retired context returns null without disclosing retired records. Available during execution."
                    )
                if path == "/dockflow/v1/ui/filter-options":
                    success = {"$ref": "#/components/schemas/FilterOptions"}
                    operation["parameters"] = [
                        {
                            "name": "collection",
                            "in": "query",
                            "required": True,
                            "schema": {
                                "enum": [
                                    "pipelines",
                                    "definitions",
                                    "components",
                                    "experiments",
                                    "runs",
                                    "tasks",
                                    "attempts",
                                    "artifacts",
                                ]
                            },
                        },
                        {
                            "name": "search",
                            "in": "query",
                            "schema": {
                                "type": "string",
                                "maxLength": 256,
                                "default": "",
                            },
                        },
                        {
                            "name": "field",
                            "in": "query",
                            "schema": {"enum": ["type"]},
                            "description": "Distinct artifact type suggestions; only valid with collection=artifacts.",
                        },
                        *[
                            {
                                "name": name,
                                "in": "query",
                                "schema": string,
                                "description": "Exact selected parent ID. Supported only for dependent resource collections.",
                            }
                            for name in (
                                "definition_id",
                                "experiment_id",
                                "run_id",
                                "task_id",
                            )
                        ],
                    ]
                    operation["description"] = (
                        "Read-only project-scoped ID/name substring suggestions, at most ten, with exact remaining_count. Newest first (execution start with creation fallback for workloads; definition/creation date otherwise). Empty search returns recent options. Parent scopes: components by definition_id; runs by definition_id/experiment_id; definitions used by live runs in experiment_id; tasks by run_id; attempts by run_id/task_id. Optional field=type returns distinct artifact types. No payload storage reads."
                    )
                if collection == "deletions":
                    success = {"$ref": "#/components/schemas/DeletionPlan"}
                elif collection == "storage":
                    success = {"$ref": "#/components/schemas/StorageScanPage"}
                elif collection == "retention":
                    success = mapping
                if success is not None:
                    for status in statuses:
                        operation["responses"][status] = {
                            "description": "Successful operation",
                            "content": {"application/json": {"schema": success}},
                        }
                if path == "/dockflow/v1/runs" and method == "post":
                    operation["parameters"] = [
                        {
                            "name": "Idempotency-Key",
                            "in": "header",
                            "schema": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 128,
                            },
                            "description": "Reuse this key only for the same request when retrying after uncertain response loss.",
                        }
                    ]
        app.openapi_schema = schema
        return schema

    app.openapi = document
