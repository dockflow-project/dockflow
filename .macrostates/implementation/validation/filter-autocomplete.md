# Filter autocomplete validation

## Scope and delivery

The unpublished working tree implements the
[filter autocomplete contract](../../specs/053_dockflow-pipelines/013_web-interface.md#filter-autocomplete)
and [native search API](../../specs/053_dockflow-pipelines/010_service-api.md#filter-suggestions-and-resource-search).
Primary resource Search fields and related-ID filters match names and IDs;
Cleanup's Artifact filter and distinct artifact Type suggestions are included.
Opening an empty field shows up to ten recent options. Workloads use execution
start with creation fallback, and definitions/components use registration time.
Names precede exact selected IDs. Apply filters remains the submission action.

Specification and implementation impact are Minor additive changes. Existing
exact filters, pagination semantics, authentication, routes and graph ownership
remain compatible. Usage, generated API schema/reference, package/composition
metadata and architecture align. Application and finalized baseline identities
remain unchanged. Definer testing and acceptance remain pending; no commit,
integration, distribution rebuild, tag, publication or workflow closure occurred.

## Measured results

| Check | Result |
| --- | --- |
| API/SQL | Twelve dedicated tests passed. Coverage includes recent ten-result limits, deterministic ID ties, name/ID matching, pipeline/component context, execution-start ordering, literal wildcard characters, retired target/context exclusion, all eight collections, distinct types, authentication, invalid/duplicate query rejection, generated schema, cursor binding, combined exact/search filters, read-only snapshots and project isolation. |
| Existing API/web regressions | Seventeen reference-name and 45 web tests passed alongside the initial eleven autocomplete tests; the added pagination/isolation case passed in the final twelve-case autocomplete run. One existing Starlette dependency warning. |
| JavaScript | All seven existing browser-module test files passed, including cleanup/reference/API behavior. |
| Targeted browser | Six authenticated groups passed: empty-field recent-ten ordering; mouse and Up/Down/Enter/Escape input; partial ID and mixed-case name matching; exact selected values and submitted filtering; delayed-reply isolation; unavailable/empty states and recovery; every resource/reference/type filter including Cleanup; responsive geometry and sign-out. |
| Existing browser journey | Fifteen authenticated groups passed, including actual Docker completion, pipeline/version upload, idempotency, logs, clone/reuse, comparison, artifact pin/import/lineage, failure/cancellation, narrow navigation, API explorer and memory-only sign-out. No page errors or external requests. |
| Final preview | Read-only browser checks passed for all six resource lists without page errors or mutations. The service reloaded its existing configuration/data to expose the new API and asset; all four Runs and ten artifacts present before reload remained afterward. |
| Static/specification | Ruff lint/format, Pyright, frontend formatting, generated API-reference drift, Macrostates composition/import integrity and whitespace checks passed. The distribution asset inventory includes the new browser module. |
| Visual | Desktop 1440-by-1000, narrow 390-by-844 and short 390-by-500 captures inspected. Lists remain within the workspace/viewport and leave sidebar controls unobstructed. Reviewed captures were discarded. |

Browser qualification used Chromium 140 on Linux and real disposable fixture
metadata. Delayed and unavailable responses are browser-local projections; actual
execution evidence is supplied by the separate established browser journey.
No new PostgreSQL, S3, maximum-load or additional platform qualification is
claimed. SQLite's LOWER supplies ASCII case folding; the API guide and owning
contract document this limit rather than claiming locale-aware Unicode search.

## Architecture and reproduction

`filter_options.py` supplies shared literal ID/name SQL predicates, direct
non-retired pipeline/component context and bounded recent selection. Resource
list Search uses the same predicates and existing filter-bound pagination.
Suggestions use one project-scoped read snapshot and SQL LIMIT 10; no catalog
materialization or artifact payload reads are involved. Fixed KFP schema paths
remain internal SQL constants. The read-only endpoint remains independent of the
execution mutation mutex. Distinct artifact types group live artifact metadata.

`autocomplete.js` decorates existing filter controls with a named combobox/listbox.
It debounces typing, inserts all labels as text, preserves exact selected values,
and rejects superseded responses. Page aborts, blur and dismissal invalidate
pending replies; popup placement stays inside the workspace and viewport.
Selection updates the field rather than submitting the form. Existing state and
availability selects retain their behavior.

See [browser qualification](../../../CONTRIBUTING.md#browser-qualification) for
`tools/filter_autocomplete_browser_smoke.py`. It adds anonymous experiments only
to a disposable fixture already populated by the general browser journey. Raw
execution receipts are sanitized to neutral checks; reviewed captures and the
disposable credential are removed, and only the QA service is stopped. The user
preview stays available. Twenty-four workflows remain independently open for
Definer testing and explicit acceptance/closure.

## Dependent-filter, count and inline-display refinement

Selected filters now show name followed by ID inside the input, without a
separate name hint or a changing header height. Submission and restored URL
filters retain canonical IDs. The UI uses Pipeline ID labels for immutable
version/definition references, while machine field names and routes remain intact.
Text and select controls share a 32-pixel toolbar height.

Components order Pipeline ID then Component ID and scope component suggestions
to the selected definition. Runs order Search, Experiment ID, Pipeline ID, State;
only versions used by live Runs in the selected experiment appear as pipeline
options. Executions order Search, Run ID, Task ID, State, with Tasks scoped to the
selected Run. Primary searches respect selected parents. State choices remain
complete. Parent changes clear dependent values and invalidate pending requests.

The endpoint now returns exact remaining_count with the bounded options. A SQL
window count measures matching resources or distinct types in the same snapshot,
after applying live-parent and project scope. A non-selectable sticky footer
shows `...and N more` only when the count is positive. Keyboard scrolling leaves
the active option visible above that footer. Invalid/unsupported scope arguments
are rejected; missing or retired parents return no options. Initial name lookup
uses the same invalidation epoch so it cannot restore a cleared/edited selection.

| Refinement qualification | Result |
| --- | --- |
| API/SQL | 76 tests passed: fourteen autocomplete cases plus seventeen reference-name and 45 web cases, with one existing Starlette warning. New coverage includes exact omitted counts, distinct-type counts, all dependent scope combinations, mismatched/retired parents, unsupported scopes, and unchanged accepted state. |
| Browser | Seven authenticated groups passed, including counts/footer visibility, inline and restored captions, exact ID submission, prescribed field order, scoped option identity, clearing dependent fields, complete State choices, matched heights and unchanged header geometry. Keyboard wraparound keeps the last option above the footer. Existing stale/error/navigation/sign-out and responsive checks also passed. |
| Existing execution/browser journey | Fifteen authenticated groups passed again on a separate disposable fixture with actual Docker execution, reuse, logs, upload, lineage, failure/cancellation and API explorer; no page errors or external requests. |
| JavaScript/static | Seven JavaScript test files, Ruff lint/format, Pyright, frontend formatting, generated-reference drift, Macrostates composition/import integrity and whitespace checks passed. |
| Visual | Desktop, narrow and short anonymous captures inspected; the omitted count stays visible at the dropdown bottom and leaves sidebar controls clear. Captures discarded. Anonymous DOM text projection avoids background masks obscuring the footer. |
| Preview | Reloaded only after confirming no active Runs. Read-only checks passed for component parent scope/inline caption and component/Run/execution field order and matching heights; all four Runs and ten artifacts were preserved. |

Owning contracts, usage, generated API reference, current architecture and change
classification align. The further specification refinement remains Minor and
additive. No new PostgreSQL, provider, platform or load qualification is claimed.
The disposable credential/service were removed, neutral receipts retain no
runtime IDs, and the existing user preview stays available. All twenty-four
workflows remain open; no commit, integration, publication or closure occurred.

## Inline selected-value clear control

Selected autocomplete fields now show an inline right-aligned × button with a
field-specific accessible Clear label. Mouse or keyboard activation clears the
display, canonical ID and dependent selections, hides the buttons and returns
focus to the input. It uses the existing change/reset path without submitting
filters. Input padding reserves the button area; absolute positioning preserves
field and header dimensions. Restored selections also expose the clear control;
empty/unselected fields do not. Detached-rendered labels are resolved from the
field wrapper before mounting, preserving specific accessible names.

A read-only Chromium preview check passed at desktop and narrow widths using
mouse and Enter activation. It verified button placement inside the field,
cleared canonical/dependent state, returned focus, hidden clear controls and
unchanged header dimensions. Applying the cleared form produced an empty query.
No page errors or record mutations occurred. All seven existing JavaScript test
files, frontend formatting, browser-tool lint, composition/import and whitespace
checks passed. The established browser probe now exercises Clear buttons instead
of manual parent-text removal. Broader API/execution evidence above remains for
unchanged behavior and was not rerun for this frontend refinement.

The owning contract, usage, architecture and composition align. No new service,
credential, capture, data reset, backend change, publication or workflow closure
was needed. The existing preview remains running for Definer testing.

## Selected-caption fade

Selected text now fades into an opaque clear-button area. The right-padding
selector has sufficient specificity to retain its 32-pixel inset inside compact
list headers. A pointer-transparent gradient before the button fades the caption;
the button remains opaque, accessible and clickable. Hiding the button also hides
the fade. Canonical values, field dimensions and header geometry are unchanged.

Read-only desktop and narrow Chromium preview checks passed for the computed
inset, gradient, opaque button area, click-to-clear, focus and stable header
height. Two anonymous field-only crops were visually inspected and discarded.
Frontend formatting, composition/import and whitespace checks passed. No data
mutations, backend changes, new services or publication occurred. The owning
contract, usage, architecture and package/composition metadata align. Broader
qualification above was not rerun for this CSS-only refinement.
