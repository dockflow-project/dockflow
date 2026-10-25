"""Immutable publication records in the unified Dockflow database.

Upload bytes outside SQL transactions. Reserve before uploading, and record
completion only after verification. Identical retries resolve uncertain commits.
"""

from __future__ import annotations

import contextlib

from dockflow_core import Database, LockScope, Schema
from dockflow_core.errors import DockflowError

ARTIFACT_TABLE = "dockflow_artifact_records"
ARTIFACT_SCHEMA = Schema(
    name="artifacts",
    version=1,
    statements=(
        "CREATE TABLE dockflow_artifact_records (project_id TEXT NOT NULL, storage_id TEXT NOT NULL, namespace TEXT NOT NULL, record_key TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY(project_id,storage_id,namespace,record_key))",
    ),
    tables=frozenset({ARTIFACT_TABLE}),
)


def publication_scope(adapter: Database, project_id: str) -> LockScope:
    """Shared with callers that coordinate publication and offline maintenance."""
    return LockScope(adapter, "dockflow-project", project_id)


def initialize_schema(adapter: Database, connection) -> None:
    adapter.initialize_schema(connection, ARTIFACT_SCHEMA)


def has_project_records(adapter: Database, connection, project_id: str) -> bool:
    return (
        adapter.execute(
            connection,
            "SELECT 1 FROM dockflow_artifact_records WHERE project_id=? LIMIT 1",
            (project_id,),
        ).fetchone()
        is not None
    )


def project_storage_ids(adapter: Database, connection, project_id: str) -> set[str]:
    return {
        row[0]
        for row in adapter.execute(
            connection,
            "SELECT DISTINCT storage_id FROM dockflow_artifact_records WHERE project_id=?",
            (project_id,),
        ).fetchall()
    }


def project_destinations(adapter: Database, connection, project_id: str) -> list[str]:
    return [
        row[0]
        for row in adapter.execute(
            connection,
            "SELECT record_key FROM dockflow_artifact_records WHERE project_id=? AND namespace='publication-manifests'",
            (project_id,),
        ).fetchall()
    ]


def project_rows(adapter: Database, connection, project_id: str):
    """Export publication records through a caller's consistent snapshot."""
    cursor = adapter.execute(
        connection,
        "SELECT * FROM dockflow_artifact_records WHERE project_id=?",
        (project_id,),
    )
    yield ARTIFACT_TABLE, [column[0] for column in cursor.description], cursor


class ArtifactRecords:
    """Storage-relative records; a supplied writer preserves execution fencing."""

    def __init__(
        self, adapter: Database, project_id: str, storage_id: str, *, writer=None
    ):
        self.database = adapter
        self.scope = publication_scope(adapter, project_id)
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
            self.scope.gate(connection)
            self.scope.serialize(connection)
            initialize_schema(self.database, connection)
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
            self.database.validate_schema(connection, ARTIFACT_SCHEMA)
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
