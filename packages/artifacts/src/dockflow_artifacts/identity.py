"""Deterministic publication identity, independent of orchestrator cache records."""

from __future__ import annotations

import hashlib
import math
import struct
from pathlib import Path
from typing import Any

from ._paths import canonical, inventory
from .errors import ArtifactError

PUBLICATION_ID_FORMAT = "dockflow-publication-id-v1"


def _typed(value: Any) -> list[Any]:
    """Canonical JSON tree preserving numeric types and negative zero."""
    if value is None:
        return ["null"]
    if type(value) is bool:
        return ["bool", value]
    if type(value) is int:
        if abs(value) > 2**53 - 1:
            raise ArtifactError("Identity integers must fit the portable 53-bit range")
        return ["int", str(value)]
    if type(value) is float:
        if not math.isfinite(value):
            raise ArtifactError("Identity numbers must be finite")
        return ["float64", struct.pack(">d", value).hex()]
    if type(value) is str:
        try:
            value.encode("utf-8")
        except UnicodeError:
            raise ArtifactError("Identity strings must be valid UTF-8") from None
        return ["string", value]
    if type(value) is list:
        return ["array", [_typed(item) for item in value]]
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ArtifactError("Identity object keys must be strings")
        return ["object", [[_typed(key), _typed(value[key])] for key in sorted(value)]]
    raise ArtifactError("Identity values must be portable JSON values")


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
