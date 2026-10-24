# Unified database: implementation

- Project phase: `active`
- Workflow type: `Implementation update`
- Status: completed
- Delivery state: `accepted`
- Change depth: `large`
- Branch: `feat/distributed-artifact-cache`
- Requested by: Definer
- Implementer: Implementer
- Started at: 2026-10-23 12:08 (UTC)
- Last updated at: 2026-10-24 23:48 (UTC)

## Objective and scope

Unify execution state and cache coordination in one configured database for
SQLite and PostgreSQL. Both repositories use one backend abstraction and one
versioned schema. SQLite defaults beneath `.dockflow`; PostgreSQL uses one
external connection reference. Artifact bytes remain in managed storage.
Existing split databases need no migration. Work is limited to Dockflow and
uses anonymous records and portable examples.

## Acceptance criteria

One connection configuration selects the physical database for both domains;
cache-specific connection overrides are rejected. Shared schema initialization
works in either repository order, read-only operations remain nondestructive,
and unsupported/incomplete schemas fail closed. Independent cache transactions
preserve lease/fencing semantics while state ownership stays pinned. Export and
restore include project cache records in the same consistent database snapshot.
Both real backends pass ownership, recovery, coordination and runtime tests.
Existing unrelated changes and workflows remain open. No commit or publication
is requested.

## Progress

Reviewed the split repositories, connection settings, schema initialization,
backup boundaries and existing conformance tests. Implementation is underway.

## Delivery

Updated the owning specifications and implemented the shared SQLite/PostgreSQL
adapter, single connection configuration, atomic full schema and complete project
snapshot/backup recovery. The [validation receipt](../../validation/unified-database.md)
records the final two-interpreter full regressions, real provider tests, package
builds and deployed-image checks. The [change record](../../changes/unified-database.yaml)
classifies Major impact without allocating finalized baselines or application
releases. Existing split databases are not migrated. Earlier workflows remain
independently open; this delivery remains open pending explicit Definer closure.
No implementation blocker remains. Physical multi-host qualification is not claimed.


## Definer-confirmed closure

The Definer explicitly accepted the completed delivery and authorized closure of
all open workflows on 2026-10-24 23:48 UTC, together with reviewed integration and
package publication. This scope is completed; earlier pending-state statements
are historical. Later conformance corrections retain their own evidence.
