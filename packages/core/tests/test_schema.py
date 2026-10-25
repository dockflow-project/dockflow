"""Schema services accept arbitrary callers and preserve transactional ownership."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from dockflow_core import DockflowError, Schema, database


def definition(name="example", version=1):
    return Schema(
        name=name,
        version=version,
        statements=(
            f"CREATE TABLE {name}_items (id INTEGER PRIMARY KEY, payload {{binary}})",
            f"CREATE INDEX {name}_payload ON {name}_items(payload)",
        ),
        tables=frozenset({f"{name}_items"}),
        indexes=frozenset({f"{name}_payload"}),
    )


@pytest.fixture
def adapter(tmp_path):
    return database({"backend": "sqlite", "database": str(tmp_path / "state.sqlite")})


def initialize(adapter, *schemas):
    adapter.prepare()
    connection = adapter.connect()
    try:
        adapter.begin(connection)
        for schema in schemas:
            adapter.initialize_schema(connection, schema)
        connection.execute("COMMIT")
    finally:
        connection.close()


def test_independent_schemas_versions_and_readonly_validation(adapter):
    one, two = definition(), definition("another", 7)
    initialize(adapter, one)
    initialize(adapter, two, one)
    with adapter.snapshot() as connection:
        assert adapter.tables(connection) == {
            "dockflow_schema_components",
            "example_items",
            "another_items",
        }
        assert connection.execute(
            "SELECT name,version FROM dockflow_schema_components ORDER BY name"
        ).fetchall() == [("another", 7), ("example", 1)]
        adapter.validate_schema(connection, one)
        adapter.validate_schema(connection, two)
        with pytest.raises(DockflowError, match="version"):
            adapter.validate_schema(connection, replace(one, version=2))
        with pytest.raises(DockflowError, match="missing"):
            adapter.validate_schema(connection, definition("absent"))


def test_schema_callback_and_registry_rollback_together(adapter):
    def failed(adapter, connection):
        connection.execute("INSERT INTO example_items VALUES (1,NULL)")
        raise ValueError("injected initialization failure")

    with pytest.raises(ValueError, match="injected"):
        initialize(adapter, replace(definition(), initialize=failed))
    connection = adapter.connect()
    try:
        assert adapter.tables(connection) == set()
    finally:
        connection.close()
    initialize(adapter, definition())


@pytest.mark.parametrize("object_kind", ["table", "index"])
def test_missing_registered_objects_are_never_repaired(adapter, object_kind):
    schema = definition()
    initialize(adapter, schema)
    connection = adapter.connect()
    name = "example_items" if object_kind == "table" else "example_payload"
    connection.execute(f"DROP {object_kind.upper()} {name}")
    connection.close()
    with pytest.raises(DockflowError, match="incomplete"):
        initialize(adapter, schema)
    with adapter.snapshot() as connection:
        assert name not in adapter.tables(connection) | adapter.indexes(connection)


def test_concurrent_first_use_preserves_both_consumers(adapter):
    with ThreadPoolExecutor(max_workers=8) as workers:
        futures = [
            workers.submit(initialize, adapter, definition(name))
            for name in ("example", "another") * 8
        ]
        for future in futures:
            future.result(timeout=10)
    with adapter.snapshot() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM dockflow_schema_components"
        ).fetchone() == (2,)


def test_unregistered_conflicting_objects_require_fresh_state(adapter):
    adapter.prepare()
    connection = adapter.connect()
    connection.execute("CREATE TABLE example_items (id INTEGER)")
    connection.close()
    with pytest.raises(DockflowError, match="fresh state"):
        initialize(adapter, definition())


def test_lock_namespaces_do_not_alias_identity_delimiters(adapter):
    assert adapter.lock_key("example", "mutation:item") != adapter.lock_key(
        "example:mutation", "item"
    )
    assert adapter.lock_key("example", "item") == adapter.lock_key("example", "item")
