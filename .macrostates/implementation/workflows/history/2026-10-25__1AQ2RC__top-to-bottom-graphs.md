# Top-to-bottom pipeline and Run graphs

- Project phase: `active`
- Workflow type: `Implementation amendment`
- Status: completed
- Delivery state: accepted
- Change depth: `small`
- Branch: `feature/deletion-and-storage-cleanup`
- Requested by: Definer
- Implementer: Implementer
- Started at: 2026-10-25 12:26 (UTC)
- Last updated at: 2026-10-26 12:06 (UTC)

## Objective and scope

Change every use of the shared pipeline/Run graph to flow top to bottom, including
focused subpipelines and All tasks. Place peers side by side and connect the
bottom of each source node to the top of its dependent node. Preserve selection,
hierarchy, pan/zoom and actual task identities. Update usage/current-state
documentation and verify the packaged renderer on desktop and narrow screens.

## Scope and authorization

This is a distinct graph-presentation objective from the two open deletion and
storage cleanup workflows, which remain awaiting acceptance. The authorized
development branch is retained for this unpublished review refinement. No
publication, integration, tagging or workflow closure is authorized. No effective
application baseline change is needed. The subsequent explicit specification
request is tracked in the linked
[specification workflow](2026-10-25__1ARHHE__top-to-bottom-graph-requirement.md).
Record implementation patch impact alongside the new specification Minor.

## Acceptance and next step

Pipeline and Run screens, nested scopes and All tasks render dependencies downward
with visible, correctly attached edges and usable controls. Validate representative
chains and parallel branches with the real shared renderer, plus existing
JavaScript suites and formatting/diff checks. Use disposable preview data only.
Explicit Definer acceptance and closure remain pending after delivery.

## Delivered changes and validation

The shared renderer now places dependency levels in rows and peers in columns,
sizes the canvas to the vertical layout, and draws bottom-to-top connectors.
Both call sites (pipeline/definition detail and Run detail) use it without local
orientation overrides. Usage and current architecture documents are aligned.

All six JavaScript test files passed. Chromium 140 on Linux verified actual
pipeline and successful Run screens on desktop and narrow viewports, node
selection, zoom/reset and scroll panning. A disposable in-browser graph exercised
parallel branches, focused nested scopes, breadcrumbs and All tasks containment.
All connectors attach to source bottom and dependent top centers; nodes fit
the canvas. No browser errors or page-width overflow occurred. A graph-only
screenshot was visually inspected and discarded. No persisted preview data was
changed. Frontend formatting, composition/import integrity and diff checks passed.

The existing graph contract was deliberately extended by the companion
specification workflow. Application/finalized baseline versions remain unchanged;
the source preview includes the refinement. Earlier wheel receipts predate it.
No new distribution build, commit, integration or publication was performed.
Next step: Definer testing and explicit acceptance/closure.

## Definer-authorized completion and closure

The Definer explicitly authorized acceptance and closure of all open workflows,
committing, pushing, PR submission, reviewed merge and release. The requested
local scope is delivered and relevant validation passed; no required source gap
remains. All original feature provenance and classification are preserved.
[Release qualification](../../validation/release-0.3.0.md) records the combined
evidence and separates subsequent hosted CI, merge, immutable candidate and
publication outcomes. No upload is claimed by this closure.

- Closure authorized by: Definer; explicit all-workflow closure and release instruction
- Closed at: 2026-10-26 12:06 (UTC)
