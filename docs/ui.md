# Browser interface

[Documentation index](README.md) · Prerequisite: a running [service](deployment.md)

Open `http://127.0.0.1:8080/ui/` after starting Dockflow. The service root redirects
there. The interface is included in the service package and uses the same API,
history and permissions as the CLI. No frontend build service or CDN is needed.
JavaScript is required; the CLI/API remain available without a browser.

The project name appears directly beneath the Dockflow logo as plain text.
Service readiness and **Connect/Sign out** sit at the very bottom of the left
sidebar. A divider separates them from the documentation links and runtime text
above, with another divider above that group. The selected screen uses the full height;
there is no global top bar. On short screens the menu scrolls while these controls
remain available. For a token-enabled
service, choose **Connect** and enter its bearer token. The page keeps it in
memory, not browser storage; **Sign out**, reload or leaving the page clears it.
The API reference is a separate page and may need its own connection.

## Navigation

Resource references show names alongside IDs throughout lists, details, graph
inspectors, lineage, comparisons, selectors and deletion dialogs. Executions and
tasks show their component name; Runs show the pipeline name while retaining their
invocation label; pipeline/version and experiment references show their own names.
The name appears first, followed by any invocation/attempt label and then the ID.
Filter fields show the selected name then ID inside the field without adding
header height; they submit the exact ID. Other editable ID fields retain name hints.
Shortened IDs have the complete ID in the link destination or tooltip. Identical
names remain distinguishable by ID, and selectors keep their original ID values.
If a name cannot be resolved, the ID remains visible with **Name unavailable**;
refresh can retry the lookup. Raw records, source and artifact contents stay intact.

| Section | Menu | What you can do |
| --- | --- | --- |
| Definitions | **Pipelines** | Browse catalog entries, select versions, inspect graphs/source, upload compiled definitions and create Runs. |
| Definitions | **Components** | Inspect embedded component interfaces and executor images/commands. |
| Workloads | **Experiments** | Create named groups, inspect their Runs and compare results. |
| Workloads | **Runs** | Filter history, create/clone Runs, inspect steps/results/logs, cancel active work and compare 2–5 Runs. |
| Workloads | **Executions** | Browse actual task attempts, including retries, and inspect their logs and image/result details. |
| Storage | **Artifacts** | Inspect datasets/models/results, register/import external sources, pin artifacts and follow lineage. |
| Storage | **Cleanup** | Open Storage cleanup to classify files, inspect byte estimates and review deletions. |

Section labels remain visible on the narrow icon sidebar; each icon retains its
accessible name and tooltip. **API documentation** and **Service information**
remain in the footer for the live API reference and project/runtime details.

Lists expose relevant filters, **Apply filters**, **Clear**, **Refresh** and
**Previous/Next** pagination. A list shows one page rather than all historical
records. Resource IDs, tabs and graph selections appear in navigation links,
so a detail page can be bookmarked or shared with another authorized client.

Click a search field to see up to ten recent options, even before typing. Search
by name or ID; suggestions show names before exact IDs. Definitions/components
use their registration date, and Runs/executions use their start time (creation
time while not started). Choose an option with the mouse or Up/Down and Enter,
then choose **Apply filters**. Escape dismisses suggestions. Primary **Search**
also accepts partial names/IDs directly; related-resource filters select exact
IDs. The Cleanup **Artifact** filter also searches by name/ID. **Type** suggests
recent artifact types and keeps exact type filtering.
Selected fields have an **×** button inside their right edge; long text fades
before that button so it stays clear. Use it to clear
that field and its dependent selections, then choose **Apply filters** when ready.
When more than ten matches exist, the footer says **...and N more** with the exact
remaining count. Components show **Pipeline ID** before **Component ID** and limit
component options to that pipeline. Runs show **Search**, **Experiment ID**,
**Pipeline ID**, then **State**; the pipeline choices come from Runs in the chosen
experiment. Executions show **Search**, **Run ID**, **Task ID**, then **State**;
the task choices belong to the chosen Run. Changing a parent clears its dependent
selection. State always offers every valid state. Text fields and selects have
matching heights. **Pipeline ID** labels the immutable definition/version ID in
these filters; API fields and links keep their existing identities.

List screens keep their title, filters and actions above the rows, with pagination
and counts fixed at the bottom. Scroll within the list; column headings stay at
its top and move with their columns when scrolling horizontally. Focus the list
to scroll with the keyboard. This also applies to experiment Runs, artifact
consumers, Run task results, comparisons and cleanup files. On narrow screens the
top controls wrap or scroll within their section; cleanup options can collapse.
Resource tabs remain above embedded lists.

Catalog counts describe the current server page and indicate when more records
exist. Task results and comparison fields page through already loaded rows and
label loaded counts and any truncated subset. Changing filters/pages returns to
the top of the list. Refreshing the same query preserves row position and local
page; a failed refresh keeps the last displayed data with an error and **Try again**.

Element detail screens keep a compact identity/status/action header above their
information area. Tabs, where present, stay at the bottom of that header. Scroll
the remaining area to inspect the record; navigation and its project/service context
stay visible. Long JSON/source blocks scroll with that information area. Focus
the area for keyboard scrolling. Refreshing the same element and tab keeps its
position; changing tabs starts at the top. Tabs are retained in bookmarkable URLs
and browser history. Long header context/actions have their own bounded overflow
on narrow screens.

Components use **Overview**, **Interface**, **Executor** and **Source** tabs.
Task and execution details use **Overview**, **Inputs / outputs**, **Logs** and
**Record**: Overview includes outcome, attempts/reuse and error details; inputs,
parameters and outputs appear together; Record shows the complete retained data.
Choose **Logs** to inspect retained execution output. Artifact **Contents/Overview/Lineage**
and pipeline/Run tabs keep their existing information. Service information uses
the same fixed-header layout without extra tabs; experiment Runs retain the list
layout.

## Pipelines and versions

Open a pipeline to select its immutable version. The current default is marked;
selecting an older version does not change the default. Its tabs are:

- **Graph**: top-to-bottom dependencies and selectable component/subpipeline nodes
  at the current pipeline level. Selecting a node shows its input/output contract and
  task configuration. Use **Open subpipeline** to inspect its children, and the
  breadcrumbs in the graph toolbar to return to a parent. The top-level graph
  omits the redundant Pipeline breadcrumb row. **All tasks** shows the complete hierarchy
  with dotted containment edges; **Grouped view** restores the focused level.
  Pipeline and Run graphs use this orientation in every scope. Use zoom controls
  and scroll or drag the background to pan.
- **Summary**: version/pipeline IDs, content digest, profile, availability and
  root interface.
- **Source**: retained compiled YAML/JSON with **Copy source** and
  **Download source**.

Pipeline and Run detail screens keep a compact title/status bar and resource tabs
at the top of the selected screen. The graph fills the remaining space: scroll or
pan its contents while its toolbar and navigation stay in place. Selecting a
step opens an independently scrolling inspector on the right; on narrow screens
it opens as a right-hand drawer. Use **Close step details** to dismiss it.
Selection, inspector tabs and browser back/forward retain the mounted graph,
zoom and pan position. Live Run updates and **Refresh** preserve the viewport
for the same definition and graph scope. Other resource tabs scroll below the
fixed headers. Left navigation remains available throughout.

To move around a graph, hold the primary mouse button on an empty area and drag.
The graph follows the pointer, and the cursor changes from a grab hand to a
grabbing hand. Release to stop, including outside the graph. Node clicks still
select steps; scrollbars, mouse wheel, touch scrolling and keyboard panning are
also available. Dragging changes position without changing zoom.

Try the [98-step scrolling example](../examples/scrolling/README.md) for a graph
with eight parallel branches and enough depth to scroll in both directions.

**Upload pipeline** accepts a compiled `.yaml`, `.yml` or `.json` file plus an
optional display name/description. For an API-owned pipeline, **Upload version**
adds a uniquely named immutable version. Images must already be available to
the execution engine. Upload does not compile source, build images or execute
the pipeline.

A configuration-owned pipeline shows its origin. Update its server-side compiled
file and use the CLI/API `definitions refresh`; uploading a new version over
that registration is rejected. Source is displayed as text, not executed.

## Create or clone a Run

Choose **Create run** from a pipeline/version or the Runs page:

1. Select a definition version or paste its known `definition_…` ID.
2. Choose an experiment (or **Default**) and optionally name/describe the Run.
3. Fill the typed root parameters and artifact IDs. Optional fields have include
   controls; declared defaults are shown. Artifact selectors accept a known ID
   even when it is not in the currently loaded choices.
4. Choose a reuse scope and a key for keyed scope. **none** requests fresh
   selected computation; compiled cache restrictions still apply.
5. Optionally expand **Advanced selection and historical bindings** to specify
   native selection, explicit artifact bindings and historical attempts as JSON.
6. Use **Validate inputs** to check the definition and root inputs, then
   **Start run** to submit. The complete execution plan is checked on submission.

Successful acceptance opens the new Run. It may be queued behind another Run;
acceptance is not completion. Submission retries from the same unchanged form
reuse an idempotency key. After an uncertain connection failure, retry the same
form instead of immediately creating another submission.

**Clone run** prepopulates a new form with the original definition, inputs,
parameters and execution selection. It creates a new Run when submitted and
does not modify or restart the historical Run in place.

## Inspect a Run and its steps

The Run header shows state, timestamps/duration and links to its experiment and
exact definition. **Cancel run** is offered for nonterminal Runs and asks for
confirmation. Completed outputs remain recorded. **Refresh** reloads the view.

The Run tabs are:

| Tab | Contents |
| --- | --- |
| **Graph** | The compiled graph with observed task states, plus a selectable step panel. |
| **Details** | Invocation, parameters, selection, historical bindings and the accepted record. |
| **Artifacts** | Root inputs/outputs and each task's artifact/parameter results. |
| **Logs** | Run-level retained log pages with stream attribution. |

Select a graph step to open **Overview**, **Inputs / outputs**, **Attempts** and
**Logs**. Artifact IDs link to their descriptors. Attempts link to actual
execution details; a reused task has no new container attempt and links to the
original successful producer. Skipped, failed, interrupted and reused states are
shown explicitly, rather than all appearing as successful execution.

Subpipeline nodes show their own recorded state and a summary of nested tasks.
Open them to inspect individual execution or registration tasks. Grouping changes
only the view: attempts, cache reuse and artifact lineage retain their original
task paths. Graph location and selection are included in the URL; a direct link
to a nested task opens its parent level unless the URL explicitly selects another
level. Browser Back/Forward and live updates retain that context. Existing flat
definitions remain flat; author a native KFP subpipeline to group related tasks.

Nonterminal Run views can refresh every three seconds. Turn off **Live updates**
when inspecting a fixed view. Updates pause while the page is hidden or a form
is being edited. Log tabs use explicit bounded loads rather than a live unbounded
stream, so navigation/refresh does not silently consume unlimited logs.

The log viewer supports **All streams**, `stdout`, `stderr` and `system`,
**Load logs/Load more**, and **Start from beginning**. Each page follows the API
cursor. Task/attempt views narrow the log request to that execution.
Task stdout/stderr is saved during execution. Choose **Load more / refresh**
to see newly available output while a task runs; the browser does not automatically
follow logs. Components must flush their output to make it available promptly.
Terminal color codes are removed for plain browser display; stored logs retain them.

## Compare Runs

On a Runs list or experiment page, select 2–5 Runs from the page and choose
**Compare runs**. The table aligns state, definition, duration, input parameters,
task output parameters and finite numeric artifact metadata. Missing fields are
shown as **Absent**, not zero. Metric values link back to their source artifacts.

Comparison reads recorded results; it does not rerun a model or infer comparable
units from unrelated metric names. Complex classification plots remain outside
the comparison interface; open an artifact's Contents tab to preview its files.

## Artifacts and lineage

**Upload artifact** accepts a file from your computer and registers it in managed
storage in one step. Set its type and optional data revision/JSON metadata, then
choose **Upload and register**. ZIPs offer keeping the archive or extracting it
into a directory artifact. Success opens Contents; errors keep the form available
for correction. No Run is created. Manually added artifacts require explicit
deletion and are excluded from automatic retention. See
[upload usage and limits](artifacts.md#upload-and-register-a-new-artifact).

**Register artifact** offers two operations: **Import · managed copy** and
**Register · external reference**. Enter a service-visible allowed URI, type
schema/version and optional data revision/JSON metadata. This form does not
upload a file from your browser. See [artifacts](artifacts.md) for the storage
and source-allowlist rules.

An artifact opens on **Contents**, the first tab:

- CSV files show a table with **Previous/Next** pages loaded from the service.
  Large files stay on storage; the browser loads the current rows. The first
  record supplies headings, and quoted/multiline UTF-8 values remain text.
- JSON shows a highlighted tree. Click a branch to expand/collapse it; **Show next
  100** reveals more children. Large numbers retain their exact spelling. Expansion
  and scroll position survive refresh for the same registered file.
- PNG, JPEG, GIF and WebP images display with **Actual size / Fit to width** controls.
- Directories show their registered files/folders. Open a name, use the path
  breadcrumbs to go up, or use browser Back/Forward. Newly added, unregistered
  files do not appear in this snapshot browser.
- UTF-8 text has a bounded text preview. Unsupported binary files show an
  explanation. Metadata-only artifacts show their metadata tree.

**View as** can select CSV, JSON, image or text when automatic detection is
unsuitable. Previews have explicit limits: JSON is limited to 2 MiB/20,000 nodes/
64 levels, images to 8 MiB/40 megapixels/16,384 pixels per side, and text to its
first 64 KiB. CSV pages use bounded reads and reject records over 128 KiB or
rows over 200 columns. Large/invalid files show an explanation and keep the
other artifact tabs available. Changed files or expired page cursors require
**Start from beginning**. A partial preview does not verify the full checksum;
its footer states the verification limit.

An artifact's **Overview** shows type, origin, ownership, availability,
publication state, URIs, fingerprints, inventory and metadata. Numeric metadata
appears as metric values. **Lineage** links the original producing Run/Task/
Attempt and paginated consumer tasks. External artifacts correctly show no
Dockflow computational producer.

**Pin/Unpin** changes an explicit retention pin after confirmation. It does not
make missing data available or change reuse equivalence. Payload URIs are shown
as data; Contents reads registered files through the authenticated service and
does not fetch arbitrary URLs or render artifact HTML/SVG/scripts.

## Bounded views and errors

The graph displays at most 1,000 nodes per focused level or **All tasks** view.
Its toolbar shows visible and total task counts. Version/input selectors load up
to 2,000 records and accept known IDs for additional history. Comparison is bounded
to 2,000 tasks and 200 output artifacts per Run. The page shows a notice when a
limit applies; inspect the exact definition/source or individual resources for
the remaining data.

Failed requests show their API explanation and a retry action where appropriate.
An update failure leaves the existing view visibly marked as stale. A recovery
hold appears on the Run/service status rather than as a fabricated success.
Use [troubleshooting](troubleshooting.md) when owner, image, storage or validation
errors prevent progress.

The API explorer at `/dockflow/v1/docs` is read-only: search operations/schemas,
filter by HTTP method, expand parameter/request/response definitions and download
the OpenAPI document. It does not submit mutations from its reference panels.

## Resource deletion and storage cleanup

See [Deletion and storage cleanup](cleanup.md) for dependency-protected Run,
execution and artifact deletion, file inventories, explicit manual-artifact
protection, DANGER confirmation and optional deployment retention. Legacy `clean`
continues to remove only disposable workspaces.
