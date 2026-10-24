"""Immutable accepted computation choices, independent of coordinator access."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from pathlib import PurePosixPath

from dockflow_database.errors import DockflowError

from .cache_registry import DEFAULT_CACHE, validate_cache
from .canonical import json_bytes, loads, validate_json
from .reuse import resolve_policy

EXECUTION_FIELDS = {
    "timeout_seconds",
    "shutdown_grace_seconds",
    "cpu_limit",
    "memory_limit_bytes",
}


@dataclass(frozen=True)
class ExecutionChoices:
    encoded: bytes

    @classmethod
    def capture(cls, settings, task_policies: dict | None = None):
        return cls.from_record(
            {
                "schema_version": 1,
                "execution": {
                    key: value
                    for key, value in settings.execution.items()
                    if key in EXECUTION_FIELDS
                },
                "images": dict(settings.images),
                "reuse": dict(settings.reuse),
                "cache": {
                    key: settings.cache[key]
                    for key in (*DEFAULT_CACHE, "storage_identity")
                },
                "task_policies": task_policies or {},
                "mounts": [
                    {"target": mount["target"], "read_only": mount["read_only"]}
                    for mount in settings.execution.get("task_mounts", [])
                ],
            }
        )

    @classmethod
    def from_record(cls, record):
        try:
            validate_json(record)
            if (
                not isinstance(record, dict)
                or set(record)
                != {
                    "schema_version",
                    "execution",
                    "images",
                    "reuse",
                    "cache",
                    "task_policies",
                    "mounts",
                }
                or type(record["schema_version"]) is not int
                or record["schema_version"] != 1
            ):
                raise ValueError
            execution = record["execution"]
            if (
                not isinstance(execution, dict)
                or set(execution) - EXECUTION_FIELDS
                or not {"timeout_seconds", "shutdown_grace_seconds"} <= execution.keys()
            ):
                raise ValueError
            for key, value in execution.items():
                if (
                    type(value) not in {int, float}
                    or not math.isfinite(value)
                    or value < 0
                    or key in {"cpu_limit", "memory_limit_bytes"}
                    and value <= 0
                    or key != "cpu_limit"
                    and type(value) is not int
                ):
                    raise ValueError
                if key in {"cpu_limit", "memory_limit_bytes"}:
                    quantity = value * 1_000_000_000 if key == "cpu_limit" else value
                    if not math.isfinite(quantity) or not 1 <= quantity < 2**63:
                        raise ValueError
            if set(record["images"]) != {"pull_policy"} or record["images"][
                "pull_policy"
            ] not in {"always", "never", "if-missing"}:
                raise ValueError
            if set(record["reuse"]) - {"scope", "scope_key"} or record["reuse"].get(
                "scope"
            ) not in {"global", "keyed", "run", "none"}:
                raise ValueError
            if set(record["cache"]) != {*DEFAULT_CACHE, "storage_identity"}:
                raise ValueError
            validate_cache(
                record["cache"], {"backend": "s3"}, {"backend": "postgresql"}
            )
            resolve_policy(record["reuse"])
            if not isinstance(record["task_policies"], dict) or not isinstance(
                record["mounts"], list
            ):
                raise ValueError
            for task, policy in record["task_policies"].items():
                if (
                    not isinstance(task, str)
                    or not task
                    or not isinstance(policy, dict)
                    or set(policy) - {"scope", "scope_key", "cache_safe", "retry_safe"}
                    or "scope" in policy
                    and policy["scope"] not in {"global", "keyed", "run", "none"}
                    or "scope_key" in policy
                    and (
                        not isinstance(policy["scope_key"], str)
                        or not policy["scope_key"]
                    )
                    or any(
                        key in policy and type(policy[key]) is not bool
                        for key in ("cache_safe", "retry_safe")
                    )
                ):
                    raise ValueError
            targets = []
            for mount in record["mounts"]:
                if (
                    not isinstance(mount, dict)
                    or set(mount) != {"target", "read_only"}
                    or not isinstance(mount["target"], str)
                    or not PurePosixPath(mount["target"]).is_absolute()
                    or ".." in PurePosixPath(mount["target"]).parts
                    or type(mount["read_only"]) is not bool
                ):
                    raise ValueError
                targets.append(mount["target"])
            if len(targets) != len(set(targets)):
                raise ValueError
            return cls(json_bytes(record))
        except (ValueError, TypeError, KeyError, AttributeError, DockflowError):
            raise DockflowError(
                "Invalid admitted execution choices", "CONFLICT", 409
            ) from None

    def to_record(self):
        return loads(self.encoded)

    @property
    def task_policies(self):
        return self.to_record()["task_policies"]

    def bind(self, settings):
        admitted = self.to_record()
        execution = {
            key: value
            for key, value in settings.execution.items()
            if key not in EXECUTION_FIELDS and key != "task_mounts"
        }
        execution.update(admitted["execution"])
        for field in ("cpu_limit", "memory_limit_bytes"):
            current = settings.execution.get(field)
            requested = execution.get(field)
            if current is not None and (requested is None or requested > current):
                raise DockflowError(
                    "Coordinator resource policy cannot honor admitted limits",
                    "CONFLICT",
                    409,
                )
        available = {
            mount["target"]: mount
            for mount in settings.execution.get("task_mounts", [])
        }
        mounts = []
        for requested in admitted["mounts"]:
            match = available.get(requested["target"])
            if match is None or match["read_only"] != requested["read_only"]:
                raise DockflowError(
                    "Coordinator cannot provide an admitted task mount", "CONFLICT", 409
                )
            mounts.append(dict(match))
        execution["task_mounts"] = mounts
        cache = validate_cache(
            admitted["cache"], settings.artifacts, settings.state_storage
        )
        return replace(
            settings,
            execution=execution,
            images=admitted["images"],
            reuse=admitted["reuse"],
            cache=cache,
        )
