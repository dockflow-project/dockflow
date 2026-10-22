"""Lightweight feature CLI; imports execution dependencies only on invocation."""

from __future__ import annotations

import functools
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import typer

from .canonical import loads
from .config import find_config, load_settings
from .console import DEFAULT_OUTPUT_LIMIT, OutputMode, RunConsole, run_summary
from .errors import DockflowError

app = typer.Typer(
    help="Execute and inspect compiled KFP pipelines.",
    add_completion=False,
    no_args_is_help=False,
)
definitions = typer.Typer(help="Compiled pipeline definitions.", no_args_is_help=True)
components = typer.Typer(
    help="Registered and embedded components.", no_args_is_help=True
)
runs = typer.Typer(help="Durable Runs.", no_args_is_help=True)
tasks = typer.Typer(help="Task lineage and attempts.", no_args_is_help=True)
artifacts = typer.Typer(help="Typed immutable artifacts.", no_args_is_help=True)
experiments = typer.Typer(help="Run groupings.", no_args_is_help=True)
metadata_app = typer.Typer(help="Check and rebuild metadata.", no_args_is_help=True)
for name, group in [
    ("definitions", definitions),
    ("components", components),
    ("runs", runs),
    ("tasks", tasks),
    ("artifacts", artifacts),
    ("experiments", experiments),
    ("metadata", metadata_app),
]:
    app.add_typer(group, name=name)


@dataclass
class Options:
    config: Path | None
    endpoint: str | None
    local: bool
    json: bool


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    config: Path | None = None,
    endpoint: str | None = None,
    local: bool = False,
    json: bool = False,
):
    if endpoint is not None and local:
        raise typer.BadParameter("--endpoint and --local are mutually exclusive")
    ctx.obj = Options(config, endpoint, local, json)
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


def boundary(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except DockflowError as exc:
            options = kwargs.get("ctx", args[0] if args else None)
            options = getattr(options, "obj", options)
            if isinstance(options, Options) and options.json:
                typer.echo(
                    json.dumps(
                        {"schema_version": 1, "error": exc.as_dict()},
                        ensure_ascii=False,
                    ),
                    err=True,
                )
            else:
                typer.echo(f"{exc.code}: {exc.message}", err=True)
            raise typer.Exit(2 if exc.code == "INVALID_ARGUMENT" else 1) from None
        except (ValueError, OSError) as exc:
            options = kwargs.get("ctx", args[0] if args else None)
            options = getattr(options, "obj", options)
            error = DockflowError(str(exc))
            if isinstance(options, Options) and options.json:
                typer.echo(
                    json.dumps(
                        {"schema_version": 1, "error": error.as_dict()},
                        ensure_ascii=False,
                    ),
                    err=True,
                )
            else:
                typer.echo(f"INVALID_ARGUMENT: {exc}", err=True)
            raise typer.Exit(2) from None

    return wrapped


def emit(ctx: typer.Context, result) -> None:
    if ctx.obj.json:
        typer.echo(
            json.dumps(
                {"schema_version": 1, "result": result},
                ensure_ascii=False,
                allow_nan=False,
            )
        )
    else:
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


def context(ctx: typer.Context, *, service: bool = False):
    from .client import Client

    options = ctx.obj
    settings = None
    try:
        selected = find_config(options.config, service=service)
    except DockflowError:
        if (
            service
            or options.config is not None
            or "DOCKFLOW_PIPELINES_CONFIG" in os.environ
            or (
                options.endpoint is None
                and not os.environ.get("DOCKFLOW_PIPELINES_ENDPOINT")
            )
        ):
            raise
    else:
        settings = load_settings(selected, service=service)
    endpoint = (
        options.endpoint
        if options.endpoint is not None
        else os.environ.get(
            "DOCKFLOW_PIPELINES_ENDPOINT",
            settings.client.get("endpoint") if settings else None,
        )
    )
    if options.local:
        endpoint = None
    if endpoint is not None and not service:
        return settings, Client(endpoint, settings.client if settings else {})
    if settings is None:
        raise DockflowError("Direct operations require a project configuration")
    return settings, None


def invoke(ctx: typer.Context, action: str, values: dict, *, mutate: bool = False):
    settings, client = context(ctx)
    if client:
        return client.operate(action, values)
    from .core import Core
    from .operations import operate

    assert settings is not None
    core = Core(settings)
    if mutate:
        with core.store.owner():
            if action == "metadata.rebuild":
                # The authoritative journal must remain usable when the index
                # being repaired cannot be opened as a database.
                core.store.initialize(require_mlmd=False)
            else:
                core.initialize()
            return operate(core, action, values)
    if action == "metadata.check":
        core.store.open_readonly_index()
    return operate(core, action, values)


def assignments(values: list[str], *, json_values: bool = False) -> dict:
    result = {}
    for value in values:
        name, separator, data = value.partition("=")
        if not separator or not name or name in result:
            raise DockflowError(f"Invalid or duplicate assignment: {name}")
        result[name] = loads(data) if json_values else data
    return result


def require_direct_idle(core) -> None:
    """Acquiring a released lock does not confirm earlier containers stopped."""
    from .core import TERMINAL

    core.store.require_owner()
    core.store.ensure_reconciled()
    unresolved_runs = [
        run["run_id"]
        for run in core.store.list("runs")
        if run.get("state") not in TERMINAL or run.get("reconciliation_required")
    ]
    unresolved_attempts = [
        attempt["attempt_id"]
        for attempt in core.store.list("attempts")
        if attempt.get("state") not in TERMINAL
        or attempt.get("reconciliation_required")
    ]
    if unresolved_runs or unresolved_attempts:
        details = [
            {
                "field": collection,
                "reason": f"{len(identifiers)} unresolved; first 20 IDs: "
                + ", ".join(identifiers[:20]),
            }
            for collection, identifiers in (
                ("runs", unresolved_runs),
                ("attempts", unresolved_attempts),
            )
            if identifiers
        ]
        raise DockflowError(
            "Unresolved prior work prevents direct execution. Start the service "
            "with this project configuration to reconcile/drain it, then stop "
            "the service before retrying direct execution.",
            "CONFLICT",
            409,
            details,
        )


def file_request(operand: str, settings, client) -> dict:
    from .core import checked_definition

    path = Path(operand)
    if (
        path.is_absolute()
        or operand.startswith(("./", "../"))
        or path.suffix in {".yaml", ".yml", ".json"}
    ):
        definition = checked_definition(path)
        return {
            "pipeline_spec": definition.document,
            "source_text": definition.raw_bytes.decode("utf-8"),
        }
    if operand.startswith("definition_"):
        return {"definition_id": operand}
    if client:
        return {
            "definition_id": client.operate("definitions.show", {"id": operand})[
                "definition_id"
            ]
        }
    from .core import Core

    record = Core(settings).resolve(operand, persist=False)
    if record.get("definition_id"):
        return {"definition_id": record["definition_id"]}
    return {
        "pipeline_spec": record["pipeline_spec"],
        "source_text": record["source_text"],
    }


@app.command()
@boundary
def run(
    ctx: typer.Context,
    definition: str,
    name: str | None = None,
    experiment: str | None = None,
    parameter: list[str] = typer.Option([]),
    input: list[str] = typer.Option([]),
    from_task: str | None = typer.Option(None, "--from"),
    tasks: str | None = None,
    bind: list[str] = typer.Option([]),
    use_execution: list[str] = typer.Option([]),
    scope: str | None = None,
    scope_key: str | None = None,
    wait: bool = typer.Option(True, "--wait/--no-wait"),
    idempotency_key: str | None = None,
    output: OutputMode = typer.Option(
        OutputMode.trimmed,
        help="Display human result details: none, trimmed (default), or full.",
    ),
    output_limit: int = typer.Option(
        DEFAULT_OUTPUT_LIMIT,
        min=128,
        help="Maximum characters per verbose block in trimmed output.",
    ),
    dockflow_output: bool = typer.Option(
        True,
        "--dockflow-output/--no-dockflow-output",
        help="Show Dockflow progress, KFP bookkeeping and human results; warnings/errors remain visible.",
    ),
    component_output: bool = typer.Option(
        True,
        "--component-output/--no-component-output",
        help="Show local component stdout/stderr; full logs are always retained.",
    ),
):
    settings, client = context(ctx)
    if from_task and tasks:
        raise DockflowError("--from and --tasks are mutually exclusive")
    if not client and (not wait or idempotency_key is not None):
        raise DockflowError(
            "--no-wait and --idempotency-key require an explicit service endpoint"
        )
    request = {
        **file_request(definition, settings, client),
        "parameters": assignments(parameter, json_values=True),
        "inputs": assignments(input),
        "bindings": assignments(bind),
        "use_executions": assignments(use_execution),
    }
    for key, value in [("display_name", name), ("experiment_id", experiment)]:
        if value is not None:
            request[key] = value
    if from_task:
        request["selection"] = {"mode": "from", "task": from_task}
    elif tasks:
        request["selection"] = {"mode": "tasks", "tasks": tasks.split(",")}
    if scope is not None or scope_key is not None:
        request["reuse"] = {
            **({"scope": scope} if scope is not None else {}),
            **({"key": scope_key} if scope_key is not None else {}),
        }
    if client:
        key = idempotency_key or str(uuid.uuid4())
        try:
            result = client.request("POST", "/dockflow/v1/runs", request, key=key)
        except DockflowError as exc:
            exc.message += (
                f"; submission key: {key} (reuse this key if acceptance is uncertain)"
            )
            raise
        if wait:
            try:
                while result["state"] not in {
                    "succeeded",
                    "failed",
                    "cancelled",
                    "interrupted",
                }:
                    time.sleep(
                        settings.client["poll_interval_seconds"] if settings else 1
                    )
                    result = client.request(
                        "GET", f"/dockflow/v1/runs/{result['run_id']}"
                    )
            except (KeyboardInterrupt, DockflowError):
                typer.echo(
                    f"Detached from Run {result['run_id']}; idempotency key {key}",
                    err=True,
                )
                raise typer.Exit(1) from None
    else:
        from .core import Core

        assert settings is not None
        core = Core(settings)
        with core.store.owner():
            core.initialize()
            require_direct_idle(core)
            # Resolve named registrations under ownership to retain catalog identity.
            if definition in settings.definitions["pipelines"]:
                request = {
                    **request,
                    "definition_id": core.resolve(definition)["definition_id"],
                }
                request.pop("pipeline_spec", None)
                request.pop("source_text", None)
            result, _ = core.submit(request)
            console = RunConsole(
                output,
                output_limit,
                sys.stderr,
                dockflow_output=dockflow_output,
                component_output=component_output,
            )
            with console.kfp_logging():
                result = core.execute(result, on_log=console.log)
    if ctx.obj.json:
        emit(ctx, result)
    elif dockflow_output:
        typer.echo(run_summary(result, output, output_limit))
    elif result["state"] in {"failed", "cancelled", "interrupted"}:
        typer.echo(run_summary(result, OutputMode.none, output_limit), err=True)
    if wait and result["state"] != "succeeded":
        raise typer.Exit(1)


def register_list(group, collection: str):
    @group.command("list")
    @boundary
    def list_command(
        ctx: typer.Context,
        name: str | None = None,
        state: str | None = None,
        experiment: str | None = None,
        type: str | None = None,
        availability: str | None = None,
        page_size: int = 50,
        page_token: str | None = None,
    ):
        allowed = {
            "definitions": {"name"},
            "components": {"name"},
            "runs": {"state", "experiment_id"},
            "artifacts": {"type", "availability"},
            "experiments": {"name"},
        }[collection]
        filters = {
            key: value
            for key, value in {
                "name": name,
                "state": state,
                "experiment_id": experiment,
                "type": type,
                "availability": availability,
            }.items()
            if value is not None
        }
        if set(filters) - allowed:
            raise DockflowError(f"Unsupported filters for {collection}")
        emit(
            ctx,
            invoke(
                ctx,
                collection + ".list",
                {"filters": filters, "page_size": page_size, "page_token": page_token},
            ),
        )


def register_show(group, collection: str):
    @group.command("show")
    @boundary
    def show(ctx: typer.Context, id: str):
        emit(ctx, invoke(ctx, collection + ".show", {"id": id}))


for collection, group in [
    ("definitions", definitions),
    ("components", components),
    ("runs", runs),
    ("artifacts", artifacts),
    ("experiments", experiments),
]:
    register_list(group, collection)
    register_show(group, collection)
register_show(tasks, "tasks")


@definitions.command("validate")
@boundary
def validate(ctx: typer.Context, definition: str):
    settings, client = context(ctx)
    request = file_request(definition, settings, client)
    emit(ctx, invoke(ctx, "definitions.validate", request))


@definitions.command("refresh")
@boundary
def refresh(ctx: typer.Context):
    emit(ctx, invoke(ctx, "definitions.refresh", {}, mutate=True))


@runs.command("cancel")
@boundary
def cancel(ctx: typer.Context, id: str):
    emit(ctx, invoke(ctx, "runs.cancel", {"id": id}, mutate=True))


def artifact_command(operation: str):
    @artifacts.command(operation)
    @boundary
    def create(
        ctx: typer.Context,
        uri: str = typer.Option(..., "--uri"),
        type: str = typer.Option(..., "--type"),
        type_version: str | None = None,
        version: str | None = None,
        metadata: list[str] = typer.Option([]),
    ):
        from .artifacts import BUILTIN_TYPES

        if type_version is None and type not in BUILTIN_TYPES:
            raise DockflowError("Custom artifact types require --type-version")
        emit(
            ctx,
            invoke(
                ctx,
                "artifacts.create",
                {
                    "operation": operation,
                    "uri": uri,
                    "type": {
                        "schema_title": type,
                        "schema_version": type_version or "0.0.1",
                    },
                    "metadata": assignments(metadata, json_values=True),
                    **({"version": version} if version else {}),
                },
                mutate=True,
            ),
        )


artifact_command("register")
artifact_command("import")


def pin_command(operation: str):
    @artifacts.command(operation)
    @boundary
    def pin(ctx: typer.Context, id: str):
        emit(ctx, invoke(ctx, "artifacts." + operation, {"id": id}, mutate=True))


pin_command("pin")
pin_command("unpin")


@experiments.command("create")
@boundary
def create_experiment(ctx: typer.Context, name: str, description: str = ""):
    emit(
        ctx,
        invoke(
            ctx,
            "experiments.create",
            {"display_name": name, "description": description},
            mutate=True,
        ),
    )


@metadata_app.command("check")
@boundary
def check(ctx: typer.Context, verify_contents: bool = False):
    emit(ctx, invoke(ctx, "metadata.check", {"verify_contents": verify_contents}))


@metadata_app.command("rebuild")
@boundary
def rebuild(ctx: typer.Context, apply: bool = False):
    emit(ctx, invoke(ctx, "metadata.rebuild", {"apply": apply}, mutate=apply))


@app.command()
@boundary
def clean(ctx: typer.Context, apply: bool = False):
    emit(ctx, invoke(ctx, "clean", {"apply": apply}, mutate=apply))


@app.command()
@boundary
def capabilities(ctx: typer.Context):
    try:
        result = invoke(ctx, "capabilities", {})
    except DockflowError as exc:
        if (
            ctx.obj.config
            or ctx.obj.endpoint
            or os.environ.get("DOCKFLOW_PIPELINES_CONFIG")
            or os.environ.get("DOCKFLOW_PIPELINES_ENDPOINT")
        ):
            raise
        from .core import capabilities as actual

        if exc.code != "INVALID_ARGUMENT":
            raise
        result = actual()
    emit(ctx, result)


@app.command()
@boundary
def logs(
    ctx: typer.Context,
    run_id: str,
    task: str | None = None,
    attempt: str | None = None,
    follow: bool = False,
    cursor: str | None = None,
    limit_bytes: int = 65536,
):
    if follow and ctx.obj.json:
        raise DockflowError("--json cannot be used with --follow")
    while True:
        page = invoke(
            ctx,
            "logs",
            {
                "run_id": run_id,
                "task_id": task,
                "attempt_id": attempt,
                "cursor": cursor,
                "limit_bytes": limit_bytes,
            },
        )
        if ctx.obj.json:
            emit(ctx, page)
        else:
            for entry in page["entries"]:
                typer.echo(f"[{entry['stream']}] {entry['text']}", nl=False)
        if not follow or page["terminal"]:
            return
        cursor = page["next_cursor"]
        time.sleep(1)


@app.command()
@boundary
def serve(ctx: typer.Context, host: str | None = None, port: int | None = None):
    if ctx.obj.endpoint is not None or ctx.obj.local:
        raise DockflowError("serve rejects explicit client connection options")
    settings = load_settings(
        ctx.obj.config,
        service=True,
        overrides={
            **({"service.host": host} if host else {}),
            **({"service.port": port} if port is not None else {}),
        },
    )
    try:
        import uvicorn

        from .service import create_app
    except ImportError as exc:
        raise DockflowError(
            "Install dockflow-pipelines[runtime,service,s3] to serve pipelines",
            "UNAVAILABLE",
            503,
        ) from exc
    uvicorn.run(
        create_app(settings),
        host=settings.service["host"],
        port=settings.service["port"],
        log_level="info",
    )
