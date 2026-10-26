# Fixed list layout implementation

- Project phase: `active`
- Workflow type: `Implementation update`
- Status: completed
- Delivery state: accepted
- Change depth: `medium`
- Branch: `feature/deletion-and-storage-cleanup`
- Requested by: Definer
- Implementer: Implementer
- Started at: 2026-10-25 19:11 (UTC)
- Last updated at: 2026-10-26 12:06 (UTC)

## Objective and scope

Implement the companion [list layout contract](2026-10-25__21WH81__fixed-list-layout-specification.md)
through shared layout/pagination helpers. Cover all catalog lists and record-table
views, including cleanup inventory, with fixed top/bottom regions and a single
scrolling table region with sticky headings. Preserve filters/actions, cursors,
selection protections, graph workspace and existing content; keep bounded local
paging honest about loaded/truncated data. Make auxiliary cleanup tools accessible
without placing them below the table. Qualify desktop/narrow, overflow, keyboard,
pagination and empty states against disposable fixtures.

## Authorization and acceptance

The ten prior deliveries remain separately open and awaiting acceptance. Continue
on the authorized branch without integration, publication, tags or closure.
Track implementation Minor impact and preserve finalized/application versions.
Do not modify the current preview's example records during validation; use
read-only browser projections or separate disposable fixtures for mutation tests.
Update usage/current architecture and measured evidence. Explicit Definer testing
and closure remain pending after local unpublished delivery.

## Delivered implementation and qualification

Shared DOM/CSS helpers implement the fixed title/filter/action region, single
scrolling table region with sticky headings and fixed pagination/count footer.
Catalogs, experiment Runs, artifact consumer lineage, Run task results,
comparisons and cleanup use the layout. Server cursors remain intact; bounded
local tables label loaded/truncated counts. Refresh preserves row position/local
page and keeps the last valid list on failure. Empty states and keyboard focus
remain visible on narrow screens. Cleanup estimates stay in the footer, with
job/retention dialogs and collapsible options above the table.

The [qualification receipt](../../validation/fixed-list-layout.md) records eleven
list browser groups, real cursor checks and the actual 98-task result table;
14 existing browser journeys, eight graph workspace groups, six cleanup journeys,
45 web/API tests and 34 JavaScript checks passed. Changed-tool lint/format,
frontend formatting, composition/import and whitespace checks passed. Visual
desktop/narrow captures were inspected and discarded. A cleanup test now retries
only an explicit idle-owner planning conflict after a Run finishes.

Browser qualification is Chromium on Linux; other engines/devices and backend
provider matrices were not newly qualified. Mutations and new Docker executions
ran only on separate disposable fixtures. The current preview data remains
intact and the source preview contains this refinement. No distribution rebuild,
commit, integration, tag or publication occurred. All twelve workflows remain
open, with delivery awaiting Definer testing and explicit acceptance/closure.

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
