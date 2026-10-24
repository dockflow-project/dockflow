# Concurrent PostgreSQL Runs: implementation

- Project phase: `active`
- Workflow type: `Implementation update`
- Status: `completed`
- Delivery state: `accepted`
- Change depth: `large`
- Branch: `feat/distributed-artifact-cache`
- Requested by: Definer
- Implementer: Implementer
- Started at: 2026-10-23 12:36 (UTC)
- Last updated at: 2026-10-24 23:48 (UTC)

## Objective and scope

Preserve one local SQLite database and coordinator while enabling PostgreSQL
coordination of independent isolated hosts in one project. Add fenced per-Run
ownership, concurrent admission/queue claims, scoped recovery and exclusive
maintenance through the shared database abstraction. Artifact bytes remain in
commonly accessible storage. Tasks within each Run remain sequential.

## Acceptance criteria

Independent PostgreSQL processes execute different Runs concurrently; one Run
has at most one current authorized owner. Leases use database time, renew while
execution is active and fence stale writers after expiry/takeover. Shared journal,
identity, catalog, idempotency and stop/publication updates remain transactional.
Recovery never stops another live Run and never assumes another Docker daemon
proves an abandoned container stopped. Maintenance excludes coordinators and
cache writers. SQLite exclusion and runtime behavior remain supported. Test
independent processes, competing claims, faults, cancellation, recovery and
service/direct paths on real providers. Update contracts and operating guides;
retain anonymous records and unrelated existing changes. No commit, publication
or closure of earlier workflows is authorized.

## Progress

Reviewed project ownership, pinned sessions, journal sequence allocation, worker
RPC, direct admission, queue dispatch, cancellation and maintenance boundaries.

## Delivery

Updated owning specifications and implemented backend-selected coordination,
fenced PostgreSQL Run leases, transactional admission/counters, direct reservation,
shared queue dispatch, remote cancellation, scoped recovery and maintenance gates.
Immutable cache observations preserve live producer lifecycle and portable recovery.
The [validation receipt](../../validation/concurrent-postgresql-runs.md) binds the final
source and records full supported-interpreter regressions, real independent-service
Docker/S3 execution, package checks and final-image qualification. The
[change record](../../changes/concurrent-postgresql-runs.yaml) classifies Major impact
without allocating finalized baselines or application releases. Temporary providers
and the additional interpreter environment were removed. Existing unrelated work
and earlier open workflows remain preserved. No implementation blocker remains;
physical multi-host qualification is not claimed. Keep this workflow open pending
explicit Definer acceptance/closure. No commit or publication was performed.


## Acceptance and closure

The Definer explicitly accepted the completed delivery and authorized closure of
all open workflows on 2026-10-24 23:48 UTC, together with reviewed integration and
package publication. This scope is completed; earlier pending-state statements
are historical. Later conformance corrections retain their own evidence.
