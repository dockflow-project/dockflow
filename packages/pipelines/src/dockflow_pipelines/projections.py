"""Pure journal-to-domain projection definitions and complete expected row sets."""

from __future__ import annotations

import base64
from dataclasses import dataclass

from dockflow_core.canonical import json_bytes, loads

from .records import COLLECTIONS

# Key columns and remaining columns, in deterministic inspection order.
DOMAINS = {
    "dockflow_state_resources": (("collection", "public_id"), ("value",)),
    "dockflow_definition_sources": (("definition_id",), ("value",)),
    "dockflow_output_sets": (("attempt_id",), ("value",)),
    "dockflow_cache_observations": (("attempt_id",), ("value",)),
    "dockflow_log_snapshots": (("attempt_id", "stream"), ("value",)),
    "dockflow_resource_inputs": (
        ("collection", "public_id", "input_name"),
        ("artifact_id",),
    ),
    "dockflow_log_entries": (
        ("sequence",),
        ("run_id", "task_id", "attempt_id", "value"),
    ),
}


@dataclass(frozen=True)
class Projection:
    table: str
    identity: tuple
    data: bytes


def project_record(record: dict, expand) -> list[Projection]:
    result = []
    if record.get("event_kind") == "cache_observation":
        payload = record["payload"]
        result.append(
            Projection(
                "dockflow_cache_observations",
                (payload["manifest"]["producer"]["attempt_id"],),
                json_bytes(payload),
            )
        )
    for event in expand(record):
        payload = event["payload"]
        kind = event["kind"]
        if kind == "resource_put":
            collection = payload["collection"]
            resource = payload["resource"]
            result.append(
                Projection(
                    "dockflow_state_resources",
                    (collection, resource[COLLECTIONS[collection] + "_id"]),
                    json_bytes(resource),
                )
            )
        elif kind == "output_set":
            result.append(
                Projection(
                    "dockflow_output_sets",
                    (payload["marker"]["attempt_id"],),
                    json_bytes(payload["marker"]),
                )
            )
            result.extend(
                Projection(
                    "dockflow_state_resources",
                    ("artifacts", value["artifact_id"]),
                    json_bytes(value),
                )
                for value in payload["artifacts"].values()
            )
        elif kind == "definition_source":
            result.append(
                Projection(
                    "dockflow_definition_sources",
                    (payload["definition_id"],),
                    base64.b64decode(payload["base64"], validate=True),
                )
            )
        elif kind == "attempt_log_snapshot":
            result.append(
                Projection(
                    "dockflow_log_snapshots",
                    (payload["attempt_id"], payload["stream"]),
                    base64.b64decode(payload["base64"], validate=True),
                )
            )
        elif event.get("event_kind") == "log":
            result.append(
                Projection(
                    "dockflow_log_entries", (event["sequence"],), json_bytes(payload)
                )
            )
    return result


def expected_rows(records, expand):
    expected = {table: {} for table in DOMAINS}
    for record in records:
        for projection in project_record(record, expand):
            table, key, data = projection.table, projection.identity, projection.data
            if table == "dockflow_log_entries":
                payload = loads(data)
                value = (
                    payload["run_id"],
                    payload.get("task_id"),
                    payload.get("attempt_id"),
                    data,
                )
            else:
                value = (data,)
            expected[table][key] = value
            if table == "dockflow_state_resources":
                bindings = expected["dockflow_resource_inputs"]
                for old in [old for old in bindings if old[:2] == key]:
                    del bindings[old]
                for name, artifact in loads(data).get("inputs", {}).items():
                    if isinstance(artifact, str):
                        bindings[(*key, name)] = (artifact,)
    return expected
