# Web interface

## Purpose and delivery

Provide a first-party browser interface in the existing single-project Pipelines
service. Follow the familiar KFP information architecture: pipeline catalog and
versions, experiments, runs, execution graphs, step details, logs and artifacts.
This is an independently implemented Dockflow interface, not the upstream KFP
frontend or a promise of its unsupported backend operations. The reference UX is
[KFP interfaces](https://www.kubeflow.org/docs/components/pipelines/interfaces/)
and [Run concepts](https://www.kubeflow.org/docs/components/pipelines/concepts/run/),
with execution semantics limited to this package's qualified profile.

Ship HTML, CSS and JavaScript inside the Pipelines Python distribution and generic
service image. No separate UI server, Node runtime, build-time frontend framework,
CDN, internet access or consumer project customization is required. `/` redirects
to `/ui/`; hash routes support browser back/forward, bookmarks and refresh without
server rewrites. The interface talks to the same origin's existing API/core.
It creates no alternate metadata database, queue, executor or lifecycle authority.

## Shell, navigation and access

A persistent left sidebar contains Pipelines, Experiments, Runs, Artifacts,
Executions and Components, followed by API documentation and Service information.
A header shows the current project and connection state. Selected navigation,
page title, breadcrumbs, toolbar and content tabs identify the current context.
Use a compact blue/white KFP-like visual language with Dockflow branding. Status
labels always include text in addition to color. Tables, forms, dialogs, graph
nodes and tabs must be keyboard accessible, have visible focus, and remain usable
on a narrow viewport through wrapping/scrolling rather than clipped actions.

Static shell/assets and `/dockflow/v1/docs` are publicly loadable and contain no
project records or secrets. Existing health probe exceptions remain. All data,
OpenAPI and mutation routes retain configured bearer authentication. On 401 show
a token-entry dialog with password input; retain the token only in page memory,
never URLs, cookies, browser storage, logs or downloadable files. Signing out
clears token and displayed project data; refreshing requires authentication again.
The normal private no-token deployment opens directly. No user accounts, RBAC,
namespace switcher, cookies or implicit cross-origin service connection is added.

Apply a same-origin content security policy, disallow framing and MIME sniffing,
and use no executable HTML from definitions, logs, parameters or metadata. Render
untrusted content as text. Mutation requests from a browser with a foreign Origin
are rejected; non-browser CLI/KFP clients without Origin keep their contract.
Do not fetch arbitrary artifact URLs, load external images or embed artifact HTML
in the application origin. Use the existing token/TLS deployment boundary.

Lists use server pagination (50 by default, at most 200); show Next/Previous and
explicit exact filters. No page is presented as the entire history when a cursor
exists. Loading, empty, disconnected, unauthorized, conflict, not found and
unsupported states provide actionable messages and retry without silently
inventing records. Error displays include available request IDs and details.

Bound convenience selectors to 2,000 loaded records and show truncation clearly;
definition/artifact fields still permit an explicit known ID. A version beyond
the selector remains reachable by its immutable definition route. This bound
does not alter API pagination or claim the selector contains the complete history.

## Pipelines and components

The Pipelines table shows name, description, source/origin, current version and
creation time. Upload Pipeline opens a dialog for compiled YAML/JSON, optional
name and description; it uses the existing bounded KFP multipart endpoint.
Registration success navigates to the accepted catalog. Upload never executes a
Run. Invalid files, duplicate names and unsupported features show server errors.

Pipeline detail exposes an immutable version selector, current-default marker,
Graph, Summary and Source tabs, Create Run and Upload Version. Older versions
remain navigable. The selected version is retained when creating a Run. Upload
Version requires an explicit version name; configuration-owned catalogs explain
that their files are refreshed through CLI/API instead. Source shows retained
original text, permits copying/downloading it, and labels its actual format.
Summary includes IDs, digest, profile, creation time, descriptions and root
input/output contracts. Unregistered definitions remain reachable from Runs.

The graph contains exact compiled task paths, dependencies and nested DAG
containment. Graph nodes show display name, component, condition/group indicators
and are selectable through mouse or keyboard. Pan through scrolling and provide
zoom controls. Node inspection shows compiled inputs/outputs, executor/image and
condition without executing anything. Large graphs remain scrollable. A graph
is a view of the accepted definition, not an editable authoring surface.
Render at most 1,000 graph nodes in one view, with an explicit truncation notice
and source inspection available for the full definition. Never hide that a
display is bounded or reinterpret truncation as missing execution.

Components has a paginated list, exact name/definition filters, and a detail
screen for component ID, parent definition, interface and executor/image. Embedded
components retain their accepted definition association. No component/image
build or separate upload protocol is implied.

## Experiments, creation and run comparison

Experiments lists names, descriptions and dates. Create Experiment accepts name
and description. Detail shows the experiment and its paginated Runs with a
Create Run action that preselects this experiment. Duplicate names display 409.

Runs lists name, status, creation/start/finish times or duration, experiment and
version links. Exact state, experiment and definition filters reset pagination.
Create Run accepts a registered immutable definition (or a known definition ID),
name, description, experiment (Default when omitted), root parameters and root
artifact IDs. Parameter controls are derived from the definition: strings stay
strings, boolean controls remain boolean, numbers and JSON preserve the admitted
types. Show defaults, required/optional status and descriptions. Artifact inputs
select existing IDs; file paths refer to service-side registration/import, not
browser-local filesystem upload.

Expose reuse scope/key and an Advanced section for the supported selection,
explicit artifact bindings and historical executions. Validate uses the existing
validation endpoint for definition/root bindings; final submission validates the
full plan. A successful submission navigates to the accepted Run. Disable duplicate
submission while pending and retain one Idempotency-Key for an unchanged request
when retrying after uncertain transport failure. Changing the request creates a
new key. Surface accepted IDs/recovery failures accurately.

Select two to five Runs from the current list to Compare. Show status, definition,
duration, parameters, scalar task output parameters and numeric artifact-metadata
metrics in a side-by-side table. Link every Run/artifact source. Missing values
are shown as absent, never zero; distinguish different metric names/tasks and do
not silently aggregate them. This is inspection, not statistical significance or
an experiment optimization system.
Limit one comparison to 2,000 tasks and 200 output artifacts per Run, bound
concurrent fetches, and show any truncation. Values outside that display remain
available through individual Run/task/artifact inspection.

## Run and step detail

Run detail shows immutable invocation identity, state, timestamps and errors;
a linked experiment/version; Graph, Details, Artifacts and Logs tabs; Clone Run
and Cancel actions. Clone populates an editable new-run form with the original
version and supported invocation options; it creates a distinct Run. Cancel
requires an explicit confirmation, is offered for nonterminal Runs and respects
queued/active/terminal cancellation semantics. There is no invented retry/resume
operation. Do not label an interrupted Run as successfully completed.

Graph overlays actual Task states on the compiled graph. Before task admission,
a node may have no task record. Selecting a node opens a detail panel with
Overview, Inputs/Outputs, Attempts and Logs. Expose parameters, named artifact
links, scalar outputs, errors, execution image identity, attempt order, exit
status and publication state. Reused tasks link to the actual original attempt
and have no fabricated attempt; skipped/omitted/blocked states stay distinct.
Executions provides paginated attempt records and links to their Run/Task.

Poll visible active Run details approximately every three seconds, with a pause
control and manual refresh. Stop background polling on hidden pages, navigation,
authentication failure and terminal completion. Ignore/abort stale responses so
a prior page cannot overwrite the current route. Retain selected tabs/task and
avoid interrupting user input. Connection failures retain the last visible data
with an explicit stale/error notice and allow retry.

Logs use existing cursor-bounded pages, stream attribution, timestamps and task/
attempt filters. Show stdout, stderr and system as text. Explicit Load More and
Refresh advance the cursor without duplicating entries. Keep a bounded browser
buffer of at most 1 MiB of UTF-8 log text and explain dropped earlier display
entries; durable service logs remain unchanged. Distinguish no output yet from
unavailable/deleted logs (410).
The execution adapter persists stdout/stderr during execution. Manual Load
More/Refresh retrieves new output from active tasks; the browser does not
automatically follow logs. Explain that component buffering may delay output.
Strip terminal color sequences for plain browser display, including sequences
split across records, without interpreting log content as HTML or changing
retained text.

## Artifacts and lineage

Artifacts lists IDs, type, origin, availability, publication and pin state with
exact type/availability filters. Register/Import opens a form for allowed
server-visible URI, artifact type/version and JSON metadata, using the existing
API and idle-owner restrictions. Explain reference versus managed copy. Artifact
detail shows descriptor/source/content URIs as text, digest/inventory, metadata,
actual producer, pin/unpin, Overview and Lineage tabs. Numeric metrics in metadata
are displayed without loading payloads; other metadata remains inspectable JSON.

Lineage shows the true producer separately and paginated consumer tasks. Reused
outputs are references to the original producer, not new production events.
Consumer links lead to task/Run details. External artifacts explicitly have no
Dockflow producer. Missing/corrupt/unavailable payloads retain their historical
lineage; inspection never assumes that an artifact URI is safe browser content.
Binary downloads, arbitrary HTML/Markdown rendering and dataset previews are
outside this UI increment and must be described honestly.

## Service information and API documentation

Service information displays capabilities, actual versions, limits, profile and
health/readiness with clear qualification limits. It does not expose credentials
or add service start/stop/cleanup controls. API documentation is a packaged,
offline OpenAPI explorer at `/dockflow/v1/docs`: searchable method/path sections,
parameters, request bodies, responses and component schemas derived from the
actual OpenAPI document. Offer schema download. Do not depend on external Swagger
assets or maintain a second handwritten endpoint contract. Documentation links
must work from a clean source checkout; publication hosting is separate.

## Validation

Verify auth/no-token journeys, public shell versus protected data, unknown assets,
traversal rejection, security headers, origin checks and packaged asset presence.
Exercise catalog/version upload, typed Run creation, validation/idempotency,
cancellation, graph hierarchy, task/attempt links, logs paging, metrics comparison,
artifact registration/pinning/lineage and error/empty states. Use actual browser
interaction against a disposable service plus API tests. Include XSS-shaped
names/logs/metadata and verify text rendering. Validate desktop and narrow layouts,
keyboard interaction, navigation and no external network dependencies. Record
browser/platform and actual execution coverage separately from fixture records.
