# Grouped sidebar specification

- Project phase: `active`
- Workflow type: `Specification update`
- Status: completed
- Delivery state: accepted
- Change depth: `small`
- Branch: `feature/deletion-and-storage-cleanup`
- Requested by: Definer
- Implementer: Implementer
- Started at: 2026-10-25 18:48 (UTC)
- Last updated at: 2026-10-26 12:06 (UTC)

## Objective and scope

Require sidebar sections in order: Definitions (Pipelines, Components), Workloads
(Experiments, Runs, Executions), Storage (Artifacts, Cleanup). Rename the sidebar
cleanup label while preserving its destination and screen title. Preserve footer
utilities, accessible navigation, narrow layouts and current-page highlighting.
Implement through the companion
[implementation workflow](2026-10-25__20JZ7N__grouped-sidebar-implementation.md).

## Scope and authorization

This information-organization objective is distinct from the eight open deletion,
orientation, workspace and background-pan workflows, which remain awaiting
acceptance. Continue on the authorized branch; no integration, publication,
tagging or closure is authorized. Advance the local Pipelines contract by a Minor
for additive required grouping, align composition and preserve application and
finalized project versions. Use anonymous attribution and portable paths.

## Acceptance and next step

Update the owning sidebar and cleanup references, validate specification/package
alignment and document usage. The implementation gap remains pending until the
companion change passes browser checks. Explicit acceptance and closure remain
pending after unpublished delivery.

## Delivered requirements and evidence

Pipelines 013 now owns the exact three named sections and requested item order,
Cleanup label, accessible/narrow captions, detail-route highlighting and separate
footer utilities. Pipelines 015 and usage guides align the cleanup entry point.
The local Pipelines package advances from 13.3.0 to 13.4.0 for the additive grouping
requirement; composition and entrypoint match. Existing Artifacts dependencies
remain satisfied. Application/finalized baseline versions are unchanged.
Composition/import and diff checks passed. The companion implementation satisfies
the requirement, with browser evidence recorded there and no known gap. Definer
testing, acceptance and explicit closure remain pending; no publication occurred.

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
