# Shared Core boundary

`dockflow-core` (`dockflow_core`, under `packages/core/`) owns reusable primitives
for the other Dockflow distributions. All other distributions declare the exact
shared application version as a direct dependency. Core depends on none of them:
no direct, lazy, optional or dynamic import, entry-point discovery, domain schema,
record model, query, resource name or consuming-package policy belongs in Core.
Adding a shared primitive requires an actual reusable responsibility; do not move
feature behavior into Core solely to reduce a feature package's size.

## Database services and schema ownership

Core owns the SQLite/PostgreSQL adapter interface, connection and transaction
primitives, dialect operations, durability settings, clock expressions, generic
locking, driver failure classification and schema coordination. SQLite uses the
standard library; PostgreSQL remains an optional, lazily imported driver. Import
and configuration inspection must not connect, create files or discover secrets.

Each consumer supplies its schema identity, version, DDL, required tables/indexes
and any backend-specific initialization callback. Core may keep its own generic
schema-version registry; its contents are supplied by consumers, without a built-in
list of known packages. Initialize and validate each declared schema atomically
under database serialization. A registered schema with an unsupported version or
missing required objects fails closed; read-only operations never initialize or
repair it. Unregistered conflicting tables require fresh state. No migration or
compatibility shim for the discarded database package is required.

Artifacts owns publication reservations, completion manifests and their persistence
logic. Pipelines owns execution state, ownership, events, logs, queries, projections,
backup selection and cache coordination. Pipelines explicitly initializes and
validates the Artifacts schema it consumes, in addition to its own. Standalone
Artifacts initializes only its own schema and does not create Pipelines tables.
Both initialization orders must work in one physical SQLite/PostgreSQL database;
schema identities have independent versions and concurrent first use is safe.
Consumer transaction/retry/fencing policies remain with those consumers. Shared
database access must preserve maintenance exclusion and immutable publication.

## Other shared primitives

Common errors, portable JSON validation/serialization and deterministic typed
encoding, stream hashing, filesystem symlink checks and durable file operations
may live in Core. Domain-specific error translation, identity envelopes, path
rules, storage adapters, public IDs, lifecycle states and CLI registration remain
with their owning packages. Moving a primitive must preserve established digest
bytes, numeric types, negative zero, invalid-input rejection and durability order.

## Qualification

Verify Core in an environment containing no consuming distribution and no optional
driver. Exercise an arbitrary caller-defined schema, independent versions,
transaction rollback, mismatches/incompleteness and simultaneous initialization.
Verify that standalone Artifacts creates no Pipelines schema, then add Pipelines
and exercise both initialization orders against SQLite and PostgreSQL. Check
dependency direction statically and in clean wheel/sdist installations. Retain
domain conformance tests and golden serialization/publication identity vectors.
