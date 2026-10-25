"""Consumer-supplied schema descriptions, without a registry of consumers."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .database import Database


@dataclass(frozen=True)
class Schema:
    name: str
    version: int
    statements: tuple[str, ...]
    tables: frozenset[str]
    indexes: frozenset[str] = frozenset()
    initialize: Callable[[Database, Any], None] | None = None

    def __post_init__(self):
        if (
            not re.fullmatch(r"[a-z][a-z0-9_-]*", self.name)
            or type(self.version) is not int
            or self.version < 1
            or not self.tables
            or any(
                not re.fullmatch(r"[a-z_][a-z0-9_]*", name)
                for name in self.tables | self.indexes
            )
            or "dockflow_schema_components" in self.tables
        ):
            raise ValueError("Invalid schema definition")
