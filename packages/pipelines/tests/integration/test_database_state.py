"""Fresh environments retain catalog, history, source, logs and artifact access."""

import json

import pytest
from dockflow_core.errors import DockflowError
from dockflow_pipelines.config import load_settings
from dockflow_pipelines.core import Core
from dockflow_pipelines.metadata import ControlStore
from dockflow_pipelines.records import new_id


def fixture_definition():
    return {
        "pipelineInfo": {"name": "database-state"},
        "schemaVersion": "2.1.0",
        "sdkVersion": "kfp-2.17.0",
        "root": {"executorLabel": "exec-echo"},
        "deploymentSpec": {
            "executors": {
                "exec-echo": {
                    "container": {
                        "image": "python:3.13-slim",
                        "command": ["echo", "retained"],
                    }
                }
            }
        },
    }


def worker_settings(store, options, name):
    root = store.state.parent / name
    root.mkdir(exist_ok=True)
    inputs = store.state.parent / "inputs"
    inputs.mkdir(exist_ok=True)
    configuration = root / "project.toml"
    state_fields = "\n".join(
        f"{key}={json.dumps(value)}" for key, value in options.items()
    )
    configuration.write_text(
        f'schema_version=1\n[project]\nid="{store.project_id}"\n[state]\n{state_fields}\n'
        f"[artifacts]\nmanaged_root={json.dumps(str(store.state.parent / 'artifacts'))}\n"
        f"external_roots=[{json.dumps(str(inputs))}]\n"
    )
    return load_settings(configuration)


def test_new_environment_retains_full_history_and_idempotency(database_state):
    store, options = database_state
    first = Core(worker_settings(store, options, "environment-a"))
    second_settings = worker_settings(store, options, "environment-b")
    source = json.dumps(fixture_definition()) + "\n"
    with first.store.owner():
        first.initialize()
        _, definition = first.upload_pipeline(source, "retained-pipeline")
        request = {"definition_id": definition["definition_id"]}
        run, repeated = first.submit(request, "persistent-submission")
        assert not repeated
        first.store.log(run["run_id"], "retained output\n", "stdout")
        first.store.put("runs", {**run, "state": "succeeded"})
        first.create_experiment("later")
        page = first.page("experiments", page_size=1)
        assert page["next_page_token"]
        input_path = store.state.parent / "inputs/dataset"
        input_path.write_bytes(b"retained-artifact")
        artifact = first.artifacts.register(
            input_path.as_uri(),
            {"schema_title": "system.Dataset", "schema_version": "0.0.1"},
            managed=True,
        )
    # No state/definition/log mount is supplied to this fresh environment.
    second = Core(second_settings)
    with second.store.owner():
        second.initialize()
        assert second.store.get("runs", run["run_id"])["state"] == "succeeded"
        assert (
            second.resolve("retained-pipeline", persist=False)["definition_id"]
            == definition["definition_id"]
        )
        assert (
            second.store.definition_source(definition["definition_id"])
            == source.encode()
        )
        assert second.store.log_entries(run["run_id"])[0]["text"] == "retained output\n"
        repeated_run, repeated = second.submit(request, "persistent-submission")
        assert repeated and repeated_run["run_id"] == run["run_id"]
        assert second.page(
            "experiments", page_size=1, page_token=page["next_page_token"]
        )["items"]
        assert (
            second.artifacts.verify(artifact["artifact_id"])["availability"]
            == "available"
        )
        assert second.store.check(verify_contents=True, artifacts=second.artifacts)[
            "valid"
        ]
    assert not (second_settings.state / "records").exists()
    if options["backend"] == "postgresql":
        assert second_settings.cache["database"]["backend"] == "postgresql"
        assert not first.settings.state.exists()
        assert not second_settings.state.exists()


def test_portable_export_import_both_backends(database_state):
    store, options = database_state
    run_id = new_id("run")
    with store.owner():
        store.initialize()
        store.put("runs", {"run_id": run_id, "state": "succeeded"})
        store.log(run_id, "portable history", "stderr")
        snapshot = store.state.parent / "portable.sqlite"
        store.export_database(snapshot)
    # Restore into a distinct empty project slot on either backend, preserving ID.
    restored_options = {
        "backend": "sqlite",
        "database": str(store.state.parent / "restored.sqlite"),
    }
    restored = ControlStore(
        store.state.parent / "restored-worker",
        store.project_id,
        storage=restored_options,
    )
    with restored.owner():
        restored.import_database(snapshot)
        restored.initialize()
        assert restored.get("runs", run_id)["state"] == "succeeded"
        assert restored.log_entries(run_id)[0]["text"] == "portable history"
        assert restored.check()["valid"]
        with pytest.raises(DockflowError, match="empty"):
            restored.import_database(snapshot)
    assert (
        restored.database.owner_metadata()["owner_id"]
        != store.database.owner_metadata()["owner_id"]
    )
    # Exercise portable SQLite -> external PostgreSQL import as well.
    if options["backend"] == "postgresql":
        with store.owner():
            with store.database.transaction() as connection:
                from dockflow_pipelines.database_schema import PROJECT_TABLES

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
            store.import_database(snapshot)
            store.initialize()
            assert store.check()["valid"]


def test_unknown_schema_and_legacy_files_fail_without_reinterpretation(tmp_path):
    store = ControlStore(tmp_path / "state", "dockflow-schema")
    with store.owner():
        store.initialize()
        with store.database.transaction() as connection:
            connection.execute("UPDATE dockflow_schema_components SET version=999")
    with pytest.raises(DockflowError, match="schema"), store.owner():
        pass
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "project.json").write_text("{}")
    store = ControlStore(legacy, "dockflow-schema")
    with pytest.raises(DockflowError, match="Legacy"), store.owner():
        pass
    assert not (legacy / "state.sqlite").exists()


def test_config_postgresql_is_lazy_and_never_records_dsn(tmp_path, monkeypatch):
    config = tmp_path / "project.toml"
    config.write_text(
        'schema_version=1\n[project]\nid="dockflow-postgresql"\n[state]\nbackend="postgresql"\ndsn_env="DOCKFLOW_STATE_SECRET"\n'
    )
    secret = "postgresql://synthetic:password@127.0.0.1:1/dockflow"
    monkeypatch.setenv("DOCKFLOW_STATE_SECRET", secret)
    settings = load_settings(config)
    assert settings.cache["database"]["backend"] == "postgresql"
    assert secret not in json.dumps(settings.effective())
    assert "password" not in json.dumps(settings.effective())
    assert not settings.state.exists()
    with pytest.raises(DockflowError) as error, Core(settings).store.owner():
        pass
    assert secret not in str(error.value)
    assert "password" not in str(error.value)
    assert not settings.state.exists()


@pytest.mark.parametrize(
    "table",
    [
        '[state]\nbackend="mysql"',
        '[state]\nbackend="postgresql"',
        '[state]\ndsn_env="SECRET"',
        '[state]\nbackend="postgresql"\ndsn_env="SECRET"\ndatabase="state.sqlite"',
        '[metadata]\nbackend="sqlite"',
    ],
)
def test_invalid_state_configuration_is_side_effect_free(tmp_path, table):
    configuration = tmp_path / "project.toml"
    configuration.write_text(
        'schema_version=1\n[project]\nid="dockflow-invalid"\n' + table
    )
    with pytest.raises(DockflowError):
        load_settings(configuration)
    assert list(tmp_path.iterdir()) == [configuration]


@pytest.mark.parametrize(
    "field,value",
    [
        ("backend", "sqlite"),
        ("registry", "cache.sqlite"),
        ("dsn_env", "DOCKFLOW_CACHE_DSN"),
    ],
)
def test_cache_connection_overrides_are_rejected(tmp_path, monkeypatch, field, value):
    configuration = tmp_path / "project.toml"
    configuration.write_text(
        'schema_version=1\n[project]\nid="dockflow-cache-override"\n[cache]\n'
        + field
        + '="'
        + value
        + '"\n'
    )
    with pytest.raises(DockflowError):
        load_settings(configuration)
    configuration.write_text(
        'schema_version=1\n[project]\nid="dockflow-cache-override"\n'
    )
    monkeypatch.setenv("DOCKFLOW_PIPELINES_CACHE_" + field.upper(), value)
    with pytest.raises(DockflowError, match="single database"):
        load_settings(configuration)
    assert list(tmp_path.iterdir()) == [configuration]


def test_orphaned_sql_resources_do_not_count_as_empty(database_state):
    store, _ = database_state
    with store.owner():
        store.database.put_resource(
            "runs", {"run_id": new_id("run"), "state": "succeeded"}
        )
        assert not store.database.project_empty()
        with pytest.raises(DockflowError, match="identity record is missing"):
            store.initialize()


def test_foreign_sqlite_database_is_not_reinterpreted(tmp_path):
    import sqlite3

    database = tmp_path / "foreign.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE original_records (value TEXT)")
        connection.execute("INSERT INTO original_records VALUES ('retained')")
    store = ControlStore(
        tmp_path / "work",
        "dockflow-fresh",
        storage={"backend": "sqlite", "database": str(database)},
    )
    with pytest.raises(DockflowError, match="fresh state"), store.owner():
        pass
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM original_records").fetchall() == [
            ("retained",)
        ]
        assert not connection.execute(
            "SELECT name FROM sqlite_master WHERE name='dockflow_schema_components'"
        ).fetchall()


def test_missing_authoritative_table_is_not_a_fresh_project(database_state):
    store, _ = database_state
    with store.owner():
        store.initialize()
    if store.database.backend == "sqlite":
        import sqlite3

        connection = sqlite3.connect(
            store.database.options["database"], isolation_level=None
        )
        connection.execute("DROP TABLE dockflow_events")
        connection.close()
    else:
        # Validate a missing-table observation without damaging the shared schema.
        from types import SimpleNamespace

        with store.database.reader() as connection:

            def execute(sql, parameters=()):
                cursor = connection.execute(sql, parameters)
                if "pg_catalog.pg_tables" in sql:
                    return SimpleNamespace(
                        fetchall=lambda: [
                            row
                            for row in cursor.fetchall()
                            if row[0] != "dockflow_events"
                        ]
                    )
                return cursor

            with pytest.raises(DockflowError, match="schema is incomplete"):
                store.database._validate_schema(SimpleNamespace(execute=execute))
        return
    with pytest.raises(DockflowError, match="schema is incomplete"), store.owner():
        store.initialize()
    with pytest.raises(DockflowError, match="schema is incomplete"):
        store.list("runs")
