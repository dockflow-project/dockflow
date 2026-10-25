"""Durable per-key coordination; no artifact I/O occurs inside transactions.

Both backends use the same transitions. The entry lock (SQLite's writer lock or
PostgreSQL's row lock) linearizes decisions; a result grants authority only once
its transaction commits. Connections are short-lived and never inherited by a
worker or held while waiting, computing, or hashing.
"""

from __future__ import annotations

import contextlib
import logging
import math
import random
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any, TypeVar

from dockflow_artifacts.persistence import publication_scope
from dockflow_core.canonical import digest, json_bytes, loads
from dockflow_core.database import database
from dockflow_core.errors import DockflowError

from .database_schema import initialize_schema

LOGGER = logging.getLogger(__name__)
KEY_FORMAT = "dockflow-task-signature-v2"
VALIDATION_VERSION = "dockflow-output-set-v1"
ACTIVE = {"RUNNING", "VALIDATING"}
T = TypeVar("T")

DEFAULT_CACHE = {
    "namespace": "default",
    "topology": "local",
    "shared_filesystem": False,
    "lease_seconds": 120.0,
    "heartbeat_seconds": 30.0,
    "wait_seconds": 1800.0,
    "poll_seconds": 0.25,
    "poll_max_seconds": 5.0,
    "max_attempts": 3,
    "backoff_seconds": 1.0,
    "backoff_max_seconds": 30.0,
    "transaction_timeout_seconds": 5.0,
    "infrastructure_attempts": 4,
    "freshness_seconds": 0.0,
}
CACHE_FIELDS = {*DEFAULT_CACHE, "storage_identity"}


def cache_error(code: str, message: str | None = None) -> DockflowError:
    return DockflowError(
        message or code.replace("_", " ").capitalize(),
        code=code,
        status=409 if code in {"OWNERSHIP_LOST", "CACHE_CONFLICT"} else 503,
    )


def validate_cache(options: dict, artifacts: dict, storage: dict):
    """Validate cache policy against the already selected project database."""
    value = {**DEFAULT_CACHE, **options}
    if set(options) - CACHE_FIELDS:
        raise DockflowError("Unknown cache settings")
    for field in ("namespace", "storage_identity"):
        if field in value and (
            not isinstance(value[field], str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value[field])
        ):
            raise DockflowError(f"cache.{field} requires a safe stable identifier")
    if value["topology"] not in {"local", "shared"}:
        raise DockflowError("cache.topology must be local or shared")
    if type(value["shared_filesystem"]) is not bool:
        raise DockflowError("cache.shared_filesystem must be boolean")
    for field in ("max_attempts", "infrastructure_attempts"):
        if type(value[field]) is not int or not 1 <= value[field] <= 100:
            raise DockflowError(f"cache.{field} must be an integer from 1 to 100")
    for field in DEFAULT_CACHE.keys() - {
        "namespace",
        "topology",
        "shared_filesystem",
        "max_attempts",
        "infrastructure_attempts",
    }:
        number = value[field]
        minimum = (
            0
            if field in {"backoff_seconds", "backoff_max_seconds", "freshness_seconds"}
            else 1e-6
        )
        if (
            type(number) not in {int, float}
            or not math.isfinite(number)
            or number < minimum
        ):
            raise DockflowError(f"cache.{field} has an invalid duration")
    if (
        value["heartbeat_seconds"] + value["transaction_timeout_seconds"] * 2
        >= value["lease_seconds"]
        or value["poll_max_seconds"] < value["poll_seconds"]
        or value["backoff_max_seconds"] < value["backoff_seconds"]
    ):
        raise DockflowError("Cache timing settings leave insufficient lease/poll room")
    if storage["backend"] == "sqlite" and value["topology"] != "local":
        raise DockflowError("SQLite cache supports local processes only")
    value["database"] = dict(storage)
    if value["topology"] == "shared":
        if not value.get("storage_identity"):
            raise DockflowError("Shared cache requires an explicit storage_identity")
        if artifacts["backend"] == "filesystem" and not value["shared_filesystem"]:
            raise DockflowError(
                "Shared filesystem cache requires shared_filesystem=true"
            )
    value.setdefault(
        "storage_identity",
        digest(
            {
                key: str(artifacts[key])
                for key in ("backend", "managed_root", "endpoint", "bucket", "prefix")
                if key in artifacts
            }
        ),
    )
    return value


@dataclass(frozen=True)
class Ownership:
    scope_id: str
    cache_key: str
    attempt_id: str
    owner_id: str
    fencing_token: int
    lease_expires_at: float
    remaining_seconds: float


@dataclass(frozen=True)
class Resolution:
    kind: str
    revision: int
    episode_id: str
    ownership: Ownership | None = None
    artifact: dict | None = None
    reason: str | None = None
    recheck_after: float = 0.0


# Scalar state has database constraints. Portable manifest/provenance JSON is
# opaque to SQL; every transition validates its entry references under the lock.


class Registry:
    def __init__(self, options: dict, project_id: str, *, before_commit=None):
        self.before_commit = before_commit
        self.options = {**DEFAULT_CACHE, **options}
        self.scope_id = digest(
            {"project_id": project_id, "namespace": self.options["namespace"]}
        )
        self.project_id = project_id
        self.database = database(self.options["database"])
        self.scope = publication_scope(self.database, project_id)
        self.postgres = self.database.backend == "postgresql"
        self.policy = {
            key: self.options[key]
            for key in (
                "storage_identity",
                "max_attempts",
                "lease_seconds",
                "heartbeat_seconds",
                "backoff_seconds",
                "backoff_max_seconds",
                "freshness_seconds",
            )
        }
        self.policy["storage_token"] = self.options.get("storage_token")
        self.policy.update(
            key_schema_version=KEY_FORMAT, validation_version=VALIDATION_VERSION
        )

    def _connect(self):
        conn = self.database.connect(
            mapping=True,
            timeout=self.options["transaction_timeout_seconds"],
            create=False,
        )
        try:
            self.database.begin(conn)
            self.scope.gate(conn)
            return conn
        except BaseException:
            conn.close()
            raise

    def _sql(self, conn, sql: str, values=()):
        return self.database.execute(conn, sql, values)

    def _one(self, conn, sql: str, values=()) -> Any:
        row = self._sql(conn, sql, values).fetchone()
        return dict(row) if row is not None else None

    def _time(self, conn) -> float:
        return float(
            self._one(conn, f"SELECT {self.database.clock_expression} AS value")[
                "value"
            ]
        )

    def _transaction(self, callback: Callable[[Any], T]) -> T:
        for ordinal in range(self.options["infrastructure_attempts"]):
            conn = None
            try:
                conn = self._connect()
                result = callback(conn)
                if self.before_commit is not None:
                    self.before_commit()
                claim = self.options.get("execution_claim")
                if claim:
                    row = self._one(
                        conn,
                        f"SELECT owner_id,fence,active,lease_expires_at,{self.database.clock_expression} AS now FROM dockflow_run_owners WHERE project_id=? AND run_id=?",
                        (self.project_id, claim["run_id"]),
                    )
                    if (
                        not row
                        or row["owner_id"] != claim["owner_id"]
                        or row["fence"] != claim["fence"]
                        or not row["active"]
                        or row["lease_expires_at"] <= row["now"]
                    ):
                        raise cache_error("OWNERSHIP_LOST")
                conn.execute("COMMIT")
                return result
            except DockflowError:
                raise
            except Exception as exc:
                if self.database.unique_error(exc):
                    raise cache_error(
                        "CACHE_CONFLICT",
                        "Cache identity or immutable publication conflicts",
                    ) from None
                retryable = self.database.retryable_error(exc)
                if (
                    not retryable
                    or ordinal + 1 == self.options["infrastructure_attempts"]
                ):
                    # Driver strings can contain connection credentials.
                    raise cache_error("CACHE_REGISTRY_UNAVAILABLE") from None
                self.event("registry_contention", reason="TRANSACTION_RETRY")
            finally:
                if conn is not None:
                    with contextlib.suppress(Exception):
                        conn.rollback()
                    with contextlib.suppress(Exception):
                        conn.close()
            time.sleep(random.uniform(0.01, min(0.25, 0.025 * 2**ordinal)))
        raise AssertionError("Unreachable transaction retry")

    def initialize(self) -> None:
        try:
            self.database.prepare()
            # Schema creation and scope registration share one transaction. Create
            # the SQLite file via the common adapter before opening a cache tx.
            conn = self.database.connect(
                timeout=self.options["transaction_timeout_seconds"]
            )
            conn.close()
        except DockflowError:
            raise
        except Exception:
            raise cache_error("CACHE_REGISTRY_UNAVAILABLE") from None

        def migrate(conn):
            initialize_schema(self.database, conn)
            configuration = json_bytes(self.policy).decode()
            self._sql(
                conn,
                "INSERT INTO df_cache_scopes VALUES(?,?,?) ON CONFLICT DO NOTHING",
                (self.scope_id, self.project_id, configuration),
            )
            existing = self._one(
                conn,
                "SELECT configuration FROM df_cache_scopes WHERE scope_id=?",
                (self.scope_id,),
            )
            if loads(existing["configuration"]) != self.policy:
                raise cache_error(
                    "CACHE_CONFLICT", "Cache scope storage or production policy differs"
                )

        self._transaction(migrate)

    def event(self, event: str, key: str | None = None, **fields) -> None:
        LOGGER.info(
            "cache.%s",
            event,
            extra={
                "cache_event": event,
                "scope_id": self.scope_id,
                "cache_key": key,
                **fields,
            },
        )

    def _entry(self, conn, key: str, create: bool = False):
        scope = self._one(
            conn,
            "SELECT configuration FROM df_cache_scopes WHERE scope_id=?",
            (self.scope_id,),
        )
        if scope is None or loads(scope["configuration"]) != self.policy:
            raise cache_error(
                "CACHE_CONFLICT", "Cache scope storage or production policy differs"
            )
        if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{64}", key):
            raise DockflowError("Cache key must be a lowercase SHA-256 digest")
        if create:
            # Insert and SELECT are deliberately separate PostgreSQL statements:
            # READ COMMITTED gets a fresh snapshot after a conflicting insert.
            self._sql(
                conn,
                """INSERT INTO df_cache_entries VALUES(
                ?,?,?,0,0,NULL,NULL,?,0,0,NULL,0,0) ON CONFLICT DO NOTHING""",
                (self.scope_id, key, KEY_FORMAT, str(uuid.uuid4())),
            )
        entry = self._one(
            conn,
            "SELECT * FROM df_cache_entries WHERE scope_id=? AND cache_key=?"
            + self.database.row_lock,
            (self.scope_id, key),
        )
        if entry is None:
            raise DockflowError("Cache entry not found", "NOT_FOUND", 404)
        return entry

    def _save_entry(self, conn, entry: dict, now: float):
        entry["revision"] += 1
        entry["updated_at"] = now
        if not entry["created_at"]:
            entry["created_at"] = now
        fields = [key for key in entry if key not in {"scope_id", "cache_key"}]
        self._sql(
            conn,
            "UPDATE df_cache_entries SET "
            + ",".join(f"{key}=?" for key in fields)
            + " WHERE scope_id=? AND cache_key=?",
            (*[entry[key] for key in fields], self.scope_id, entry["cache_key"]),
        )

    def _attempt(self, conn, attempt_id: str) -> Any:
        return self._one(
            conn, "SELECT * FROM df_cache_attempts WHERE attempt_id=?", (attempt_id,)
        )

    def _artifact(self, conn, artifact_id: str) -> Any:
        artifact = self._one(
            conn, "SELECT * FROM df_cache_artifacts WHERE artifact_id=?", (artifact_id,)
        )
        if artifact:
            artifact["manifest"] = loads(artifact["manifest"])
        return artifact

    @staticmethod
    def _new_episode(entry):
        entry.update(
            episode_id=str(uuid.uuid4()),
            attempts_started=0,
            next_retry_at=0,
            blocked_reason=None,
        )

    def _ownership(self, attempt: dict, now: float) -> Ownership:
        return Ownership(
            **{
                key: attempt[key]
                for key in (
                    "scope_id",
                    "cache_key",
                    "attempt_id",
                    "owner_id",
                    "fencing_token",
                    "lease_expires_at",
                )
            },
            remaining_seconds=max(0, attempt["lease_expires_at"] - now),
        )

    def _assert_owner(self, conn, entry, ownership, now):
        attempt = self._attempt(conn, ownership.attempt_id)
        if not (
            ownership.scope_id == self.scope_id
            and ownership.cache_key == entry["cache_key"]
            and entry["current_attempt_id"] == ownership.attempt_id
            and entry["generation"] == ownership.fencing_token
            and attempt
            and attempt["owner_id"] == ownership.owner_id
            and attempt["scope_id"] == self.scope_id
            and attempt["cache_key"] == ownership.cache_key
            and attempt["fencing_token"] == ownership.fencing_token
            and attempt["state"] in ACTIVE
            and attempt["lease_expires_at"] > now
        ):
            self.event(
                "rejected_stale_mutation",
                ownership.cache_key,
                attempt_id=ownership.attempt_id,
                fence=ownership.fencing_token,
                reason="OWNERSHIP_LOST",
            )
            raise cache_error("OWNERSHIP_LOST")
        return attempt

    def _terminal(self, conn, entry, attempt, now, state, code, retryable):
        self._sql(
            conn,
            "UPDATE df_cache_attempts SET state=?,finished_at=?,error_code=?,retryable=? WHERE attempt_id=?",
            (state, now, code, int(retryable), attempt["attempt_id"]),
        )
        entry["current_attempt_id"] = None
        if not retryable:
            entry["blocked_reason"] = code
        elif entry["attempts_started"] >= self.options["max_attempts"]:
            entry["blocked_reason"] = "CACHE_RETRY_EXHAUSTED"
        else:
            delay = min(
                self.options["backoff_max_seconds"],
                self.options["backoff_seconds"] * 2 ** (entry["attempts_started"] - 1),
            )
            entry["next_retry_at"] = now + delay * random.uniform(0.8, 1.0)
        self._save_entry(conn, entry, now)
        self.event(
            "expiry" if state == "EXPIRED" else state.lower(),
            entry["cache_key"],
            attempt_id=attempt["attempt_id"],
            fence=attempt["fencing_token"],
            reason=code,
        )
        if entry["blocked_reason"]:
            self.event(
                "retry_exhaustion", entry["cache_key"], reason=entry["blocked_reason"]
            )
        elif retryable:
            self.event("retry_scheduled", entry["cache_key"], reason=code)

    def resolve_or_claim(
        self,
        key: str,
        owner_id: str,
        claim_request_id: str,
        run_id: str,
        step_id: str,
        *,
        allow_claim: bool = True,
    ) -> Resolution:
        request_digest = digest(
            [self.scope_id, key, owner_id, run_id, step_id, allow_claim]
        )

        def resolve(conn):
            entry = self._entry(conn, key, create=True)
            now = self._time(conn)
            if not entry["created_at"]:
                self._save_entry(conn, entry, now)
            replay = self._one(
                conn,
                "SELECT * FROM df_cache_attempts WHERE claim_request_id=?",
                (claim_request_id,),
            )
            if replay:
                if replay["request_digest"] != request_digest:
                    raise cache_error(
                        "CACHE_CONFLICT", "Claim request identifier payload differs"
                    )
                if replay["state"] == "SUCCEEDED":
                    return Resolution(
                        "PUBLISHED",
                        entry["revision"],
                        replay["episode_id"],
                        artifact=self._artifact(conn, replay["artifact_id"]),
                    )
                self._assert_owner(conn, entry, self._ownership(replay, now), now)
                return Resolution(
                    "PRODUCE",
                    entry["revision"],
                    entry["episode_id"],
                    ownership=self._ownership(replay, now),
                )
            selected = (
                self._artifact(conn, entry["published_artifact_id"])
                if entry["published_artifact_id"]
                else None
            )
            if selected and selected["state"] == "AVAILABLE":
                if selected["valid_until"] is None or selected["valid_until"] > now:
                    return Resolution(
                        "REUSE",
                        entry["revision"],
                        entry["episode_id"],
                        artifact=selected,
                    )
                entry["published_artifact_id"] = None
                self._new_episode(entry)
                self._save_entry(conn, entry, now)
            if entry["current_attempt_id"]:
                attempt = self._attempt(conn, entry["current_attempt_id"])
                if attempt["state"] not in ACTIVE:
                    raise cache_error(
                        "CACHE_CONFLICT", "Registry owner points to terminal attempt"
                    )
                if attempt["lease_expires_at"] > now:
                    return Resolution(
                        "WAIT",
                        entry["revision"],
                        entry["episode_id"],
                        reason="ACTIVE_PRODUCER",
                        recheck_after=attempt["lease_expires_at"] - now,
                    )
                self._terminal(
                    conn, entry, attempt, now, "EXPIRED", "LEASE_EXPIRED", True
                )
            if entry["blocked_reason"]:
                return Resolution(
                    "BLOCKED",
                    entry["revision"],
                    entry["episode_id"],
                    reason=entry["blocked_reason"],
                )
            if entry["next_retry_at"] > now:
                return Resolution(
                    "WAIT",
                    entry["revision"],
                    entry["episode_id"],
                    reason="RETRY_COOLDOWN",
                    recheck_after=entry["next_retry_at"] - now,
                )
            if not allow_claim:
                return Resolution(
                    "MISS",
                    entry["revision"],
                    entry["episode_id"],
                    reason="PRODUCTION_NOT_SELECTED",
                )
            entry["generation"] += 1
            entry["attempts_started"] += 1
            attempt_id = "attempt_" + str(uuid.uuid4())
            self._sql(
                conn,
                """INSERT INTO df_cache_attempts VALUES(
                ?,?,?,?,?,?,?,?,?,?,'RUNNING',?,?,?,NULL,NULL,NULL,NULL)""",
                (
                    attempt_id,
                    self.scope_id,
                    key,
                    entry["episode_id"],
                    entry["generation"],
                    owner_id,
                    run_id,
                    step_id,
                    claim_request_id,
                    request_digest,
                    now + self.options["lease_seconds"],
                    now,
                    now,
                ),
            )
            entry["current_attempt_id"] = attempt_id
            self._save_entry(conn, entry, now)
            return Resolution(
                "PRODUCE",
                entry["revision"],
                entry["episode_id"],
                ownership=self._ownership(self._attempt(conn, attempt_id), now),
            )

        result = self._transaction(resolve)
        self.event(
            "claim" if result.kind == "PRODUCE" else result.kind.lower(),
            key,
            reason=result.reason,
            attempt_id=result.ownership.attempt_id if result.ownership else None,
            fence=result.ownership.fencing_token if result.ownership else None,
        )
        if result.kind == "PRODUCE":
            self.event("miss", key, run_id=run_id, step_id=step_id)
            if result.ownership and result.ownership.fencing_token > 1:
                self.event(
                    "takeover",
                    key,
                    attempt_id=result.ownership.attempt_id,
                    fence=result.ownership.fencing_token,
                )
        return result

    def renew_lease(self, ownership: Ownership) -> Ownership:
        def renew(conn):
            entry = self._entry(conn, ownership.cache_key)
            now = self._time(conn)
            attempt = self._assert_owner(conn, entry, ownership, now)
            # Never shorten a lease after a backward database clock jump.
            expires = max(
                attempt["lease_expires_at"], now + self.options["lease_seconds"]
            )
            self._sql(
                conn,
                "UPDATE df_cache_attempts SET lease_expires_at=?,heartbeat_at=? WHERE attempt_id=?",
                (expires, now, ownership.attempt_id),
            )
            return self._ownership({**attempt, "lease_expires_at": expires}, now)

        return self._transaction(renew)

    def begin_validation(self, ownership: Ownership) -> None:
        def validate(conn):
            entry = self._entry(conn, ownership.cache_key)
            now = self._time(conn)
            self._assert_owner(conn, entry, ownership, now)
            self._sql(
                conn,
                "UPDATE df_cache_attempts SET state='VALIDATING' WHERE attempt_id=?",
                (ownership.attempt_id,),
            )
            self._save_entry(conn, entry, now)

        self._transaction(validate)
        self.event(
            "validation",
            ownership.cache_key,
            attempt_id=ownership.attempt_id,
            fence=ownership.fencing_token,
        )

    def publish(self, ownership: Ownership, manifest: dict) -> dict:
        from .cache_storage import validate_manifest

        validate_manifest(
            manifest, self.options["storage_identity"], ownership.attempt_id
        )
        manifest_digest = digest(manifest)

        def publish(conn):
            entry = self._entry(conn, ownership.cache_key)
            now = self._time(conn)
            attempt = self._attempt(conn, ownership.attempt_id)
            if not attempt or attempt["state"] != "SUCCEEDED":
                self._assert_owner(conn, entry, ownership, now)
            if (
                manifest["signature"] != ownership.cache_key
                or not attempt
                or attempt["scope_id"] != self.scope_id
                or attempt["cache_key"] != ownership.cache_key
                or attempt["run_id"] != manifest["producer"]["run_id"]
                or attempt["step_id"] != manifest["producer"]["task_id"]
            ):
                raise cache_error(
                    "CACHE_CONFLICT", "Publication differs from claimed identity"
                )
            if (
                attempt
                and attempt["owner_id"] == ownership.owner_id
                and attempt["fencing_token"] == ownership.fencing_token
                and attempt["state"] == "SUCCEEDED"
            ):
                artifact = self._artifact(conn, attempt["artifact_id"])
                if artifact["manifest_digest"] != manifest_digest:
                    raise cache_error(
                        "CACHE_CONFLICT", "Publication replay descriptor differs"
                    )
                return artifact
            self._assert_owner(conn, entry, ownership, now)
            if attempt["state"] != "VALIDATING":
                raise cache_error("CACHE_CONFLICT", "Publication requires validation")
            artifact_id = manifest["artifact_id"]
            freshness = self.options["freshness_seconds"]
            self._sql(
                conn,
                """INSERT INTO df_cache_artifacts VALUES(
                ?,?,?,?,'AVAILABLE',?,?,?,?,?,?,?,NULL,NULL)""",
                (
                    artifact_id,
                    self.scope_id,
                    ownership.cache_key,
                    ownership.attempt_id,
                    self.options["storage_identity"],
                    json_bytes(manifest).decode(),
                    manifest_digest,
                    VALIDATION_VERSION,
                    now,
                    now,
                    now + freshness if freshness else None,
                ),
            )
            self._sql(
                conn,
                "UPDATE df_cache_attempts SET state='SUCCEEDED',artifact_id=?,finished_at=? WHERE attempt_id=?",
                (artifact_id, now, ownership.attempt_id),
            )
            entry.update(
                published_artifact_id=artifact_id,
                current_attempt_id=None,
                blocked_reason=None,
                next_retry_at=0,
            )
            self._save_entry(conn, entry, now)
            return self._artifact(conn, artifact_id)

        artifact = self._transaction(publish)
        self.event(
            "publish",
            ownership.cache_key,
            attempt_id=ownership.attempt_id,
            fence=ownership.fencing_token,
        )
        return artifact

    def finish_failed(
        self,
        ownership: Ownership,
        code: str,
        *,
        retryable: bool = False,
        cancelled: bool = False,
    ) -> None:
        # Error codes only; exception text may contain secrets, DSNs or paths.
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", code):
            raise DockflowError("Cache failure requires a safe reason code")
        state = "CANCELLED" if cancelled else "FAILED"

        def finish(conn):
            entry = self._entry(conn, ownership.cache_key)
            now = self._time(conn)
            attempt = self._attempt(conn, ownership.attempt_id)
            if (
                attempt
                and attempt["owner_id"] == ownership.owner_id
                and attempt["fencing_token"] == ownership.fencing_token
                and attempt["state"] == state
                and attempt["error_code"] == code
            ):
                return
            attempt = self._assert_owner(conn, entry, ownership, now)
            self._terminal(conn, entry, attempt, now, state, code, retryable)

        self._transaction(finish)
        self.event(
            "cancellation" if cancelled else "failure",
            ownership.cache_key,
            attempt_id=ownership.attempt_id,
            fence=ownership.fencing_token,
            reason=code,
        )

    def inspect(self, key: str) -> dict:
        def inspect(conn):
            entry = self._entry(conn, key)
            attempts = [
                dict(row)
                for row in self._sql(
                    conn,
                    "SELECT * FROM df_cache_attempts WHERE scope_id=? AND cache_key=? ORDER BY fencing_token",
                    (self.scope_id, key),
                ).fetchall()
            ]
            artifacts = [
                self._artifact(conn, row["artifact_id"])
                for row in self._sql(
                    conn,
                    "SELECT artifact_id FROM df_cache_artifacts WHERE scope_id=? AND cache_key=? ORDER BY published_at,artifact_id",
                    (self.scope_id, key),
                ).fetchall()
            ]
            return {
                "entry": entry,
                "attempts": attempts,
                "artifacts": artifacts,
                "registry_now": self._time(conn),
                "policy": self.policy,
            }

        return self._transaction(inspect)

    def invalidate(self, key: str, expected_artifact_id: str, reason: str) -> dict:
        if not isinstance(expected_artifact_id, str) or not re.fullmatch(
            r"artifact_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
            expected_artifact_id,
        ):
            raise DockflowError("Cache invalidation requires an artifact ID")
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 256:
            raise DockflowError(
                "Cache invalidation requires a nonsecret reason (1–256 characters)"
            )

        def invalidate(conn):
            entry = self._entry(conn, key)
            now = self._time(conn)
            if entry["published_artifact_id"] != expected_artifact_id:
                raise cache_error("CACHE_CONFLICT", "Selected cache artifact changed")
            if entry["current_attempt_id"]:
                attempt = self._attempt(conn, entry["current_attempt_id"])
                self._terminal(
                    conn, entry, attempt, now, "CANCELLED", "INVALIDATED", True
                )
            self._sql(
                conn,
                "UPDATE df_cache_artifacts SET state='INVALID',invalidated_at=?,invalidation_reason=? WHERE artifact_id=? AND scope_id=? AND cache_key=?",
                (now, reason, expected_artifact_id, self.scope_id, key),
            )
            entry.update(published_artifact_id=None, generation=entry["generation"] + 1)
            self._new_episode(entry)
            self._save_entry(conn, entry, now)
            return entry

        result = self._transaction(invalidate)
        self.event("invalidation", key, reason="ARTIFACT_INVALIDATED")
        return result

    def reset_retry_episode(
        self, key: str, expected_revision: int, reason: str
    ) -> dict:
        if (
            type(expected_revision) is not int
            or expected_revision < 0
            or not isinstance(reason, str)
            or not reason.strip()
            or len(reason) > 256
        ):
            raise DockflowError("Cache reset requires a revision and nonsecret reason")

        def reset(conn):
            entry = self._entry(conn, key)
            now = self._time(conn)
            if entry["revision"] != expected_revision:
                raise cache_error("CACHE_CONFLICT", "Cache revision changed")
            if entry["current_attempt_id"]:
                attempt = self._attempt(conn, entry["current_attempt_id"])
                if attempt["lease_expires_at"] > now:
                    raise cache_error("CACHE_CONFLICT", "A cache producer is active")
                self._terminal(
                    conn, entry, attempt, now, "EXPIRED", "LEASE_EXPIRED", True
                )
            if entry["published_artifact_id"]:
                artifact = self._artifact(conn, entry["published_artifact_id"])
                if artifact["state"] == "AVAILABLE" and (
                    artifact["valid_until"] is None or artifact["valid_until"] > now
                ):
                    raise cache_error(
                        "CACHE_CONFLICT", "A reusable artifact is selected"
                    )
                entry["published_artifact_id"] = None
            self._new_episode(entry)
            entry["generation"] += 1
            self._save_entry(conn, entry, now)
            return entry

        result = self._transaction(reset)
        self.event("retry_reset", key, reason=reason, reason_code="EXPLICIT_RESET")
        return result


__all__ = ["Registry", "Ownership", "Resolution", "asdict"]
