# Generic Core boundary qualification

Qualification is complete for the unpublished development tree on `release/0.2.0`.
Publication remains paused; the preceding candidate has been superseded.

## Contract and ownership mapping

- General Dockflow's Core boundary owns reusable services and dependency direction.
- The previous shared database schema moves to Pipelines execution/cache DDL and
  Artifacts publication DDL, with independent entries in Core's generic registry.
- Pipeline query/index expressions and project export selection move to Pipelines.
- Publication reservations/manifests and their repository move to Artifacts.
- Generic connections, dialects, driver classification, lock primitives and schema
  coordination remain in Core, with no domain imports or registered consumers.
- Typed JSON validation/encoding and stream hashing are shared through Core.
  Publication's typed object keys and Pipelines' digest encoding remain distinct
  caller choices, covered by golden bytes.
- Symlink checks, directory/ancestor flushing, atomic writes, UTC timestamps and
  common errors move to Core. Domain error translation and durability policies
  remain in their callers; CLI consumes common errors.
- Pipeline IDs/states, lifecycle transitions, execution/configuration policy,
  storage protocols, source admission and CLI discovery remain with their owners.
  Their semantics are not generic primitives and were not moved.

## Impact and compatibility

The distribution/import boundary and discarded physical schema format change;
specification and implementation impacts are Major. General Dockflow, Pipelines
and Artifacts local specification packages receive Major increments. CLI receives
a compatible Minor dependency/common-error contract addition. Project baseline
numbers remain a release-preparation concern; the existing candidate requires
recalculation. Root application VERSION remains unchanged and unpublished.

Historical change records and receipts retain their original package names and
measured results. Active source, build/install/publish configuration and current
documentation use Core. No migration, compatibility package or import facade is
introduced. No third-party dependency update is intended.

## Validation on 2026-10-25

All provider qualification uses disposable local resources, synthetic credentials
and fresh state. The same final runtime/test/build inventory passes:

| Interpreter | Passed | Intentional skips | Upstream warnings | Elapsed |
| --- | --- | --- | --- | --- |
| Python 3.12.15 | 813 | 14 | 5 | 155.24 seconds |
| Python 3.13.17 | 813 | 14 | 5 | 154.38 seconds |

The 23 added cases cover generic schemas, rollback/version validation, namespace
isolation, independent consumer initialization, package/import boundaries and
publication identity golden bytes. Warnings are the existing Starlette/httpx
deprecation and upstream KFP client compatibility notices. No required test failed.

SQLite 3.53.1, PostgreSQL 18.6, the repository's MinIO source build and actual
Docker execution cover initialization order, concurrent first use, independent
schemas/versions, rollback, ownership/fencing, publication, backup and restore.
Generic lock keys frame caller names to avoid delimiter aliases across scopes.
Artifacts supplies its project read/export queries; Pipelines consumes that
interface while retaining selection and snapshot orchestration.

All four wheels and source distributions build. Core-only, CLI/Core, standalone
Artifacts/Core and combined base installations pass without runtime extras.
Each source distribution rebuilds outside its original checkout. The sanitized
receipt is `dist/core-verification/verification.json`; source is explicitly dirty
and unpublished. No third-party locked package changed.

The final service image `dockflow-pipelines:core-verification`, identity
`sha256:ad38d691b8e413b88f88b4ce7e30643dbd6767381fd947b00db83166af380276`,
passes non-root readiness, packaged UI/OpenAPI, two-step execution, artifact
publication, reuse, retained logs and restart with persistent history. The receipt
is `dist/core-service-verification.json`. The isolated engine reports Docker
29.7.2 on linux/amd64. Other native hosts/architectures are not qualified here.

Ruff lint/format, Pyright, generated API/version checks, Macrostates composition
and imported integrity, impact coverage, whitespace, portable-reference and local
Markdown-link checks pass. Node's five test files pass. Static and blocked-import
checks prove Core loads without any consuming package or optional integration.
Standalone Artifacts creates only its own table and the generic version registry.

## Evidence and release disposition

The final runtime/test/build inventory is retained at
`tmp/reviews/generic-core/source.json`: 156 files with aggregate SHA-256
`16ca06ec01df7fb7d38140a605275ef9f4daa95ced6a3c94a44937302f3591e1`.
The exact file hashes identify the dirty source independently of the origin
commit. Specification selections and validation/workflow prose are tracked
separately from that runtime inventory.

The unintegrated database-package candidate was superseded coherently. Its plan
is retained at `tmp/reviews/generic-core/superseded-release-plan.yaml`; all ten
archived change-record hashes matched before the records returned to pending
scope unchanged. Committed baseline declarations are restored while current Core
contract selections remain. No candidate is prepared, no tag was created and no
publication resumed. A future release must recalculate the pending scope under
the current four-distribution policy. The fresh backup format is `dockflow-sql-v5`.

The new specification and implementation workflows await acceptance. Release preparation remains on hold. Existing historical receipts
retain their original scope and obsolete package identities as provenance.
