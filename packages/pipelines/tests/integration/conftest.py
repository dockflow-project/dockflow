"""Explicit opt-in PostgreSQL execution-state fixture."""

import os
import uuid

import pytest
from dockflow_pipelines.metadata import ControlStore


@pytest.fixture(params=["sqlite", "postgresql"])
def database_state(request, tmp_path, monkeypatch):
    backend = request.param
    if backend == "postgresql":
        dsn = os.environ.get("DOCKFLOW_TEST_STATE_POSTGRES_DSN")
        if not dsn:
            pytest.skip("Requires disposable PostgreSQL state test database")
        monkeypatch.setenv("DOCKFLOW_STATE_TEST_DSN", dsn)
        options = {"backend": backend, "dsn_env": "DOCKFLOW_STATE_TEST_DSN"}
    else:
        options = {"backend": backend, "database": str(tmp_path / "shared.sqlite")}
    project = "dockflow-state-" + uuid.uuid4().hex
    store = ControlStore(tmp_path / "worker-a", project, storage=options)
    yield store, options
    store.database.release()
    if backend == "postgresql":
        import psycopg

        with psycopg.connect(dsn, autocommit=True) as connection:
            from dockflow_pipelines.database_schema import PROJECT_TABLES

            tables = store.database.adapter.tables(connection)
            for table in reversed(PROJECT_TABLES):
                if table not in tables:
                    continue
                predicate = (
                    "project_id=%s"
                    if table.startswith("dockflow_") or table == "df_cache_scopes"
                    else "scope_id IN (SELECT scope_id FROM df_cache_scopes WHERE project_id=%s)"
                )
                connection.execute(f"DELETE FROM {table} WHERE {predicate}", (project,))
            for table in ("dockflow_run_owners", "dockflow_state_owners"):
                if table not in tables:
                    continue
                connection.execute(
                    f"DELETE FROM {table} WHERE project_id=%s", (project,)
                )
