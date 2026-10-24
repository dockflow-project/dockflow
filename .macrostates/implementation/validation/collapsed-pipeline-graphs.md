# Collapsed pipeline graph qualification

Date: 2026-10-22. Scope: unreleased Pipelines browser presentation on the
`feat/collapsed-pipeline-graphs` working tree, starting from
`032444d3686f5951cb0b2457e64a023ded502387`. This is implementation evidence against
the existing nested-graph contract, not a new accepted baseline or release.

## Local regression checks

- `node --test packages/pipelines/tests/web/*.test.mjs`: all five test files pass.
- `node packages/pipelines/tests/web/graph.test.mjs`: all 11 projection tests pass,
  including five added cases for collapsed levels, repeated nested invocations,
  deep links, complete hierarchy inspection and multi-level breadcrumbs.
- `pytest -q packages/pipelines/tests/test_web.py`: 45 pass using the locked
  development environment with local thread/socket support. The existing
  Starlette TestClient deprecation warning remains.
- `macrostates check`: passes composition and imported-package checks.

No executor, API schema, artifact store or persisted record format changed.

## Real browser checks

Chromium through Playwright 1.55.0 exercised a disposable, non-executing service
with a generic two-level nested definition. Its queued Run allowed observation
of the normal active-view polling. Ten checks passed:

1. The root collapses its hierarchy; an HTML-shaped display name remains text.
2. Keyboard activation opens the exact native subpipeline path.
3. Two-level breadcrumbs, Back/Forward and reload preserve scope.
4. All tasks includes containment edges; Grouped view restores the prior level.
5. A task-only deep link opens its parent and selects its qualified task path.
6. An invalid graph path explains its fallback to the pipeline level.
7. Active-Run refresh retains graph scope and selection.
8. Group controls remain usable at a 390-pixel viewport width.
9. A synthetic 1,005-child group displays 1,000 nodes, an accurate visible count,
   and an explicit truncation notice after opening; its root remains one node.
10. No JavaScript errors or external requests occurred.

The large synthetic graph exercised the shipped renderer directly in the
browser; it was not submitted as an execution qualification. Disposable state
and screenshots are scratch evidence and are not retained in the source tree.

## Consuming pipeline qualification

A separately owned, filesystem-backed integration with 22 logical computations
was rebuilt against local development source. Its native KFP IR has
24 root tasks and 90 tasks across all levels. The browser confirms 24 initial
nodes, two children when a logical step opens, and a separately inspectable
registration importer below that. Typed Model/Dataset outputs remain declared.

The consuming project's structural tests pass (12 tests), and its component,
service and executor images pass the existing offline CA trust checks. A real
synthetic-data Run through the API succeeded: all 90 task records succeeded,
with 22 actual container attempts and typed Model/Dataset root outputs. Nested
graphs and registration importers do not fabricate additional container attempts.
An identical Run through the direct local CLI then succeeded against the same
repository-backed state and executor. All 22 computations were reused with zero
new container attempts; the remaining 68 nested/importer task records succeeded.
Both root artifact IDs and their publication paths were retained. The API owner
was stopped before local execution, preserving the existing single-owner rule.

The final generic service image was rebuilt from development source and passed
the consumer's offline CA checks: Python 3.13.17, certifi 2026.10.19, gRPC 1.84.1,
plus vendored SDK, interpreter pip, ensurepip and system stores. The API was then
restarted and left running with the current configured definition.

Five additional read-only Chromium checks passed on the completed and reused
Runs: nested task attempts/logs remain accessible, output URI inspection works,
the real graph toggles between 24 and 90 nodes, reused computations link to the
original producer without a new attempt, and no JavaScript errors occur.
The API reports both typed outputs available at their original content URIs.
The served `graph.js` bytes exactly match the final working-tree asset:
SHA-256 `e22124635fff790844a667d710443f3bd3de21c187a2f00a21261e62de204a9c`.

## Limits

Qualification covers Linux, Chromium and the supported native nested KFP IR
profile. A Kubernetes/KFP frontend deployment was not started. Other browsers,
native desktop platforms and new execution features are not claimed. Collapsing
does not infer logical groups from flat definitions; authors supply native
subpipelines. Historical definitions retain their original grouping.
