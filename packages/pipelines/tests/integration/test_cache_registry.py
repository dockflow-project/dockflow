"""One conformance suite, real connections and independent spawned processes.

PostgreSQL is opt-in: DOCKFLOW_TEST_CACHE_POSTGRES_DSN must select a disposable
database. Each case uses a fresh scope; no existing table or scope is deleted.
"""

import copy
import multiprocessing
import os
import queue
import sqlite3
import time
import uuid
from pathlib import Path

import pytest
from dockflow_database.errors import DockflowError
from dockflow_pipelines.artifacts import ArtifactStore
from dockflow_pipelines.cache import Lease, wait_for_resolution
from dockflow_pipelines.cache_registry import Registry
from dockflow_pipelines.cache_storage import make_manifest
from dockflow_pipelines.canonical import digest, json_bytes
from dockflow_pipelines.metadata import ControlStore
from dockflow_pipelines.records import new_id


@pytest.fixture(
    params=["sqlite", pytest.param("postgresql", marks=pytest.mark.postgresql)]
)
def registry(request, tmp_path):
    options = {
        "database": {
            "backend": request.param,
            "database": str(tmp_path / "state.sqlite"),
        },
        "storage_identity": "dockflow-test-store",
        "backoff_seconds": 0,
        "backoff_max_seconds": 0,
        "poll_seconds": 0.02,
        "poll_max_seconds": 0.1,
        "wait_seconds": 30,
    }
    if request.param == "postgresql":
        if not os.environ.get("DOCKFLOW_TEST_CACHE_POSTGRES_DSN"):
            pytest.skip("Set DOCKFLOW_TEST_CACHE_POSTGRES_DSN to a disposable database")
        options["database"] = {
            "backend": "postgresql",
            "dsn_env": "DOCKFLOW_TEST_CACHE_POSTGRES_DSN",
        }
    result = Registry(options, "dockflow-cache-test-" + uuid.uuid4().hex)
    result.initialize()
    return result


def claim(registry, key=None, request_id=None, owner="owner"):
    return registry.resolve_or_claim(
        key or digest("key"),
        owner,
        request_id or str(uuid.uuid4()),
        new_id("run"),
        new_id("task"),
    )


def expire(registry, ownership):
    registry._transaction(
        lambda conn: registry._sql(
            conn,
            "UPDATE df_cache_attempts SET lease_expires_at=0 WHERE attempt_id=?",
            (ownership.attempt_id,),
        )
    )


def empty_manifest(registry, ownership):
    attempt = next(
        item
        for item in registry.inspect(ownership.cache_key)["attempts"]
        if item["attempt_id"] == ownership.attempt_id
    )
    return make_manifest(
        {},
        {},
        {},
        {
            "run_id": attempt["run_id"],
            "task_id": attempt["step_id"],
            "attempt_id": ownership.attempt_id,
        },
        ownership.cache_key,
        registry.options["storage_identity"],
    )


def publish_empty(registry, ownership):
    registry.begin_validation(ownership)
    manifest = empty_manifest(registry, ownership)
    return registry.publish(ownership, manifest)


def assert_invariants(registry, key):
    view = registry.inspect(key)
    entry, attempts = view["entry"], view["attempts"]
    fences = [item["fencing_token"] for item in attempts]
    assert fences == sorted(set(fences))
    assert entry["generation"] >= max(fences)
    active = [item for item in attempts if item["state"] in {"RUNNING", "VALIDATING"}]
    assert len(active) <= 1
    assert [item["attempt_id"] for item in active] == (
        [entry["current_attempt_id"]] if entry["current_attempt_id"] else []
    )
    for item in attempts:
        assert item["scope_id"] == entry["scope_id"] and item["cache_key"] == key
        assert (item["finished_at"] is None) == (
            item["state"] in {"RUNNING", "VALIDATING"}
        )
    for artifact in view["artifacts"]:
        assert artifact["manifest_digest"] == digest(artifact["manifest"])
        producer = next(
            item
            for item in attempts
            if item["attempt_id"] == artifact["producer_attempt_id"]
        )
        assert producer["state"] == "SUCCEEDED"
        assert producer["artifact_id"] == artifact["artifact_id"]
    if entry["published_artifact_id"]:
        assert (
            next(
                item
                for item in view["artifacts"]
                if item["artifact_id"] == entry["published_artifact_id"]
            )["state"]
            == "AVAILABLE"
        )


def test_claim_replay_publish_restart_and_policy_conflict(registry):
    key = digest("key")
    args = (key, "owner", str(uuid.uuid4()), new_id("run"), new_id("task"))
    first = registry.resolve_or_claim(*args)
    assert (
        registry.resolve_or_claim(*args).ownership.attempt_id
        == first.ownership.attempt_id
    )
    assert claim(registry).kind == "WAIT"
    with pytest.raises(DockflowError, match="payload differs"):
        registry.resolve_or_claim(key, "other-owner", *args[2:])
    artifact = publish_empty(registry, first.ownership)
    assert registry.publish(first.ownership, artifact["manifest"]) == artifact
    assert registry.resolve_or_claim(*args).kind == "PUBLISHED"
    reopened = Registry(registry.options, "unused")
    reopened.scope_id = registry.scope_id
    reopened.initialize()
    assert claim(reopened).artifact == artifact
    conflicting = Registry({**registry.options, "max_attempts": 8}, "unused")
    conflicting.scope_id = registry.scope_id
    with pytest.raises(DockflowError, match="policy differs"):
        conflicting.initialize()
    assert_invariants(registry, key)


def test_expiry_fences_every_owner_mutation_and_stale_invalidation(registry):
    old = claim(registry).ownership
    expire(registry, old)
    replacement = claim(registry).ownership
    assert replacement.fencing_token > old.fencing_token
    for mutation in (
        lambda: registry.renew_lease(old),
        lambda: registry.begin_validation(old),
        lambda: registry.finish_failed(old, "OLD_FAILURE", retryable=True),
        lambda: registry.finish_failed(old, "OLD_CANCEL", cancelled=True),
        lambda: registry.publish(old, empty_manifest(registry, old)),
    ):
        with pytest.raises(DockflowError) as error:
            mutation()
        assert error.value.code == "OWNERSHIP_LOST"
    original = publish_empty(registry, replacement)
    with pytest.raises(DockflowError):
        registry.finish_failed(old, "LATE_FAILURE")
    registry.invalidate(old.cache_key, original["artifact_id"], "TEST_CORRUPTION")
    newer = claim(registry).ownership
    current = publish_empty(registry, newer)
    with pytest.raises(DockflowError) as error:
        registry.invalidate(old.cache_key, original["artifact_id"], "DELAYED_REPORT")
    assert error.value.code == "CACHE_CONFLICT"
    assert claim(registry).artifact == current
    # An old publication acknowledgment never reselects invalidated history.
    assert (
        registry.publish(replacement, original["manifest"])["artifact_id"]
        == original["artifact_id"]
    )
    assert claim(registry).artifact == current
    assert_invariants(registry, old.cache_key)


def test_budget_nonretryable_reset_and_restart(registry):
    for ordinal in range(3):
        ownership = claim(registry).ownership
        assert ownership.fencing_token == ordinal + 1
        registry.finish_failed(ownership, "EXECUTION_FAILED", retryable=True)
        registry.initialize()
    blocked = claim(registry)
    assert blocked.kind == "BLOCKED" and blocked.reason == "CACHE_RETRY_EXHAUSTED"
    view = registry.inspect(digest("key"))
    assert view["entry"]["attempts_started"] == 3
    with pytest.raises(DockflowError):
        registry.reset_retry_episode(
            digest("key"), view["entry"]["revision"] - 1, "TEST_RESET"
        )
    registry.reset_retry_episode(digest("key"), view["entry"]["revision"], "TEST_RESET")
    ownership = claim(registry).ownership
    with pytest.raises(DockflowError, match="active"):
        registry.reset_retry_episode(
            digest("key"),
            registry.inspect(digest("key"))["entry"]["revision"],
            "RESET_LIVE",
        )
    registry.finish_failed(ownership, "VALIDATION_FAILED")
    assert claim(registry).reason == "VALIDATION_FAILED"
    assert_invariants(registry, digest("key"))


def test_shared_cooldown_and_expired_budget(registry):
    registry.options.update(backoff_seconds=10, backoff_max_seconds=10)
    ownership = claim(registry).ownership
    expire(registry, ownership)
    waiting = claim(registry)
    assert waiting.kind == "WAIT" and waiting.reason == "RETRY_COOLDOWN"
    view = registry.inspect(digest("key"))
    deadline = view["entry"]["next_retry_at"]
    for _ in range(8):
        assert claim(registry).kind == "WAIT"
    assert registry.inspect(digest("key"))["entry"]["next_retry_at"] == deadline
    assert registry.inspect(digest("key"))["entry"]["attempts_started"] == 1
    assert_invariants(registry, digest("key"))


def test_waiter_timeout_and_cancellation_leave_producer_untouched(registry):
    ownership = claim(registry).ownership
    with pytest.raises(DockflowError) as error:
        wait_for_resolution(
            registry,
            ownership.cache_key,
            "waiter",
            "run",
            "task",
            lambda: None,
            lambda _: None,
            deadline=time.monotonic() + 0.1,
        )
    assert error.value.code == "CACHE_WAIT_TIMEOUT"
    with pytest.raises(DockflowError) as error:
        wait_for_resolution(
            registry,
            ownership.cache_key,
            "waiter",
            "run",
            "task",
            lambda: "cancelled",
            lambda _: None,
        )
    assert error.value.code == "CACHE_CANCELLED"
    assert registry.renew_lease(ownership).remaining_seconds > 0
    assert registry.inspect(ownership.cache_key)["entry"]["attempts_started"] == 1


def test_ambiguous_claim_and_publish_commit_recover_without_extra_attempt(
    registry, monkeypatch
):
    original = registry._connect
    pending = [True]

    class Ambiguous:
        def __init__(self, connection):
            self.connection = connection

        def execute(self, sql, *args):
            result = self.connection.execute(sql, *args)
            if sql == "COMMIT" and pending[0]:
                pending[0] = False
                if registry.postgres:
                    import psycopg

                    raise psycopg.OperationalError("injected response loss")
                error = sqlite3.OperationalError("injected response loss")
                error.sqlite_errorcode = sqlite3.SQLITE_BUSY
                raise error
            return result

        def rollback(self):
            return self.connection.rollback()

        def close(self):
            return self.connection.close()

    monkeypatch.setattr(registry, "_connect", lambda: Ambiguous(original()))
    ownership = claim(registry).ownership
    assert registry.inspect(ownership.cache_key)["entry"]["attempts_started"] == 1
    registry.begin_validation(ownership)
    manifest = empty_manifest(registry, ownership)
    pending[0] = True
    published = registry.publish(ownership, manifest)
    assert published["manifest"] == manifest
    changed = {**manifest, "artifact_id": new_id("artifact")}
    with pytest.raises(DockflowError, match="differs"):
        registry.publish(ownership, changed)
    assert_invariants(registry, ownership.cache_key)


def test_database_clock_jumps_never_revive_stale_owner(registry, monkeypatch):
    ownership = claim(registry).ownership
    original = registry._time
    monkeypatch.setattr(registry, "_time", lambda conn: original(conn) + 100000)
    replacement = claim(registry).ownership
    monkeypatch.setattr(registry, "_time", lambda conn: original(conn) - 100000)
    with pytest.raises(DockflowError) as error:
        registry.renew_lease(ownership)
    assert error.value.code == "OWNERSHIP_LOST"
    registry.renew_lease(replacement)
    assert_invariants(registry, ownership.cache_key)


def test_healthy_heartbeat_and_lost_responses(registry, monkeypatch):
    registry.options.update(
        lease_seconds=0.8, heartbeat_seconds=0.1, transaction_timeout_seconds=0.05
    )
    started = time.monotonic()
    ownership = claim(registry).ownership
    with Lease(registry, ownership, started) as lease:
        until = time.monotonic() + 1.6
        while time.monotonic() < until:
            time.sleep(0.05)
            lease.check()
        assert claim(registry).kind == "WAIT"
    expire(registry, ownership)
    fresh = claim(registry).ownership

    def unavailable(_):
        raise DockflowError("injected", "CACHE_REGISTRY_UNAVAILABLE", 503)

    monkeypatch.setattr(registry, "renew_lease", unavailable)
    with Lease(registry, fresh, time.monotonic()) as lease:
        assert lease.lost.wait(2)
        with pytest.raises(DockflowError):
            lease.check()


def _producer_manifest(registry, ownership, root, ordinal):
    state = Path(root) / f"worker-{ordinal}"
    store = ControlStore(state, "dockflow-cache-bytes")
    with store.owner():
        store.initialize()
        artifacts = ArtifactStore(
            store, {"backend": "filesystem", "managed_root": Path(root) / "managed"}
        )
        source = state / "source"
        source.mkdir()
        (source / "file.txt").write_text("verified shared cache bytes")
        (source / "empty").mkdir()
        original = next(
            item
            for item in registry.inspect(ownership.cache_key)["attempts"]
            if item["attempt_id"] == ownership.attempt_id
        )
        producer = {
            "pipeline_name": "dockflow-cache-test",
            "task_name": "produce",
            "run_id": original["run_id"],
            "task_id": original["step_id"],
            "attempt_id": ownership.attempt_id,
            "definition_id": new_id("definition"),
            "output_name": "dataset",
            "cache_namespace": "cache-v1",
        }
        contract = {
            "artifacts": {
                "dataset": {
                    "artifactType": {
                        "schemaTitle": "system.Dataset",
                        "schemaVersion": "0.0.1",
                    }
                }
            }
        }
        output = artifacts.publish(
            source,
            {"schema_title": "system.Dataset", "schema_version": "0.0.1"},
            producer,
        )
        manifest = make_manifest(
            {"dataset": output},
            {},
            contract,
            {field: producer[field] for field in ("run_id", "task_id", "attempt_id")},
            ownership.cache_key,
            registry.options["storage_identity"],
        )
        artifacts.verify_cache(manifest, registry.options["storage_identity"])
        return manifest


def _contender(options, scope, root, ordinal, barrier, result):
    registry = Registry(options, "unused")
    registry.scope_id = scope
    try:
        registry.initialize()
        barrier.wait(timeout=25)
        outcome, started = wait_for_resolution(
            registry,
            digest("contention"),
            str(uuid.uuid4()),
            new_id("run"),
            new_id("task"),
            lambda: None,
            lambda _: None,
        )
        produced = outcome.kind == "PRODUCE"
        if produced:
            with Lease(registry, outcome.ownership, started):
                registry.begin_validation(outcome.ownership)
                manifest = _producer_manifest(
                    registry, outcome.ownership, root, ordinal
                )
                artifact = registry.publish(outcome.ownership, manifest)
        else:
            artifact = outcome.artifact
        control = ControlStore(Path(root) / f"reader-{ordinal}", "dockflow-cache-bytes")
        artifact_store = ArtifactStore(
            control, {"backend": "filesystem", "managed_root": Path(root) / "managed"}
        )
        artifact_store.verify_cache(artifact["manifest"], options["storage_identity"])
        result.put((produced, artifact["manifest_digest"]))
    except BaseException as exc:
        result.put(("error", type(exc).__name__, str(exc)))


@pytest.mark.parametrize("repeat", range(3))
def test_twenty_process_barrier_one_producer_and_verified_bytes(
    registry, tmp_path, repeat
):
    if repeat == 2:
        initial = claim(registry, key=digest("contention")).ownership
        registry.finish_failed(initial, "RETRYABLE_EXECUTION", retryable=True)
    context = multiprocessing.get_context("spawn")
    barrier, result = context.Barrier(20), context.Queue()
    processes = [
        context.Process(
            target=_contender,
            args=(
                registry.options,
                registry.scope_id,
                str(tmp_path),
                ordinal,
                barrier,
                result,
            ),
        )
        for ordinal in range(20)
    ]
    try:
        for process in processes:
            process.start()
        outcomes = [result.get(timeout=45) for _ in processes]
        assert all(item[0] != "error" for item in outcomes), outcomes
        assert sum(item[0] for item in outcomes) == 1
        assert len({item[1] for item in outcomes}) == 1
        for process in processes:
            process.join(timeout=5)
            assert process.exitcode == 0
        assert_invariants(registry, digest("contention"))
        view = registry.inspect(digest("contention"))
        assert (
            view["entry"]["attempts_started"]
            == len(view["attempts"])
            == (2 if repeat == 2 else 1)
        )
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)


def _crashing_producer(options, scope, root, crash_window, result):
    registry = Registry(options, "unused")
    registry.scope_id = scope
    ownership = claim(registry).ownership
    manifest = None
    if crash_window in {"validation", "finalized", "published"}:
        registry.begin_validation(ownership)
    if crash_window in {"finalized", "published"}:
        manifest = _producer_manifest(registry, ownership, root, 0)
    if crash_window == "published":
        registry.publish(ownership, manifest)
    result.put((ownership, manifest))
    time.sleep(60)


@pytest.mark.parametrize(
    "crash_window", ["claim", "validation", "finalized", "published"]
)
def test_killed_producer_crash_windows_no_partial_hit(registry, tmp_path, crash_window):
    context = multiprocessing.get_context("spawn")
    result = context.Queue()
    process = context.Process(
        target=_crashing_producer,
        args=(registry.options, registry.scope_id, str(tmp_path), crash_window, result),
    )
    process.start()
    try:
        old, manifest = result.get(timeout=15)
    except queue.Empty:
        pytest.fail("Producer did not reach crash window")
    finally:
        process.terminate()
        process.join(timeout=5)
    if crash_window == "published":
        assert claim(registry).artifact["manifest"] == manifest
    else:
        assert claim(registry).kind == "WAIT"
        expire(registry, old)
        replacement = claim(registry)
        assert replacement.kind == "PRODUCE"
        assert replacement.ownership.fencing_token > old.fencing_token
        assert not registry.inspect(old.cache_key)["artifacts"]
        if manifest:
            with pytest.raises(DockflowError) as error:
                registry.publish(old, manifest)
            assert error.value.code == "OWNERSHIP_LOST"
    assert_invariants(registry, digest("key"))


def test_storage_corruption_access_errors_paths_and_isolation(
    registry, tmp_path, monkeypatch
):
    ownership = claim(registry).ownership
    registry.begin_validation(ownership)
    manifest = _producer_manifest(registry, ownership, str(tmp_path), 0)
    artifact = registry.publish(ownership, manifest)
    store = ArtifactStore(
        ControlStore(tmp_path / "consumer", "dockflow-cache-bytes"),
        {"backend": "filesystem", "managed_root": tmp_path / "managed"},
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            store,
            "_download_descriptor",
            lambda *args: (_ for _ in ()).throw(PermissionError("temporary")),
        )
        with pytest.raises(DockflowError) as error:
            store.verify_cache(manifest, registry.options["storage_identity"])
        assert error.value.code == "ARTIFACT_UNAVAILABLE"
        assert claim(registry).artifact["artifact_id"] == artifact["artifact_id"]
    descriptor = manifest["outputs"]["dataset"]
    payload = tmp_path / "managed" / descriptor["managed_path"]
    assert not payload.stat().st_mode & 0o222
    target = payload / "file.txt"
    target.chmod(0o644)
    target.write_text("corrupt")
    with pytest.raises(DockflowError) as error:
        store.verify_cache(manifest, registry.options["storage_identity"])
    assert error.value.code == "CACHE_CORRUPT"
    registry.invalidate(
        ownership.cache_key, artifact["artifact_id"], "CONFIRMED_CORRUPTION"
    )
    replacement = claim(registry).ownership
    registry.begin_validation(replacement)
    next_manifest = _producer_manifest(registry, replacement, str(tmp_path), 1)
    current = registry.publish(replacement, next_manifest)
    target.write_text("late stale mutation")
    store.verify_cache(current["manifest"], registry.options["storage_identity"])
    malicious = copy.deepcopy(next_manifest)
    malicious["outputs"]["dataset"]["managed_path"] = "../../escape"
    with pytest.raises(DockflowError):
        store.verify_cache(malicious, registry.options["storage_identity"])
    malicious = copy.deepcopy(next_manifest)
    malicious["outputs"]["dataset"]["content_uri"] = "file:///producer-local"
    with pytest.raises(DockflowError):
        store.verify_cache(malicious, registry.options["storage_identity"])
    assert b"file:///" not in json_bytes(next_manifest)
    assert_invariants(registry, ownership.cache_key)


def test_freshness_new_episode_once_and_snapshot_retention(registry, monkeypatch):
    registry.options["freshness_seconds"] = 1
    first = claim(registry).ownership
    artifact = publish_empty(registry, first)
    selected = claim(registry)
    original = registry._time
    monkeypatch.setattr(registry, "_time", lambda conn: original(conn) + 2)
    second = claim(registry)
    assert second.kind == "PRODUCE" and second.episode_id != selected.episode_id
    assert claim(registry).kind == "WAIT"
    assert registry.inspect(first.cache_key)["entry"]["attempts_started"] == 1
    assert selected.artifact == artifact  # already selected immutable snapshot
    assert_invariants(registry, first.cache_key)


def _hold_entry_lock(options, scope, key, ready, release):
    registry = Registry(options, "unused")
    registry.scope_id = scope
    connection = registry._connect()
    try:
        registry._entry(connection, key)
        ready.put("locked")
        assert release.wait(15)
    finally:
        connection.rollback()
        connection.close()


def test_real_busy_or_row_lock_retry_does_not_charge_production_budget(
    registry, monkeypatch
):
    key = digest("lock-retry")
    assert (
        registry.resolve_or_claim(
            key, "observer", str(uuid.uuid4()), "run", "task", allow_claim=False
        ).kind
        == "MISS"
    )
    registry.options["transaction_timeout_seconds"] = 0.05
    context = multiprocessing.get_context("spawn")
    ready, release = context.Queue(), context.Event()
    process = context.Process(
        target=_hold_entry_lock,
        args=(registry.options, registry.scope_id, key, ready, release),
    )
    process.start()
    observed = []

    def event(kind, *args, **kwargs):
        observed.append(kind)
        if kind == "registry_contention":
            release.set()

    monkeypatch.setattr(registry, "event", event)
    try:
        assert ready.get(timeout=10) == "locked"
        assert claim(registry, key).kind == "PRODUCE"
        assert "registry_contention" in observed
        assert registry.inspect(key)["entry"]["attempts_started"] == 1
        assert_invariants(registry, key)
    finally:
        release.set()
        process.join(timeout=5)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
    assert process.exitcode == 0


def _park_producer(options, scope, key, ready, release):
    registry = Registry(options, "unused")
    registry.scope_id = scope
    outcome = claim(registry, key)
    ready.put(outcome.kind)
    assert release.wait(15)


def test_different_keys_compute_concurrently_without_open_transactions(registry):
    context = multiprocessing.get_context("spawn")
    ready, release = context.Queue(), context.Event()
    processes = [
        context.Process(
            target=_park_producer,
            args=(registry.options, registry.scope_id, digest(key), ready, release),
        )
        for key in ("first", "second")
    ]
    try:
        for process in processes:
            process.start()
        assert [ready.get(timeout=10) for _ in processes] == ["PRODUCE", "PRODUCE"]
        assert all(process.is_alive() for process in processes)
        for key in ("first", "second"):
            assert_invariants(registry, digest(key))
    finally:
        release.set()
        for process in processes:
            process.join(timeout=5)
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
    assert all(process.exitcode == 0 for process in processes)


def test_rollback_before_claim_commit_grants_no_attempt(registry, monkeypatch):
    original = registry._sql

    def fail_after_insert(connection, statement, values=()):
        result = original(connection, statement, values)
        if "INSERT INTO df_cache_attempts" in statement:
            raise RuntimeError("injected failure before commit")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(registry, "_sql", fail_after_insert)
        with pytest.raises(DockflowError):
            claim(registry)
    ownership = claim(registry).ownership
    assert ownership.fencing_token == 1
    assert registry.inspect(ownership.cache_key)["entry"]["attempts_started"] == 1
    assert_invariants(registry, ownership.cache_key)


def _race_transition(options, scope, ownership, manifest, action, barrier, results):
    registry = Registry(options, "unused")
    registry.scope_id = scope
    try:
        barrier.wait(timeout=15)
        if action == "publish":
            registry.publish(ownership, manifest)
        elif action == "renew":
            registry.renew_lease(ownership)
        elif action == "fail":
            registry.finish_failed(ownership, "RACED_FAILURE")
        elif action == "claim":
            claim(registry, ownership.cache_key)
        elif action == "invalidate":
            registry.invalidate(
                ownership.cache_key, manifest["artifact_id"], "DELAYED_REPORT"
            )
        results.put((action, "accepted"))
    except DockflowError as exc:
        results.put((action, exc.code))


@pytest.mark.parametrize("scenario", ["terminal", "expiry", "invalidation"])
def test_independent_process_fenced_transition_races(registry, scenario):
    old = claim(registry).ownership
    registry.begin_validation(old)
    old_manifest = empty_manifest(registry, old)
    ownership, manifest = old, old_manifest
    if scenario == "terminal":
        actions = [
            ("publish", old, old_manifest),
            ("fail", old, old_manifest),
            ("renew", old, old_manifest),
        ]
    elif scenario == "expiry":
        expire(registry, old)
        actions = [
            (name, old, old_manifest) for name in ("claim", "renew", "fail", "publish")
        ]
    else:
        artifact = registry.publish(old, old_manifest)
        registry.invalidate(old.cache_key, artifact["artifact_id"], "REBUILD")
        ownership = claim(registry).ownership
        registry.begin_validation(ownership)
        manifest = empty_manifest(registry, ownership)
        actions = [
            ("invalidate", old, old_manifest),
            ("publish", old, old_manifest),
            ("publish", ownership, manifest),
        ]
    context = multiprocessing.get_context("spawn")
    barrier, results = context.Barrier(len(actions)), context.Queue()
    processes = [
        context.Process(
            target=_race_transition,
            args=(
                registry.options,
                registry.scope_id,
                owner,
                value,
                action,
                barrier,
                results,
            ),
        )
        for action, owner, value in actions
    ]
    try:
        for process in processes:
            process.start()
        outcomes = [results.get(timeout=20) for _ in processes]
        for process in processes:
            process.join(timeout=5)
            assert process.exitcode == 0
        assert_invariants(registry, old.cache_key)
        view = registry.inspect(old.cache_key)
        if scenario == "terminal":
            assert (
                sum(
                    status == "accepted"
                    for action, status in outcomes
                    if action in {"publish", "fail"}
                )
                == 1
            )
        elif scenario == "expiry":
            assert dict(outcomes)["claim"] == "accepted"
            assert all(
                status == "OWNERSHIP_LOST"
                for action, status in outcomes
                if action != "claim"
            )
            assert view["entry"]["generation"] == 2
        else:
            assert dict(outcomes)["invalidate"] == "CACHE_CONFLICT"
            assert view["entry"]["published_artifact_id"] == manifest["artifact_id"]
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
