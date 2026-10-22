"""The versioned, typed JSON digest format used by durable Dockflow records."""

from __future__ import annotations

import hashlib
import json
import math
import struct
from typing import Any

MAX_INTEGER = 2**53 - 1
FORMAT = "dockflow-json-v1"


def _string(value: str) -> str:
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise ValueError("JSON strings cannot contain unpaired surrogates") from exc
    return value


def canonical_tree(value: Any) -> list[Any]:
    """Encode a portable JSON value without losing its numeric type or -0.0."""
    if value is None:
        return ["null"]
    if isinstance(value, bool):
        return ["bool", value]
    if isinstance(value, int):
        if abs(value) > MAX_INTEGER:
            raise ValueError("JSON integer exceeds the portable 53-bit range")
        return ["int", str(value)]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
        return ["float64", struct.pack(">d", value).hex()]
    if isinstance(value, str):
        return ["string", _string(value)]
    if isinstance(value, list):
        return ["array", [canonical_tree(item) for item in value]]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("JSON object keys must be strings")
        return [
            "object",
            [[_string(key), canonical_tree(value[key])] for key in sorted(value)],
        ]
    raise ValueError(f"Unsupported JSON value type: {type(value).__name__}")


def validate_json(value: Any) -> None:
    canonical_tree(value)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        canonical_tree(value), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def json_bytes(value: Any) -> bytes:
    """Serialize validated ordinary JSON, preserving portable parameter types."""
    validate_json(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def loads(source: str | bytes) -> Any:
    """Strict JSON parsing shared by durable records and external boundaries."""

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON object key: {key}")
            result[key] = value
        return result

    def constant(value: str) -> None:
        raise ValueError(f"Non-finite JSON number: {value}")

    result = json.loads(source, object_pairs_hook=pairs, parse_constant=constant)
    validate_json(result)
    return result


canonical_json = canonical_bytes
sha256 = digest
