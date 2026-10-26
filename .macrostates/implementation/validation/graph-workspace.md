# Graph workspace qualification

- Date: 2026-10-25
- Attribution: Implementer
- Delivery: unpublished source preview, awaiting Definer testing.
- Scope: Pipelines 013 pipeline and Run workspace layout.
- Branch: `feature/deletion-and-storage-cleanup`.

## Delivered behavior

The fixed left navigation and project/service bar surround a viewport-sized
workspace. Pipeline/definition and Run detail screens add a compact resource
header with bottom tabs. Graph contents scroll within the remaining space while
the graph toolbar/hierarchy navigation stay visible. Selected steps open an
independently scrolling right inspector; narrow screens use a dismissible drawer.

Selection-only navigation updates the inspector and selected-node styling on the
existing graph without refetching the page. Inspector tabs, close and history
preserve graph DOM identity, zoom and pan. Closing restores keyboard focus to the
selected graph node without scrolling it into view. Live/explicit refreshes
restore viewport state captured at commit time, retaining interactions during
in-flight requests. Canvas bounds preserve far-right pan when closing the panel
widens the viewport. Changed definition identities/scopes initialize new views.
ARIA boolean attributes now expose true/false states correctly.

## Validation

| Check | Observed result |
| --- | --- |
| Web/API regression suite, CPython 3.13 | 45 passed; one existing dependency deprecation warning. |
| JavaScript suites | All six files passed, including query identity and scope/version navigation checks. |
| Existing Chromium journey, separate fixture and real Docker executions | 14 journeys passed; no page errors or external requests. Covers uploads/versions, submission/idempotency, completion, reuse, task/attempt/log navigation, cancellation/failure, artifact operations and normal collections. |
| Workspace Chromium probe | Eight grouped journeys passed: pipeline/Run desktop/narrow layouts, fixed headers, full available height, long graphs, independent inspector scrolling, graph DOM identity, selection/history, inspector tabs/close, keyboard pan, scope navigation, explicit/live refresh and non-Graph tabs. |
| Refresh and resize edge cases | Pan/zoom during a held refresh is retained at completion; far-right pan survives inspector close. |
| Additional manual browser assertions | Wide screens use all available width; switching immutable pipeline versions resets zoom; inspector tab and close actions retain appropriate keyboard focus; mobile project/service controls do not overlap. |
| Visual review | Desktop and narrow workspace layouts and inspector presentation inspected. Temporary screenshots discarded. |
| Static checks | Ruff lint/format, Pyright, frontend formatting, composition/import integrity and diff whitespace passed. |

Browser qualification uses Chromium 140 on Linux. Desktop/narrow probes use
1440-by-1000 and 390-by-844 viewports, with additional 1920-by-1080 width checks.
The workspace probe performs read-only API requests; long/nested graphs and a
running status are browser-local projections. Actual execution, lifecycle and
mutation coverage comes from the separate end-to-end fixture. Neither establishes
additional operating-system/browser qualification. Storage/provider suites were
not repeated for this browser-only implementation change.

The reusable [scrolling example](../../../examples/scrolling/README.md) supplies
98 actual compiled tasks: eight branches of twelve steps, plus start/finish.
The service accepted it and registered it in the disposable preview for manual
testing. At 100% zoom Chromium measured 2254-by-2464 graph contents within a
1216-by-743 viewport. Both scroll directions, mounted graph/pan preservation
during selection/inspector close, and absence of browser errors were verified.
The component program's integer output was checked locally; no Run was submitted.
Its source, compiled definition and documentation are retained; its temporary
masked screenshot was inspected and discarded. Example lint/format and diff
checks passed. This is actual registered IR, separate from the browser-local
response projections used by the earlier stress probe.

The subsequent compact-toolbar correction removes the standalone Pipeline row at
the root and in All tasks; useful nested breadcrumbs share the existing graph
toolbar. Desktop/narrow pipeline and Run checks confirm that the toolbar sits
directly above the canvas with no extra location row or overflow. All eight
workspace journeys and six JavaScript files passed after the correction,
including nested return navigation, pan/zoom and selection/refresh stability.
Frontend formatting, composition/import and diff checks passed. A graph-only
screenshot was visually inspected and discarded. This presentation correction
preserves the effective navigation contract and does not change package versions.

## Reproduction and delivery

During subsequent authorized manual testing, the disposable preview was reset and
both examples were executed afresh with reuse disabled. The cleanup Run completed
two new attempts and the scrolling Run completed 98 new attempts; all tasks and
attempts succeeded with exit status zero. Expected scalar results are 21 and 14,
respectively. Four sample artifact records, including manual/pinned fixtures,
and the orphan file were restored. Metadata/content checks and readiness passed;
Chromium confirmed the fresh 98-task Run graph scrolls on both axes. The same
preview port is retained with new project/resource identities. Non-fixture data
was untouched, no raw operational logs were retained, and no publication occurred.

See [browser qualification](../../../CONTRIBUTING.md#browser-qualification) and
the [UI guide](../../../docs/ui.md). The dedicated regression probe is
`tools/graph_workspace_browser_smoke.py --url FIXTURE_URL`; it requires a
disposable fixture with a pipeline and Run. The existing browser journey's
sanitized receipt is `tmp/graph-workspace-browser-checks/result.json`; runtime
identifiers were removed and screenshots discarded. Retain no raw exported logs.

The local source preview contains the changes. Earlier package receipts predate
these UI refinements; no new distribution build is claimed. Application versions
and finalized project baselines remain unchanged. The local Pipelines contract
and composition include the additive workspace requirement. The prior deletion
and orientation deliveries remain separately tracked. No commit, integration,
tag or publication occurred; explicit Definer testing, acceptance and workflow
closure remain pending.
