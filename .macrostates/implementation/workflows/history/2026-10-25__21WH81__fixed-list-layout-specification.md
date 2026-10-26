# Fixed list layout specification

- Project phase: `active`
- Workflow type: `Specification update`
- Status: completed
- Delivery state: accepted
- Change depth: `medium`
- Branch: `feature/deletion-and-storage-cleanup`
- Requested by: Definer
- Implementer: Implementer
- Started at: 2026-10-25 19:11 (UTC)
- Last updated at: 2026-10-26 12:06 (UTC)

## Objective and scope

Require record-list screens to fill the selected workspace with fixed title,
filter/action context at the top, a scrolling list with sticky column headings,
and fixed bottom pagination/counts. Cover catalogs, experiment Runs, artifact
consumers, Run results, comparison fields and cleanup files. Preserve server
cursor semantics and distinguish bounded locally loaded rows from global totals.
Require empty/error/narrow/keyboard behavior without page overflow. Implement via
the companion [workflow](2026-10-25__21WH81__fixed-list-layout-implementation.md).

## Scope and authorization

This list-workspace objective is separate from the ten open earlier deliveries,
which remain awaiting acceptance. Continue on the authorized development branch;
no integration, publication, tags or closure is authorized. Advance the local
Pipelines contract by a Minor and align composition; preserve application and
finalized project versions. Use anonymous attribution and portable evidence.

## Acceptance and next step

Update Pipelines 013 and cleanup references, usage and validation criteria.
Validate composition and qualify the companion implementation. The temporary
implementation gap remains open until browser checks pass. Explicit Definer
testing, acceptance and closure remain pending after unpublished delivery.

## Delivered requirements and evidence

Pipelines 013 owns the shared fixed list workspace, sticky headings, server/local
counts, refresh/empty/error behavior and narrow/keyboard requirements. Pipelines
015 specializes cleanup footer estimates and top tool access. The local Pipelines
contract advances by a Minor; package, composition and entrypoint align. Usage,
current architecture and validation criteria are updated. Composition/import
integrity and diff checks passed. The companion implementation passes the
[qualification](../../validation/fixed-list-layout.md), leaving no known gap.
Application/finalized versions remain unchanged. No publication or closure
occurred; Definer testing and explicit acceptance remain pending.

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
