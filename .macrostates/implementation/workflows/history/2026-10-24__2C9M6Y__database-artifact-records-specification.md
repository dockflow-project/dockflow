# Database artifact records: specification

- Project phase: `active`
- Workflow type: `Specification update`
- Status: completed
- Delivery state: `accepted`
- Change depth: `large`
- Branch: `feat/distributed-artifact-cache`
- Requested by: Definer
- Implementer: Implementer
- Started at: 2026-10-24 22:13 (UTC)
- Last updated at: 2026-10-24 23:48 (UTC)

## Objective and scope

Move artifact publication claims, completion manifests and recovery descriptors
into the unified SQLite/PostgreSQL database using one shared backend abstraction.
Keep payload bytes and a storage identity marker in artifact storage. Support
standalone Artifacts and Pipelines without coupling Artifacts to the orchestrator.
Update owning contracts, configuration, backup/restore, packages and tests.
Existing data need no migration; reject incompatible state without deleting it.

## Acceptance criteria

Concurrent identical publication converges and conflicting/overlapping paths fail.
Interrupted uploads can be retried without advertising incomplete artifacts.
SQLite and PostgreSQL share the implementation, including maintenance exclusion,
fencing and project-scoped backups. No artifact bookkeeping sidecars remain.
Retain anonymous portable records and unrelated existing work. No commit, external
publication, workflow closure or deletion of existing project state is authorized.

## Progress and remaining work

Reviewed storage publication boundaries and existing shared database adapter.
Implement extraction, SQL records, integration and qualification. No blocker.

## Delivery

Implemented the shared database distribution, SQL publication records and fenced
Pipelines recovery descriptors. Updated owning contracts, fresh-state formats,
standalone configuration, coordinated package/release tooling, backup/restore
and operating guides. The [validation receipt](../../validation/database-artifact-records.md)
records both supported-interpreter regressions, real providers/processes, final
artifact identities and source bindings. The [change record](../../changes/database-artifact-records.yaml)
classifies Major impact without assigning finalized baselines or application
releases. No implementation blocker remains. Temporary providers/environments
were removed. Keep this workflow open pending explicit Definer acceptance/closure.


## Definer-confirmed closure

The Definer explicitly accepted the completed delivery and authorized closure of
all open workflows on 2026-10-24 23:48 UTC, together with reviewed integration and
package publication. This scope is completed; earlier pending-state statements
are historical. Later conformance corrections retain their own evidence.
