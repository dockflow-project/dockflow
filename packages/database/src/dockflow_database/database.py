"""Backend boundary shared by all Dockflow repositories.

Connections, SQL dialect, durability, schema and driver failure classification
live here. Repositories retain their own transaction/retry policies: an uncertain
execution commit must poison its pinned owner, while idempotent cache operations
may retry on fresh short-lived connections. No connection is shared by workers.
"""

from __future__ import annotations

import contextlib
import errno
import hashlib
import importlib
import math
import os
import sqlite3
import stat
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .database_schema import (
    CACHE_SCHEMA,
    PROJECT_TABLES,
    REQUIRED_INDEXES,
    REQUIRED_TABLES,
    RESOURCE_QUERY_FIELDS,
    SCHEMA_LOCK,
    SCHEMA_VERSION,
    STATE_SCHEMA,
)
from .errors import DockflowError
from .locking import owner_lock as _owner_lock


class OwnerConflict(Exception):
    """Another coordinator holds the operational execution lock."""


class Database(ABC):
    backend: str
    binary_type: str
    write_begin: str
    snapshot_begin: str
    row_lock: str
    clock_expression: str

    def __init__(self, options: dict):
        self.options = dict(options)

    @abstractmethod
    def connect(
        self, *, readonly=False, mapping=False, timeout=5.0, create=True
    ) -> Any:
        """Open an autocommit connection, without opening a transaction."""

    @abstractmethod
    def prepare(self) -> None:
        """Prepare durable storage only for an authorized mutating operation."""

    @abstractmethod
    def tables(self, connection) -> set[str]: ...

    @abstractmethod
    def indexes(self, connection) -> set[str]: ...

    @abstractmethod
    def owner_connection(
        self, lock_id: int, *, exclusive: bool = False
    ) -> tuple[Any, Any]: ...

    concurrent_runs = False

    @staticmethod
    def project_key(project_id: str, purpose: str = "state-v1") -> int:
        return int.from_bytes(
            hashlib.sha256(
                ("dockflow-" + purpose + ":" + project_id).encode()
            ).digest()[:8],
            "big",
            signed=True,
        )

    def project_transaction(self, connection, project_id: str) -> None:
        """Serialize short shared-state mutations; SQLite has its writer lock."""
        return None

    def transaction_gate(self, connection, project_id: str) -> None:
        """Exclude maintenance from independent cache/lease transactions."""
        return None

    def try_maintenance(self, connection, project_id: str) -> bool:
        return True

    def end_maintenance(self, connection, project_id: str) -> None:
        return None

    def sql(self, statement: str) -> str:
        return statement

    def execute(self, connection, statement: str, parameters=()):
        return connection.execute(self.sql(statement), parameters)

    def json_text(self, column: str, path: str) -> str:
        """Internal scalar query view; never coerce canonical stored JSON."""
        import re

        if not re.fullmatch(
            r"[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)?", column
        ) or not re.fullmatch(r"[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*", path):
            raise ValueError("Invalid internal JSON query path")
        if self.backend == "postgresql":
            return f"({column}::jsonb #>> '{{{path.replace('.', ',')}}}')"
        return f"CAST(json_extract(CAST({column} AS TEXT), '$.{path}') AS TEXT)"

    def text_order(self, expression: str) -> str:
        collation = '"C"' if self.backend == "postgresql" else "BINARY"
        return f"({expression} COLLATE {collation})"

    def resource_sort_name(self, column="value", collection="collection"):
        version = self.json_text(column, "version_name")
        name = self.json_text(column, "name")
        display = self.json_text(column, "display_name")
        return f"CASE WHEN {collection}='definitions' THEN COALESCE(NULLIF({version},''),{name},'') WHEN {collection}='pipelines' THEN COALESCE({name},'') ELSE COALESCE({display},'') END"

    def event_field(self, field):
        paths = {
            "kind": ("event_kind", "kind"),
            "run_id": (
                "payload.run_id",
                "payload.marker.run_id",
                "payload.manifest.producer.run_id",
            ),
            "attempt_id": (
                "payload.attempt_id",
                "payload.marker.attempt_id",
                "payload.manifest.producer.attempt_id",
            ),
        }[field]
        return (
            "COALESCE("
            + ",".join(self.json_text("value", path) for path in paths)
            + ")"
        )

    def query_indexes(self, connection):
        created = self.text_order(
            f"COALESCE({self.json_text('value', 'created_at')},'')"
        )
        name = self.text_order(self.resource_sort_name())
        connection.execute(
            f"CREATE INDEX dockflow_resource_created ON dockflow_state_resources(project_id,collection,{created} DESC,public_id)"
        )
        connection.execute(
            f"CREATE INDEX dockflow_resource_name_order ON dockflow_state_resources(project_id,collection,{name},public_id)"
        )
        for field in RESOURCE_QUERY_FIELDS:
            identifier = "dockflow_query_" + field.replace(".", "_")
            expression = self.json_text("value", field)
            connection.execute(
                f"CREATE INDEX {identifier} ON dockflow_state_resources(project_id,collection,{expression},{created} DESC,public_id)"
            )
        state = self.json_text("value", "state")
        sequence = f"CAST({self.json_text('value', 'acceptance_sequence')} AS BIGINT)"
        connection.execute(
            f"CREATE INDEX dockflow_queue ON dockflow_state_resources(project_id,collection,{state},{sequence},public_id)"
        )
        event = self.event_field("kind")
        run = self.event_field("run_id")
        attempt = self.event_field("attempt_id")
        connection.execute(
            f"CREATE INDEX dockflow_event_lookup ON dockflow_events(project_id,{event},{run},{attempt},sequence)"
        )

        connection.execute(
            f"CREATE INDEX dockflow_event_attempt ON dockflow_events(project_id,{event},{attempt},sequence)"
        )

    def begin(self, connection, *, readonly=False):
        connection.execute(self.snapshot_begin if readonly else self.write_begin)

    def schema_exists(self, connection) -> bool:
        return "dockflow_schema" in self.tables(connection)

    def validate_schema(self, connection) -> None:
        if not self.schema_exists(connection):
            raise DockflowError("Dockflow database schema is missing", "CONFLICT", 409)
        rows = connection.execute("SELECT version FROM dockflow_schema").fetchall()
        versions = [row["version"] if isinstance(row, dict) else row[0] for row in rows]
        if versions != [SCHEMA_VERSION]:
            raise DockflowError("Unsupported Dockflow database schema", "CONFLICT", 409)
        if not REQUIRED_TABLES <= self.tables(
            connection
        ) or not REQUIRED_INDEXES <= self.indexes(connection):
            raise DockflowError(
                "Dockflow database schema is incomplete; restore a verified backup",
                "CONFLICT",
                409,
            )

    def schema_lock(self, connection):
        """The SQLite write transaction already serializes schema creation."""
        return None

    def initialize_schema(self, connection) -> None:
        """Called inside a write transaction by either repository."""
        self.schema_lock(connection)
        if self.schema_exists(connection):
            self.validate_schema(connection)
            return
        tables = self.tables(connection)
        if tables and (
            self.backend == "sqlite"
            or any(name.startswith(("dockflow_", "df_cache_")) for name in tables)
        ):
            raise DockflowError(
                "Existing database is not a unified Dockflow database; select fresh state",
                "CONFLICT",
                409,
            )
        connection.execute("CREATE TABLE dockflow_schema (version INTEGER PRIMARY KEY)")
        self.execute(
            connection, "INSERT INTO dockflow_schema VALUES (?)", (SCHEMA_VERSION,)
        )
        for statement in STATE_SCHEMA:
            connection.execute(statement.format(binary=self.binary_type))
        for statement in CACHE_SCHEMA:
            connection.execute(statement)
        self.query_indexes(connection)
        self.validate_schema(connection)

    @contextlib.contextmanager
    def snapshot(self):
        connection = None
        try:
            connection = self.connect(readonly=True)
            if connection is None:
                raise DockflowError("Database snapshot is missing", "NOT_FOUND", 404)
            self.begin(connection, readonly=True)
            self.validate_schema(connection)
            yield connection
        except DockflowError:
            raise
        except Exception:
            raise DockflowError(
                "Cannot read Dockflow database snapshot", "UNAVAILABLE", 503
            ) from None
        finally:
            if connection is not None:
                connection.close()

    def project_rows(self, connection, project_id: str):
        """Portable project export including all cache namespaces, excluding owners."""
        for table in PROJECT_TABLES:
            predicate = (
                "project_id=?"
                if table.startswith("dockflow_") or table == "df_cache_scopes"
                else "scope_id IN (SELECT scope_id FROM df_cache_scopes WHERE project_id=?)"
            )
            cursor = self.execute(
                connection, f"SELECT * FROM {table} WHERE {predicate}", (project_id,)
            )
            columns = [column[0] for column in cursor.description]
            yield table, columns, cursor

    @staticmethod
    def unique_error(error) -> bool:
        return (
            isinstance(error, sqlite3.IntegrityError)
            or getattr(error, "sqlstate", None) == "23505"
        )

    @staticmethod
    def retryable_error(error) -> bool:
        code = getattr(error, "sqlstate", None)
        return (
            (
                isinstance(error, sqlite3.OperationalError)
                and getattr(error, "sqlite_errorcode", 0) & 0xFF
                in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
            )
            or code in {"40001", "40P01", "55P03", "57014"}
            or (
                (code is None or code.startswith("08"))
                and type(error).__name__ in {"OperationalError", "InterfaceError"}
                and not isinstance(error, sqlite3.Error)
            )
        )


class SQLiteDatabase(Database):
    backend = "sqlite"
    binary_type = "BLOB"
    write_begin = "BEGIN IMMEDIATE"
    snapshot_begin = "BEGIN"
    row_lock = ""
    clock_expression = "(julianday('now') - 2440587.5) * 86400.0"

    def connect(self, *, readonly=False, mapping=False, timeout=5.0, create=True):
        # Several publishers may initialize a fresh SQLite file simultaneously.
        # Switching to WAL can report BUSY without honoring busy_timeout. Retry
        # only connection setup, before the caller has executed any transaction.
        deadline = time.monotonic() + timeout
        while True:
            try:
                return self._connect_once(
                    readonly=readonly, mapping=mapping, timeout=timeout, create=create
                )
            except sqlite3.OperationalError as error:
                if not self.retryable_error(error) or time.monotonic() >= deadline:
                    raise
                time.sleep(0.01)

    def _connect_once(self, *, readonly=False, mapping=False, timeout=5.0, create=True):
        path = Path(self.options["database"]).absolute()
        if not path.exists() and (readonly or not create):
            if readonly:
                return None
            raise DockflowError(
                "Dockflow database is uninitialized", "UNAVAILABLE", 503
            )
        connection = sqlite3.connect(
            path.as_uri()
            + ("?mode=ro" if readonly else "?mode=rwc" if create else "?mode=rw"),
            uri=True,
            timeout=timeout,
            isolation_level=None,
            check_same_thread=False,
        )
        try:
            if mapping:
                connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            if not readonly:
                if connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] != "wal":
                    raise DockflowError(
                        "Dockflow database requires SQLite WAL", "UNAVAILABLE", 503
                    )
                connection.execute("PRAGMA synchronous=FULL")
            return connection
        except BaseException:
            connection.close()
            raise

    def prepare(self):
        from .locking import no_links as _no_links

        path = Path(self.options["database"])
        _no_links(path)
        reject_network_sqlite(path.absolute())
        path.parent.mkdir(parents=True, exist_ok=True)

    def tables(self, connection):
        return {
            row["name"] if isinstance(row, dict) else row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }

    def indexes(self, connection):
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }

    def owner_connection(self, lock_id, *, exclusive=False):
        self.prepare()
        path = Path(self.options["database"])
        lock_path = (
            path.with_suffix(path.suffix + ".owner") if os.name == "nt" else path
        )
        descriptor = os.open(
            lock_path,
            os.O_RDWR
            | os.O_CREAT
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            raise DockflowError(
                "State ownership requires a regular database file", "UNAVAILABLE", 503
            )
        stream = os.fdopen(descriptor, "r+b")
        try:
            try:
                _owner_lock(stream, acquire=True)
            except OSError as error:
                if error.errno in {errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK}:
                    raise OwnerConflict from None
                raise
            return self.connect(), stream
        except BaseException:
            stream.close()
            raise


class PostgreSQLDatabase(Database):
    concurrent_runs = True
    backend = "postgresql"
    binary_type = "BYTEA"
    write_begin = "BEGIN ISOLATION LEVEL READ COMMITTED"
    snapshot_begin = "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY"
    row_lock = " FOR UPDATE"
    clock_expression = "EXTRACT(EPOCH FROM clock_timestamp())"

    def connect(self, *, readonly=False, mapping=False, timeout=5.0, create=True):
        try:
            module = importlib.import_module("psycopg")
        except ImportError:
            raise DockflowError(
                "Install dockflow-database[postgresql] for PostgreSQL",
                "UNAVAILABLE",
                503,
            ) from None
        dsn = os.environ.get(self.options["dsn_env"])
        if not dsn:
            raise DockflowError(
                "Database DSN environment variable is missing or empty",
                "UNAVAILABLE",
                503,
            )
        milliseconds = max(1, int(timeout * 1000))
        return module.connect(
            dsn,
            autocommit=True,
            connect_timeout=max(1, math.ceil(timeout)),
            options=f"-c statement_timeout={milliseconds} -c lock_timeout={milliseconds} -c synchronous_commit=on",
            row_factory=importlib.import_module("psycopg.rows").dict_row
            if mapping
            else importlib.import_module("psycopg.rows").tuple_row,
        )

    def prepare(self):
        pass

    def sql(self, statement):
        return statement.replace("?", "%s")

    def tables(self, connection):
        return {
            row["tablename"] if isinstance(row, dict) else row[0]
            for row in connection.execute(
                "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname=current_schema()"
            ).fetchall()
        }

    def indexes(self, connection):
        return {
            row["indexname"] if isinstance(row, dict) else row[0]
            for row in connection.execute(
                "SELECT indexname FROM pg_catalog.pg_indexes WHERE schemaname=current_schema()"
            ).fetchall()
        }

    def schema_lock(self, connection):
        self.execute(connection, "SELECT pg_advisory_xact_lock(?)", (SCHEMA_LOCK,))

    def project_transaction(self, connection, project_id):
        self.execute(
            connection,
            "SELECT pg_advisory_xact_lock(?)",
            (self.project_key(project_id, "mutation-v1"),),
        )

    def transaction_gate(self, connection, project_id):
        self.execute(
            connection,
            "SELECT pg_advisory_xact_lock_shared(?)",
            (self.project_key(project_id),),
        )

    def try_maintenance(self, connection, project_id):
        return self.execute(
            connection,
            "SELECT pg_try_advisory_lock(?)",
            (self.project_key(project_id),),
        ).fetchone()[0]

    def end_maintenance(self, connection, project_id):
        self.execute(
            connection, "SELECT pg_advisory_unlock(?)", (self.project_key(project_id),)
        )

    def owner_connection(self, lock_id, *, exclusive=False):
        connection = self.connect()
        try:
            function = (
                "pg_try_advisory_lock" if exclusive else "pg_try_advisory_lock_shared"
            )
            if not self.execute(
                connection, f"SELECT {function}(?)", (lock_id,)
            ).fetchone()[0]:
                raise OwnerConflict
            return connection, None
        except BaseException:
            connection.close()
            raise


def database(options: dict) -> Database:
    backends = {"sqlite": SQLiteDatabase, "postgresql": PostgreSQLDatabase}
    try:
        cls = backends[options["backend"]]
    except (KeyError, TypeError):
        raise DockflowError("Unsupported database backend") from None
    return cls(options)


def reject_network_sqlite(path: Path) -> None:
    """Reject known Linux network mounts; other platforms require operator care."""
    mounts = Path("/proc/mounts")
    if not mounts.exists():
        return
    try:
        rows = [line.split() for line in mounts.read_text().splitlines()]
    except OSError:
        return
    matching = [
        (Path(row[1].replace("\\040", " ")), row[2])
        for row in rows
        if len(row) >= 3 and path.is_relative_to(Path(row[1].replace("\\040", " ")))
    ]
    if matching:
        _, filesystem = max(matching, key=lambda row: len(row[0].parts))
        if filesystem in {
            "nfs",
            "nfs4",
            "cifs",
            "smbfs",
            "9p",
            "ceph",
            "afs",
            "fuse.sshfs",
            "fuse.s3fs",
            "fuse.rclone",
            "glusterfs",
            "lustre",
        }:
            raise DockflowError("SQLite requires a local filesystem")
