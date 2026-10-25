"""Strict versioned configuration, with no runtime or infrastructure effects."""

import copy
import math
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from dockflow_core.database import reject_network_sqlite
from dockflow_core.errors import DockflowError

from .cache_registry import (
    CACHE_FIELDS,
    DEFAULT_CACHE,
    validate_cache,
)

DEFAULTS = {
    "project": {"root": "."},
    "definitions": {"pipelines": {}, "components": {}},
    "state": {"directory": ".dockflow", "backend": "sqlite"},
    "execution": {
        "task_mounts": [],
        "task_parallelism": 1,
        "run_lease_seconds": 120.0,
        "run_heartbeat_seconds": 30.0,
        "timeout_seconds": 0,
        "shutdown_grace_seconds": 30,
    },
    "images": {"pull_policy": "if-missing"},
    "artifacts": {
        "backend": "filesystem",
        "external_roots": [],
        "allowed_uri_prefixes": [],
        "prefix": "",
        "tls_verify": True,
        "allow_insecure_http": False,
    },
    "reuse": {"scope": "global"},
    "cache": dict(DEFAULT_CACHE),
    "policies": {},
    "client": {"poll_interval_seconds": 1.0, "tls_verify": True},
    "service": {
        "host": "127.0.0.1",
        "port": 8080,
        "queue_capacity": 100,
        "request_max_bytes": 16777216,
    },
}
FIELDS = {
    "project": {"id", "root"},
    "definitions": {"pipelines", "components"},
    "state": {"directory", "backend", "database", "dsn_env"},
    "execution": {
        "work_directory",
        "task_parallelism",
        "run_lease_seconds",
        "run_heartbeat_seconds",
        "timeout_seconds",
        "shutdown_grace_seconds",
        "cpu_limit",
        "memory_limit_bytes",
        "task_mounts",
    },
    "images": {"pull_policy"},
    "artifacts": {
        "backend",
        "root",
        "managed_root",
        "external_roots",
        "allowed_uri_prefixes",
        "endpoint",
        "bucket",
        "prefix",
        "tls_verify",
        "allow_insecure_http",
    },
    "reuse": {"scope", "scope_key"},
    "cache": CACHE_FIELDS,
    "policies": {"file"},
    "client": {
        "endpoint",
        "poll_interval_seconds",
        "token_file",
        "ca_file",
        "tls_verify",
    },
    "service": {"host", "port", "queue_capacity", "request_max_bytes", "token_file"},
}
ENV = {
    "ENDPOINT": "client.endpoint",
    "PROJECT_ROOT": "project.root",
    "STATE_DIRECTORY": "state.directory",
    "STATE_BACKEND": "state.backend",
    "STATE_DATABASE": "state.database",
    "STATE_DSN_ENV": "state.dsn_env",
    "WORK_DIRECTORY": "execution.work_directory",
    "TIMEOUT_SECONDS": "execution.timeout_seconds",
    "SHUTDOWN_GRACE_SECONDS": "execution.shutdown_grace_seconds",
    "CPU_LIMIT": "execution.cpu_limit",
    "MEMORY_LIMIT_BYTES": "execution.memory_limit_bytes",
    "IMAGE_PULL_POLICY": "images.pull_policy",
    "ARTIFACTS_BACKEND": "artifacts.backend",
    "ARTIFACTS_ROOT": "artifacts.root",
    "ARTIFACTS_MANAGED_ROOT": "artifacts.managed_root",
    "S3_ENDPOINT": "artifacts.endpoint",
    "S3_BUCKET": "artifacts.bucket",
    "S3_PREFIX": "artifacts.prefix",
    "S3_TLS_VERIFY": "artifacts.tls_verify",
    "S3_ALLOW_INSECURE_HTTP": "artifacts.allow_insecure_http",
    "REUSE_SCOPE": "reuse.scope",
    "REUSE_SCOPE_KEY": "reuse.scope_key",
    "HOST": "service.host",
    "PORT": "service.port",
    "QUEUE_CAPACITY": "service.queue_capacity",
    "REQUEST_MAX_BYTES": "service.request_max_bytes",
    "POLL_INTERVAL_SECONDS": "client.poll_interval_seconds",
    "CLIENT_TOKEN_FILE": "client.token_file",
    "CLIENT_CA_FILE": "client.ca_file",
    "CLIENT_TLS_VERIFY": "client.tls_verify",
    "SERVICE_TOKEN_FILE": "service.token_file",
}
ENV.update(
    {
        "RUN_LEASE_SECONDS": "execution.run_lease_seconds",
        "RUN_HEARTBEAT_SECONDS": "execution.run_heartbeat_seconds",
    }
)
ENV.update({"CACHE_" + key.upper(): "cache." + key for key in CACHE_FIELDS})
BOOLS = {"tls_verify", "allow_insecure_http", "shared_filesystem"}
INTS = {
    "max_attempts",
    "infrastructure_attempts",
    "timeout_seconds",
    "shutdown_grace_seconds",
    "memory_limit_bytes",
    "port",
    "queue_capacity",
    "request_max_bytes",
}
FLOATS = {
    "run_lease_seconds",
    "run_heartbeat_seconds",
    "cpu_limit",
    "poll_interval_seconds",
    *(key for key in DEFAULT_CACHE if key.endswith("_seconds")),
}


def validate_endpoint(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise DockflowError(
            "Endpoint must be an absolute HTTP(S) URL without credentials, query or fragment"
        )
    try:
        _ = parsed.port
    except ValueError as exc:
        raise DockflowError("Invalid endpoint port") from exc
    return value.rstrip("/")


@dataclass
class Settings:
    config_path: Path
    project_id: str
    root: Path
    state: Path
    work_directory: Path
    definitions: dict
    execution: dict
    images: dict
    artifacts: dict
    reuse: dict
    policies: dict
    client: dict
    service: dict
    sources: dict
    cache: dict
    state_storage: dict

    def effective(self) -> dict:
        def convert(value) -> Any:
            if isinstance(value, Path):
                return str(value)
            if isinstance(value, dict):
                return {key: convert(item) for key, item in value.items()}
            if isinstance(value, list):
                return [convert(item) for item in value]
            return value

        return convert(vars(self))


def _path(value, root: Path) -> Path:
    if not isinstance(value, str | Path) or not str(value):
        raise DockflowError("Filesystem settings must be nonempty paths")
    result = Path(value)
    return (result if result.is_absolute() else root / result).resolve()


def find_config(explicit: str | Path | None, service: bool = False) -> Path:
    selection = (
        explicit
        if explicit is not None
        else os.environ.get("DOCKFLOW_PIPELINES_CONFIG")
    )
    if selection is not None:
        if not str(selection):
            raise DockflowError("An explicitly selected config cannot be empty")
        path = Path(selection).resolve()
        if not path.is_file():
            raise DockflowError(f"Selected configuration does not exist: {path}")
        return path
    if not service:
        for directory in [Path.cwd(), *Path.cwd().parents]:
            path = directory / ".dockflow-pipelines.toml"
            if path.is_file():
                return path
    raise DockflowError(
        "Select a project configuration with --config or DOCKFLOW_PIPELINES_CONFIG"
    )


def load_settings(
    explicit: str | Path | None = None,
    *,
    service: bool = False,
    overrides: dict | None = None,
) -> Settings:
    path = find_config(explicit, service)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DockflowError(f"Cannot parse configuration {path}: {exc}") from exc
    if type(raw.get("schema_version")) is not int or raw["schema_version"] != 1:
        raise DockflowError("Configuration requires schema_version = 1")
    if set(raw) - {"schema_version", *FIELDS}:
        raise DockflowError(
            f"Unknown configuration tables: {sorted(set(raw) - {'schema_version', *FIELDS})}"
        )
    data = copy.deepcopy(DEFAULTS)
    sources = {
        f"{section}.{key}": "default"
        for section, values in DEFAULTS.items()
        for key in values
    }
    sources["schema_version"] = "file"
    sources["config_path"] = (
        "option"
        if explicit is not None
        else "environment"
        if "DOCKFLOW_PIPELINES_CONFIG" in os.environ
        else "discovery"
    )
    for section, allowed in FIELDS.items():
        table = raw.get(section, {})
        if not isinstance(table, dict) or set(table) - allowed:
            raise DockflowError(f"Unknown or invalid fields in [{section}]")
        data[section].update(table)
        sources.update({f"{section}.{key}": "file" for key in table})
    if any(
        "DOCKFLOW_PIPELINES_CACHE_" + field in os.environ
        for field in ("BACKEND", "REGISTRY", "DSN_ENV")
    ):
        raise DockflowError(
            "Cache connection overrides are unsupported; configure the single database in state"
        )
    for suffix, key in ENV.items():
        variable = f"DOCKFLOW_PIPELINES_{suffix}"
        if variable not in os.environ:
            continue
        value = os.environ[variable]
        section, field = key.split(".")
        if not value and suffix != "S3_PREFIX":
            raise DockflowError(f"{variable} cannot be empty")
        try:
            if field in BOOLS:
                if value.lower() not in {"true", "false"}:
                    raise ValueError("expected true or false")
                value = value.lower() == "true"
            elif field in INTS:
                if not re.fullmatch(r"[0-9]+", value):
                    raise ValueError("expected nonnegative decimal integer")
                value = int(value)
            elif field in FLOATS:
                value = float(value)
        except ValueError as exc:
            raise DockflowError(f"Invalid {variable}: {exc}") from exc
        data[section][field] = value
        sources[key] = "environment"
    for key, value in (overrides or {}).items():
        section, field = key.split(".")
        if section not in FIELDS or field not in FIELDS[section]:
            raise DockflowError(f"Unknown setting override: {key}")
        data[section][field] = value
        sources[key] = "option"
    identity = data["project"].get("id")
    if not isinstance(identity, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", identity
    ):
        raise DockflowError(
            "project.id must be a stable ASCII identifier (1–128 characters)"
        )
    root = _path(data["project"]["root"], path.parent)
    state = _path(data["state"]["directory"], root)
    storage = data["state"]
    if not isinstance(storage["backend"], str) or storage["backend"] not in {
        "sqlite",
        "postgresql",
    }:
        raise DockflowError("Unsupported state.backend")
    if storage["backend"] == "sqlite":
        if "dsn_env" in storage:
            raise DockflowError("SQLite state forbids dsn_env")
        storage["database"] = str(
            _path(storage.get("database", state / "state.sqlite"), root)
        )
        reject_network_sqlite(Path(storage["database"]))
        sources.setdefault("state.database", "derived")
    elif (
        "database" in storage
        or not isinstance(storage.get("dsn_env"), str)
        or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", storage["dsn_env"])
    ):
        raise DockflowError("PostgreSQL state requires dsn_env and forbids database")
    work = _path(data["execution"].get("work_directory", state / "work"), root)
    sources.setdefault("execution.work_directory", "derived")
    execution = data["execution"]
    mounts = execution.get("task_mounts", [])
    if not isinstance(mounts, list) or len(mounts) > 32:
        raise DockflowError("execution.task_mounts must be a list of at most 32 mounts")
    mount_sources, mount_targets = set(), set()
    normalized_mounts = []
    for mount in mounts:
        if (
            not isinstance(mount, dict)
            or set(mount) - {"source", "target", "read_only"}
            or not isinstance(mount.get("source"), str)
            or type(mount.get("read_only", True)) is not bool
        ):
            raise DockflowError(
                "Task mounts require source, optional target and boolean read_only"
            )
        source = _path(mount["source"], root)
        target = mount.get("target", str(source))
        if not isinstance(target, str):
            raise DockflowError("Task mount targets must be absolute non-root paths")
        # Explicit destinations belong to the Linux container, not the host OS.
        # Omitted destinations retain the documented same-path source default.
        target_path = PurePosixPath(target) if "target" in mount else source
        if (
            not target_path.is_absolute()
            or ".." in target_path.parts
            or target_path.parent == target_path
        ):
            raise DockflowError("Task mount targets must be absolute non-root paths")
        target = str(target_path)
        if str(source) in mount_sources or target in mount_targets:
            raise DockflowError("Task mount sources and targets must be unique")
        mount_sources.add(str(source))
        mount_targets.add(target)
        normalized_mounts.append(
            {
                "source": str(source),
                "target": target,
                "read_only": mount.get("read_only", True),
            }
        )
    if mounts:
        execution["task_mounts"] = normalized_mounts
    if (
        type(execution["task_parallelism"]) is not int
        or execution["task_parallelism"] != 1
    ):
        raise DockflowError("execution.task_parallelism must be 1")
    for field in ("run_lease_seconds", "run_heartbeat_seconds"):
        number = execution[field]
        if type(number) not in {int, float} or not math.isfinite(number) or number <= 0:
            raise DockflowError(f"execution.{field} must be finite and positive")
    if execution["run_heartbeat_seconds"] + 10 >= execution["run_lease_seconds"]:
        raise DockflowError(
            "Run lease must exceed heartbeat plus database timeout margin"
        )
    for field in ("timeout_seconds", "shutdown_grace_seconds"):
        value = execution[field]
        if type(value) is not int or value < 0:
            raise DockflowError(f"execution.{field} must be a nonnegative integer")
    for table_name, field in [
        ("execution", "cpu_limit"),
        ("execution", "memory_limit_bytes"),
        ("client", "poll_interval_seconds"),
    ]:
        if field not in data[table_name]:
            continue
        value = data[table_name][field]
        if type(value) not in {int, float} or not math.isfinite(value) or value <= 0:
            raise DockflowError(f"{table_name}.{field} must be finite and positive")
        if field == "memory_limit_bytes" and type(value) is not int:
            raise DockflowError("execution.memory_limit_bytes must be an integer")
        if table_name == "execution":
            quantity = value * 1_000_000_000 if field == "cpu_limit" else value
            if not math.isfinite(quantity) or not 1 <= quantity < 2**63:
                raise DockflowError(
                    f"execution.{field} is outside Docker's representable limits"
                )
    for field in ("port", "queue_capacity", "request_max_bytes"):
        value = data["service"][field]
        if type(value) is not int or value <= 0 or (field == "port" and value > 65535):
            raise DockflowError(f"service.{field} is invalid")
    for table_name in ("artifacts", "client"):
        for field in BOOLS & data[table_name].keys():
            if type(data[table_name][field]) is not bool:
                raise DockflowError(f"{table_name}.{field} must be boolean")
    if data["images"]["pull_policy"] not in {"if-missing", "always", "never"}:
        raise DockflowError("Invalid images.pull_policy")
    if data["reuse"]["scope"] not in {"global", "keyed", "run", "none"}:
        raise DockflowError("Invalid reuse.scope")
    if data["reuse"]["scope"] == "keyed" and not data["reuse"].get("scope_key"):
        raise DockflowError("reuse.scope_key is required for keyed scope")
    artifacts = data["artifacts"]
    if artifacts["backend"] not in {"filesystem", "s3"}:
        raise DockflowError("Unsupported artifact backend")
    if artifacts["backend"] == "filesystem":
        if any(key in artifacts for key in ("endpoint", "bucket")):
            raise DockflowError(
                "S3 endpoint/bucket are invalid with filesystem storage"
            )
        if "root" in artifacts and "managed_root" in artifacts:
            raise DockflowError(
                "Configure either artifacts.root or artifacts.managed_root, not both"
            )
        if "managed_root" in artifacts:
            artifacts["managed_root"] = _path(artifacts["managed_root"], root)
        else:
            artifacts["root"] = _path(artifacts.get("root", "artifacts"), root)
            artifacts["managed_root"] = artifacts["root"] / "managed"
            sources.setdefault("artifacts.root", "default")
            sources["artifacts.managed_root"] = "derived"
    else:
        if (
            "root" in artifacts
            or "managed_root" in artifacts
            or not artifacts.get("endpoint")
            or not artifacts.get("bucket")
        ):
            raise DockflowError(
                "S3 requires endpoint/bucket and forbids artifacts.root and artifacts.managed_root"
            )
        validate_endpoint(artifacts["endpoint"])
        if (
            urlsplit(artifacts["endpoint"]).scheme == "http"
            and not artifacts["allow_insecure_http"]
        ):
            raise DockflowError("S3 HTTP requires artifacts.allow_insecure_http = true")
        if any(part in {".", ".."} for part in artifacts["prefix"].split("/")):
            raise DockflowError("S3 prefix cannot contain dot segments")
    for field in ("external_roots", "allowed_uri_prefixes"):
        if not isinstance(artifacts[field], list) or any(
            not isinstance(item, str) or not item for item in artifacts[field]
        ):
            raise DockflowError(
                f"artifacts.{field} must be an array of nonempty strings"
            )
    artifacts["external_roots"] = [
        _path(item, root) for item in artifacts["external_roots"]
    ]
    for prefix in artifacts["allowed_uri_prefixes"]:
        parsed = urlsplit(prefix)
        if (
            parsed.scheme != "s3"
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise DockflowError(
                "Allowed remote URI prefixes must be credential-free s3:// locations"
            )
    protected = [state]
    if artifacts["backend"] == "filesystem":
        # Protect the configured parent directory when artifacts.root is selected.
        managed = artifacts.get("root", artifacts["managed_root"])
        if (
            managed == state
            or managed.is_relative_to(state)
            or state.is_relative_to(managed)
        ):
            raise DockflowError(
                "Managed artifact storage must be outside control state and metadata"
            )
        protected.append(managed)
    if any(item == work or item.is_relative_to(work) for item in protected):
        raise DockflowError(
            "Execution work must not contain control state, metadata or managed artifacts"
        )
    if artifacts["backend"] == "filesystem" and work.is_relative_to(managed):
        raise DockflowError("Execution work must not overlap managed artifacts")
    for external in artifacts["external_roots"]:
        if any(
            external == item
            or external.is_relative_to(item)
            or item.is_relative_to(external)
            for item in [work, *protected]
        ):
            raise DockflowError(
                "External input roots must not overlap state, work or managed storage"
            )
    for kind, registrations in data["definitions"].items():
        if not isinstance(registrations, dict):
            raise DockflowError(f"definitions.{kind} must be a name-to-file map")
        for name, filename in registrations.items():
            if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name):
                raise DockflowError(f"Invalid definition name: {name}")
            if not isinstance(filename, str | Path) or not str(filename):
                raise DockflowError(
                    "Compiled definition sources must be nonempty paths"
                )
            # Check the original source path before normalization erases link
            # provenance. Compiled snapshots must come from regular files.
            if isinstance(filename, str | Path):
                original = Path(filename)
                original = original if original.is_absolute() else root / original
                if any(item.is_symlink() for item in (original, *original.parents)):
                    raise DockflowError(
                        "Compiled definition source paths cannot contain symlinks"
                    )
            # Keep the lexical path for capture to recheck changes after loading.
            source = Path(filename)
            registrations[name] = Path(
                os.path.abspath(source if source.is_absolute() else root / source)
            )
    for table_name in ("client", "service"):
        for field in ("token_file", "ca_file"):
            if field in data[table_name]:
                data[table_name][field] = _path(data[table_name][field], root)
    if "endpoint" in data["client"]:
        data["client"]["endpoint"] = validate_endpoint(data["client"]["endpoint"])
    if "file" in data["policies"]:
        data["policies"]["file"] = _path(data["policies"]["file"], root)
    storage_options = {
        key: value for key, value in storage.items() if key != "directory"
    }
    cache = validate_cache(data["cache"], artifacts, storage_options)
    if storage["backend"] == "sqlite":
        database = Path(storage["database"])
        if database.is_relative_to(work) or (
            artifacts["backend"] == "filesystem"
            and database.is_relative_to(artifacts["managed_root"])
        ):
            raise DockflowError(
                "State database must be outside work and managed artifacts"
            )
    sources.setdefault("cache.database", "derived")
    sources.setdefault("cache.storage_identity", "derived")
    return Settings(
        path,
        identity,
        root,
        state,
        work,
        data["definitions"],
        execution,
        data["images"],
        artifacts,
        data["reuse"],
        data["policies"],
        data["client"],
        data["service"],
        sources,
        cache,
        {key: value for key, value in storage.items() if key != "directory"},
    )
