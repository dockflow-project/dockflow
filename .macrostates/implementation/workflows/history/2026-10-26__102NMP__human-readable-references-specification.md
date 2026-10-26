# Human-readable resource references specification

- Project phase: `active`
- Workflow type: `Specification update`
- Status: completed
- Delivery state: accepted
- Change depth: `medium`
- Branch: `feature/deletion-and-storage-cleanup`
- Requested by: Definer
- Implementer: Implementer
- Started at: 2026-10-26 09:20 (UTC)
- Last updated at: 2026-10-26 12:06 (UTC)

## Objective and authorization

Define and implement consistent human-readable names beside resource IDs across
web lists, details, graph inspectors, lineage, comparisons, selectors and dialogs.
Executions/tasks include component names; Runs include compiled pipeline names;
pipelines/versions and experiments include their corresponding names. Preserve
exact IDs, URLs, provenance, raw records, pagination and graph position/zoom.
Resolve only referenced records with bounded authenticated read-only lookups,
including missing/deleted targets without breaking the page. Treat names as text.

Use the authorized branch and preserve all prior changes and example data. Track
additive Minor specification/implementation impact. Keep delivery unpublished for
Definer testing. No commit, integration, release, publication or workflow closure
is authorized. The eighteen earlier workflows remain independently open.

## Delivered scope and qualification

The web contract owns consistent component/pipeline/experiment context beside
resource IDs throughout lists, details, related references, graph inspectors,
lineage, comparison, selectors and deletion surfaces. The native API owns bounded
read-only reference-name requests/responses. Acceptance, package selection,
generated reference, usage and current architecture align. Both impacts are
additive Minor; finalized project/application versions remain unchanged.

Implementation resolves requested records and direct name-bearing dependencies
without catalog scans, then decorates browser text/title/field hints in place.
Exact IDs/routes/values, invocation labels and raw records/provenance remain.
Missing names retain usable IDs; optional lookup failures and stale replies are
isolated. Refresh/navigation invalidates cache; sign-out clears name state.
Graph selection/name updates preserve graph DOM, zoom and position.

The [receipt](../../validation/human-readable-references.md) records 245 backend
passes with 30 optional skips, 38 JavaScript checks, eight dedicated browser
groups with/without bearer auth, fourteen existing browser journeys and static/
reference/specification checks. Anonymous desktop/narrow captures were inspected
and discarded. Disposable QA services and credentials were removed.

The existing preview was restarted in place, retaining two successful Runs and
all ten artifacts, including the manually uploaded artifact. Real execution-row
reference names were checked without submitting/mutating preview data. No build,
commit, integration, tag or publication occurred. The eighteen earlier workflows
remain independent; all twenty await Definer testing and explicit acceptance/
closure.

## Name-first display refinement

The same reference-label objective now requires the human-readable name before
its ID, including when preserving an invocation/attempt label. Selected ID inputs
keep their values and show the resolved name above the input. This remains within
the original scope and does not authorize publication or workflow closure.
Shared captions now place resolved names before invocation/attempt labels and
IDs; existing names/adjacent IDs are not duplicated. Execution headings use the
same decoration, and selected ID hints appear above inputs without changing
values. The contract/package selection and UI usage align. All seven JavaScript
test files, frontend formatting, composition/import and whitespace checks passed.
Read-only real-browser checks on the existing preview verified list ordering,
execution headings and hint/input order with exact values and no page errors.
No backend/data/release changes or publication occurred; testing/closure remains
pending.

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
