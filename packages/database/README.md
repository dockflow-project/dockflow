# Dockflow Database

Shared SQLite/PostgreSQL connections, physical schema, transaction gates and
immutable artifact bookkeeping for Dockflow Pipelines and Dockflow Artifacts.
The SQLite core uses the Python standard library. Install the `postgresql` extra
for external PostgreSQL. Connections are opened only by explicit operations.

Install `dockflow-database==0.2.0`, or
`dockflow-database[postgresql]==0.2.0` for PostgreSQL support.

This package follows the shared Dockflow application version and MIT license.
Development includes AI assistance. See the repository persistence documentation
for configuration and deployment requirements.
