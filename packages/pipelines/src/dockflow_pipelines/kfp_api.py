"""Bounded KFP 2.17 v2beta1 adapter; native extensions stay on native routes."""

from fastapi import Request
from fastapi.responses import JSONResponse
from python_multipart.exceptions import MultipartParseError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from .core import only_fields
from .errors import DockflowError

STATES = {
    "queued": "PENDING",
    "pending": "PENDING",
    "running": "RUNNING",
    "cancelling": "CANCELING",
    "succeeded": "SUCCEEDED",
    "failed": "FAILED",
    "blocked": "FAILED",
    "interrupted": "FAILED",
    "cancelled": "CANCELED",
    "reused": "SKIPPED",
    "skipped": "SKIPPED",
}


def kfp_error(error: DockflowError):
    codes = {
        400: 3,
        401: 16,
        403: 7,
        404: 5,
        409: 9,
        410: 5,
        413: 8,
        422: 3,
        429: 8,
        500: 13,
        501: 12,
        503: 14,
    }
    return JSONResponse(
        {"code": codes.get(error.status, 2), "message": error.message, "details": []},
        status_code=error.status,
    )


def experiment_view(record):
    return {
        **{
            key: record.get(key)
            for key in (
                "experiment_id",
                "display_name",
                "description",
                "created_at",
                "last_run_created_at",
            )
        },
        "namespace": "",
        "storage_state": "AVAILABLE",
    }


def pipeline_view(record):
    return {
        "pipeline_id": record["pipeline_id"],
        "display_name": record["name"],
        "name": record["name"],
        "created_at": record["created_at"],
        "description": record.get("description", ""),
        "namespace": "",
    }


def version_view(record):
    return {
        "pipeline_id": record["pipeline_id"],
        "pipeline_version_id": record["definition_id"],
        "display_name": record.get("version_name")
        or record.get("name")
        or record["definition_id"],
        "name": record.get("version_name")
        or record.get("name")
        or record["definition_id"],
        "created_at": record["created_at"],
        "pipeline_spec": record["pipeline_spec"],
        "description": record.get("description", ""),
    }


def run_view(core, record):
    details = []
    for task_id in record.get("task_ids", []):
        task = core.store.get("tasks", task_id)
        item = {
            "run_id": record["run_id"],
            "task_id": task_id,
            "display_name": task["name"],
            "state": STATES[task["state"]],
            "create_time": task.get("created_at"),
            "start_time": task.get("started_at"),
            "end_time": task.get("finished_at"),
        }
        if task.get("attempt_ids") and core.store.index:
            attempt_id = task["attempt_ids"][-1]
            execution = core.store.index.store.get_execution_by_type_and_name(
                "dockflow.v1.attempt", attempt_id
            )
            if execution:
                item["execution_id"] = str(execution.id)
        for field in ("inputs", "outputs"):
            mapped = {}
            if core.store.index:
                for name, artifact_id in task.get(field, {}).items():
                    if not isinstance(artifact_id, str):
                        continue
                    node = core.store.index.store.get_artifact_by_type_and_name(
                        "dockflow.v1.artifact", artifact_id
                    )
                    if node:
                        mapped[name] = {"artifact_ids": [str(node.id)]}
            item[field] = mapped
        if task.get("error"):
            item["error"] = {"code": 2, "message": str(task["error"]), "details": []}
        details.append(item)
    result = {
        key: record.get(key)
        for key in (
            "run_id",
            "experiment_id",
            "display_name",
            "description",
            "created_at",
            "finished_at",
        )
    }
    result.update(
        {
            "state": STATES[record["state"]],
            "storage_state": "AVAILABLE",
            "pipeline_version_id": record["definition_id"],
            "pipeline_spec": record["pipeline_spec"],
            "runtime_config": {"parameters": record["parameters"]},
            "scheduled_at": record.get("started_at"),
            "run_details": {"task_details": details},
        }
    )
    if record.get("error"):
        result["error"] = {"code": 2, "message": str(record["error"]), "details": []}
    return result


def mount_kfp(app, core, scheduler):
    prefix = "/apis/v2beta1"

    def values(request, allowed):
        if set(request.query_params) - allowed or any(
            len(request.query_params.getlist(key)) != 1 for key in request.query_params
        ):
            raise DockflowError("Unsupported or duplicate KFP query arguments")
        query = dict(request.query_params)
        if query.get("namespace"):
            raise DockflowError("Namespaces are unsupported")
        query.pop("namespace", None)
        return query

    class CompleteMultipartParser(MultiPartParser):
        """Require the parser's terminal boundary, including for truncated files."""

        complete = False

        def on_end(self):
            super().on_end()
            self.complete = True

        async def parse(self):
            form = await super().parse()
            if not self.complete:
                await form.close()
                raise MultiPartException("Incomplete multipart body")
            return form

    async def upload(request: Request, *, version: bool):
        if not scheduler.ready:
            raise DockflowError("Service is not ready", "UNAVAILABLE", 503)
        allowed = {"name", "display_name", "description"} | (
            {"pipelineid"} if version else {"namespace"}
        )
        if set(request.query_params) - allowed or any(
            len(request.query_params.getlist(key)) != 1 for key in request.query_params
        ):
            raise DockflowError("Unsupported or duplicate KFP upload query arguments")
        query = dict(request.query_params)
        if query.get("namespace"):
            raise DockflowError(
                "Namespaces are unsupported", "UNSUPPORTED_CAPABILITY", 422
            )
        if (
            "name" in query
            and "display_name" in query
            and query["name"] != query["display_name"]
        ):
            raise DockflowError("name and display_name must agree")
        name = query.get("display_name", query.get("name"))
        if version and (not query.get("pipelineid") or name is None):
            raise DockflowError(
                "Version uploads require pipelineid and name/display_name"
            )
        parser = CompleteMultipartParser(
            request.headers,
            request.stream(),
            max_files=1,
            max_fields=0,
            max_part_size=core.settings.service["request_max_bytes"],
        )
        try:
            form = await parser.parse()
            try:
                parts = form.multi_items()
                if (
                    len(parts) != 1
                    or parts[0][0] != "uploadfile"
                    or not isinstance(parts[0][1], UploadFile)
                ):
                    raise DockflowError(
                        "Multipart must contain exactly one uploadfile file and no other fields"
                    )
                raw = await parts[0][1].read()
            finally:
                await form.close()
        except (MultiPartException, MultipartParseError, ValueError, KeyError) as exc:
            # Starlette closes files for semantic parser failures. Low-level
            # malformed syntax can fail before that cleanup path.
            for stream in parser._files_to_close_on_error:
                stream.close()
            raise DockflowError("Invalid multipart pipeline upload") from exc
        if (
            raw.startswith((b"PK\x03\x04", b"PK\x05\x06", b"\x1f\x8b"))
            or raw[257:262] == b"ustar"
        ):
            raise DockflowError(
                "Archive uploads are unsupported; upload compiled UTF-8 YAML/JSON",
                "UNSUPPORTED_CAPABILITY",
                422,
            )
        try:
            source = raw.decode("utf-8")
        except UnicodeError as exc:
            raise DockflowError("Pipeline upload must be UTF-8 YAML/JSON") from exc
        catalog, definition = await run_in_threadpool(
            core.upload_pipeline,
            source,
            name,
            query.get("description", ""),
            query.get("pipelineid") if version else None,
        )
        return version_view(definition) if version else pipeline_view(catalog)

    @app.post(prefix + "/pipelines/upload")
    async def upload_pipeline(request: Request):
        return await upload(request, version=False)

    @app.post(prefix + "/pipelines/upload_version")
    async def upload_pipeline_version(request: Request):
        return await upload(request, version=True)

    def listing(request, collection, envelope, view, extra=None):
        query = values(
            request,
            {
                "page_size",
                "page_token",
                "sort_by",
                "filter",
                "namespace",
                "experiment_id",
            },
        )
        filters = dict(extra or {})
        if query.get("experiment_id"):
            if collection != "runs":
                raise DockflowError("experiment_id applies only to Runs")
            filters["experiment_id"] = query["experiment_id"]
        if query.get("filter"):
            if collection not in {"experiments", "pipelines"}:
                raise DockflowError("This KFP collection does not support filters")
            try:
                from .canonical import loads

                parsed = loads(query["filter"])
                only_fields(parsed, {"predicates"}, "filter")
                predicates = parsed["predicates"]
                if not isinstance(predicates, list) or len(predicates) != 1:
                    raise ValueError("one predicate required")
                predicate = predicates[0]
                only_fields(
                    predicate,
                    {"operation", "key", "stringValue", "string_value"},
                    "filter predicate",
                )
                if (
                    predicate["operation"] not in {"EQUALS", 1}
                    or predicate["key"] != "display_name"
                    or ("stringValue" in predicate) == ("string_value" in predicate)
                ):
                    raise ValueError("unsupported predicate")
                filters["display_name" if collection == "experiments" else "name"] = (
                    predicate.get("stringValue", predicate.get("string_value"))
                )
            except (ValueError, KeyError, TypeError) as exc:
                raise DockflowError(
                    "Only a single display_name EQUALS predicate is supported"
                ) from exc
        sort = query.get("sort_by", "created_at desc")
        if sort not in {
            "",
            "created_at",
            "created_at asc",
            "created_at desc",
            "display_name",
            "display_name asc",
            "display_name desc",
        }:
            raise DockflowError("Unsupported KFP sort_by")
        if collection == "pipelines":
            filters["registration"] = True
        try:
            size = int(query.get("page_size", 50))
        except ValueError as exc:
            raise DockflowError("Invalid KFP page_size") from exc
        with core.mutex:
            page = core.page(
                collection,
                page_size=size or 50,
                page_token=query.get("page_token"),
                filters=filters,
                sort_by=sort or "created_at desc",
            )
            total = len(
                [
                    item
                    for item in core.store.list(collection)
                    if all(item.get(key) == value for key, value in filters.items())
                ]
            )
            return {
                envelope: [view(item) for item in page["items"]],
                "total_size": total,
                "next_page_token": page["next_page_token"] or "",
            }

    @app.get(prefix + "/healthz")
    def health():
        return {"multi_user": False, "pipeline_store": "database"}

    @app.post(prefix + "/experiments")
    def create_experiment(request: Request):
        body = request.state.body
        only_fields(body, {"display_name", "description", "namespace"})
        if body.get("namespace"):
            raise DockflowError("Namespaces are unsupported")
        if "display_name" not in body:
            raise DockflowError("display_name is required")
        with core.mutex:
            return experiment_view(
                core.create_experiment(
                    body["display_name"], body.get("description", "")
                )
            )

    @app.get(prefix + "/experiments")
    def list_experiments(request: Request):
        return listing(request, "experiments", "experiments", experiment_view)

    @app.get(prefix + "/experiments/{id}")
    def get_experiment(id: str):
        return experiment_view(core.store.get("experiments", id))

    @app.post(prefix + "/runs")
    def create_run(request: Request):
        if not scheduler.ready:
            raise DockflowError("Service is not ready", "UNAVAILABLE", 503)
        body = request.state.body
        only_fields(
            body,
            {
                "experiment_id",
                "display_name",
                "description",
                "pipeline_spec",
                "pipeline_version_reference",
                "runtime_config",
            },
        )
        if ("pipeline_spec" in body) == ("pipeline_version_reference" in body):
            raise DockflowError(
                "Exactly one pipeline_spec or pipeline_version_reference is required"
            )
        native = {
            key: body[key]
            for key in ("experiment_id", "display_name", "description")
            if body.get(key) is not None and body.get(key) != ""
        }
        runtime = body.get("runtime_config") or {}
        only_fields(runtime, {"parameters", "pipeline_root"}, "runtime_config")
        artifact_options = core.settings.artifacts
        expected_root = (
            str(artifact_options.get("root", artifact_options["managed_root"]))
            if artifact_options["backend"] == "filesystem"
            else f"s3://{artifact_options['bucket']}/{artifact_options['prefix']}".rstrip(
                "/"
            )
        )
        if runtime.get("pipeline_root") and runtime["pipeline_root"].rstrip(
            "/"
        ) != expected_root.rstrip("/"):
            raise DockflowError(
                "runtime_config.pipeline_root cannot override configured storage"
            )
        native["parameters"] = runtime.get("parameters", {})
        if "pipeline_spec" in body:
            native["pipeline_spec"] = body["pipeline_spec"]
        else:
            reference = body["pipeline_version_reference"]
            only_fields(
                reference,
                {"pipeline_id", "pipeline_version_id"},
                "pipeline_version_reference",
            )
            if not reference.get("pipeline_id"):
                raise DockflowError("pipeline_id is required")
            with core.mutex:
                catalog = core.store.get("pipelines", reference["pipeline_id"])
                definition_id = (
                    reference.get("pipeline_version_id") or catalog["definition_id"]
                )
                definition = core.store.get("definitions", definition_id)
                if definition.get("pipeline_id") != catalog["pipeline_id"]:
                    raise DockflowError(
                        "Pipeline version does not belong to this Pipeline"
                    )
            native["definition_id"] = definition_id
        with core.mutex:
            run, _ = core.submit(native, request.headers.get("idempotency-key"))
            return run_view(core, run)

    @app.get(prefix + "/runs")
    def list_runs(request: Request):
        return listing(request, "runs", "runs", lambda record: run_view(core, record))

    @app.get(prefix + "/runs/{id}")
    def get_run(id: str):
        with core.mutex:
            return run_view(core, core.store.get("runs", id))

    @app.post(prefix + "/runs/{id}:terminate")
    def terminate(id: str, request: Request):
        only_fields(request.state.body, set())
        with core.mutex:
            core.cancel(id)
        return {}

    @app.get(prefix + "/pipelines")
    def list_pipelines(request: Request):
        return listing(request, "pipelines", "pipelines", pipeline_view)

    @app.get(prefix + "/pipelines/{id}")
    def get_pipeline(id: str):
        with core.mutex:
            return pipeline_view(core.store.get("pipelines", id))

    @app.get(prefix + "/pipelines/{pipeline_id}/versions")
    def list_versions(pipeline_id: str, request: Request):
        with core.mutex:
            core.store.get("pipelines", pipeline_id)
            return listing(
                request,
                "definitions",
                "pipeline_versions",
                version_view,
                {"pipeline_id": pipeline_id},
            )

    @app.get(prefix + "/pipelines/{pipeline_id}/versions/{id}")
    def get_version(pipeline_id: str, id: str):
        with core.mutex:
            record = core.store.get("definitions", id)
            if record.get("pipeline_id") != pipeline_id:
                raise DockflowError(
                    "Pipeline version not found in this Pipeline", "NOT_FOUND", 404
                )
            return version_view(record)

    @app.api_route(
        "/apis/{version}/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        include_in_schema=False,
    )
    def unsupported(version: str, path: str):
        if version in {"v1beta1", "v2beta1"} and path.split("/")[0] in {
            "pipelines",
            "runs",
            "experiments",
            "recurringruns",
            "artifacts",
            "visualizations",
            "mlmd",
        }:
            raise DockflowError(
                "This KFP operation is outside the supported profile",
                "UNIMPLEMENTED",
                501,
            )
        raise DockflowError("Unknown KFP route", "NOT_FOUND", 404)
