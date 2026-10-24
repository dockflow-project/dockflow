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
                                    "description": "Exact equality filter.",
                                }
                                for field in native_filters.get(collection, [])
                                if not path.endswith("/lineage")
                            ],
                        ]
                        if model
                        else operation.get("parameters", [])
                    )
                if path.endswith("/lineage"):
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
