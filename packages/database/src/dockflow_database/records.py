"""Immutable publication records in the unified Dockflow database.

Upload bytes outside SQL transactions. Reserve before uploading, and record
completion only after verification. Identical retries resolve uncertain commits.
"""

from __future__ import annotations

import contextlib
import re
from pathlib import Path

from .database import Database, database
from .errors import DockflowError


def configured_database(options: dict | Database) -> Database:
    if isinstance(options, Database):
        return options
    if not isinstance(options, dict):
        raise DockflowError("Database configuration must be an object")
    backend = options.get("backend")
    field = "database" if backend == "sqlite" else "dsn_env"
    if (
        not isinstance(backend, str)
        or backend not in {"sqlite", "postgresql"}
        or set(options) != {"backend", field}
        or not isinstance(options.get(field), str)
        or not options[field]
    ):
        raise DockflowError("Expected SQLite database path or PostgreSQL dsn_env")
    if backend == "sqlite":
        if not Path(options[field]).is_absolute():
            raise DockflowError("Database path must be absolute")
    elif not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", options[field]):
        raise DockflowError("Database dsn_env must name an environment variable")
    return database(options)


class ArtifactRecords:
    """Storage-relative records; a supplied writer preserves execution fencing."""

    def __init__(
        self, adapter: Database, project_id: str, storage_id: str, *, writer=None
    ):
        self.database = adapter
        self.project_id = project_id
        self.storage_id = storage_id
        self.writer = writer

    @contextlib.contextmanager
    def transaction(self):
        if self.writer is not None:
            with self.writer() as connection:
                yield connection
            return
        connection = None
        try:
            self.database.prepare()
            connection = self.database.connect()
            self.database.begin(connection)
            self.database.initialize_schema(connection)
            self.database.transaction_gate(connection, self.project_id)
            self.database.project_transaction(connection, self.project_id)
            yield connection
            connection.execute("COMMIT")
        except DockflowError:
            raise
        except Exception:
            raise DockflowError(
                "Artifact database operation failed", "UNAVAILABLE", 503
            ) from None
        finally:
            if connection is not None:
                connection.close()

    def get(self, namespace: str, key: str) -> bytes | None:
        with self.database.snapshot() as connection:
            row = self.database.execute(
                connection,
                "SELECT value FROM dockflow_artifact_records WHERE project_id=? AND storage_id=? AND namespace=? AND record_key=?",
                (self.project_id, self.storage_id, namespace, key),
            ).fetchone()
            return row[0].encode() if row else None

    def put_many(self, namespace: str, records: dict[str, bytes]) -> None:
        with self.transaction() as connection:
            for key, value in records.items():
                parameters = (self.project_id, self.storage_id, namespace, key)
                self.database.execute(
                    connection,
                    "INSERT INTO dockflow_artifact_records VALUES (?,?,?,?,?) ON CONFLICT DO NOTHING",
                    (*parameters, value.decode()),
                )
                observed = self.database.execute(
                    connection,
                    "SELECT value FROM dockflow_artifact_records WHERE project_id=? AND storage_id=? AND namespace=? AND record_key=?",
                    parameters,
                ).fetchone()
                if observed[0] != value.decode():
                    raise DockflowError(
                        "Artifact location is reserved for another publication",
                        "CONFLICT",
                        409,
                    )

    def put(self, namespace: str, key: str, value: bytes) -> None:
        self.put_many(namespace, {key: value})
