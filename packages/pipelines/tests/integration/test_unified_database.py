"""Both repositories use one schema, connection contract and project snapshot."""

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from dockflow_database.database import Database, database
from dockflow_database.database_schema import REQUIRED_TABLES
from dockflow_database.errors import DockflowError
from dockflow_pipelines.cache_registry import Registry
from dockflow_pipelines.cache_storage import make_manifest
from dockflow_pipelines.canonical import digest
from dockflow_pipelines.metadata import ControlStore
from dockflow_pipelines.records import new_id


def cache(options, project, namespace="default"):
    return Registry(
        {
            "database": options,
            "namespace": namespace,
            "storage_identity": "dockflow-unified-store",
            "backoff_seconds": 0,
            "backoff_max_seconds": 0,
        },
        project,
    )


def claim(registry):
    return registry.resolve_or_claim(
        digest("unified-key"), "owner", str(uuid.uuid4()), new_id("run"), new_id("task")
    )


def publish(registry, ownership):
    attempt = registry.inspect(ownership.cache_key)["attempts"][-1]
    manifest = make_manifest(
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
    registry.begin_validation(ownership)
    return registry.publish(ownership, manifest)


@pytest.mark.parametrize("first", ["state", "cache"])
def test_initialization_order_and_cache_progress_with_pinned_owner(
    database_state, first
):
    store, options = database_state
    registry = cache(options, store.project_id)
    if first == "cache":
        registry.initialize()
    with store.owner():
        store.initialize()
        registry.initialize()
        assert isinstance(store.database.adapter, Database)
        assert type(store.database.adapter) is type(registry.database)
        assert store.database.adapter.options == registry.database.options
        assert REQUIRED_TABLES <= registry.database.tables(store.database.connection)
        # A separate cache connection must commit while the state session owns the
        # project. The owner lock is not a long-running SQL writer transaction.
        with ThreadPoolExecutor(max_workers=1) as workers:
            ownership = workers.submit(claim, registry).result(timeout=10).ownership
            workers.submit(registry.renew_lease, ownership).result(timeout=10)
            published = workers.submit(publish, registry, ownership).result(timeout=10)
        store.set_project_metadata(
            "verification", {"artifact_id": published["artifact_id"]}
        )
    fresh = ControlStore(
        store.state.parent / "fresh-worker", store.project_id, storage=options
    )
    assert (
        fresh.project_metadata("verification")["artifact_id"]
        == published["artifact_id"]
    )
    assert claim(cache(options, store.project_id)).artifact == published
    if options["backend"] == "sqlite":
        assert not (store.state / "cache-v1/registry.sqlite").exists()


def test_snapshot_preserves_all_cache_namespaces_and_excludes_other_projects(
    database_state, tmp_path
):
    store, options = database_state
    registries = [
        cache(options, store.project_id, namespace)
        for namespace in ("default", "other")
    ]
    foreign = cache(options, store.project_id + "-foreign")
    foreign.initialize()
    claim(foreign)
    with store.owner():
        store.initialize()
        store.set_project_metadata("verification", {"retained": True})
        for registry in registries:
            registry.initialize()
            ownership = claim(registry).ownership
            registry.finish_failed(ownership, "TRANSIENT", retryable=True)
            publish(registry, claim(registry).ownership)
        expected = [registry.inspect(digest("unified-key")) for registry in registries]
        snapshot = tmp_path / "snapshot.sqlite"
        store.export_database(snapshot)
    portable = database({"backend": "sqlite", "database": str(snapshot)})
    with portable.snapshot() as connection:
        assert connection.execute(
            "SELECT DISTINCT project_id FROM df_cache_scopes"
        ).fetchall() == [(store.project_id,)]
        assert (
            connection.execute("SELECT * FROM dockflow_state_owners").fetchall() == []
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM dockflow_schema"
        ).fetchone() == (1,)
    # Restore to a fresh SQLite database, including when the source is PostgreSQL.
    restored_options = {
        "backend": "sqlite",
        "database": str(tmp_path / "restored.sqlite"),
    }
    target = ControlStore(
        tmp_path / "restored-worker", store.project_id, storage=restored_options
    )
    with target.owner():
        target.import_database(snapshot)
        target.initialize()
        assert target.project_metadata("verification") == {"retained": True}
        for registry, original in zip(registries, expected, strict=True):
            reopened = cache(
                restored_options, store.project_id, registry.options["namespace"]
            )
            reopened.initialize()
            observed = reopened.inspect(digest("unified-key"))
            assert {k: v for k, v in observed.items() if k != "registry_now"} == {
                k: v for k, v in original.items() if k != "registry_now"
            }
            assert claim(reopened).kind == "REUSE"


def test_restore_rejects_cache_only_nonempty_project(database_state, tmp_path):
    store, options = database_state
    with store.owner():
        store.initialize()
        snapshot = tmp_path / "snapshot.sqlite"
        store.export_database(snapshot)
    target = ControlStore(
        tmp_path / "target-worker",
        store.project_id,
        storage={"backend": "sqlite", "database": str(tmp_path / "target.sqlite")},
    )
    registry = cache(target.database.options, target.project_id)
    registry.initialize()
    claim(registry)
    with target.owner(), pytest.raises(DockflowError, match="empty"):
        target.import_database(snapshot)


def test_split_database_is_not_silently_adopted(tmp_path):
    import sqlite3

    options = {"backend": "sqlite", "database": str(tmp_path / "split.sqlite")}
    with sqlite3.connect(options["database"]) as connection:
        connection.execute("CREATE TABLE df_cache_schema (version INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO df_cache_schema VALUES(1)")
    registry = cache(options, "dockflow-split")
    with pytest.raises(DockflowError, match="fresh state"):
        registry.initialize()
    with sqlite3.connect(options["database"]) as connection:
        assert connection.execute("SELECT version FROM df_cache_schema").fetchall() == [
            (1,)
        ]
        assert not connection.execute(
            "SELECT name FROM sqlite_master WHERE name='dockflow_schema'"
        ).fetchall()


def test_export_keeps_one_snapshot_during_independent_cache_commit(
    database_state, tmp_path, monkeypatch
):
    from dockflow_pipelines.state_database import StateDatabase

    store, options = database_state
    registry = cache(options, store.project_id)
    with store.owner():
        store.initialize()
        registry.initialize()
        ownership = claim(registry).ownership
        original = registry.inspect(ownership.cache_key)
        target = StateDatabase(
            {"backend": "sqlite", "database": str(tmp_path / "snapshot.sqlite")},
            store.project_id,
        )
        with store.database.transaction():
            store.set_project_metadata("retained", {"snapshot": True})
        target.acquire()
        try:
            execute = target.execute
            committed = []

            def concurrent_commit(connection, statement, parameters=()):
                if (
                    statement.startswith("INSERT INTO dockflow_project_metadata")
                    and not committed
                ):
                    registry.finish_failed(ownership, "CONCURRENT", retryable=True)
                    committed.append(True)
                return execute(connection, statement, parameters)

            monkeypatch.setattr(target, "execute", concurrent_commit)
            target.copy_project(store.database)
            assert committed
            exported = cache(target.options, store.project_id).inspect(
                ownership.cache_key
            )
            for field in ("entry", "attempts", "artifacts"):
                assert exported[field] == original[field]
            assert (
                registry.inspect(ownership.cache_key)["attempts"][0]["state"]
                == "FAILED"
            )
        finally:
            target.release()


def test_portable_snapshot_restores_cache_into_selected_backend(
    database_state, tmp_path
):
    from dockflow_database.database_schema import PROJECT_TABLES

    store, options = database_state
    with store.owner():
        store.initialize()
        registry = cache(options, store.project_id)
        registry.initialize()
        published = publish(registry, claim(registry).ownership)
        snapshot = tmp_path / "portable.sqlite"
        store.export_database(snapshot)
        # Only this test project's disposable records are removed, in FK order.
        with store.database.transaction() as connection:
            for table in reversed(PROJECT_TABLES):
                predicate = (
                    "project_id=?"
                    if table.startswith("dockflow_") or table == "df_cache_scopes"
                    else "scope_id IN (SELECT scope_id FROM df_cache_scopes WHERE project_id=?)"
                )
                store.database.execute(
                    connection,
                    f"DELETE FROM {table} WHERE {predicate}",
                    (store.project_id,),
                )
        assert store.database.project_empty(include_cache=True)
        store.import_database(snapshot)
        store.initialize()
        assert claim(cache(options, store.project_id)).artifact == published
