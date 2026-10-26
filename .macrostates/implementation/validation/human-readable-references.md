# Human-readable resource reference validation

## Scope and delivery

The unpublished development working tree implements the
[web reference contract](../../specs/053_dockflow-pipelines/013_web-interface.md#human-readable-resource-references).
Execution/Task references resolve component names; Run references resolve compiled
pipeline names; pipeline/version and experiment references resolve their names.
Invocation labels and exact IDs/targets/values remain available. Names decorate
references in place rather than changing resource records or rebuilding graphs.

The additive specification and implementation have Minor impact. Application and
finalized project versions remain unchanged. Testing is implementation evidence;
Definer acceptance, workflow closure, integration and publication remain separate.

## Measured results

| Check | Result |
| --- | --- |
| Backend/native API regressions | 245 passed, 30 optional backend cases skipped and three existing dependency warnings. Includes reference-name, interface, web, KFP registration, Contents, deletion and upload suites. |
| Reference API coverage | 17 cases passed: actual component/pipeline/experiment context distinct from invocation names; direct dependency/request deduplication without catalog scans; unavailable/retired context isolation; strict count/field/ID schema; auth/Origin/query rules; read availability during execution; unchanged authoritative state; no-store response and generated models. Retired context is simulated at the shared record accessor; existing deletion regressions also pass. |
| JavaScript | 38 checks passed across seven files, including exact identity parsing, existing label/ID preservation, no duplicated names/adjacent IDs, unavailable context and markup-shaped text. |
| Dedicated browser probe | Eight groups passed on unauthenticated and bearer-authenticated disposable fixtures. Actual Docker execution/reuse supplied records for list/detail/header/attempt/deletion, graph inspector, artifact producer/consumer, comparison, catalog/version, experiment and selector references. Original invocation labels and exact ID values/targets/titles remained intact. |
| Browser failure/state boundaries | Lookup 503 retained usable screens and refresh recovered names. More than 200 projected references used separate bounded/deduplicated requests. Delayed replies did not overwrite navigation/sign-out context; authenticated sign-out cleared name state. Graph DOM identity, zoom and viewport survived inspector/name changes. Markup-shaped experiment names stayed inert text. |
| Established browser journey | Fourteen groups passed with actual Docker execution, compiled/version uploads, idempotent Run submission, reuse/logs/comparison, artifact pin/import/lineage, failure/cancellation, keyboard/narrow navigation and API explorer. The original-producer locator now accepts the added name/ID caption. |
| Visual/final preview | Anonymous desktop execution-table and narrow detail captures inspected, then discarded. The user preview restarted on its existing configuration/data; both successful Runs and all ten artifacts remained. Native name lookup and actual execution-row component/pipeline/Task context passed without submitting data. |
| Static/reference/specification | Ruff lint/format, Pyright, frontend formatting, generated API reference, Macrostates composition/import and whitespace checks passed. Package verification's asset inventory includes the new module. |

Browser qualification used Chromium 140 on Linux at 1440-by-1000 and 390-by-844.
No new PostgreSQL, S3/SeaweedFS, additional browser/platform or maximum-load
qualification is claimed. Name resolution uses existing SQL resource scope/read
snapshots, not payload storage. The browser's extra-batch references are local
DOM projections of valid but absent IDs; they do not create backend records.
Actual execution/reuse coverage is distinct from those projections.

## Architecture and reproduction

`reference_names.py` resolves a bounded requested set and cached direct
dependencies inside a read snapshot, failing closed for retired context. The
read-only native endpoint is independent of list filters/cursors and remains
available during execution. It exposes only names and availability, not additional
resource payloads. Generated API schemas define request/response contracts.

`references.js` observes reference links, explicit ID labels and selector/filter
values under the workspace and open dialogs. It deduplicates/chunks requests,
updates text/title or an accessible field hint, and keeps exact targets/values.
Epoch checks prevent stale updates; navigation refreshes the name cache and
sign-out clears name state and retained non-authentication dialog contents.
Existing graph nodes, list pagination and scrolling remain owned by their views.
Raw source/records and artifact payload previews are not decorated.

See [browser qualification](../../../CONTRIBUTING.md#browser-qualification) for
`tools/reference_names_browser_smoke.py`, optional bearer authentication and
disposable fixture setup. The probe registers a catalog/experiment and two Runs
using a unique reuse key. It never resets/deletes data. Optional captures project
anonymous visible text in the browser only, preserving stored state/URLs/values;
captures are discarded after review and neutral receipts contain no runtime IDs.

Usage, current architecture, generated reference and specifications/composition
align. QA services/credentials were removed; the existing user preview remains
running. No distribution rebuild, commit, integration, tag or publication occurred.
Twenty workflows remain independently open for Definer testing and explicit
acceptance/closure.

## Name-first display refinement

The shared formatter now puts names before IDs and preserves invocation/attempt
labels between them. Execution headings participate in the same decoration;
editable ID fields show their name hint above the field without altering values.
The ordering requirement is explicit in the owning web contract and usage guide.

All seven JavaScript test files passed after updating ordering assertions;
frontend formatting, composition/import and whitespace checks passed. A read-only
browser check on the existing preview verified every named execution-list
reference had its name before its visible ID, the execution heading led with its
component name, and the selected definition's name hint preceded its unchanged
ID input. No page errors, data mutations, new services, captures or publication
occurred. Earlier broader checks above remain separate evidence for unchanged
API/storage behavior; they were not rerun for this presentation-only refinement.
