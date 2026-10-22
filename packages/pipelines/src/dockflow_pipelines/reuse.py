"""Dependency-local task signatures and explicit reuse scope resolution."""

from __future__ import annotations

from typing import Any

from .canonical import canonical_bytes, digest
from .definitions import DefinitionError

SIGNATURE_FORMAT = "dockflow-task-signature-v1"
ADAPTER = "dockflow-kfp-2.17-v1-posix-owner-home-v1"


def resolve_policy(
    config: dict[str, Any],
    submission: dict[str, Any] | None = None,
    task_policy: dict[str, Any] | None = None,
    *,
    run_id: str = "",
) -> dict[str, Any]:
    task_policy = task_policy or {}
    submission = submission or {}
    scope = task_policy.get(
        "scope", submission.get("scope", config.get("scope", "global"))
    )
    if scope not in {"global", "keyed", "run", "none"}:
        raise DefinitionError(f"Invalid reuse scope: {scope}")
    key = (
        task_policy.get("scope_key", submission.get("key", config.get("scope_key")))
        if scope == "keyed"
        else None
    )
    if scope == "keyed" and (not isinstance(key, str) or not key):
        raise DefinitionError("Keyed reuse requires a nonempty key")
    if scope != "keyed" and "key" in submission:
        raise DefinitionError("A reuse key is only valid with keyed scope")
    return {
        "scope": scope,
        "key": key,
        "token": run_id if scope == "run" else None,
        "cache_safe": task_policy.get("cache_safe", True),
        "retry_safe": task_policy.get("retry_safe", False),
    }


def task_signature(
    *,
    project_id: str,
    component: dict[str, Any],
    executor: dict[str, Any],
    parameters: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
    image: dict[str, Any],
    policy: dict[str, Any],
    resources: dict[str, Any] | None = None,
) -> dict[str, Any]:
    executable = {
        key: value
        for key, value in component.items()
        if key in {"inputDefinitions", "outputDefinitions"}
    }
    # Compiler labels and task/display names do not affect computation.
    executable["executor"] = executor
    artifact_view = {}
    for name, artifact in sorted(artifacts.items()):
        artifact_view[name] = {
            key: artifact.get(key)
            for key in (
                "artifact_id",
                "fingerprint",
                "type",
                "metadata",
                "version",
                "source_version",
            )
        }
        # Components see materialized local URIs; provider namespace still affects
        # the identity of imported snapshots through origin and source revision.
        artifact_view[name]["source_uri"] = artifact.get("source_uri")
    envelope = {
        "format": SIGNATURE_FORMAT,
        "algorithm": "sha256",
        "project_id": project_id,
        "scope": policy["scope"],
        "key": policy.get("key"),
        "scope_token": policy.get("token"),
        "executable": executable,
        "parameters": parameters,
        "artifacts": artifact_view,
        "image": image,
        "resources": resources or {},
        "adapter": ADAPTER,
    }
    return {
        "format": SIGNATURE_FORMAT,
        "algorithm": "sha256",
        "value": digest(envelope),
        "envelope": envelope,
    }


def candidates(
    attempts: list[dict[str, Any]], signature: dict[str, Any]
) -> list[dict[str, Any]]:
    values = [
        attempt
        for attempt in attempts
        if attempt.get("state") == "succeeded"
        and attempt.get("signature", {}).get("value") == signature["value"]
        and attempt.get("publication_state") == "committed"
    ]
    # Most recent time first, ascending public ID as the stable tie break.
    values.sort(key=lambda item: item["attempt_id"])
    values.sort(key=lambda item: item.get("finished_at", ""), reverse=True)
    return values


__all__ = [
    "canonical_bytes",
    "digest",
    "task_signature",
    "resolve_policy",
    "candidates",
]
