# Domain persistence cleanup: implementation

- Project phase: `active`
- Workflow type: `Implementation update`
- Status: `completed`
- Delivery state: `accepted`
- Change depth: `large`
- Branch: `feat/distributed-artifact-cache`
- Requested by: Definer
- Implementer: Implementer
- Started at: 2026-10-24 22:44 (UTC)
- Last updated at: 2026-10-24 23:48 (UTC)

## Objective and scope

Review the current implementation for carryovers from file-backed state, split
databases and earlier storage layouts. Replace virtual filesystem persistence
with domain repositories and numeric journal sequences; remove duplicate resource
projections, obsolete index wrappers, import shims and historical descriptor reads.
Keep current supported CLI, API, configuration, SQL coordination and artifact
publication behavior. Update specs, tests, backup/recovery and current docs.
Existing data need no migration. Preserve unrelated work and existing project data.

## Acceptance criteria

No file-shaped SQL keys or generic state read/write/path interface remain in
production code. Durable domain records use explicit identities and one resource
projection. Journal validation/replay, source integrity, logs, output commits,
cache observations, leases, fencing, recovery and project isolation remain tested.
Use the shared database package directly; actual payload/temporary/backup files
retain filesystem APIs. Inspect all implementation packages for related leftovers.
Qualify both SQL backends, supported interpreters, real providers, packages and
service image. No commit, external publication or workflow closure is authorized.

## Progress

Completed the implementation audit and domain repository/schema cleanup,
removed import/identity facades and unused compatibility paths, repaired stale
current-state documentation and updated tests, including deterministic concurrent
lock coverage. The final full suites pass on Python 3.12 and 3.13 with real
PostgreSQL, S3 and Docker. Package installation/source rebuilds, the service image,
static checks, generated API docs, specification integrity and documentation
checks pass. Disposable qualification resources were removed. No blocker.

## Delivery

See [validation](../../validation/domain-persistence-cleanup.md),
[change impact](../../changes/domain-persistence-cleanup.yaml) and
[work origin](../../work/domain-persistence-cleanup.yaml). The Pipelines specification
package receives a Major change; application and finalized project baseline
versions remain unchanged. Fresh state is required, with no migration or deletion
of existing project data. The work is ready for acceptance; the workflow remains
open. No commit, publication or closure was performed.


## Acceptance and closure

The Definer explicitly accepted the completed delivery and authorized closure of
all open workflows on 2026-10-24 23:48 UTC, together with reviewed integration and
package publication. This scope is completed; earlier pending-state statements
are historical. Later conformance corrections retain their own evidence.
