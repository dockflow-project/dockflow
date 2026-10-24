"""Bounded, non-authoritative coordinator diagnostics.

The SQL state adapter owns session lifetimes and durable state.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from .canonical import loads

OWNER_METADATA_MAX_BYTES = 8192


def _owner_endpoint(value: Any) -> str | None:
    """Only expose a bounded credential-free HTTP endpoint in diagnostics."""
    if not isinstance(value, str) or not value or len(value) > 2048:
        return None
    if not value.isprintable() or any(character.isspace() for character in value):
        return None
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            return None
        _ = parsed.port
    except ValueError:
        return None
    return value


def parse_owner_metadata(raw: bytes) -> tuple[str, dict[str, Any]]:
    """Validate bounded SQL diagnostics; only the live session proves ownership."""
    if len(raw) > OWNER_METADATA_MAX_BYTES:
        return "oversized", {}
    try:
        value = loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        return "malformed", {}
    if not isinstance(value, dict):
        return "malformed", {}
    owner: dict[str, Any] = {}
    if type(value.get("schema_version")) is int and value["schema_version"] == 1:
        owner["schema_version"] = value["schema_version"]
    owner_id = value.get("owner_id")
    if isinstance(owner_id, str):
        try:
            identifier = uuid.UUID(owner_id)
            if identifier.version == 4 and str(identifier) == owner_id:
                owner["owner_id"] = owner_id
        except ValueError:
            pass
    hostname = value.get("hostname")
    if (
        isinstance(hostname, str)
        and 1 <= len(hostname) <= 255
        and hostname.isprintable()
        and hostname.strip()
    ):
        owner["hostname"] = hostname
    pid = value.get("pid")
    if type(pid) is int and 0 < pid <= 2**53 - 1:
        owner["pid"] = pid
    if isinstance(value.get("mode"), str) and value["mode"] in {"local", "service"}:
        owner["mode"] = value["mode"]
    project_id = value.get("project_id")
    if isinstance(project_id, str) and re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", project_id
    ):
        owner["project_id"] = project_id
    acquired_at = value.get("acquired_at")
    if (
        isinstance(acquired_at, str)
        and len(acquired_at) <= 64
        and re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)",
            acquired_at,
        )
    ):
        try:
            parsed = datetime.fromisoformat(acquired_at.replace("Z", "+00:00"))
            if parsed.utcoffset() == UTC.utcoffset(None):
                owner["acquired_at"] = acquired_at
        except ValueError:
            pass
    endpoint = value.get("endpoint")
    if "endpoint" in value and endpoint is None:
        owner["endpoint"] = None
    elif (endpoint := _owner_endpoint(endpoint)) is not None:
        owner["endpoint"] = endpoint
    if type(value.get("schema_version")) is not int:
        return "malformed", owner
    if value["schema_version"] != 1:
        return "unsupported_schema", owner
    required = {
        "schema_version",
        "owner_id",
        "hostname",
        "pid",
        "mode",
        "project_id",
        "acquired_at",
        "endpoint",
    }
    return ("valid" if owner.keys() >= required else "malformed"), owner
