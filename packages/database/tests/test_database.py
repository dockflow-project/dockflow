"""The shared library's lazy configuration and schema boundaries."""

import sys

import pytest
from dockflow_database import DockflowError
from dockflow_database.records import configured_database


@pytest.mark.parametrize(
    "options",
    [
        None,
        {},
        {"backend": "other"},
        {"backend": []},
        {"backend": "sqlite", "database": "relative.sqlite"},
        {"backend": "postgresql", "dsn_env": "postgresql://secret"},
        {"backend": "sqlite", "database": "/unused.sqlite", "dsn": "secret"},
    ],
)
def test_invalid_configuration_is_secret_safe(options):
    with pytest.raises(DockflowError) as error:
        configured_database(options)
    assert "secret" not in str(error.value)


def test_readonly_missing_database_never_creates_files(tmp_path):
    adapter = configured_database(
        {"backend": "sqlite", "database": str(tmp_path / "missing/state.sqlite")}
    )
    with pytest.raises(DockflowError, match="snapshot is missing"):
        with adapter.snapshot():
            pass
    assert not (tmp_path / "missing").exists()


def test_postgresql_configuration_does_not_import_driver_or_connect(monkeypatch):
    monkeypatch.setitem(sys.modules, "psycopg", None)
    adapter = configured_database(
        {"backend": "postgresql", "dsn_env": "DOCKFLOW_SYNTHETIC_MISSING_DSN"}
    )
    with pytest.raises(DockflowError, match=r"dockflow-database\[postgresql\]"):
        adapter.connect()
