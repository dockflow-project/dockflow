"""Versioned record identities shared by persistence and its adapters.

This module is pure: importing identity helpers never imports a native runtime,
opens a database, creates state, or acquires execution ownership.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

COLLECTIONS = {
    "pipelines": "pipeline",
    "components": "component",
    "definitions": "definition",
    "experiments": "experiment",
    "runs": "run",
    "tasks": "task",
    "attempts": "attempt",
    "artifacts": "artifact",
}
TERMINAL = {"succeeded", "failed", "cancelled", "interrupted"}


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def new_id(kind: str) -> str:
    if kind not in COLLECTIONS.values():
        raise ValueError(f"Unknown public ID kind: {kind}")
    return f"{kind}_{uuid.uuid4()}"
