# Collapsed pipeline graphs

- Project phase: `active`
- Workflow type: `Implementation amendment`
- Status: completed
- Delivery state: `accepted`
- Change depth: `medium`
- Branch: `feat/collapsed-pipeline-graphs`
- Requested by: Definer
- Implementer: AI-assisted implementation
- Started at: 2026-10-22 17:50 (UTC)
- Last updated at: 2026-10-24 23:48 (UTC)

## Original request and scope

Present nested pipeline execution and artifact-publication helpers as collapsed
logical nodes, retain access to their internal graph, and qualify a consuming
pipeline against the updated development service. Preserve native task identity,
execution, artifact lineage and cache semantics. No publication or merge is in scope.

## Acceptance criteria

- Pipeline and Run graphs default to one visible node per immediate child task.
- Nested graphs can be opened with breadcrumbs and inspected without hiding the
  underlying task records, errors, attempts, outputs or logs.
- Deep task links, browser navigation and live refresh retain graph context.
- A complete task view remains available, with truthful limits and safe text rendering.
- Nested authoring and real execution are qualified against a consuming pipeline;
  qualification records in this repository remain anonymous and portable.

## Design and current contract

The existing web-interface contract requires exact task paths, dependencies and
nested containment. Collapsed navigation specializes that presentation without
changing execution or the accepted graph. No specification change is currently
needed; any discovered mismatch will be surfaced for a deliberate specification update.

## Work done

- Inspected the current graph renderer and nested-task projection.
- Verified a clean primary checkout and created the scoped development branch
  before any file edits, as part of the authorized implementation setup.
- Added immediate-child graph projection, keyboard-accessible subpipeline controls,
  breadcrumbs and an explicit complete hierarchy view for pipeline and Run pages.
- Retained native task identities, observed states, details, logs, attempts,
  artifact lineage and reuse; added query-backed graph scope and safe fallback.
- Qualified display bounds, safe labels, browser history, deep links, polling and
  narrow layouts with focused regression and real Chromium checks.
- Qualified a native grouped consuming pipeline: 22 computations, 24 root nodes,
  90 total tasks; API execution succeeds and the direct CLI reuses all 22
  computations without new attempts against the shared state.
- Rebuilt the consuming service from final source, checked CA bundles, verified
  served source and completed/reused task inspection, and left the API running.
- Updated usage/current architecture documentation and recorded pending patch
  impact against the unchanged specification baseline. See the
  [qualification receipt](../../validation/collapsed-pipeline-graphs.md) and
  [change record](../../changes/collapsed-pipeline-graphs.yaml).

## Remaining work

Implementation and applicable qualification are complete. Await Definer acceptance
and explicit workflow closure. No commit, proposal, push, merge or publication was
requested or performed. Existing application/baseline declarations remain unchanged.

## Blockers

None identified.


## Definer-confirmed closure

The Definer explicitly accepted the completed delivery and authorized closure of
all open workflows on 2026-10-24 23:48 UTC, together with reviewed integration and
package publication. This scope is completed; earlier pending-state statements
are historical. Later conformance corrections retain their own evidence.
