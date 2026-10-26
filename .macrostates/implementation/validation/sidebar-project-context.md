# Sidebar project context validation

## Scope and delivery

The plain project name sits beneath the Dockflow brand without a visible label
or colored box. Readiness and Connect/Sign out sit at the very bottom of the fixed sidebar
footer, below a divider and the utility links/runtime text. Another divider sits
above the utilities. The global top bar is removed, giving selected
screens the full viewport height. Grouped navigation scrolls independently while
the brand, context and footer remain reachable. Long project identifiers wrap,
provide a complete tooltip and support bounded keyboard scrolling.

The owning [web contract](../../specs/053_dockflow-pipelines/013_web-interface.md),
usage guide and current architecture align. Specification and implementation
impact are Minor presentation refinements; API, routes and authentication
semantics remain unchanged. Application and finalized baseline versions remain
unchanged. This is an unpublished source preview awaiting Definer testing and
explicit acceptance; the twenty earlier workflows remain independently open.

## Measured results

| Check | Result |
| --- | --- |
| Web backend | 45 tests passed, with one existing Starlette dependency warning. |
| JavaScript | 38 checks passed across seven files. |
| Sidebar browser qualification | Four authenticated groups and three unauthenticated groups passed: context location, full-height list geometry, long project identifiers, keyboard access, independent menu scrolling, unavailable/recovered readiness, and sign-out/reconnection. |
| Existing browser journey | Fifteen authenticated groups passed, including actual Docker execution, pipeline/version upload, idempotency, reuse, logs, comparison, artifact pin/import/lineage, failure/cancellation, narrow navigation, API explorer and memory-only sign-out. No page errors or external requests. |
| Graph workspace | Eight authenticated groups passed, covering full-height header/viewport geometry, graph scope, inspector selection, unchanged graph/zoom/position, scrolling, panning, keyboard interaction, history and refresh. The probe permits the bounded read-only name lookup while still rejecting graph/page refetch on selection. |
| Artifact Contents | Six authenticated groups passed for CSV, JSON, image, directory and text previews, including fixed detail regions and narrow layouts. |
| Visual review | Desktop 1440-by-1000, narrow 390-by-844 and short 390-by-500 captures inspected and discarded. Context controls and independently scrolling navigation remained usable; the main area starts at the viewport top. |
| Static/reference/specification | Ruff lint/format, frontend formatting, generated API reference, composition/import integrity and whitespace checks passed. |
| Existing preview | Read-only qualification passed without restarting or resetting data. Both successful Runs and all ten artifacts remain present. |

Chromium 140 on Linux supplied browser evidence. Long project identifiers and
unavailable readiness are browser-local projections; they do not alter stored
records. Dedicated sidebar checks only read service data and change browser
authentication state. Actual execution qualification used a separate disposable
fixture. No new storage-provider, database-provider, platform or load qualification
is claimed for this shell presentation change.

## Reproduction and disposition

See [browser qualification](../../../CONTRIBUTING.md#browser-qualification) for
`tools/sidebar_context_browser_smoke.py` and optional bearer authentication.
`tools/graph_workspace_browser_smoke.py` also accepts a token file. Existing
Contents and general browser probes exercise the relocated controls without
changing their authentication hooks. Anonymous receipts retain check descriptions
only; reviewed captures and the disposable credential were removed, and the QA
service stopped. The existing preview remains running.

No distribution rebuild, commit, integration, tag or publication occurred.
Twenty-two workflows remain open for independent testing and explicit acceptance.

## Sidebar distribution refinement

The same shell objective now separates plain project identity beneath the logo
from readiness/connection controls above API documentation in the fixed footer.
The owning contract, usage, architecture and package/composition metadata align.
Seven targeted browser groups passed after redistribution: three unauthenticated
on the existing preview and four on an isolated authenticated fixture. Checks
cover exact placement, absence of the label/box, full-height lists, long project
identifiers, independent menu scrolling, readiness recovery and sign-out/connect.
No page errors occurred. Desktop, narrow and short captures were inspected and
discarded; formatting, lint, composition/import and whitespace checks passed.
Earlier broader regression results above apply to unchanged application behavior
and were not rerun for this HTML/CSS refinement. The preview data remains intact;
only the disposable fixture and its credential were removed. Delivery remains
unpublished and awaits Definer acceptance.

## Bottom-aligned status and connection controls

The sidebar footer now contains an upper divider, utility links/runtime text,
a second divider, then service status and Connect/Sign out at the very bottom.
The same DOM IDs and authentication handlers are retained. Both groups stay
fixed while navigation scrolls independently; narrow layouts stack the bottom
controls within the existing icon sidebar.

Three read-only Chromium browser groups passed on the existing preview: exact
footer order, both divider borders, viewport-bottom alignment, full-height list
geometry, long project identity, desktop/narrow/short navigation access and
unavailable/recovered readiness. No page errors occurred. Desktop and short/narrow
footer-only captures were visually inspected and discarded. Frontend formatting,
browser-tool lint/format, composition/import integrity and whitespace checks
passed. Earlier authenticated/backend/graph checks above cover unchanged
behavior and were not rerun for this HTML/CSS relocation.

The owning contract, usage, architecture and composition align. This further
presentation refinement has Minor specification/implementation impact. No
backend changes, data mutations, service restart, credentials, publication or
workflow closure occurred. The user preview remains available; all twenty-four
current workflows remain independently open for explicit acceptance.
