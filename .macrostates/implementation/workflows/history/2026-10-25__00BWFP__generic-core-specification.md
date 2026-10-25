# Generic Dockflow Core specification

- Project phase: active
- Workflow type: Specification update
- Status: completed
- Delivery state: accepted
- Change depth: large
- Branch: release/0.2.0
- Requested by: Definer
- Closure authorized by: Definer; explicit all-workflow closure and release instruction
- Closed at: 2026-10-25 00:33 (UTC)
- Implementer: Implementer
- Started at: 2026-10-25 00:06 (UTC)
- Last updated at: 2026-10-25 00:33 (UTC)

## Objective and scope

Replace the shared database distribution with a domain-independent Dockflow Core.
Core supplies reusable database, schema coordination and other genuinely shared
primitives, with no knowledge of or dependency on consuming packages. Each
consumer owns its schemas, queries and persistence policy. Keep one physical
SQLite/PostgreSQL database and preserve standalone Artifacts installation.
Review additional common code and move appropriate primitives without changing
persisted identity algorithms. Update contracts, imports, packaging, release
preparation, documentation and meaningful boundary/provider tests together.
Existing state and unpublished distribution compatibility need no migration.

## Related work and publication hold

The coordinated release preparation workflow remains open and publication is
paused by the Definer. Its prepared candidate predates this design and is stale;
it must be recalculated before any integration or publication. Preserve its
prepared change archives and original provenance. This distinct specification
and implementation outcome does not close or silently resume release work.

## Acceptance

Core imports no consuming package and contains no domain schema, query names or
records. Consumers initialize/version only their declared schemas, including
Artifacts-first and Pipelines-first use of one database. All other distributions
depend on Core. Verify standalone builds/installs, lazy imports, generic schema
coordination and SQLite/PostgreSQL integration; retain domain behavior checks.

## Progress

Contracts and implementation are aligned. Core contains only generic services;
consumer schema/query/repository ownership, imports, packaging and current
architecture documentation are updated. Source, driver and model boundaries are
covered by static and isolated-install checks. Publication remains on hold and
workflow closure awaits acceptance.

## Candidate disposition

The paused, unintegrated release preparation was reversed coherently after all
ten archived-record hashes matched its preserved plan. Records returned to
pending scope unchanged; numeric declarations returned to the committed baseline
while the new Core contract selections remain. The superseded plan is retained
under `tmp/reviews/generic-core/`. No publication or release integration occurred.

## Completed qualification

The final source passes 813 tests on each of Python 3.12.15 and 3.13.17 with real
PostgreSQL, S3 and Docker, plus clean wheel installs, standalone source rebuilds,
the non-root service image, static checks and specification integrity/coverage.
Each interpreter has 14 intentional skips and five upstream warnings. No required
implementation remains. See [Core validation](../../validation/generic-core.md) for
exact scope, source identity and receipts. New workflows remain open for acceptance;
the release workflow remains on hold and no publication resumed.

## Definer-confirmed closure

The Definer explicitly accepts the completed work, closes the open workflows and
authorizes PR preparation, pushing, reviewed merge and package publication.
The qualified Core contract and implementation are accepted. Final tests pass
813 cases on each supported interpreter. The remaining publication-description
references were reconciled with the accepted dependency/schema ownership design;
this editorial correction changes no runtime behavior.
Subsequent release execution is tracked by 2026-10-25__01XXNW__core-release-finalization.md and the hosted release
system. External CI/publication outcomes remain pending rather than fabricated.
