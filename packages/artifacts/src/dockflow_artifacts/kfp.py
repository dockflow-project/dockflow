"""Optional authoring helper; emits only the standard KFP importer contract."""

from __future__ import annotations

import json
from typing import Any


def importer_component(
    artifact_class: Any,
    *,
    metadata: dict[str, Any] | None = None,
    reimport: bool = False,
    name: str | None = None,
) -> Any:
    """Register a published URI as a typed artifact, retaining normal KFP lineage.

    Call this factory outside the parent pipeline definition. Its result is a
    callable graph component accepting ``uri`` as a string or parameter channel.
    Metadata must be static JSON. Pass the resulting task.output to a standard
    downstream artifact input. The sub-pipeline exposes the URI
    as a parent input, which the native KFP 2.17 importer can resolve.
    The caller owns credentials, payload publication and retention.
    """
    try:
        from kfp import dsl
    except ImportError as exc:
        raise ImportError(
            "Install dockflow-artifacts[kfp] to author KFP pipelines"
        ) from exc
    try:
        frozen_metadata = json.loads(json.dumps(metadata, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ValueError("Importer metadata must be static JSON values") from exc
    if frozen_metadata is not None and not isinstance(frozen_metadata, dict):
        raise ValueError("Importer metadata must be a JSON object")

    def register(uri):
        return dsl.importer(
            artifact_uri=uri,
            artifact_class=artifact_class,
            metadata=frozen_metadata,
            reimport=reimport,
        ).output

    # KFP inspects concrete annotations when creating the graph component.
    register.__annotations__ = {"uri": str, "return": artifact_class}
    return dsl.pipeline(name=name or "import-published-artifact")(register)
