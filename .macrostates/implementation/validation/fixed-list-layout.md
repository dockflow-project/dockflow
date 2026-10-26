# Fixed list layout qualification

- Date: 2026-10-25
- Attribution: Implementer
- Scope: Pipelines 013 record-list workspace and 015 cleanup placement.
- Delivery: unpublished source preview, awaiting Definer testing.
- Branch: `feature/deletion-and-storage-cleanup`.

## Delivered behavior

Catalog lists, experiment Runs, artifact consumers, Run task results, comparisons
and cleanup files fill the selected workspace. Top context/filter/actions and
bottom pagination/counts stay in place around one scrolling list region. Column
headings stick to that region and scroll horizontally with their cells. The list
is named and keyboard-focusable with a visible focus outline. Empty results keep
headings/footer and show their explanation within the visible narrow area.

Server lists retain their existing cursors and per-page counts. Already-loaded
task results and comparison fields page locally, explicitly labeling loaded counts
and truncation. Filter/page changes reset row scroll. Same-query refresh retains
row position and local page; failed refresh keeps the last valid list with retry.
Cleanup byte estimates remain in the fixed footer; job/retention tools open from
top actions and secondary options collapse on narrow screens. Eligibility,
selection expansion and deletion confirmation contracts are unchanged.

## Measured results

| Check | Result |
| --- | --- |
| Dedicated list browser probe | Eleven grouped checks passed: six catalogs, experiment Runs, artifact consumers, local result/comparison pagination, bounded truncation and cleanup. No page errors. |
| Layout/input assertions | Desktop/narrow fixed regions, sticky headings, vertical/horizontal overflow, keyboard scrolling, cursor boundaries, filter resets, refresh position, empty states, stale-view recovery and disabled controls passed. |
| Actual server cursors | Components and Executions traversed real pages with Next/Previous, distinct rows and reset scroll. |
| Actual Run results | The existing 98-task Run paged loaded task results; explicit refresh preserved its second page and scroll. Comparison fields paged locally. |
| Existing browser journeys | Fourteen journeys passed on a separate fixture with actual Docker execution, upload/version, idempotency, reuse, task/log navigation, failure/cancellation, artifact operations and comparison. No page errors or external requests. |
| Graph workspace probe | Eight grouped journeys passed, covering background panning, selection/history, independent inspector scroll, zoom/pan retention, scopes, live refresh and fixed headers. No page errors. |
| Cleanup browser probe | Six journeys passed on a separate fresh fixture: orphan exclusion, exact DANGER, pin blockers, explicit manual-artifact deletion, execution/Run deletion and desktop/narrow inventory. No page errors. |
| Web/API regression | 45 tests passed on CPython 3.13, with one existing dependency deprecation warning. |
| JavaScript regression | All 34 checks across six test files passed. |
| Static/specification checks | Changed-tool Ruff lint/format, frontend formatting, composition/import integrity and diff whitespace passed. |
| Visual review | Desktop/narrow catalog, task results, lineage empty state and cleanup layouts inspected; temporary screenshots discarded. |

The list probe uses browser-local cursor pages, consumer rows, bounded task replies
and cleanup inventory to exercise long/empty/error views without modifying the
preview. Real cursor and 98-task checks read existing records. Mutation/execution
journeys ran only against separate disposable fixtures. Cleanup qualification
initially encountered the interval between terminal Run outcome and scheduler
owner release; the probe now retries only that explicit idle-owner planning
conflict, never an apply operation. A subsequent complete run passed.

Qualification covers Chromium 140 on Linux at 1440-by-1000 and 390-by-844. It does
not establish other browser/device qualification or repeat backend storage/provider
suites. The preview's example records and files were not reset or deleted.
Exported browser receipts retain neutral results only; runtime identifiers and
temporary screenshots were removed.

## Reproduction and delivery

See [browser qualification](../../../CONTRIBUTING.md#browser-qualification) for
`tools/list_workspace_browser_smoke.py --url FIXTURE_URL`, fixture prerequisites
and the established browser/graph probes. Cleanup mutation checks use
`tools/cleanup_browser_smoke.py` against a fresh `--cleanup` fixture. The
[UI guide](../../../docs/ui.md) and [cleanup guide](../../../docs/cleanup.md)
describe the controls.

The local Pipelines package/composition include the list contract. Application
versions and finalized project baselines remain unchanged. No package rebuild,
commit, integration, tag or publication occurred. Earlier deliveries remain
separately open; Definer testing, acceptance and explicit closure are pending.
