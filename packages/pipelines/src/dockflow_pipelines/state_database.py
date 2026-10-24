"""Transactional project state and pinned-session execution ownership.

SQLite and PostgreSQL share the domain journal and resource schema. The owner session
never reconnects: losing it revokes all subsequent mutation authority.
"""

from __future__ import annotations

import contextlib
import os
import socket
import threading
import uuid
from typing import Any

from dockflow_database.database import OwnerConflict, database
from dockflow_database.errors import DockflowError

from .canonical import json_bytes, loads
from .ownership import _owner_endpoint, parse_owner_metadata
from .queries import ResourceQueries
from .records import utc_now


class StateDatabase:
    def __init__(self, options: dict, project_id: str):
        self.adapter = database(options)
        self.queries = ResourceQueries(self)
        self.options = self.adapter.options
        self.backend = options["backend"]
        self.project_id = project_id
        self.connection: Any = None
        self.lock_stream: Any = None
        self.mutex = threading.RLock()
        self.depth = 0
        self.owner_id: str | None = None
        self.poisoned = False
        self.snapshot_active = False
        self.snapshot_connection: Any = None
        self.local = threading.local()
        self.exclusive = False
        self.maintenance_depth = 0
        self.active_run: str | None = None
        self.lock_id = self.adapter.project_key(project_id)

    @property
    def held(self) -> bool:
        return self.connection is not None

    def _connect(self, *, readonly: bool = False) -> Any:
        try:
            return self.adapter.connect(readonly=readonly)
        except DockflowError:
            raise
        except Exception:
            raise DockflowError(
                "Cannot connect to the state database", "UNAVAILABLE", 503
            ) from None

    def execute(self, connection: Any, sql: str, parameters: tuple = ()) -> Any:
        try:
            return self.adapter.execute(connection, sql, parameters)
        except Exception:
            raise DockflowError(
                "State database operation failed; inspect retained state before retrying",
                "UNAVAILABLE",
                503,
            ) from None

    def _schema_exists(self, connection: Any) -> bool:
        return self.adapter.schema_exists(connection)

    def _validate_schema(self, connection: Any) -> None:
        self.adapter.validate_schema(connection)

    @contextlib.contextmanager
    def reader(self):
        with self.mutex:
            if self.snapshot_active:
                yield self.snapshot_connection
                return
            if self.held:
                yield self.connection
                return
            connection = self._connect(readonly=True)
            try:
                if connection is None or not self._schema_exists(connection):
                    yield None
                else:
                    self._validate_schema(connection)
                    yield connection
            except DockflowError:
                raise
            except Exception:
                raise DockflowError(
                    "Cannot read state database", "UNAVAILABLE", 503
                ) from None
            finally:
                if connection is not None:
                    connection.close()

    @contextlib.contextmanager
    def snapshot(self):
        """One consistent read boundary; never initialize a missing store."""
        with self.mutex:
            if (
                self.snapshot_active
                or self.depth
                or (self.held and not self.adapter.concurrent_runs)
            ):
                yield
                return
            connection = self._connect(readonly=True)
            try:
                if connection is not None and self._schema_exists(connection):
                    self.execute(
                        connection,
                        self.adapter.snapshot_begin,
                    )
                    self._validate_schema(connection)
                    self.snapshot_connection = connection
                self.snapshot_active = True
                yield
            finally:
                self.snapshot_active = False
                self.snapshot_connection = None
                if connection is not None:
                    connection.close()

    def require_owner(self) -> None:
        if self.poisoned:
            raise DockflowError(
                "State ownership session is uncertain; reacquisition and reconciliation are required",
                "UNAVAILABLE",
                503,
            )
        if not self.held:
            raise DockflowError(
                "Mutating control state requires coordinator ownership", "CONFLICT", 409
            )
        if getattr(self.connection, "closed", False):
            raise DockflowError(
                "State ownership session was lost; reconciliation is required",
                "UNAVAILABLE",
                503,
            )

    @contextlib.contextmanager
    def transaction(self):
        with self.mutex:
            self.require_owner()
            outer = self.depth == 0
            if outer:
                self.execute(self.connection, self.adapter.write_begin)
                try:
                    self.adapter.project_transaction(self.connection, self.project_id)
                    self.check_run_authority(self.connection)
                except BaseException:
                    with contextlib.suppress(Exception):
                        self.connection.rollback()
                    raise
            savepoint = f"dockflow_nested_{self.depth}"
            if not outer:
                self.execute(self.connection, f"SAVEPOINT {savepoint}")
            self.depth += 1
            try:
                yield self.connection
                if outer:
                    self.check_run_authority(self.connection)
                    try:
                        self.execute(self.connection, "COMMIT")
                    except BaseException:
                        self.poisoned = True
                        raise
                else:
                    self.execute(self.connection, f"RELEASE SAVEPOINT {savepoint}")
            except BaseException:
                if outer:
                    try:
                        self.execute(self.connection, "ROLLBACK")
                    except Exception:
                        # A broken session is never replaced automatically.
                        pass
                else:
                    try:
                        self.execute(
                            self.connection, f"ROLLBACK TO SAVEPOINT {savepoint}"
                        )
                        self.execute(self.connection, f"RELEASE SAVEPOINT {savepoint}")
                    except Exception:
                        self.poisoned = True
                raise
            finally:
                self.depth -= 1

    @property
    def run_claim(self):
        return getattr(self.local, "run_claim", None)

    def check_run_authority(self, connection=None) -> None:
        claim = self.run_claim
        if claim is not None:
            claim.check(connection or self.connection)

    @contextlib.contextmanager
    def maintenance(self):
        self.require_owner()
        with self.mutex:
            if self.run_claim is not None or self.active_run is not None:
                raise DockflowError(
                    "Maintenance cannot run inside execution ownership", "CONFLICT", 409
                )
            outer = self.maintenance_depth == 0
            if outer and not self.adapter.try_maintenance(
                self.connection, self.project_id
            ):
                raise DockflowError(
                    "Other coordinators prevent exclusive maintenance", "CONFLICT", 409
                )
            self.maintenance_depth += 1
            try:
                yield
            finally:
                self.maintenance_depth -= 1
                if outer:
                    self.adapter.end_maintenance(self.connection, self.project_id)

    def current_sequence(self) -> int:
        with self.reader() as connection:
            row = (
                self.execute(
                    connection,
                    "SELECT sequence FROM dockflow_project_counters WHERE project_id=?",
                    (self.project_id,),
                ).fetchone()
                if connection is not None
                else None
            )
        return int(row[0]) if row else 0

    def allocate_sequence(self) -> int:
        self.require_owner()
        self.execute(
            self.connection,
            "INSERT INTO dockflow_project_counters VALUES (?,0) ON CONFLICT DO NOTHING",
            (self.project_id,),
        )
        return int(
            self.execute(
                self.connection,
                "UPDATE dockflow_project_counters SET sequence=sequence+1 WHERE project_id=? RETURNING sequence",
                (self.project_id,),
            ).fetchone()[0]
        )

    def _initialize_schema(self) -> None:
        with self.transaction() as connection:
            self.adapter.initialize_schema(connection)

    def _conflict(self) -> DockflowError:
        owner = {}
        try:
            with self.reader() as connection:
                if connection is not None:
                    row = self.execute(
                        connection,
                        "SELECT value FROM dockflow_state_owners WHERE project_id=?",
                        (self.project_id,),
                    ).fetchone()
                    if row:
                        _, owner = parse_owner_metadata(bytes(row[0]))
        except Exception:
            pass
        endpoint = owner.get("endpoint")
        action = (
            f" Use --endpoint {endpoint} explicitly."
            if endpoint
            else " Stop the current owner before retrying."
        )
        return DockflowError(
            "State is owned by another Dockflow coordinator." + action,
            "CONFLICT",
            409,
            details=[
                {
                    "field": "state.backend",
                    "reason": "owner_conflict",
                    "owner_metadata_status": "valid" if owner else "unavailable",
                    "owner": owner,
                }
            ],
        )

    def acquire(self, endpoint: str | None = None, *, exclusive: bool = False) -> None:
        if self.held:
            raise RuntimeError("State ownership is already acquired")
        connection = None
        stream = None
        try:
            try:
                connection, stream = self.adapter.owner_connection(
                    self.lock_id, exclusive=exclusive
                )
            except OwnerConflict:
                raise self._conflict() from None
            self.connection = connection
            self.exclusive = exclusive or not self.adapter.concurrent_runs
            self.poisoned = False
            self.lock_stream = stream
            self._initialize_schema()
            self.owner_id = str(uuid.uuid4())
            diagnostic = {
                "schema_version": 1,
                "owner_id": self.owner_id,
                "project_id": self.project_id,
                "hostname": socket.gethostname(),
                "pid": os.getpid(),
                "mode": "service" if endpoint else "local",
                "acquired_at": utc_now(),
                "endpoint": _owner_endpoint(endpoint),
            }
            with self.transaction():
                self.execute(
                    connection,
                    "INSERT INTO dockflow_state_owners(project_id,value) VALUES (?,?) ON CONFLICT(project_id) DO UPDATE SET value=excluded.value",
                    (self.project_id, json_bytes(diagnostic)),
                )
        except BaseException as exc:
            self.connection = None
            self.lock_stream = None
            if connection is not None:
                connection.close()
            if stream is not None:
                stream.close()
            if isinstance(exc, DockflowError | KeyboardInterrupt | SystemExit):
                raise
            raise DockflowError(
                "Cannot acquire state database ownership", "UNAVAILABLE", 503
            ) from None

    def release(self) -> None:
        connection, self.connection = self.connection, None
        stream, self.lock_stream = self.lock_stream, None
        self.owner_id = None
        try:
            if connection is not None:
                connection.close()
        finally:
            if stream is not None:
                stream.close()

    def _value(
        self, table: str, identity: dict, *, required: bool = True
    ) -> bytes | None:
        predicate = " AND ".join(name + "=?" for name in identity)
        with self.reader() as connection:
            row = (
                self.execute(
                    connection,
                    f"SELECT value FROM {table} WHERE project_id=? AND {predicate}",
                    (self.project_id, *identity.values()),
                ).fetchone()
                if connection is not None
                else None
            )
        if row is None:
            if not required:
                return None
            raise DockflowError("Domain record not found", "NOT_FOUND", 404)
        return row[0].encode() if isinstance(row[0], str) else bytes(row[0])

    def _json(
        self, table: str, identity: dict, *, required: bool = True
    ) -> dict | None:
        raw = self._value(table, identity, required=required)
        if raw is None:
            return None
        try:
            value = loads(raw)
            if not isinstance(value, dict):
                raise ValueError
            return value
        except (ValueError, UnicodeError):
            raise DockflowError("Invalid domain record", "CONFLICT", 409) from None

    def _put_value(
        self, table: str, identity: dict, data: bytes, *, immutable: bool = False
    ) -> None:
        with self.transaction() as connection:
            if immutable:
                current = self._value(table, identity, required=False)
                if current is not None:
                    if current != data:
                        raise DockflowError(
                            "Conflicting immutable domain record", "CONFLICT", 409
                        )
                    return
            columns = ("project_id", *identity, "value")
            placeholders = ",".join("?" for _ in columns)
            conflict = ",".join(columns[:-1])
            self.execute(
                connection,
                f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders}) ON CONFLICT({conflict}) DO UPDATE SET value=excluded.value",
                (
                    self.project_id,
                    *identity.values(),
                    data.decode()
                    if table in {"dockflow_events", "dockflow_state_resources"}
                    else data,
                ),
            )

    def project_metadata(self, name: str) -> dict | None:
        return self._json("dockflow_project_metadata", {"name": name}, required=False)

    def set_project_metadata(self, name: str, value: dict, *, immutable=False) -> None:
        self._put_value(
            "dockflow_project_metadata",
            {"name": name},
            json_bytes(value),
            immutable=immutable,
        )

    def events(
        self, *, kind=None, run_id=None, attempt_id=None
    ) -> list[tuple[int, dict]]:
        clauses = ["project_id=?"]
        parameters = [self.project_id]
        if kind is not None:
            clauses.append(self.adapter.event_field("kind") + "=?")
            parameters.append(kind)
        if run_id is not None:
            clauses.append(self.adapter.event_field("run_id") + "=?")
            parameters.append(run_id)
        if attempt_id is not None:
            expression = self.adapter.event_field("attempt_id")
            clauses.append(expression + "=?")
            parameters.append(attempt_id)
        with self.reader() as connection:
            rows = (
                self.execute(
                    connection,
                    "SELECT sequence,value FROM dockflow_events WHERE "
                    + " AND ".join(clauses)
                    + " ORDER BY sequence",
                    tuple(parameters),
                ).fetchall()
                if connection is not None
                else []
            )
        try:
            return [(int(row[0]), loads(row[1])) for row in rows]
        except (ValueError, UnicodeError):
            raise DockflowError("Invalid journal event", "CONFLICT", 409) from None

    def append_event(self, event: dict) -> None:
        self._put_value(
            "dockflow_events",
            {"sequence": event["sequence"]},
            json_bytes(event),
            immutable=True,
        )

    def definition_source(self, definition_id: str) -> bytes:
        value = self._value(
            "dockflow_definition_sources", {"definition_id": definition_id}
        )
        assert value is not None
        return value

    def put_definition_source(self, definition_id: str, value: bytes) -> None:
        self._put_value(
            "dockflow_definition_sources",
            {"definition_id": definition_id},
            value,
            immutable=True,
        )

    def output_set(self, attempt_id: str) -> dict | None:
        return self._json(
            "dockflow_output_sets", {"attempt_id": attempt_id}, required=False
        )

    def put_output_set(self, marker: dict) -> None:
        self._put_value(
            "dockflow_output_sets",
            {"attempt_id": marker["attempt_id"]},
            json_bytes(marker),
            immutable=True,
        )

    def cache_observation(self, attempt_id: str) -> dict | None:
        return self._json(
            "dockflow_cache_observations", {"attempt_id": attempt_id}, required=False
        )

    def put_cache_observation(self, attempt_id: str, value: dict) -> None:
        self._put_value(
            "dockflow_cache_observations",
            {"attempt_id": attempt_id},
            json_bytes(value),
            immutable=True,
        )

    def log_snapshot(self, attempt_id: str, stream: str) -> bytes:
        value = self._value(
            "dockflow_log_snapshots", {"attempt_id": attempt_id, "stream": stream}
        )
        assert value is not None
        return value

    def put_log_snapshot(self, attempt_id: str, stream: str, value: bytes) -> None:
        self._put_value(
            "dockflow_log_snapshots",
            {"attempt_id": attempt_id, "stream": stream},
            value,
            immutable=True,
        )

    def resource(self, collection: str, public_id: str) -> dict | None:
        return self._json(
            "dockflow_state_resources",
            {"collection": collection, "public_id": public_id},
            required=False,
        )

    def clear_projections(self) -> None:
        with self.transaction() as connection:
            for table in (
                "dockflow_resource_inputs",
                "dockflow_log_entries",
                "dockflow_state_resources",
                "dockflow_definition_sources",
                "dockflow_output_sets",
                "dockflow_cache_observations",
                "dockflow_log_snapshots",
            ):
                self.execute(
                    connection,
                    f"DELETE FROM {table} WHERE project_id=?",
                    (self.project_id,),
                )

    def owner_metadata(self) -> dict:
        with self.reader() as connection:
            row = (
                self.execute(
                    connection,
                    "SELECT value FROM dockflow_state_owners WHERE project_id=?",
                    (self.project_id,),
                ).fetchone()
                if connection is not None
                else None
            )
        return parse_owner_metadata(bytes(row[0]))[1] if row else {}

    def put_resource(self, collection: str, resource: dict) -> None:
        from .records import COLLECTIONS

        with self.transaction() as connection:
            public_id = resource[COLLECTIONS[collection] + "_id"]
            if (
                self.execute(
                    connection,
                    "SELECT numeric_id FROM dockflow_state_ids WHERE project_id=? AND collection=? AND public_id=?",
                    (self.project_id, collection, public_id),
                ).fetchone()
                is None
            ):
                row = self.execute(
                    connection,
                    "SELECT COALESCE(MAX(numeric_id),0)+1 FROM dockflow_state_ids WHERE project_id=? AND collection=?",
                    (self.project_id, collection),
                ).fetchone()
                self.execute(
                    connection,
                    "INSERT INTO dockflow_state_ids VALUES (?,?,?,?)",
                    (self.project_id, collection, public_id, row[0]),
                )
            self.execute(
                connection,
                "INSERT INTO dockflow_state_resources(project_id,collection,public_id,value) VALUES (?,?,?,?) ON CONFLICT(project_id,collection,public_id) DO UPDATE SET value=excluded.value",
                (
                    self.project_id,
                    collection,
                    resource[COLLECTIONS[collection] + "_id"],
                    json_bytes(resource).decode(),
                ),
            )
            self.execute(
                connection,
                "DELETE FROM dockflow_resource_inputs WHERE project_id=? AND collection=? AND public_id=?",
                (self.project_id, collection, public_id),
            )
            for name, artifact in resource.get("inputs", {}).items():
                if isinstance(artifact, str):
                    self.execute(
                        connection,
                        "INSERT INTO dockflow_resource_inputs VALUES (?,?,?,?,?)",
                        (self.project_id, collection, public_id, name, artifact),
                    )

    def put_log_entry(self, sequence: int, payload: dict):
        with self.transaction() as connection:
            self.execute(
                connection,
                "INSERT INTO dockflow_log_entries VALUES (?,?,?,?,?,?) ON CONFLICT(project_id,sequence) DO UPDATE SET run_id=excluded.run_id,task_id=excluded.task_id,attempt_id=excluded.attempt_id,value=excluded.value",
                (
                    self.project_id,
                    sequence,
                    payload["run_id"],
                    payload.get("task_id"),
                    payload.get("attempt_id"),
                    json_bytes(payload).decode(),
                ),
            )

    def log_entries(
        self, run_id, *, sequence=0, offset=0, task_id=None, attempt_id=None, limit=None
    ):
        clauses = ["project_id=?", "run_id=?", "sequence" + (">=?" if offset else ">?")]
        values = [self.project_id, run_id, sequence]
        for name, value in (("task_id", task_id), ("attempt_id", attempt_id)):
            if value is not None:
                clauses.append(name + "=?")
                values.append(value)
        sql = (
            "SELECT sequence,value FROM dockflow_log_entries WHERE "
            + " AND ".join(clauses)
            + " ORDER BY sequence"
        )
        if limit is not None:
            sql += " LIMIT ?"
            values.append(limit)
        with self.reader() as connection:
            rows = (
                self.execute(connection, sql, tuple(values)).fetchall()
                if connection is not None
                else []
            )
        return [{**loads(row[1]), "sequence": int(row[0])} for row in rows]

    def project_empty(self, *, include_cache: bool = False) -> bool:
        with self.reader() as connection:
            if connection is None:
                return True
            if (
                include_cache
                and self.execute(
                    connection,
                    "SELECT 1 FROM dockflow_artifact_records WHERE project_id=? LIMIT 1",
                    (self.project_id,),
                ).fetchone()
            ):
                return False
            if self.execute(
                connection,
                "SELECT 1 FROM dockflow_project_counters WHERE project_id=?",
                (self.project_id,),
            ).fetchone():
                return False
            if (
                include_cache
                and self.execute(
                    connection,
                    "SELECT 1 FROM df_cache_scopes WHERE project_id=? LIMIT 1",
                    (self.project_id,),
                ).fetchone()
            ):
                return False
            return all(
                self.execute(
                    connection,
                    f"SELECT 1 FROM {table} WHERE project_id=? LIMIT 1",
                    (self.project_id,),
                ).fetchone()
                is None
                for table in (
                    "dockflow_project_metadata",
                    "dockflow_resource_inputs",
                    "dockflow_log_entries",
                    "dockflow_events",
                    "dockflow_definition_sources",
                    "dockflow_output_sets",
                    "dockflow_cache_observations",
                    "dockflow_log_snapshots",
                    "dockflow_state_resources",
                    "dockflow_state_ids",
                )
            )

    def internal_id(self, collection: str, public_id: str) -> int | None:
        with self.reader() as connection:
            row = (
                self.execute(
                    connection,
                    "SELECT numeric_id FROM dockflow_state_ids WHERE project_id=? AND collection=? AND public_id=?",
                    (self.project_id, collection, public_id),
                ).fetchone()
                if connection is not None
                else None
            )
        return int(row[0]) if row else None

    def cache_manifests(self) -> list[dict]:
        with self.reader() as connection:
            if connection is None:
                return []
            rows = self.execute(
                connection,
                "SELECT manifest FROM df_cache_artifacts WHERE state='AVAILABLE' AND scope_id IN (SELECT scope_id FROM df_cache_scopes WHERE project_id=?)",
                (self.project_id,),
            ).fetchall()
            return [loads(row[0]) for row in rows]

    def artifact_store_ids(self) -> set[str]:
        with self.reader() as connection:
            if connection is None:
                return set()
            return {
                row[0]
                for row in self.execute(
                    connection,
                    "SELECT DISTINCT storage_id FROM dockflow_artifact_records WHERE project_id=?",
                    (self.project_id,),
                ).fetchall()
            }

    def publication_destinations(self) -> list[str]:
        with self.reader() as connection:
            if connection is None:
                return []
            return [
                row[0]
                for row in self.execute(
                    connection,
                    "SELECT record_key FROM dockflow_artifact_records WHERE project_id=? AND namespace='publication-manifests'",
                    (self.project_id,),
                ).fetchall()
            ]

    def cache_store_tokens(self) -> set[str]:
        with self.reader() as connection:
            if connection is None:
                return set()
            rows = self.execute(
                connection,
                "SELECT configuration FROM df_cache_scopes WHERE project_id=?",
                (self.project_id,),
            ).fetchall()
            return {
                value for row in rows if (value := loads(row[0]).get("storage_token"))
            }

    def copy_project(self, source: StateDatabase) -> None:
        """Copy one consistent project snapshot, including cache fencing/history."""
        with (
            source.adapter.snapshot() as source_connection,
            self.transaction() as target_connection,
        ):
            for table, columns, rows in source.adapter.project_rows(
                source_connection, source.project_id
            ):
                placeholders = ",".join("?" for _ in columns)
                statement = (
                    f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})"
                )
                for row in rows:
                    self.execute(target_connection, statement, tuple(row))

    def resources(self, collection: str) -> list[dict]:
        return self.queries.select(collection)
