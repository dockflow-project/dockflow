# Scrolling example

This static KFP pipeline has **98 steps**: Start, eight parallel branches with
twelve steps each, and Finish. At 100% zoom its graph is wider and taller than a
typical viewport. Each executable step increments an integer and writes a small
parameter result using `python:3.13-slim`; it needs no component Python packages.

Upload [pipeline.yaml](pipeline.yaml) through **Pipelines → Upload pipeline** and
name it **Scrolling example — 98 steps**. The graph is immediately available.
Drag the empty graph background with the primary mouse button, or use its
scrollbars/trackpad in both directions. Select a step to open
the inspector, and switch selections to verify zoom and position remain stable.
Use **Zoom out** or **Reset** to compare views.

Execution is optional. To inspect scrolling on a Run graph, create a Run after
making `python:3.13-slim` available to the service's Docker engine. Dockflow executes
ready tasks serially, including these independent branches; completing all
98 containers can take several minutes. This example does not require execution
to inspect its pipeline graph. The sample image tag is for local demonstration;
use a verified immutable image reference for deployment.

To regenerate the compiled definition from the repository root:

```bash
uv run --all-packages --all-extras python examples/scrolling/pipeline.py
```

Dockflow consumes the compiled file; it does not run this compiler script.
