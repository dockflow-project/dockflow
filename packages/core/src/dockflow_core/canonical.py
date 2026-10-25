"""Portable JSON validation, serialization and deterministic typed encoding."""

from __future__ import annotations

import hashlib
import json
import math
import struct
from typing import Any

MAX_INTEGER = 2**53 - 1


def _string(value: str) -> str:
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise ValueError("JSON strings cannot contain unpaired surrogates") from exc
    return value


def canonical_tree(
    value: Any, *, typed_keys: bool = False, strict_types: bool = False
) -> list[Any]:
    """Encode a portable JSON value without losing its numeric type or -0.0."""

    def is_kind(kind):
        return type(value) is kind if strict_types else isinstance(value, kind)

    def encode(item):
        return canonical_tree(item, typed_keys=typed_keys, strict_types=strict_types)

    if value is None:
        return ["null"]
    if is_kind(bool):
        return ["bool", value]
    if is_kind(int):
        if abs(value) > MAX_INTEGER:
            raise ValueError("JSON integer exceeds the portable 53-bit range")
        return ["int", str(value)]
    if is_kind(float):
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
        return ["float64", struct.pack(">d", value).hex()]
    if is_kind(str):
        return ["string", _string(value)]
    if is_kind(list):
        return ["array", [encode(item) for item in value]]
    if is_kind(dict):
        if any(
            (type(key) is not str if strict_types else not isinstance(key, str))
            for key in value
        ):
            raise ValueError("JSON object keys must be strings")
        return [
            "object",
            [
                [encode(key) if typed_keys else _string(key), encode(value[key])]
                for key in sorted(value)
            ],
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


def stable_json_bytes(value: Any) -> bytes:
    """Sorted finite JSON with ASCII escaping, without a typed identity envelope."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
