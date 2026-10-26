# Graph background pan qualification

- Date: 2026-10-25
- Attribution: Implementer
- Scope: Pipelines 013 background drag panning.
- Delivery: unpublished source preview, awaiting Definer testing.
- Branch: `feature/deletion-and-storage-cleanup`.

## Delivered behavior

The shared graph renderer pans bounded scroll offsets when the primary mouse/pen
pointer drags its background. Content follows screen-space movement at the current
zoom. A small motion threshold and grab/grabbing cursors distinguish the gesture;
pointer capture retains delivery outside the viewport. Release, cancellation,
lost capture, window blur and wheel input end it. Node/control and native-scrollbar
presses are excluded; touch pointers remain delegated to native scrolling. Periodic
Run refresh initiation waits while an active drag is in progress.

## Validation results

| Check | Observed result |
| --- | --- |
| Workspace Chromium probe | Eight grouped journeys passed with background drag checks on pipeline/Run desktop/narrow and focused/All tasks views; no page errors. |
| Gesture checks | Both axes/directions at 100% and 110% zoom, tiny-motion threshold, secondary-button exclusion, origin/maximum bounds, cursor feedback, outside release, pointer cancellation/lost capture, blur and wheel cleanup passed. Releasing a background drag over a node does not select it. |
| Existing workspace checks | Graph DOM/zoom/pan during selection/history/inspector actions, keyboard scrolling, same-scope refresh, in-flight refresh interaction, fixed headers and normal collection layout passed. A held drag delays periodic refresh initiation. |
| Registered scrolling example | Actual 98-task graph accepted trusted mouse and Chromium-emulated pen drags on both axes. Touch pointers were not captured. Trusted node clicks, movement starting on nodes and zoom controls retained their behavior. |
| Web/API regression suite | 45 passed on CPython 3.13; one existing dependency deprecation warning. |
| JavaScript regression suites | All six files passed. |
| Static/specification checks | Frontend formatting, changed-tool Ruff lint/format, composition/import integrity and diff whitespace passed. |

Browser qualification uses Chromium 140 on Linux with 1440-by-1000 and
390-by-844 viewports. Pen coverage uses browser emulation; physical pen devices,
other browser engines and native touch hardware are not additionally qualified.
Custom touch capture remains disabled and touch-action remains native. The
workspace probe uses browser-local long-graph/running-status projections without
changing persisted definitions or executions; the 98-task example is a real
registered definition. No executions were submitted for this change. Backend
storage/provider suites were not repeated for this frontend-only interaction.

## Reproduction and delivery

Use `tools/graph_workspace_browser_smoke.py --url FIXTURE_URL` against the standard
disposable fixture with an existing registered pipeline/Run. The probe selects the
pipeline associated with that Run, so adding the scrolling example does not alter
its fixture assumptions. See [browser qualification](../../../CONTRIBUTING.md#browser-qualification)
and the [scrolling example](../../../examples/scrolling/README.md).

Specifications, composition, usage and current architecture describe the feature.
Application/finalized project versions remain unchanged; earlier wheel receipts
predate these UI refinements. No package rebuild, commit, integration, tags or
publication occurred. The source preview contains the feature for Definer testing;
acceptance and explicit workflow closure remain pending.
