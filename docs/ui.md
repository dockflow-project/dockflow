# Browser interface

[Documentation index](README.md) · Prerequisite: a running [service](deployment.md)

Open `http://127.0.0.1:8080/ui/` after starting Dockflow. The service root redirects
there. The interface is included in the service package and uses the same API,
history and permissions as the CLI. No frontend build service or CDN is needed.
JavaScript is required; the CLI/API remain available without a browser.

The project name and service readiness appear in the top bar. For a token-enabled
service, choose **Connect** and enter its bearer token. The page keeps it in
memory, not browser storage; **Sign out**, reload or leaving the page clears it.
The API reference is a separate page and may need its own connection.

## Navigation

| Menu | What you can do |
| --- | --- |
| **Pipelines** | Browse catalog entries, select versions, inspect graphs/source, upload compiled definitions and create Runs. |
| **Experiments** | Create named groups, inspect their Runs and compare results. |
| **Runs** | Filter history, create/clone Runs, inspect steps/results/logs, cancel active work and compare 2–5 Runs. |
| **Artifacts** | Inspect datasets/models/results, register/import external sources, pin artifacts and follow lineage. |
| **Executions** | Browse actual task attempts, including retries, and inspect their logs and image/result details. |
| **Components** | Inspect embedded component interfaces and executor images/commands. |
| **Service information** | See project identity, runtime versions, capabilities, queue size and limits. |
| **API documentation** | Browse/search the live OpenAPI contract and download its JSON. |

Lists expose relevant filters, **Apply filters**, **Clear**, **Refresh** and
**Previous/Next** pagination. A list shows one page rather than all historical
records. Resource IDs, tabs and graph selections appear in navigation links,
so a detail page can be bookmarked or shared with another authorized client.

## Pipelines and versions

Open a pipeline to select its immutable version. The current default is marked;
selecting an older version does not change the default. Its tabs are:

- **Graph**: dependencies, nested graph groups and selectable component nodes.
  Use zoom controls and scroll to pan. Selecting a node shows its input/output
  contract and task configuration.
- **Summary**: version/pipeline IDs, content digest, profile, availability and
  root interface.
- **Source**: retained compiled YAML/JSON with **Copy source** and
  **Download source**.

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
units from unrelated metric names. Complex classification plots and arbitrary
artifact file previews are outside the current interface.

## Artifacts and lineage

**Register artifact** offers two operations: **Import · managed copy** and
**Register · external reference**. Enter a service-visible allowed URI, type
schema/version and optional data revision/JSON metadata. This form does not
upload a file from your browser. See [artifacts](artifacts.md) for the storage
and source-allowlist rules.

An artifact's **Overview** shows type, origin, ownership, availability,
publication state, URIs, fingerprints, inventory and metadata. Numeric metadata
appears as metric values. **Lineage** links the original producing Run/Task/
Attempt and paginated consumer tasks. External artifacts correctly show no
Dockflow computational producer.

**Pin/Unpin** changes an explicit retention pin after confirmation. It does not
make missing data available or change reuse equivalence. Payload URIs are shown
as data; the browser does not automatically fetch remote URLs, download arbitrary
artifact bytes or render artifact HTML.

## Bounded views and errors

The graph displays at most 1,000 nodes. Version/input selectors load up to 2,000
records and accept known IDs for additional history. Comparison is bounded to
2,000 tasks and 200 output artifacts per Run. The page shows a notice when a
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
