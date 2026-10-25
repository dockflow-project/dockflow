"""Each domain supplies its own schema while sharing one selected database."""

import os
import subprocess
import sys
import uuid

import pytest
from dockflow_artifacts.persistence import ARTIFACT_SCHEMA, ArtifactRecords
from dockflow_core import DockflowError, Schema
from dockflow_pipelines.database_schema import PIPELINE_SCHEMA
from dockflow_pipelines.metadata import ControlStore


@pytest.fixture
def isolated_backend(database_state, monkeypatch, tmp_path):
    original, options = database_state
    if options["backend"] == "sqlite":
        yield original, options
        return
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    dsn = os.environ[options["dsn_env"]]
    name = "dockflow_core_schema_" + uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as administration:
        administration.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name))
        )
        try:
            monkeypatch.setenv(
                "DOCKFLOW_CORE_SCHEMA_TEST_DSN", make_conninfo(dsn, dbname=name)
            )
            selected = {
                "backend": "postgresql",
                "dsn_env": "DOCKFLOW_CORE_SCHEMA_TEST_DSN",
            }
            store = ControlStore(
                tmp_path / "isolated", original.project_id, storage=selected
            )
            try:
                yield store, selected
            finally:
                store.database.release()
        finally:
            administration.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


@pytest.mark.parametrize("first", ["artifacts", "pipelines"])
def test_consumer_initialization_orders_and_independent_versions(
    isolated_backend, first
):
    store, _ = isolated_backend
    adapter = store.database.adapter
    records = ArtifactRecords(adapter, store.project_id, "shared-storage")
    if first == "artifacts":
        records.put("example", "key", b"retained")
        with adapter.snapshot() as connection:
            assert adapter.schema_exists(connection, ARTIFACT_SCHEMA)
            assert adapter.tables(connection) == {
                "dockflow_schema_components",
                "dockflow_artifact_records",
            }
            assert not adapter.schema_exists(connection, PIPELINE_SCHEMA)
    with store.owner():
        store.initialize()
        records.put("example", "key", b"retained")
    assert records.get("example", "key") == b"retained"
    with adapter.snapshot() as connection:
        adapter.validate_schema(connection, ARTIFACT_SCHEMA)
        adapter.validate_schema(connection, PIPELINE_SCHEMA)


def test_standalone_artifacts_creates_only_its_schema(tmp_path):
    root = tmp_path / "artifacts"
    database_path = tmp_path / "state.sqlite"
    source = tmp_path / "source"
    source.write_bytes(b"retained")
    code = """
import importlib.abc, sqlite3, sys
class Blocked(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('dockflow_pipelines', 'dockflow_cli')):
            raise AssertionError('consumer import: ' + fullname)
sys.meta_path.insert(0, Blocked())
from dockflow_artifacts import Publisher
publisher = Publisher(sys.argv[1], database={'backend':'sqlite','database':sys.argv[2]})
receipt = publisher.publish(sys.argv[3], 'example')
assert publisher.verify('example') == receipt
with sqlite3.connect(sys.argv[2]) as connection:
    assert set(row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")) == {'dockflow_schema_components', 'dockflow_artifact_records'}
    assert connection.execute('SELECT name,version FROM dockflow_schema_components').fetchall() == [('artifacts',1)]
"""
    subprocess.run(
        [sys.executable, "-c", code, str(root), str(database_path), str(source)],
        check=True,
        capture_output=True,
    )


def test_corrupt_artifact_schema_does_not_block_version_check_for_other_schema(
    isolated_backend,
):
    store, _ = isolated_backend
    adapter = store.database.adapter
    with store.owner():
        store.initialize()
        try:
            with store.database.transaction() as connection:
                adapter.execute(
                    connection,
                    "UPDATE dockflow_schema_components SET version=999 WHERE name='artifacts'",
                )
            with adapter.snapshot() as connection:
                adapter.validate_schema(connection, PIPELINE_SCHEMA)
                with pytest.raises(DockflowError, match="version"):
                    adapter.validate_schema(connection, ARTIFACT_SCHEMA)
            with pytest.raises(DockflowError, match="version"):
                store.database._validate_schema(store.database.connection)
        finally:
            with store.database.transaction() as connection:
                adapter.execute(
                    connection,
                    "UPDATE dockflow_schema_components SET version=? WHERE name='artifacts'",
                    (ARTIFACT_SCHEMA.version,),
                )


def test_arbitrary_schema_and_concurrent_initialization_on_both_backends(
    isolated_backend,
):
    from concurrent.futures import ThreadPoolExecutor
    from dataclasses import replace

    store, _ = isolated_backend
    adapter = store.database.adapter
    schema = Schema(
        name="example",
        version=3,
        statements=(
            "CREATE TABLE example_items (id INTEGER PRIMARY KEY, value {binary})",
        ),
        tables=frozenset({"example_items"}),
    )

    def initialize():
        adapter.prepare()
        connection = adapter.connect()
        try:
            adapter.begin(connection)
            adapter.initialize_schema(connection, schema)
            connection.execute("COMMIT")
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=8) as workers:
        for future in [workers.submit(initialize) for _ in range(8)]:
            future.result(timeout=15)
    with adapter.snapshot() as connection:
        assert adapter.tables(connection) == {
            "dockflow_schema_components",
            "example_items",
        }
        adapter.validate_schema(connection, schema)
        with pytest.raises(DockflowError, match="version"):
            adapter.validate_schema(connection, replace(schema, version=4))


def test_simultaneous_publication_and_pipeline_first_use(isolated_backend):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    store, _ = isolated_backend
    start = Barrier(2)
    records = ArtifactRecords(store.database.adapter, store.project_id, "shared-store")

    def initialize_pipeline():
        start.wait(timeout=10)
        with store.owner():
            store.initialize()
            store.set_project_metadata("example", {"retained": True})

    def initialize_publication():
        start.wait(timeout=10)
        records.put("example", "key", b"retained")

    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [
            workers.submit(operation)
            for operation in (initialize_pipeline, initialize_publication)
        ]
        for future in futures:
            future.result(timeout=15)
    assert records.get("example", "key") == b"retained"
    assert store.project_metadata("example") == {"retained": True}
