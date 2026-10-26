# Dockflow Core

Domain-independent primitives shared by Dockflow CLI, Pipelines and Artifacts:
SQLite/PostgreSQL adapters, caller-defined schema initialization/versioning,
generic locks, common errors, portable JSON encoding, stream hashing and durable
filesystem operations. Core imports no consuming package and owns no domain
schema, models, queries or persistence policy.

Install `dockflow-core==0.3.0`, or `dockflow-core[postgresql]==0.3.0` for
PostgreSQL support. The SQLite implementation uses the Python standard library.
Optional drivers and connections are initialized only by explicit operations.

Consumers supply `Schema` definitions and retain their own queries and policies.
Several independently versioned schemas can share one physical database.

This package follows the shared Dockflow application version and MIT license.
Development includes AI assistance. See the repository documentation for
configuration and deployment requirements.
