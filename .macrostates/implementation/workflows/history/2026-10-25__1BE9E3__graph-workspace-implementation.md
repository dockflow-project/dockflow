# Graph workspace implementation

- Project phase: `active`
- Workflow type: `Implementation update`
- Status: completed
- Delivery state: accepted
- Change depth: `medium`
- Branch: `feature/deletion-and-storage-cleanup`
- Requested by: Definer
- Implementer: Implementer
- Started at: 2026-10-25 12:39 (UTC)
- Last updated at: 2026-10-26 12:06 (UTC)

## Objective and scope

Implement the companion [graph workspace contract](2026-10-25__1BE9E3__graph-workspace-specification.md):
fixed shell/resource headers, compact contextual controls and bottom tabs,
viewport-filling graph, independent right inspector scrolling, and in-place
selection that retains zoom/pan. Preserve route/history, task details, live
updates, all existing resource actions and authentication boundaries. Qualify
desktop/narrow layouts against disposable data without changing existing projects.

## Authorization and impact

The four prior deletion/orientation workflows remain awaiting acceptance; this
objective has separate tracking. The existing development branch remains
authorized. No publication, integration, tagging or closure is authorized.
Track implementation Minor impact and keep application/finalized baseline versions
unchanged. Export only anonymized evidence and portable paths.

## Acceptance and next step

Verify fixed navigation/headers, full graph bounds and independent scroll regions;
selection DOM identity/zoom/pan across task switches, detail tabs and history;
scope/version navigation, live refresh, close controls, narrow layout and normal
non-detail screens. Run relevant frontend suites and browser journeys, update
usage/current architecture and record measured qualification. Explicit acceptance
and closure remain pending after local unpublished delivery.

## Delivered work and evidence

The Definer explicitly authorized resetting the disposable example data and
rerunning it. Recreate only `tmp/deletion-user-test`, restore both example
pipelines and cleanup fixtures, and execute fresh Runs with reuse disabled,
including the 98-step scrolling example. This continues manual workspace testing;
the earlier no-execution boundary is superseded for this requested reset/rerun.
Keep the preview endpoint stable and verify terminal results before delivery.
Existing non-fixture projects, source changes and publication remain outside scope.
The verified fixture service was stopped and only its disposable directory was
reset, then recreated on the same port. Both pipelines were restored. The cleanup
Run completed two tasks and the scrolling Run completed 98 tasks, each with one
new successful attempt, exit status zero and no reuse. The cleanup result is 21;
the scrolling Finish result is 14. Four artifact records, the manual database,
pinned dataset and orphan file are restored. Metadata content checks pass and
the service is ready. Chromium verified the new 98-task Run graph and both scroll
directions. The preview remains running for manual testing; deep-link identities
were regenerated. No non-fixture project or source implementation was changed,
and no commit, integration or publication occurred. Acceptance remains pending.

Removing the redundant standalone graph-location row continues the original
compact workspace/available-space objective. Omit the root Pipeline breadcrumb
and fold meaningful nested-scope breadcrumbs into the existing toolbar. Preserve
subpipeline return navigation, graph controls and all viewport interactions.
The existing graph contract requires navigation but no separate breadcrumb row;
this is a presentation correction without a specification/package version change.
The other nine open workflows remain awaiting acceptance.
The redundant root row is removed in pipeline/Run and All tasks views; nested
breadcrumbs share the existing toolbar. Chromium verified root toolbars directly
above the canvas on desktop/narrow screens, and all eight grouped workspace
journeys passed, including nested return navigation, selection, drag/zoom,
keyboard scrolling and refresh. All six JavaScript suites, frontend formatting,
composition/import checks and diff checks passed. The graph screenshot was
visually inspected and discarded. Usage/current architecture are aligned; the
source preview contains the refinement. No specification baseline, local package
version, application version, publication or acceptance state was advanced.

The manual-scrolling validation request continues this workspace objective:
provide a reproducible 98-task compiled example and register it in the existing
disposable preview. Eight parallel branches of twelve steps plus start/finish
exercise both scroll directions. Validate accepted IR and actual browser scroll
dimensions/selection. Registration is authorized; automatic execution, publication
and workflow closure are not part of this refinement.
The compiler source, compiled IR and usage guide live under `examples/scrolling/`.
The real service accepted all 98 tasks and the requested preview registration.
Chromium confirmed a 2254-by-2464 content area in a 1216-by-743 graph viewport,
scrolling in both directions, stable mounted graph/pan on selection and close,
and no page errors. The step program's integer output was verified locally;
Ruff and diff checks passed. The example was not submitted for execution.
Screenshots were inspected and discarded. Definer testing remains pending.

The viewport workspace, compact resource headers, independent inspector and
in-place selection are implemented. Focus is restored after inspector tab/close
actions; same-scope refresh retains pan/zoom, including interactions during
requests and far-right pan after inspector close. Shared DOM helpers expose ARIA
booleans correctly. Usage, current architecture and browser reproduction guidance
are updated. The existing browser probe follows the compact status location.

[Qualification](../../validation/graph-workspace.md) records 45 web/API tests, six
JavaScript files, 14 existing real-execution browser journeys, eight workspace
journeys, visual/keyboard checks and passing static/composition checks. The source
preview remains available for Definer testing. No existing project data changed;
the separate regression fixture was disposable. No new wheel, commit, tag,
integration or publication is claimed. Next step: Definer acceptance and explicit
closure, which remain pending alongside the four previous workflows.

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
