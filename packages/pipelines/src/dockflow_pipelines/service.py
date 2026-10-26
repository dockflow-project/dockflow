"""Native REST API and a single durable owner with isolated Run workers."""

from __future__ import annotations

import contextlib
import logging
import multiprocessing
import re
import threading
import time
from collections.abc import AsyncIterator
from urllib.parse import urlsplit

from dockflow_core.canonical import loads
from dockflow_core.errors import DockflowError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from .core import Core, capabilities, only_fields
from .operations import operate
from .records import TERMINAL

LOGGER = logging.getLogger(__name__)


def _route_path(request: Request) -> str:
    """Use the router's path, independent of URL reconstruction from headers."""
    path = request.scope["path"]
    root = request.scope.get("root_path", "")
    if root and (path == root or path.startswith(root + "/")):
        return path[len(root) :]
    return path


def _validate_host(request: Request) -> None:
    hosts = request.headers.getlist("host")
    if len(hosts) != 1:
        raise DockflowError("Exactly one Host header is required")
    host = hosts[0]
    try:
        authority = urlsplit("//" + host)
        invalid = (
            not authority.hostname
            or authority.netloc != host
            or authority.username is not None
            or "\\" in host
            or any(ord(character) <= 32 or ord(character) >= 127 for character in host)
        )
        # Accessing port also validates malformed and out-of-range values.
        _ = authority.port
    except ValueError:
        invalid = True
    if invalid:
        raise DockflowError("Invalid Host header")


RPC = {
    "store": {
        "check_execution",
        "get",
        "has_output_set",
        "put",
        "list",
        "query",
        "append",
        "log",
        "commit_output_set",
        "ensure_reconciled",
        "verify_output_set",
        "finish_run",
        "import_cache_result",
        "publish_cache_result",
    },
    "artifacts": {
        "get",
        "list",
        "register",
        "materialize",
        "verify",
        "publish",
        "verify_cache",
        "storage_identity",
    },
}


class _Remote:
    def __init__(self, pipe, target):
        self.pipe, self.target = pipe, target

    def __getattr__(self, name):
        if name not in RPC[self.target]:
            raise AttributeError(name)

        def call(*args, **kwargs):
            self.pipe.send((self.target, name, args, kwargs))
            status, value = self.pipe.recv()
            if status == "error":
                raise DockflowError(
                    value["message"],
                    value["code"],
                    value["status"],
                    value.get("details"),
                )
            return value

        return call


def _worker(pipe, settings, run):
    from .engine import execute_run

    try:
        result = execute_run(
            _Remote(pipe, "store"), _Remote(pipe, "artifacts"), settings, run
        )
        pipe.send(("finished", result))
    except BaseException as exc:
        pipe.send(("failed", type(exc).__name__ + ": " + str(exc)))
    finally:
        pipe.close()


class Scheduler:
    def __init__(self, core: Core):
        self.core = core
        self.stopping = threading.Event()
        self.thread = None
        self.active_run = None
        self.ready = False
        self.error = None
        self.last_recovery = 0.0
        self.execution_enabled = True
        self.last_retention = 0.0

    def available(self) -> bool:
        return (
            self.ready
            and not self.stopping.is_set()
            and (
                not self.execution_enabled
                or self.thread is not None
                and self.thread.is_alive()
            )
        )

    def reconcile(self) -> None:
        """Recover only claimable abandoned Runs; never touch a live remote Run."""
        if not self.core.store.database.adapter.supports_shared_owners:
            self._reconcile()
            return
        for run in self.core.store.database.queries.recovery_runs():
            try:
                with self.core.store.run_owner(
                    run["run_id"], self.core.settings.execution, recovering=True
                ):
                    self._reconcile(run["run_id"])
            except DockflowError as exc:
                if exc.code != "RUN_BUSY":
                    LOGGER.warning("Run recovery remains unresolved: %s", exc)

    def _reconcile(self, run_id: str | None = None) -> None:
        """Confirm recorded handles stopped on their original Docker daemon."""
        import docker
        from docker.errors import NotFound
        from dockflow_core.time import utc_now

        client = docker.from_env()
        try:
            client.ping()
            with self.core.store.database.transaction():
                self.core.store._recover_committed_outputs(
                    self.core.store.accepted_events(kind="output_set", run_id=run_id)
                )
            for attempt in self.core.store.database.queries.select(
                "attempts", filters={"run_id": run_id} if run_id is not None else None
            ):
                if (
                    attempt["state"]
                    not in {
                        "running",
                        "publishing",
                    }
                    and not attempt.get("reconciliation_required")
                    and not (run_id is not None and attempt.get("container_id"))
                ):
                    continue
                identifier = attempt.get("container_id")
                if identifier:
                    daemon_id = attempt.get("daemon_id")
                    if daemon_id:
                        if client.info().get("ID") != daemon_id:
                            raise DockflowError(
                                "Recorded attempt belongs to a different Docker daemon; reconcile its original daemon before dispatch",
                                "UNAVAILABLE",
                                503,
                            )
                    elif self.core.store.database.backend == "postgresql":
                        raise DockflowError(
                            "Recorded Docker daemon identity is missing; execution remains unresolved",
                            "UNAVAILABLE",
                            503,
                        )
                    try:
                        container = client.containers.get(identifier)
                        labels = container.labels
                        if (
                            labels.get("dockflow.project")
                            != self.core.settings.project_id
                            or labels.get("dockflow.attempt") != attempt["attempt_id"]
                            or (
                                run_id is not None
                                and (
                                    labels.get("dockflow.run") != attempt["run_id"]
                                    or labels.get("dockflow.task") != attempt["task_id"]
                                )
                            )
                        ):
                            raise DockflowError(
                                "Recorded container ownership does not match; reconciliation required",
                                "CONFLICT",
                                409,
                            )
                        container.reload()
                        if container.attrs["State"].get("Running"):
                            container.stop(
                                timeout=self.core.settings.execution[
                                    "shutdown_grace_seconds"
                                ]
                            )
                            container.reload()
                        if container.attrs["State"].get("Running"):
                            raise DockflowError(
                                "Container stop is unconfirmed", "UNAVAILABLE", 503
                            )
                        retained = self.core.store.log_entries(attempt["run_id"])
                        for stream, stdout, stderr in [
                            ("stdout", True, False),
                            ("stderr", False, True),
                        ]:
                            text = container.logs(stdout=stdout, stderr=stderr).decode(
                                "utf-8", "replace"
                            )
                            captured = "".join(
                                entry["text"]
                                for entry in retained
                                if entry["attempt_id"] == attempt["attempt_id"]
                                and entry["stream"] == stream
                            )
                            # Earlier adapters included Docker timestamps in
                            # text; current chunks have journal timestamps.
                            if not text.startswith(captured):
                                captured = re.sub(
                                    r"(?m)^\d{4}-\d{2}-\d{2}T[\d:.]+Z ", "", captured
                                )
                            if not text.startswith(captured):
                                raise DockflowError(
                                    "Retained container logs differ from saved output; "
                                    "reconciliation required",
                                    "CONFLICT",
                                    409,
                                )
                            if tail := text[len(captured) :]:
                                self.core.store.log(
                                    attempt["run_id"],
                                    tail,
                                    stream=stream,
                                    task_id=attempt["task_id"],
                                    attempt_id=attempt["attempt_id"],
                                )
                            self.core.store.snapshot_attempt_log(
                                attempt["run_id"],
                                attempt["task_id"],
                                attempt["attempt_id"],
                                stream,
                                text.encode("utf-8"),
                            )
                        # Retire the handle before relinquishing the recovery hold.
                        # A stale worker can no longer start a formerly-created container.
                        container.remove(force=True)
                    except NotFound:
                        pass
                state = (
                    "succeeded"
                    if self.core.store.has_output_set(attempt["attempt_id"])
                    else "interrupted"
                )
                self.core.store.put(
                    "attempts",
                    {
                        **attempt,
                        "state": state,
                        "finished_at": attempt.get("finished_at") or utc_now(),
                        "reconciliation_required": False,
                        "error": None
                        if state == "succeeded"
                        else {"reason": "worker_lost"},
                    },
                )
            # Clear Run holds only after every uncertain Attempt was reconciled.
            # A later failed stop must leave terminal Runs held for the retry.
            runs = (
                [self.core.store.get("runs", run_id)]
                if run_id is not None
                else self.core.store.database.queries.recovery_runs()
            )
            for run in runs:
                if run["state"] in {"running", "cancelling"}:
                    self.core.store.finish_run(
                        {
                            **run,
                            "state": "interrupted",
                            "reconciliation_required": False,
                            "finished_at": utc_now(),
                            "error": {
                                "reason": "worker_lost",
                                "message": "Recovered after execution owner loss; no automatic rerun",
                            },
                        },
                        recovering=True,
                    )
                elif run["state"] in TERMINAL and run.get("reconciliation_required"):
                    self.core.store.finish_run(
                        {**run, "reconciliation_required": False}, recovering=True
                    )
        finally:
            client.close()

    def start(self):
        self.reconcile()
        if self.core.settings.artifacts["backend"] == "s3":
            self.core.artifacts._s3().head_bucket(
                Bucket=self.core.settings.artifacts["bucket"]
            )
        self.ready = True
        self.thread = threading.Thread(
            target=self._loop, name="dockflow-owner", daemon=True
        )
        self.thread.start()

    def _loop(self):
        try:
            self._dispatch_loop()
        except Exception as exc:
            # A failed scheduler cannot continue accepting work. Do not silently
            # start a replacement while execution/commit authority is uncertain.
            self.error = (
                "Scheduler stopped; resolve the failure and restart the service"
            )
            LOGGER.error("Scheduler stopped (%s)", type(exc).__name__)
            self.stopping.set()
        finally:
            self.ready = False

    def _dispatch_loop(self):
        while not self.stopping.is_set():
            if (
                self.core.store.database.adapter.supports_shared_owners
                and time.monotonic() - self.last_recovery >= 2
            ):
                self.reconcile()
                self.last_recovery = time.monotonic()
            with self.core.mutex:
                if self.stopping.is_set():
                    return
                if self.core.store.reconciliation_required:
                    self.ready = False
                    self.error = "Accepted metadata requires offline reconciliation before dispatch"
                    self.stopping.set()
                    return
                queued = self.core.store.database.queries.queued()
            dispatched = False
            for run in queued:
                try:
                    with self.core.store.run_owner(
                        run["run_id"], self.core.settings.execution
                    ):
                        with self.core.mutex:
                            if self.stopping.is_set():
                                return
                            self.active_run = run["run_id"]
                        self._dispatch(run)
                        dispatched = True
                    break
                except DockflowError as exc:
                    if exc.code != "RUN_BUSY":
                        self.error = str(exc)
                        LOGGER.warning("Run dispatch refused: %s", exc)
                finally:
                    self.active_run = None
            if not dispatched:
                self.retention_tick()
                self.stopping.wait(0.1)

    def retention_tick(self):
        interval = self.core.settings.artifacts.get("retention_interval_seconds", 3600)
        if (
            self.core.settings.artifacts.get("retention_days", -1) < 0
            or time.monotonic() - self.last_retention < interval
        ):
            return
        self.last_retention = time.monotonic()
        from .deletion import Deletions

        with self.core.mutex:
            try:
                Deletions(self.core).retention({"apply": True}, automatic=True)
            except Exception as exc:
                message = (
                    exc.message
                    if isinstance(exc, DockflowError)
                    else "Retention could not inspect storage; check provider access and retry"
                )
                self.core.store.set_project_metadata(
                    "retention_status",
                    {"error": message, "last_check_at": time.time()},
                )
                LOGGER.warning("Artifact retention deferred: %s", message)

    def _dispatch(self, run):
        parent, child = multiprocessing.get_context("spawn").Pipe()
        process = multiprocessing.get_context("spawn").Process(
            target=_worker,
            args=(child, self.core.settings, run),
            name=f"dockflow-{run['run_id']}",
        )
        try:
            process.start()
        except BaseException:
            parent.close()
            child.close()
            raise
        child.close()
        finished = False
        try:
            while process.is_alive() or parent.poll():
                if parent.poll(0.1):
                    message = parent.recv()
                    if message[0] in {"finished", "failed"}:
                        finished = message[0] == "finished"
                        if not finished:
                            LOGGER.error("Run worker failed: %s", message[1])
                        break
                    target, name, args, kwargs = message
                    with self.core.mutex:
                        try:
                            if target not in RPC or name not in RPC[target]:
                                raise DockflowError(
                                    "Invalid worker operation", "INTERNAL", 500
                                )
                            value = getattr(getattr(self.core, target), name)(
                                *args, **kwargs
                            )
                            parent.send(("ok", value))
                        except DockflowError as exc:
                            if self.core.store.reconciliation_required:
                                self.ready = False
                                self.error = "Accepted metadata requires reconciliation"
                            parent.send(
                                ("error", {**exc.as_dict(), "status": exc.status})
                            )
                        except Exception:
                            LOGGER.exception("Owner operation failed")
                            parent.send(
                                (
                                    "error",
                                    {
                                        "message": "Owner operation failed; inspect retained service logs",
                                        "code": "INTERNAL",
                                        "status": 500,
                                    },
                                )
                            )
            process.join()
            if not finished:
                with self.core.mutex:
                    self._reconcile(run["run_id"])
        except (EOFError, OSError, DockflowError) as exc:
            self.ready = False
            self.error = str(exc)
            LOGGER.exception("Execution reconciliation required")
            self.stopping.set()
        finally:
            parent.close()
            self.active_run = None

    def stop(self):
        with self.core.mutex:
            self.ready = False
            self.stopping.set()
            if self.active_run:
                self.core.cancel(self.active_run, interruption=True)
        if self.thread:
            self.thread.join(
                timeout=self.core.settings.execution["shutdown_grace_seconds"] + 10
            )
        if self.thread and self.thread.is_alive():
            self.error = "Worker shutdown remains unconfirmed; ownership retained"
            LOGGER.error(self.error)
            # Never release ownership while its writer thread is still alive.
            # An external process kill leaves durable stop intent for recovery.
            self.thread.join()


def create_app(settings, *, execute: bool = True) -> FastAPI:
    core = Core(settings)
    scheduler = Scheduler(core)
    scheduler.execution_enabled = execute
    token = None

    @contextlib.asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        nonlocal token
        if settings.service.get("token_file"):
            token = settings.service["token_file"].read_text().strip()
            if not token:
                raise DockflowError("Empty service token file")
        with core.store.owner(
            endpoint=f"http://{settings.service['host']}:{settings.service['port']}"
        ):
            core.initialize()
            core.refresh()
            if execute:
                scheduler.start()
            else:
                scheduler.ready = True
            try:
                yield
            finally:
                if execute:
                    scheduler.stop()

    app = FastAPI(
        title="Dockflow Pipelines",
        version=capabilities()["versions"]["dockflow-pipelines"],
        openapi_url="/dockflow/v1/openapi.json",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.core = core
    app.state.scheduler = scheduler

    @app.exception_handler(DockflowError)
    async def domain_error(request: Request, exc: DockflowError):
        LOGGER.info(
            "request_id=%s code=%s method=%s path=%r",
            exc.request_id,
            exc.code,
            request.method,
            request.scope["path"],
        )
        if _route_path(request).startswith("/apis/"):
            from .kfp_api import kfp_error

            return kfp_error(exc)
        return JSONResponse({"error": exc.as_dict()}, status_code=exc.status)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        error = DockflowError(
            str(exc.detail),
            "NOT_FOUND" if exc.status_code == 404 else "INVALID_ARGUMENT",
            exc.status_code,
        )
        return await domain_error(request, error)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        LOGGER.exception("Unhandled request error")
        return await domain_error(
            request,
            DockflowError("Operation failed; inspect service logs", "INTERNAL", 500),
        )

    @app.middleware("http")
    async def admission(request: Request, call_next):
        try:
            from .web import is_public_shell

            _validate_host(request)
            route_path = _route_path(request)
            if (
                token
                and route_path not in {"/health/live", "/health/ready"}
                and not is_public_shell(
                    request.method,
                    route_path,
                )
            ):
                import hmac

                authorization = request.headers.get("authorization", "")
                if not hmac.compare_digest(authorization, "Bearer " + token):
                    raise DockflowError(
                        "Missing or invalid bearer token", "UNAUTHENTICATED", 401
                    )
            if request.method in {"POST", "PUT", "PATCH"}:
                origin = request.headers.get("origin")
                expected_origin = f"{request.url.scheme}://{request.url.netloc}"
                if origin is not None and origin != expected_origin:
                    raise DockflowError(
                        "Cross-origin mutations are not permitted",
                        "PERMISSION_DENIED",
                        403,
                    )
                maximum = settings.service["request_max_bytes"]
                length = request.headers.get("content-length")
                if length and (not length.isdecimal() or int(length) > maximum):
                    raise DockflowError(
                        "Request body exceeds the configured limit",
                        "REQUEST_TOO_LARGE",
                        413,
                    )
                payload = bytearray()
                async for chunk in request.stream():
                    payload.extend(chunk)
                    if len(payload) > maximum:
                        raise DockflowError(
                            "Request body exceeds the configured limit",
                            "REQUEST_TOO_LARGE",
                            413,
                        )
                request._body = bytes(payload)
                content_type = request.headers.get("content-type", "").lower()
                upload = request.method == "POST" and route_path in {
                    "/apis/v2beta1/pipelines/upload",
                    "/apis/v2beta1/pipelines/upload_version",
                    "/dockflow/v1/artifacts/upload",
                }
                if upload:
                    if content_type.split(";")[0].strip() != "multipart/form-data":
                        raise DockflowError("Uploads require multipart/form-data")
                    response = await call_next(request)
                    if response.headers.get("content-type", "").startswith(
                        "application/json"
                    ):
                        response.headers["content-type"] = (
                            "application/json; charset=utf-8"
                        )
                    return response
                if payload and (
                    content_type.split(";")[0].strip() != "application/json"
                    or (
                        "charset=" in content_type
                        and "charset=utf-8" not in content_type.replace(" ", "")
                    )
                ):
                    raise DockflowError(
                        "Request bodies must use UTF-8 application/json"
                    )
                try:
                    value = loads(bytes(payload) if payload else b"{}")
                except (ValueError, UnicodeError) as exc:
                    raise DockflowError(
                        "Body must be valid UTF-8 JSON with unique keys and portable finite numbers"
                    ) from exc
                if not isinstance(value, dict):
                    raise DockflowError("Request body must be a JSON object")
                request.state.body = value
            response = await call_next(request)
            if response.headers.get("content-type", "").startswith("application/json"):
                response.headers["content-type"] = "application/json; charset=utf-8"
            return response
        except DockflowError as exc:
            return await domain_error(request, exc)

    @app.get("/health/live")
    def live():
        return {"status": "alive", "checks": {"process": True}}

    @app.get("/health/ready")
    def ready():
        reconciliation_required = core.store.reconciliation_required
        admission_ready = scheduler.available() and not reconciliation_required
        return JSONResponse(
            {
                "status": "ready" if admission_ready else "unavailable",
                "checks": {
                    "admission": admission_ready,
                    "recovery": scheduler.error,
                    "reconciliation_required": reconciliation_required,
                },
            },
            status_code=200 if admission_ready else 503,
        )

    def query(request: Request, allowed: set[str]) -> dict:
        if set(request.query_params) - allowed or any(
            len(request.query_params.getlist(key)) != 1 for key in request.query_params
        ):
            raise DockflowError("Unknown or duplicate query arguments")
        return dict(request.query_params)

    @app.get("/dockflow/v1/capabilities")
    def get_capabilities():
        return capabilities(settings)

    for collection in (
        "pipelines",
        "definitions",
        "components",
        "runs",
        "tasks",
        "attempts",
        "artifacts",
        "experiments",
    ):

        def list_route(collection):
            def listing(request: Request):
                allowed_filters = {
                    "pipelines": {"name"},
                    "definitions": {"name", "pipeline_id", "kind"},
                    "components": {"name", "definition_id"},
                    "runs": {"state", "experiment_id", "definition_id"},
                    "tasks": {"state", "run_id", "input_artifact_id"},
                    "attempts": {"state", "run_id", "task_id"},
                    "artifacts": {"type", "availability"},
                    "experiments": {"name"},
                }[collection]
                values = query(
                    request, {"page_size", "page_token", "search", *allowed_filters}
                )
                try:
                    page_size = int(values.pop("page_size", 50))
                except ValueError as exc:
                    raise DockflowError("page_size must be an integer") from exc
                token = values.pop("page_token", None)
                if collection == "runs" and values.get("state") not in {
                    None,
                    "queued",
                    "running",
                    "cancelling",
                    *TERMINAL,
                }:
                    raise DockflowError("Unknown Run state")
                if collection == "artifacts" and values.get("availability") not in {
                    None,
                    "available",
                    "missing",
                    "inaccessible",
                    "corrupt",
                    "deleted",
                    "unknown",
                }:
                    raise DockflowError("Unknown availability state")
                execution_states = {
                    "tasks": {
                        "pending",
                        "running",
                        "reused",
                        "skipped",
                        "blocked",
                        *TERMINAL,
                    },
                    "attempts": {"running", "publishing", *TERMINAL},
                }
                if collection in execution_states and values.get("state") not in {
                    None,
                    *execution_states[collection],
                }:
                    raise DockflowError("Unknown execution state")
                if collection == "definitions" and values.get("kind") not in {
                    None,
                    "pipeline",
                    "component",
                }:
                    raise DockflowError("Unknown definition kind")
                with core.mutex:
                    return operate(
                        core,
                        collection + ".list",
                        {
                            "page_size": page_size,
                            "page_token": token,
                            "filters": values,
                        },
                    )

            return listing

        app.add_api_route(
            f"/dockflow/v1/{collection}",
            list_route(collection),
            methods=["GET"],
            name=f"list_{collection}",
        )

    for collection in (
        "pipelines",
        "definitions",
        "components",
        "runs",
        "tasks",
        "attempts",
        "artifacts",
        "experiments",
    ):

        def show_route(collection):
            def show(id: str):
                with core.mutex:
                    return operate(core, collection + ".show", {"id": id})

            return show

        app.add_api_route(
            f"/dockflow/v1/{collection}/{{id}}",
            show_route(collection),
            methods=["GET"],
            name=f"get_{collection}",
        )

    @app.post("/dockflow/v1/runs")
    def submit(request: Request):
        if not scheduler.available():
            raise DockflowError("Execution owner is not ready", "UNAVAILABLE", 503)
        with core.mutex:
            run, replay = core.submit(
                request.state.body, request.headers.get("idempotency-key")
            )
        return JSONResponse(
            run,
            status_code=200 if replay else 202,
            headers={"Location": f"/dockflow/v1/runs/{run['run_id']}"},
        )

    @app.post("/dockflow/v1/runs/{run_id}/cancel")
    def cancel(run_id: str, request: Request):
        only_fields(request.state.body, set())
        with core.mutex:
            return core.cancel(run_id)

    @app.get("/dockflow/v1/runs/{run_id}/logs")
    def logs(run_id: str, request: Request):
        values = query(request, {"task_id", "attempt_id", "cursor", "limit_bytes"})
        try:
            values["limit_bytes"] = int(values.get("limit_bytes", 65536))
        except ValueError as exc:
            raise DockflowError("limit_bytes must be an integer") from exc
        with core.mutex:
            return core.logs(run_id, **values)

    routes = {
        "/storage/scan": ("storage.scan", {"prefix"}),
        "/storage/scan/show": (
            "storage.show",
            {
                "scan_id",
                "page_size",
                "page_token",
                "selected",
                "orphans",
                "classification",
                "artifact_id",
            },
        ),
        "/deletions/plan": (
            "deletions.plan",
            {"targets", "scan_id", "selected", "orphans", "delete_files"},
        ),
        "/deletions/show": ("deletions.show", {"plan_id"}),
        "/deletions/apply": ("deletions.apply", {"plan_id", "confirmation"}),
        "/retention": ("retention", {"apply", "confirmation"}),
        "/definitions/validate": (
            "definitions.validate",
            {"definition_id", "pipeline_spec", "source_text", "parameters", "inputs"},
        ),
        "/definitions/refresh": ("definitions.refresh", set()),
        "/artifacts": (
            "artifacts.create",
            {"operation", "uri", "type", "version", "metadata"},
        ),
        "/experiments": ("experiments.create", {"display_name", "description"}),
        "/metadata/check": ("metadata.check", {"verify_contents"}),
        "/metadata/rebuild": ("metadata.rebuild", {"apply"}),
        "/clean": ("clean", {"apply"}),
    }
    for path, (action, fields) in routes.items():

        def operation_route(action, fields):
            def operation(request: Request):
                body = request.state.body
                only_fields(body, fields)
                if action == "artifacts.create" and (
                    body.get("operation") not in {"register", "import"}
                    or not {"uri", "type"} <= set(body)
                ):
                    raise DockflowError(
                        "Artifact creation requires operation, uri and type"
                    )
                if action == "experiments.create" and "display_name" not in body:
                    raise DockflowError("display_name is required")
                for field in ("apply", "verify_contents", "delete_files", "orphans"):
                    if field in body and type(body[field]) is not bool:
                        raise DockflowError(f"{field} must be boolean")
                if action == "metadata.rebuild" and body.get("apply"):
                    raise DockflowError(
                        "Stop the service and rebuild using the direct CLI",
                        "OFFLINE_REQUIRED",
                        409,
                    )
                mutation = action in {
                    "storage.scan",
                    "deletions.plan",
                    "deletions.apply",
                    "retention",
                    "definitions.refresh",
                    "artifacts.create",
                    "experiments.create",
                } or body.get("apply")
                if mutation and scheduler.active_run:
                    if action == "definitions.refresh":
                        with core.mutex:
                            if core.registrations_unchanged():
                                return JSONResponse(
                                    {
                                        "added": [],
                                        "updated": [],
                                        "unavailable": [],
                                        "diagnostics": [],
                                    }
                                )
                    raise DockflowError(
                        "Mutating maintenance requires an idle execution owner",
                        "CONFLICT",
                        409,
                    )
                with core.mutex:
                    result = operate(core, action, body)
                return JSONResponse(
                    result,
                    status_code=201
                    if action in {"artifacts.create", "experiments.create"}
                    else 200,
                )

            return operation

        app.add_api_route(
            "/dockflow/v1" + path,
            operation_route(action, fields),
            methods=["POST"],
            name=action,
        )

    @app.get("/dockflow/v1/cache/{key}")
    def cache_show(key: str):
        return operate(core, "cache.show", {"id": key})

    for cache_operation, cache_fields in (
        ("invalidate", {"artifact_id", "reason"}),
        ("reset", {"revision", "reason"}),
    ):

        def cache_route(operation, fields):
            def cache_mutate(key: str, request: Request):
                body = request.state.body
                only_fields(body, fields)
                if set(body) != fields:
                    raise DockflowError("Cache maintenance requires all request fields")
                return operate(core, "cache." + operation, {"id": key, **body})

            return cache_mutate

        app.add_api_route(
            "/dockflow/v1/cache/{key}/" + cache_operation,
            cache_route(cache_operation, cache_fields),
            methods=["POST"],
            name="cache." + cache_operation,
        )

    for operation in ("pin", "unpin"):

        def pin_route(operation):
            def pin(id: str, request: Request):
                only_fields(request.state.body, set())
                if scheduler.active_run:
                    raise DockflowError(
                        "Artifact mutation requires an idle owner", "CONFLICT", 409
                    )
                with core.mutex:
                    return core.artifacts.pin(id, operation == "pin")

            return pin

        app.add_api_route(
            f"/dockflow/v1/artifacts/{{id}}/{operation}",
            pin_route(operation),
            methods=["POST"],
            name=operation + "_artifact",
        )

    from .upload_api import mount_uploads

    mount_uploads(app, core, scheduler)
    from .kfp_api import mount_kfp

    mount_kfp(app, core, scheduler)
    from .web import mount_web

    mount_web(app, core)
    from .openapi import enhance_openapi

    enhance_openapi(app)
    return app
