# Element detail layout qualification

- Date: 2026-10-25
- Attribution: Implementer
- Scope: Pipelines 013 non-graph element detail layout.
- Delivery: unpublished source preview, awaiting Definer testing.
- Branch: `feature/deletion-and-storage-cleanup`.

## Delivered behavior

Components, artifacts, tasks/executions, service information and non-graph
pipeline/definition/Run tabs use a compact fixed detail header above the remaining
information area. Header context is bounded separately from bottom tabs. The
main information region is named, focusable and independently scrollable, with
visible keyboard focus. Long JSON/source blocks follow its scroll instead of
having a separate height limit. Embedded lists retain their own pagination/layout.

Component tabs separate overview, interface, executor and compiled source.
Task/execution tabs separate overview, inputs/outputs, logs and complete record;
overview retains attempts, reuse and errors. Artifact Overview/Lineage remain,
with compact identity/status/actions. Tab URLs/history persist context. Same-tab
refresh restores body/header scroll; failed refresh retains the last valid view
with retry. Existing actions and data remain available; graph presentation and
interaction are unchanged.

## Measured results

| Check | Result |
| --- | --- |
| Dedicated detail browser probe | Nine groups passed: components, tasks, attempts, artifacts, definition information, Run information, service information, refresh recovery and fixed execution actions. No page errors. |
| Detail layout/input checks | Fixed context and bottom tabs, independent body scroll, full remaining height, desktop/narrow layouts, long names/records, keyboard scrolling, tab selection/URLs and component Back/Forward passed. |
| Existing browser journey | Fourteen journeys passed on an isolated fixture, including actual Docker execution, upload/version, submission/idempotency, reuse, logs, comparison, artifact pin/lineage/import, failure/cancellation and narrow navigation. No page errors or external requests. |
| Shared list probe | Eleven groups passed, including artifact consumer lineage, Run task results, local paging/truncation, cleanup and all catalogs. No page errors. |
| Graph workspace probe | Eight groups passed, including desktop/narrow panning, selection/history, inspector scroll, zoom/pan retention, scopes, live refresh and non-Graph headers. No page errors. |
| Web/API regression | 45 passed on CPython 3.13, with one existing dependency deprecation warning. |
| JavaScript regression | 34 checks across all six files passed. |
| Static/specification checks | Changed-tool Ruff lint/format, frontend formatting, composition/import integrity and diff whitespace passed. |
| Visual review | Desktop/narrow execution records, scrolled information and compact artifact consumer layouts inspected; temporary screenshots discarded. |

The detail probe projects long component/task/attempt replies inside the browser;
it reads existing records, opens/dismisses the initial deletion dialog and returns
to the selected task graph without planning/applying deletion. Preview resources
and storage files were not changed. Actual mutations/executions ran only on a
separate disposable fixture. The established browser probe now selects Logs on
the execution detail page. Its first full run stopped at post-cancellation
artifact import; response-aware handling now retries only an explicit pre-mutation
idle-execution-owner conflict, and the complete subsequent run passed.

Qualification covers Chromium 140 on Linux at 1440-by-1000 and 390-by-844, plus
the existing journey's narrow viewport. Other browser engines/devices and backend
storage/provider matrices were not newly qualified. Exported receipts retain
neutral results only; runtime identifiers and temporary captures were removed.

## Reproduction and delivery

See [browser qualification](../../../CONTRIBUTING.md#browser-qualification) for
`tools/detail_workspace_browser_smoke.py --url FIXTURE_URL`, fixture prerequisites
and the existing browser/list/graph probes. The [UI guide](../../../docs/ui.md)
describes the detail tabs and scroll behavior.

The owning web contract, local package/composition, usage and current architecture
are aligned. Application and finalized project versions remain unchanged. No
distribution rebuild, commit, integration, tag or publication occurred. The source
preview contains the refinement. All fourteen workflows remain open; Definer
testing, acceptance and explicit closure remain pending.
