"""Selective SQL resource queries shared by native, KFP and scheduling adapters."""

from __future__ import annotations

from dockflow_database.errors import DockflowError

from .canonical import loads
from .records import COLLECTIONS

FIELDS = {
    "name",
    "display_name",
    "state",
    "run_id",
    "task_id",
    "pipeline_id",
    "definition_id",
    "experiment_id",
    "availability",
    "idempotency_key",
    "submitted_request_digest",
    "sha256",
    "signature.value",
    "profile",
    "registration",
    "registration_origin",
    "reconciliation_required",
    "sort_name",
    "type",
    "kind",
}


class ResourceQueries:
    def __init__(self, database):
        self.database = database

    def _field(self, field):
        return self.database.adapter.json_text(
            "r.value", "type.schema_title" if field == "type" else field
        )

    def _sort_name(self):
        return self.database.adapter.resource_sort_name("r.value", "r.collection")

    def _predicate(self, collection, filters):
        if collection not in COLLECTIONS:
            raise DockflowError("Unknown resource collection")
        db = self.database
        clauses = ["r.project_id=?", "r.collection=?"]
        values = [db.project_id, collection]
        for field, value in (filters or {}).items():
            if field == "input_artifact_id":
                clauses.append(
                    "EXISTS (SELECT 1 FROM dockflow_resource_inputs i WHERE i.project_id=r.project_id AND i.collection=r.collection AND i.public_id=r.public_id AND i.artifact_id=?)"
                )
                values.append(value)
                continue
            if field not in FIELDS:
                raise DockflowError(f"Unknown resource query field: {field}")
            expression = (
                self._sort_name() if field == "sort_name" else self._field(field)
            )
            if value is None:
                clauses.append(expression + " IS NULL")
                continue
            choices = value if isinstance(value, tuple | list | set) else [value]
            if not choices:
                clauses.append("1=0")
                continue
            clauses.append(expression + " IN (" + ",".join("?" for _ in choices) + ")")
            values.extend(self._scalar(choice) for choice in choices)
        return " AND ".join(clauses), values

    def _scalar(self, value):
        if type(value) is bool:
            return (
                str(value).lower()
                if self.database.backend == "postgresql"
                else str(int(value))
            )
        return str(value)

    def select(
        self, collection, *, filters=None, sort_by=None, boundary=None, limit=None
    ):
        db = self.database
        predicate, values = self._predicate(collection, filters)
        if sort_by is None:
            ordering = "r.public_id ASC"
        else:
            if sort_by not in {
                "created_at",
                "created_at asc",
                "created_at desc",
                "display_name",
                "display_name asc",
                "display_name desc",
            }:
                raise DockflowError("Unsupported resource ordering")
            field = sort_by.split()[0]
            descending = sort_by in {
                "created_at",
                "created_at desc",
                "display_name desc",
            }
            sort = (
                self._sort_name()
                if field == "display_name"
                else f"COALESCE({self._field('created_at')},'')"
            )
            sort = db.adapter.text_order(sort)
            ordering = sort + (" DESC" if descending else " ASC") + ",r.public_id ASC"
            if boundary is not None:
                if (
                    not isinstance(boundary, list)
                    or len(boundary) != 2
                    or not all(isinstance(value, str) for value in boundary)
                ):
                    raise DockflowError("Invalid pagination boundary")
                predicate += f" AND ({sort} {'<' if descending else '>'} ? OR ({sort}=? AND r.public_id>?))"
                values.extend([boundary[0], boundary[0], boundary[1]])
        sql = (
            "SELECT r.value FROM dockflow_state_resources r WHERE "
            + predicate
            + " ORDER BY "
            + ordering
        )
        if limit is not None:
            if type(limit) is not int or limit < 1:
                raise ValueError("Resource query limit must be positive")
            sql += " LIMIT ?"
            values.append(limit)
        with db.reader() as connection:
            rows = (
                db.execute(connection, sql, tuple(values)).fetchall()
                if connection is not None
                else []
            )
        return [loads(row[0]) for row in rows]

    def count(self, collection, *, filters=None):
        predicate, values = self._predicate(collection, filters)
        with self.database.reader() as connection:
            row = (
                self.database.execute(
                    connection,
                    "SELECT COUNT(*) FROM dockflow_state_resources r WHERE "
                    + predicate,
                    tuple(values),
                ).fetchone()
                if connection is not None
                else None
            )
        return int(row[0]) if row else 0

    def queued(self, limit=32):
        db = self.database
        state = self._field("state")
        sequence = f"CAST({self._field('acceptance_sequence')} AS BIGINT)"
        sql = f"""SELECT r.value FROM dockflow_state_resources r
            WHERE r.project_id=? AND r.collection='runs' AND {state}='queued'
            AND NOT EXISTS (SELECT 1 FROM dockflow_run_owners o WHERE
                o.project_id=r.project_id AND o.run_id=r.public_id AND o.active=1
                AND o.lease_expires_at>{db.adapter.clock_expression})
            ORDER BY {sequence},r.public_id LIMIT ?"""
        with db.reader() as connection:
            rows = (
                db.execute(connection, sql, (db.project_id, limit)).fetchall()
                if connection is not None
                else []
            )
        return [loads(row[0]) for row in rows]

    def recovery_runs(self):
        """Only unresolved Runs, excluding live ownership, regardless of history size."""
        db = self.database
        state = self._field("state")
        held = self._field("reconciliation_required")
        attempt_state = db.adapter.json_text("a.value", "state")
        attempt_hold = db.adapter.json_text("a.value", "reconciliation_required")
        attempt_run = db.adapter.json_text("a.value", "run_id")
        truth = "true" if db.backend == "postgresql" else "1"
        sql = f"""SELECT r.value FROM dockflow_state_resources r
            WHERE r.project_id=? AND r.collection='runs'
            AND ({state} IN ('running','cancelling') OR {held}=? OR EXISTS (
                SELECT 1 FROM dockflow_state_resources a WHERE a.project_id=r.project_id
                AND a.collection='attempts' AND {attempt_run}=r.public_id
                AND ({attempt_state} IN ('running','publishing') OR {attempt_hold}=?)))
            AND NOT EXISTS (SELECT 1 FROM dockflow_run_owners o WHERE
                o.project_id=r.project_id AND o.run_id=r.public_id AND o.active=1
                AND o.lease_expires_at>{db.adapter.clock_expression})
            ORDER BY r.public_id"""
        with db.reader() as connection:
            rows = (
                db.execute(connection, sql, (db.project_id, truth, truth)).fetchall()
                if connection is not None
                else []
            )
        return [loads(row[0]) for row in rows]
