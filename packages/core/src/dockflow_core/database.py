"""Domain-independent database backend boundary.

Connections, SQL dialect, durability, schema and driver failure classification
live here. Callers retain their transaction/retry policies and decide whether an
uncertain commit invalidates their session or an idempotent operation may retry.
No connection is shared by workers.
"""

from __future__ import annotations

import contextlib
import errno
import hashlib
import importlib
import math
import os
import re
import sqlite3
import stat
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .errors import DockflowError
from .locking import owner_lock as _owner_lock
from .schema import Schema


class OwnerConflict(Exception):
    """Another process holds the requested database lock."""


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

    supports_shared_owners = False

    @staticmethod
    def lock_key(namespace: str, identity: str) -> int:
        """Derive a stable signed advisory key from caller-owned names."""
        encoded_namespace = namespace.encode()
        framed = (
            str(len(encoded_namespace)).encode()
            + b":"
            + encoded_namespace
            + identity.encode()
        )
        return int.from_bytes(
            hashlib.sha256(framed).digest()[:8],
            "big",
            signed=True,
        )

    def transaction_lock(self, connection, key: int, *, shared=False) -> None:
        """SQLite's write transaction already serializes writers."""
        return None

    def try_lock(self, connection, key: int, *, shared=False) -> bool:
        return True

    def unlock(self, connection, key: int, *, shared=False) -> None:
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

    def begin(self, connection, *, readonly=False):
        connection.execute(self.snapshot_begin if readonly else self.write_begin)

    def schema_exists(self, connection, schema: Schema) -> bool:
        if "dockflow_schema_components" not in self.tables(connection):
            return False
        return (
            self.execute(
                connection,
                "SELECT version FROM dockflow_schema_components WHERE name=?",
                (schema.name,),
            ).fetchone()
            is not None
        )

    def validate_schema(self, connection, schema: Schema) -> None:
        if not self.schema_exists(connection, schema):
            raise DockflowError("Database schema is missing", "CONFLICT", 409)
        row = self.execute(
            connection,
            "SELECT version FROM dockflow_schema_components WHERE name=?",
            (schema.name,),
        ).fetchone()
        version = row["version"] if isinstance(row, dict) else row[0]
        if version != schema.version:
            raise DockflowError("Unsupported database schema version", "CONFLICT", 409)
        if not schema.tables <= self.tables(
            connection
        ) or not schema.indexes <= self.indexes(connection):
            raise DockflowError(
                "Database schema is incomplete; restore a verified backup",
                "CONFLICT",
                409,
            )

    def schema_lock(self, connection):
        """The SQLite write transaction already serializes schema creation."""
        return None

    def initialize_schema(self, connection, schema: Schema) -> None:
        """Initialize only the supplied definition inside a caller write transaction."""
        self.schema_lock(connection)
        if self.schema_exists(connection, schema):
            self.validate_schema(connection, schema)
            return
        tables = self.tables(connection)
        registry = "dockflow_schema_components"
        if schema.tables & tables or (
            self.backend == "sqlite" and tables and registry not in tables
        ):
            raise DockflowError(
                "Unregistered database objects conflict; select fresh state",
                "CONFLICT",
                409,
            )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS dockflow_schema_components (name TEXT PRIMARY KEY, version INTEGER NOT NULL CHECK(version>0))"
        )
        for statement in schema.statements:
            connection.execute(statement.format(binary=self.binary_type))
        if schema.initialize is not None:
            schema.initialize(self, connection)
        self.execute(
            connection,
            "INSERT INTO dockflow_schema_components VALUES (?,?)",
            (schema.name, schema.version),
        )
        self.validate_schema(connection, schema)

    @contextlib.contextmanager
    def snapshot(self):
        connection = None
        try:
            connection = self.connect(readonly=True)
            if connection is None:
                raise DockflowError("Database snapshot is missing", "NOT_FOUND", 404)
            self.begin(connection, readonly=True)
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
        from .filesystem import reject_symlinks

        path = Path(self.options["database"])
        try:
            reject_symlinks(path)
        except ValueError:
            raise DockflowError("Database paths cannot contain symlinks") from None
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
                "Database ownership requires a regular database file",
                "UNAVAILABLE",
                503,
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
    supports_shared_owners = True
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
                "Install dockflow-core[postgresql] for PostgreSQL",
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
        self.execute(
            connection,
            "SELECT pg_advisory_xact_lock(?)",
            (self.lock_key("dockflow-core", "schema-registry-v1"),),
        )

    def transaction_lock(self, connection, key, *, shared=False):
        function = "pg_advisory_xact_lock_shared" if shared else "pg_advisory_xact_lock"
        self.execute(connection, f"SELECT {function}(?)", (key,))

    def try_lock(self, connection, key, *, shared=False):
        function = "pg_try_advisory_lock_shared" if shared else "pg_try_advisory_lock"
        return self.execute(connection, f"SELECT {function}(?)", (key,)).fetchone()[0]

    def unlock(self, connection, key, *, shared=False):
        function = "pg_advisory_unlock_shared" if shared else "pg_advisory_unlock"
        self.execute(connection, f"SELECT {function}(?)", (key,))

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
