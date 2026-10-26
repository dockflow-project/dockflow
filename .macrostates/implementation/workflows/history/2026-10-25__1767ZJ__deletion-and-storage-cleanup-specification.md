# Deletion and storage cleanup: specification

- Project phase: `active`
- Workflow type: `Specification update`
- Status: completed
- Delivery state: accepted
- Change depth: `large`
- Branch: `feature/deletion-and-storage-cleanup`
- Requested by: Definer
- Implementer: Implementer
- Started at: 2026-10-25 11:24 (UTC)
- Last updated at: 2026-10-26 12:06 (UTC)

## Objective and scope

Define and deliver dependency-protected deletion of Runs, executions and artifacts;
optional artifact payload deletion; managed filesystem/S3 inventory and cleanup
with ownership classification, complete byte totals, explicit DANGER confirmation
and durable retryable jobs; explicit-only manual artifacts; optional disabled-by-
default deployment retention using the same eligibility checks. Preserve shared
producer references, active work, pins, publication records and storage identity.
Update owning specifications, composition, implementation, API/CLI/browser,
user documentation and qualification. Prepare an unpublished local test delivery.

## Authorization and boundaries

Development branch creation was explicitly authorized. No publication, integration,
tagging, release finalization or workflow closure is authorized. Documents and
retained evidence use anonymous role attribution and portable paths. Existing
project data and unrelated work must remain untouched. Use disposable test state.

## Acceptance criteria

All adapters share server-side eligibility, plan validation and DANGER enforcement.
Referenced artifact records and their bytes cannot be deleted. Manual registration
and imports are never orphans or automatic-retention candidates. Deletion survives
replay and cannot reset cache fences. Scan/selection estimates cover complete
inventories without double counting. Validate SQLite and available real providers,
API, CLI, browser, crash/retry/stale-plan protections and standard repository checks.

## Progress and evidence

The classification explanation refinement continues the inventory usability
objective: define on-demand help beside the Classification filter, with all seven
categories explained only after activating a question-mark button.
The owning contract and usage guide now include this behavior; composition and
diff checks passed. This clarification stays within the pending package update
and does not advance the already proposed package version or finalized baseline.

Specifications, composition, implementation and current usage documentation are
aligned. Required deletion, storage, browser and retention behavior is delivered.
Qualification is recorded in
[deletion and storage cleanup](../../validation/deletion-and-storage-cleanup.md).
Two full interpreter/provider runs passed 879 tests each; final focused runs
passed 70 each. Browser, package, static/API and composition checks passed.
A fresh local disposable service is available for Definer testing. Work remains
uncommitted and unpublished; starting application and finalized baseline versions
are preserved. No existing project data or unrelated work was changed.

## Remaining acceptance

Definer manual testing, acceptance and explicit workflow closure remain pending.
No proposal submission, integration, tags or publication is authorized.

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
