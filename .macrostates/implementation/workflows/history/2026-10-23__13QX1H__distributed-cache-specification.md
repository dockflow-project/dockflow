# Distributed cache specification

- Project phase: `active`
- Workflow type: `Specification update`
- Status: completed
- Delivery state: `accepted`
- Change depth: `large`
- Branch: `feat/distributed-artifact-cache`
- Requested by: Definer
- Implementer: Implementer
- Started at: 2026-10-23 10:24 (UTC)
- Last updated at: 2026-10-24 23:48 (UTC)

## Objective and scope

Adopt the proposed Dockflow distributed artifact-cache contract and reconcile its owning specifications. Work is confined to Dockflow. All retained documents and evidence use role attribution, portable examples and repository-relative paths. No commit, integration, tag or publication is requested.

## Acceptance criteria

The cache contract covers atomic claim-or-reuse on SQLite and PostgreSQL, durable retry episodes, renewable fenced ownership, immutable complete output sets, verified reuse, conditional invalidation, bounded cancellation/waiting and recovery. Independent-process contention, crash/stale-owner and storage fault tests establish behavior on both backends. Existing single-state execution ownership remains exclusive.

## Context and progress

The pre-existing medium-depth collapsed-pipeline-graphs amendment is awaiting acceptance and remains open. Its working-tree changes are deliberately preserved on this development branch; its scope and acceptance are independent. This feature has separate specification and implementation workflows and one work origin.

- Read the proposed feature and current execution, reuse, storage and persistence boundaries.
- Independent execution state roots may share a registry/store; one state root retains its OS owner lock and serial execution journal.

## Delivery and remaining review

The implementation, operational documentation and local qualification are delivered.
The [validation receipt](../../validation/distributed-artifact-cache.md) records exact
scope and limits; the [change record](../../changes/distributed-artifact-cache.yaml)
classifies Major impact without allocating finalized baselines or application
versions. Final test and packaging outputs are consolidated in that receipt. Physical
multi-host deployment qualification remains explicitly outstanding. Keep this
workflow open pending Definer acceptance and explicit closure; the earlier graph
workflow remains independent and open.

## Work completed

- Adopted the proposed contract as 014; preserved its section/test numbering and
  linked its topic ownership from execution, artifacts, persistence, reuse,
  configuration, CLI/API and acceptance. Clarified distributed cache versus
  per-state execution ownership and recorded versioned legacy behavior.
- Implemented the registry, lease supervision, sealed portable output sets,
  production/wait integration, stop ordering, provenance import and inspection.
- Added real SQLite/PostgreSQL process contention, crash/lease/clock/commit faults,
  conditional S3 tests, CLI/API contracts and PostgreSQL CI wiring.
- Qualified Docker/service behavior, both supported Python interpreters,
  clean artifacts, independent sdist rebuilding, typing, lint, format, generated
  API and composition/imported integrity. The receipt owns measured results.

## Blockers

No local implementation blocker remains. Physical multi-host qualification is
explicitly outstanding; no such deployment claim is made. Acceptance and workflow
closure require explicit Definer confirmation. No integration or publication was requested.


## Definer-confirmed closure

The Definer explicitly accepted the completed delivery and authorized closure of
all open workflows on 2026-10-24 23:48 UTC, together with reviewed integration and
package publication. This scope is completed; earlier pending-state statements
are historical. Later conformance corrections retain their own evidence.
