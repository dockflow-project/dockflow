# Top-to-bottom graph requirement

- Project phase: `active`
- Workflow type: `Specification update`
- Status: completed
- Delivery state: accepted
- Change depth: `small`
- Branch: `feature/deletion-and-storage-cleanup`
- Requested by: Definer
- Implementer: Implementer
- Started at: 2026-10-25 12:27 (UTC)
- Last updated at: 2026-10-26 12:06 (UTC)

## Objective and scope

Require consistent top-to-bottom flow for all pipeline and Run graphs, including
nested subpipelines and All tasks. Extend the owning web-interface contract and
its validation criteria. Track implementation in the linked
[graph amendment](2026-10-25__1AQ2RC__top-to-bottom-graphs.md).

## Authorization and impact

The Definer explicitly requested the specification addition during implementation.
This adds a presentation requirement without changing persisted data or interfaces;
advance the local Pipelines package by a Minor and align the composition/entrypoint.
Do not advance finalized project baselines or application versions. Existing
Artifacts dependencies remain satisfied. The two deletion workflows and graph
implementation workflow remain open; no closure, integration or publication is
authorized. Use anonymous role attribution and portable documentation paths.

## Acceptance and next step

Update the owning graph requirement and desktop/narrow validation criteria,
validate composition and specification consistency, and link implementation
evidence. Explicit Definer acceptance and closure remain pending after delivery.

## Delivered changes and validation

Pipelines 013 now requires vertical flow, peer columns and bottom-center to
top-center connectors in all graph screens/scopes, preserved during navigation
and zoom. Its validation section includes both screens, nested/All tasks views,
parallel branches and desktop/narrow viewports. The local package advances from
13.0.0 to 13.1.0 for this additive requirement; composition and entrypoint match.
The existing Artifacts at-least dependency remains satisfied. Finalized project
and application versions are unchanged. Macrostates composition/import checks
and diff whitespace checks passed; the linked implementation workflow records
browser coverage. No known implementation gap remains. Definer acceptance,
explicit closure and any publication remain pending and unauthorized.

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
