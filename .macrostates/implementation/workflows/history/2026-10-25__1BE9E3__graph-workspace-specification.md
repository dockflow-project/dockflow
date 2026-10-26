# Graph workspace specification

- Project phase: `active`
- Workflow type: `Specification update`
- Status: completed
- Delivery state: accepted
- Change depth: `medium`
- Branch: `feature/deletion-and-storage-cleanup`
- Requested by: Definer
- Implementer: Implementer
- Started at: 2026-10-25 12:39 (UTC)
- Last updated at: 2026-10-26 12:06 (UTC)

## Objective and scope

Specify a viewport-filling pipeline/Run workspace: persistent left navigation and
project/service bar, compact fixed resource header with bottom tabs, graph filling
the remaining area with internal pan/scroll, and an independently scrolling right
inspector. Selecting tasks must preserve the existing graph, zoom and position.
Require accessible narrow layouts and preserved state during live updates.
Implement through the companion
[implementation workflow](2026-10-25__1BE9E3__graph-workspace-implementation.md).

## Scope and authorization

This screen-layout and selection-state objective is distinct from the open
deletion and graph-orientation specification/implementation workflows. Those four
deliveries remain awaiting acceptance. Continue on the authorized development
branch; no publication, integration, tagging or closure is authorized. Use role
attribution and portable paths. Advance the local Pipelines contract by a Minor
for additive presentation requirements, align composition and record impact;
preserve application/finalized baseline versions. No deployment setting is needed
for this required screen behavior.

## Acceptance and next step

Update Pipelines 013 and its browser validation criteria, check composition and
specification consistency, document usage and implementation qualification.
The implementation gap remains open until the companion delivery passes browser
checks. Definer testing and explicit workflow closure remain pending.

## Delivered requirements and evidence

Pipelines 013 owns the fixed workspace/header, independent graph/inspector scroll,
in-place selection, viewport retention, keyboard and narrow-layout requirements.
Its validation criteria cover these behaviors. The local Pipelines package
advances from 13.1.0 to 13.2.0 for additive requirements; composition/entrypoint
align and existing Artifacts at-least dependencies remain satisfied. Finalized
project and application versions are unchanged. Macrostates composition/import
checks and diff checks passed. The companion implementation now satisfies the
contract; [qualification](../../validation/graph-workspace.md) records browser and
regression coverage. No known implementation gap remains. Definer testing,
acceptance and explicit workflow closure remain pending; no publication is
authorized.

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
