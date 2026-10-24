# Database-backed execution state: specification

- Project phase: `active`
- Workflow type: `Specification update`
- Status: completed
- Delivery state: `accepted`
- Change depth: `large`
- Branch: `feat/distributed-artifact-cache`
- Requested by: Definer
- Implementer: Implementer
- Started at: 2026-10-23 11:30 (UTC)
- Last updated at: 2026-10-24 23:48 (UTC)

## Objective and scope

Replace file-authoritative execution history with a database-backed journal,
query projections, definitions, logs and control settings. SQLite remains the
local default beneath `.dockflow`; PostgreSQL supports shared durable history
from isolated environments. Artifact bytes remain in managed storage. Existing
file history will be discarded; no history migration is required or implemented.
Work stays within Dockflow, with anonymous records and portable examples.

## Acceptance criteria

Both backends preserve IDs, complete accepted mutations, exact source snapshots,
logs, lineage, queue/idempotency state and pagination across fresh environments.
Database ownership preserves one active coordinator per project, fails closed on
connection loss and serializes durable mutations. PostgreSQL needs no durable
local history or MLMD file. Read-only operations do not initialize state; unknown
schemas/backends and legacy file history fail explicitly. Backup, restore,
rebuild, configuration, CLI/API and documentation match the new authority.
Independent-process exclusion, process death, rollback, project isolation,
provider faults and full runtime regressions are tested. Existing unrelated
changes/workflows remain open and preserved. No commit or publication requested.

## Progress

Reviewed current file journal, MLMD projection, cache registry and execution
ownership. Separate specification and implementation work is tracked here.

## Delivery

Implemented and qualified the accepted SQL-state contract. The
[validation receipt](../../validation/database-execution-state.md) records measured
results, source binding and qualification limits. The
[change record](../../changes/database-execution-state.yaml) classifies Major impact
without allocating finalized repository/application releases. Existing graph and
cache workflows remain independently open. No history migration is included.
No implementation blocker remains; physical multi-host qualification is not
claimed. Keep this workflow open pending explicit Definer acceptance/closure.


## Definer-confirmed closure

The Definer explicitly accepted the completed delivery and authorized closure of
all open workflows on 2026-10-24 23:48 UTC, together with reviewed integration and
package publication. This scope is completed; earlier pending-state statements
are historical. Later conformance corrections retain their own evidence.
