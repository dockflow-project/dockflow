"""PostgreSQL per-Run leases; execution authority is checked in every mutation."""

from __future__ import annotations

import contextlib
import threading
from dataclasses import dataclass, field
from typing import Any

from dockflow_database.errors import DockflowError


def ownership_lost():
    return DockflowError(
        "Run ownership was lost; reconcile before further execution",
        "OWNERSHIP_LOST",
        409,
    )


@dataclass
class RunClaim:
    database: Any
    run_id: str
    owner_id: str
    fence: int
    lease_seconds: float
    heartbeat_seconds: float
    recovering: bool = False
    lost: threading.Event = field(default_factory=threading.Event)
    stopping: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None

    def check_local(self):
        self.database.require_owner()
        if self.lost.is_set():
            raise ownership_lost()

    def check(self, connection):
        db = self.database
        self.check_local()
        row = db.execute(
            connection,
            f"SELECT owner_id,fence,active,lease_expires_at, {db.adapter.clock_expression} FROM dockflow_run_owners WHERE project_id=? AND run_id=?{db.adapter.row_lock}",
            (db.project_id, self.run_id),
        ).fetchone()
        if (
            not row
            or row[0] != self.owner_id
            or row[1] != self.fence
            or not row[2]
            or row[3] <= row[4]
        ):
            self.lost.set()
            raise ownership_lost()

    def renew(self):
        db = self.database
        connection = None
        try:
            db.require_owner()
            if self.lost.is_set():
                raise ownership_lost()
            connection = db.adapter.connect()
            db.adapter.begin(connection)
            db.adapter.transaction_gate(connection, db.project_id)
            row = db.adapter.execute(
                connection,
                f"UPDATE dockflow_run_owners SET lease_expires_at={db.adapter.clock_expression}+? WHERE project_id=? AND run_id=? AND owner_id=? AND fence=? AND active=1 AND lease_expires_at>{db.adapter.clock_expression} RETURNING lease_expires_at",
                (
                    self.lease_seconds,
                    db.project_id,
                    self.run_id,
                    self.owner_id,
                    self.fence,
                ),
            ).fetchone()
            if not row:
                raise ownership_lost()
            connection.execute("COMMIT")
        except Exception:
            self.lost.set()
            raise ownership_lost() from None
        finally:
            if connection is not None:
                connection.close()

    def _heartbeat(self):
        while not self.stopping.wait(self.heartbeat_seconds):
            try:
                self.renew()
            except DockflowError:
                return

    def start(self):
        self.thread = threading.Thread(
            target=self._heartbeat, name="dockflow-run-lease", daemon=True
        )
        self.thread.start()

    def stop(self):
        self.stopping.set()
        if self.thread is not None:
            self.thread.join(timeout=11)
        if self.thread is not None and self.thread.is_alive():
            self.lost.set()


def acquire(store, run_id, lease_seconds, heartbeat_seconds, recovering=False):
    db = store.database
    with db.transaction() as connection:
        run = store.get("runs", run_id)
        eligible = (
            run["state"] == "queued"
            if not recovering
            else (
                run["state"] in {"running", "cancelling"}
                or run.get("reconciliation_required")
                or any(
                    attempt.get("reconciliation_required")
                    or attempt.get("state") in {"running", "publishing"}
                    for attempt in store.list("attempts")
                    if attempt.get("run_id") == run_id
                )
            )
        )
        if not eligible:
            raise DockflowError(
                "Run is not eligible for execution or recovery", "RUN_BUSY", 409
            )
        row = db.execute(
            connection,
            f"SELECT fence,active,lease_expires_at,{db.adapter.clock_expression},owner_id FROM dockflow_run_owners WHERE project_id=? AND run_id=?{db.adapter.row_lock}",
            (db.project_id, run_id),
        ).fetchone()
        if row and row[1] and row[2] > row[3]:
            if not recovering and row[4] == db.owner_id:
                return RunClaim(
                    db,
                    run_id,
                    db.owner_id,
                    int(row[0]),
                    lease_seconds,
                    heartbeat_seconds,
                )
            raise DockflowError("Run is owned by another coordinator", "RUN_BUSY", 409)
        fence = int(row[0]) + 1 if row else 1
        db.execute(
            connection,
            f"INSERT INTO dockflow_run_owners VALUES (?,?,?,?,{db.adapter.clock_expression}+?,1) ON CONFLICT(project_id,run_id) DO UPDATE SET owner_id=excluded.owner_id,fence=excluded.fence,lease_expires_at=excluded.lease_expires_at,active=1",
            (db.project_id, run_id, db.owner_id, fence, lease_seconds),
        )
    return RunClaim(
        db, run_id, db.owner_id, fence, lease_seconds, heartbeat_seconds, recovering
    )


def reserve(store, run_id, lease_seconds=120.0):
    """Reserve a direct submission inside its admission transaction."""
    db = store.database
    if not db.adapter.concurrent_runs:
        return
    with db.transaction() as connection:
        db.execute(
            connection,
            f"INSERT INTO dockflow_run_owners VALUES (?,?,?,1,{db.adapter.clock_expression}+?,1)",
            (db.project_id, run_id, db.owner_id, lease_seconds),
        )


@contextlib.contextmanager
def owned_run(
    store, run_id, lease_seconds=120.0, heartbeat_seconds=30.0, *, recovering=False
):
    db = store.database
    if not db.adapter.concurrent_runs:
        db.require_owner()
        yield None
        return
    previous = db.run_claim
    if previous is not None:
        if previous.run_id != run_id:
            raise DockflowError("A worker cannot mutate another Run", "CONFLICT", 409)
        yield previous
        return
    with db.mutex:
        if db.active_run is not None:
            raise DockflowError("This coordinator already owns a Run", "RUN_BUSY", 409)
        claim = acquire(store, run_id, lease_seconds, heartbeat_seconds, recovering)
        db.active_run = run_id
    db.local.run_claim = claim
    claim.start()
    try:
        yield claim
    finally:
        claim.stop()
        db.local.run_claim = None
        with db.mutex:
            db.active_run = None
        # An expired owner can release only its own generation, never a takeover.
        if db.held and not db.poisoned:
            with contextlib.suppress(DockflowError):
                with db.transaction() as connection:
                    db.execute(
                        connection,
                        "UPDATE dockflow_run_owners SET active=0 WHERE project_id=? AND run_id=? AND owner_id=? AND fence=?",
                        (db.project_id, run_id, claim.owner_id, claim.fence),
                    )
