"""Deterministic publication identity, independent of orchestrator cache records."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from dockflow_core.canonical import canonical_tree

from ._paths import canonical, inventory
from .errors import ArtifactError

PUBLICATION_ID_FORMAT = "dockflow-publication-id-v1"


def _typed(value: Any) -> list[Any]:
    """Retain this publication format's typed object keys and strict input types."""
    try:
        return canonical_tree(value, typed_keys=True, strict_types=True)
    except ValueError as exc:
        raise ArtifactError(str(exc)) from None


def publication_id(
    *,
    component_name: str,
    component_version: str,
    parameters: dict[str, Any],
    inputs: dict[str, Any] | None = None,
) -> str:
    """Hash a component version and its complete declared invocation inputs.

    Parameters must include resolved defaults and any execution context. Inputs
    identify named artifacts by immutable fingerprint/version and any metadata
    observed by the component. Nothing is inferred from paths or the environment.
    This identifier does not look up, enable or override an execution cache.
    """
    if any(
        not isinstance(value, str) or not value
        for value in (component_name, component_version)
    ):
        raise ArtifactError("Component name and version must be nonempty strings")
    if type(parameters) is not dict or (
        inputs is not None and type(inputs) is not dict
    ):
        raise ArtifactError("Parameters and input identities must be JSON objects")
    envelope = {
        "format": PUBLICATION_ID_FORMAT,
        "component_name": component_name,
        "component_version": component_version,
        "parameters": parameters,
        "inputs": {} if inputs is None else inputs,
    }
    return hashlib.sha256(canonical(_typed(envelope))).hexdigest()


def fingerprint(source: str | Path) -> dict[str, str]:
    """Fingerprint a local file/tree explicitly, ignoring its temporary location."""
    kind, _, digest = inventory(Path(source).absolute())
    return {"algorithm": "sha256", "kind": kind, "value": digest}
