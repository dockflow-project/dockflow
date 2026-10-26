# Web interface

Explicit resource deletion, storage cleanup and deployment retention are governed
by [Deletion and storage cleanup](015_deletion-and-storage-cleanup.md), which
specializes the original preservation/disabled-cleanup defaults below.

## Human-readable resource references

Where the UI presents resource IDs, show their human-readable context nearby:
executions and Tasks show their component name; Runs show their compiled pipeline
name; pipelines/versions show the pipeline name; experiments show the experiment
display name. Keep invocation/task/display/version labels when different from
these names. The catalog name remains available when it differs from the compiled
pipeline name. Never substitute a task name for its component or a Run display
name for its pipeline. Component references themselves show component names.
Show the resolved name before the ID. When an invocation/attempt label is also
present, lead with the resolved name and retain that label before the ID. Existing
name-first labels and IDs on a separate following line need no duplication.
For editable ID fields, keep the exact value and place the resolved name above
the field, except autocomplete filter fields: those show name then ID inside the
field and submit the exact ID separately from that display text. Do not add a
name hint above a filter or change its header height when resolving/selecting it.

Apply this consistently to lists, detail headers/fields, related links, graph
inspectors and attempts/reuse links, artifact provenance/consumers, comparisons,
selectors/filter selections and deletion dialogs. Keep exact IDs in link targets,
values, accessible titles or nearby text even when visible IDs are shortened.
Disambiguate identical names by ID. Preserve names/IDs in raw records and JSON
source rather than rewriting stored data or payload previews. Missing/deleted
names leave the ID usable and disclose that the name is unavailable.

Resolve visible/selected references through bounded authenticated project-scoped
read-only lookups, independently of catalog pagination. Do not download entire
catalogs or issue a request per row. Deduplicate requests and keep any name cache
in page memory only, clear it on sign-out and refresh it on navigation/refresh.
Failures in optional name lookup do not replace an otherwise usable screen.
Ignore stale responses after navigation/sign-out. Render names as inert text;
allow wrapping and long-name access without displacing fixed controls. Name
updates and inspector selection must not remount the graph or reset viewport,
zoom, list pagination or independent scrolling.

## Artifact upload

The Artifacts list provides a primary Upload artifact action and preserves
Register/import by URI as a separate action. One form accepts a file, KFP type,
optional data revision and JSON metadata. For `.zip` files show a ZIP-handling
choice: keep the ZIP as a file artifact (default), or extract into a directory
artifact. Hide that choice for other file types and reset it to keep. Explain
managed destination, manual origin/explicit-only deletion and bounded upload/ZIP
extraction. Do not ask users for server paths. Submit through the native upload
API once, disable duplicate submission while busy, preserve form input on errors,
and navigate successful uploads to the artifact's first/default Contents tab.
Show the uploaded filename in list/detail headings when no data revision is set;
Overview shows filename and archive mode. Payload names/content remain inert text.
On uncertain acceptance advise checking the result before retrying.
The [artifact upload contract](006_artifacts.md#upload-and-register) owns semantics.

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

A persistent left sidebar groups primary destinations into exactly these three
labeled sections, with sections and items in the order shown:

| Section | Items in order |
| --- | --- |
| Definitions | Pipelines, Components |
| Workloads | Experiments, Runs, Executions |
| Storage | Artifacts, Cleanup |

Cleanup opens the existing Storage cleanup screen; its route and screen title
remain unchanged. API documentation and Service information remain separate
footer links. Expose named groups to assistive technology, keep section headings
readable on narrow icon layouts, and retain each destination's accessible name.
Highlight the current destination within its group, including definition/version
details under Pipelines, task/attempt details under Executions and comparisons
under Runs. Preserve existing navigation URLs and keyboard access.
A plain project name directly beneath the Dockflow logo in the persistent left
sidebar identifies the current project without a visible Project label, colored
background or enclosing box. The fixed sidebar footer has an upper horizontal
divider, followed by API documentation, Service information and runtime text,
then a second horizontal divider and service/readiness status with Connect/Sign
out at the very bottom. Both footer groups remain fixed and reachable.
Retain existing authentication/status behavior and accessible names.
Retain the complete project identity with safe wrapping, a complete tooltip and
keyboard-focusable bounded scrolling for long identities; keep status text and the
connection action reachable on narrow screens. Logo/context and footer stay in
place while the grouped navigation scrolls independently when height is limited.
There is no global top bar above the selected screen: its workspace starts at
the top edge and uses the full available viewport height. Selected navigation,
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

### Record-list workspace layout

Every record-list screen has a fixed top section for its title, filters, actions
and context, a fixed bottom bar for pagination and counts, and a main list region
that fills the remaining width and height. Keep navigation and the project/service
bar visible. Scroll rows within the main region, with column headings sticky at
its top; horizontal overflow moves headings and cells together. Do not scroll the
whole screen to reach pagination. This applies to all six catalogs, experiment
Runs, artifact consumers, Run artifact/task results, comparisons and cleanup files.

Retain server cursors and exact filters. Show the current page count and whether
more records exist without inventing a global total. Already-loaded bounded
detail/comparison tables may page locally, clearly distinguishing loaded counts
and truncated subsets from complete history. Previous/Next are disabled at the
corresponding boundaries. Empty results retain headings and the bottom bar.
Changing filters or pages resets row scroll; refreshing the same query preserves
row position and any local page. A failed refresh retains the last valid list and
reports stale data in the top section with retry available.

Give the scrolling region an accessible name, keyboard focus and visible focus
indication. On narrow screens compact/wrap controls and allow a bounded top-region
scroll or collapsed secondary options, keeping the list and bottom controls
reachable. Auxiliary tools may open from top-section actions instead of occupying
space below the list. Short metadata/link lists are not separate list workspaces.

Bound convenience selectors to 2,000 loaded records and show truncation clearly;
definition/artifact fields still permit an explicit known ID. A version beyond
the selector remains reachable by its immutable definition route. This bound
does not alter API pagination or claim the selector contains the complete history.

### Element detail workspace layout

Non-graph element views use a fixed, compact top section for identity, relevant
general information/status, context links and actions. Keep the left navigation
and its project/service context visible. The remaining width/height belongs to one
independently scrolling information area; do not scroll the outer page to reach
the element's information. Apply this to component, artifact, task and execution
details and non-graph pipeline/definition/Run tabs. Service information follows
the same layout; experiment details retain the record-list workspace contract.

Use tabs when they separate substantial information: component overview,
interface, executor and compiled source; task/execution overview, inputs/outputs,
logs and complete record. Retain artifact Contents/Overview/Lineage and pipeline/Run tabs.
Place tabs at the bottom of the fixed top section, reachable while content
scrolls. Keep tab state in bookmarkable URLs and preserve browser history.
Preserve all existing fields, provenance, logs, links, actions and mutation guards.

The information area has an accessible name, keyboard focus and visible focus.
Changing tabs starts the new information area at its beginning. Refreshing the
same element/tab retains its scroll position; failure retains the last valid
view with an actionable error. Compact or scroll long header context/actions
within bounded regions on narrow screens so tabs and useful main content remain
reachable. Render long records safely with wrapping or internal overflow. These
requirements do not alter graph interaction or embedded list pagination.

### Pipeline and Run graph workspace layout

Keep left navigation and its project/service context visible. Pipeline/definition
and Run detail screens use a compact, fixed resource header at the top edge of
the selected screen area: title, execution status where
applicable, version/context and actions. Compress spacing and metadata instead
of retaining a large page-title block. Place the resource tabs along the bottom
of this header and keep them visible while content scrolls. Preserve all existing
actions, identifiers and metadata through context controls or detail tabs.

On the Graph tab, fill all remaining screen width and height. The graph control,
its toolbar and hierarchy navigation stay in place; only the graph contents pan
or scroll within their viewport. Do not add an outer page scrollbar or fixed
graph-height limit that wastes available space. Other resource tabs scroll their
content below the same fixed headers.

Selecting a graph element opens a right inspector with its own vertical scroll
region and a visible close action. Inspector scrolling must not move the graph
or the resource header/sidebar. On narrow screens, use a dismissible right-side drawer while
keeping navigation and header controls usable. Keyboard users must be able to
reach and scroll the graph and inspector independently.

Selection, switching selected elements, inspector tabs, closing the inspector and
selection history navigation update the inspector and selection styling without
remounting or reloading the graph. Preserve graph zoom and scroll/pan position.
Background Run updates and explicit refreshes preserve the current graph viewport
when the definition and displayed graph scope remain the same. Changing versions
or graph scopes may initialize a new graph viewport. Keep selection and scope in
navigation URLs; retain viewport state only in page memory, without credentials
or additional deployment settings.

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
containment. Every pipeline and Run graph must flow from top to bottom, including
focused subpipeline levels and All tasks views. Place dependency levels in
successive rows, peers side by side, and connect each source node's bottom center
to its dependent node's top center. Preserve this orientation during selection,
scope navigation, pan and zoom.
Graph nodes show display name, component, condition/group indicators
and are selectable through mouse or keyboard. Pan through scrolling and provide
zoom controls. In every graph screen and scope, dragging the background with the
primary mouse/pen button pans the graph: contents follow the pointer on both axes
within the existing scroll bounds. Use screen-space deltas at the current zoom,
without changing zoom, selection, graph scope or the mounted graph. Show a grab
cursor on the background and a grabbing cursor while panning; ignore tiny pointer
movement. Capture the active pointer so releasing outside the viewport ends the
gesture. Clear gesture state on cancellation, lost capture, window blur or wheel
scrolling. Do not start a pan on nodes, interactive controls, native scrollbars,
secondary-button presses or additional pointers. Preserve node selection,
subpipeline controls, keyboard/scrollbar panning and native touch scrolling.
Defer periodic refresh initiation while a background drag is active.
Node inspection shows compiled inputs/outputs, executor/image and
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
actual producer, pin/unpin, Contents, Overview and Lineage tabs. Contents is first
and selected by default when a tab is absent from the URL. Explicit Overview and
Lineage links remain valid. Numeric metrics in metadata
are displayed without loading payloads; other metadata remains inspectable JSON.

Lineage shows the true producer separately and paginated consumer tasks. Reused
outputs are references to the original producer, not new production events.
Consumer links lead to task/Run details. External artifacts explicitly have no
Dockflow producer. Missing/corrupt/unavailable payloads retain their historical
lineage; inspection never assumes that an artifact URI is safe browser content.
General binary downloads and arbitrary HTML/Markdown execution remain outside
this interface. Contents specializes the previous no-payload-preview limit below.

### Artifact Contents

Provide authenticated read-only `GET /artifacts/{artifact_id}/contents` with
optional artifact-relative `path`, `format` (auto, csv, json, image, text),
`page_size` (default 50, maximum 200) and opaque `page_token`. Keep the normal
service token, no-store, safe-origin and retirement boundaries. Never accept an
arbitrary URI, browse a server root, fetch HTTP URLs, redirect to external storage,
execute payload code or expose storage credentials. Read only the registered
artifact file or files in its recorded directory inventory, subject to current
filesystem roots/S3 prefixes. Reject traversal, symlinks, nonregular files, control
state, uncommitted/retired records and unsafe locations. Reading transfers holds
no SQL transaction or execution mutex. Recheck retirement before responding.

Directory Contents is a paged browser of recorded immediate children, including
implied and empty folders. Show names, file/folder kinds, sizes, breadcrumbs and
parent navigation; opening a file selects its viewer. Do not include files added
outside the registered inventory. Explain that this is the registered inventory
and file availability is checked when opened. Retain path/format/page in the URL
and support browser history. Contents uses the fixed list layout for browser/CSV
pages; headers, navigation, counts and format controls remain accessible while
contents scroll.

CSV is parsed server-side as UTF-8 with optional BOM, LF/CRLF, quoted delimiters
and multiline fields. Recognize comma, semicolon, tab and pipe delimiters, with
comma fallback. The first logical record supplies headings; preserve duplicate/
empty headings, cell text and ragged rows without interpreting formulas/HTML.
Use bounded byte-offset continuation at logical-record boundaries, rather than
loading/materializing the complete CSV or rescanning its preceding rows on every
page. Bound each page block to 1 MiB, each logical record/header to 128 KiB and
each row to 200 columns; small bounded header/detection reads may repeat. Show
visible row ranges and Previous/Next/end state without inventing a total row count.
Malformed/oversized records fail clearly rather than being skipped. Signed opaque
cursors bind the artifact revision/fingerprint, path, format/page size and file
identity; replacement/change, tampering or service restart requires restarting
from the beginning.

JSON Contents is a syntax-highlighted collapsible tree. Expand branches on demand
and render at most 100 direct children per expansion batch, with explicit more
controls. Preserve object property order/duplicates, string escaping and exact
numeric spelling, including integers beyond browser precision. Limit JSON source
to 2 MiB, 20,000 nodes and 64 levels; disclose limits instead of silently dropping
data. Metadata-only artifacts show their metadata tree and explain there are no
storage files. Invalid JSON is reported as such; it is never interpreted as code.

Images support signature-recognized PNG, JPEG, GIF and WebP with fit-to-width and
actual-size viewing. Read through the authenticated API and embed only a generated
raster data URL. Limit encoded source to 8 MiB, dimensions to 16,384 pixels per
side and 40 megapixels. Show dimensions, size and decode/limit errors. Do not render
SVG, HTML or other active-document formats as images or embedded documents.

Provide a safe text fallback for UTF-8, limited to the first 64 KiB with explicit
truncation, and a useful unsupported state for binary/unknown types. File identity
and registered size are checked; complete bounded file reads also verify their
registered SHA-256. Partial CSV/text preview does not establish full integrity:
label this limit and retain the existing independent integrity-check contract.
Filesystem reads use non-following descriptor-relative opens and detect mutation;
S3 uses bounded conditional/versioned range reads and rejects providers that ignore
those constraints. Return actionable missing/access/changed/limit/invalid states
while keeping artifact context, Overview, Lineage and actions available.

## Service information and API documentation

Service information displays capabilities, actual versions, limits, profile and
health/readiness with clear qualification limits. It does not expose credentials
or add service start/stop/cleanup controls. API documentation is a packaged,
offline OpenAPI explorer at `/dockflow/v1/docs`: searchable method/path sections,
parameters, request bodies, responses and component schemas derived from the
actual OpenAPI document. Offer schema download. Do not depend on external Swagger
assets or maintain a second handwritten endpoint contract. Documentation links
must work from a clean source checkout; publication hosting is separate.

## Filter autocomplete

Filter resource search fields provide an accessible autocomplete list. Match
literal substrings in both the public ID and human-readable names, including
pipeline names for Runs and component names for Tasks/executions, and retain
invocation names as additional searchable context. Opening/clicking an empty
field shows recent options; typing refreshes server-side matches. Return at most
ten options, ordered newest first with public ID ascending as the stable tie
breaker. If additional matches exist, show a non-selectable footer with the exact
count, `...and N more`, scoped to the current text and selected parents. Do not
show that footer when no matches are omitted. Pipelines/components/definition versions use their creation/definition
registration date; Runs, Tasks and executions use execution start, falling back
to creation for records without a start. Other resources use creation time.

Provide primary ID/name Search on pipeline, component, experiment, Run, execution
and artifact lists, as well as autocomplete on related-resource ID filters and
the Cleanup artifact filter.
Display selected names then IDs inside the text field, preserving exact IDs as
submitted filter values and restoring the same display from URL filters.
Text inputs and selects in filter toolbars have the same control height.
When an autocomplete value is selected, show a right-aligned × button inside the
field. Give it an accessible Clear label and mouse/keyboard activation. It clears
both display and canonical selection, resets dependent filters through the same
change behavior, returns focus to the input and hides itself. Hide the button
for empty/unselected fields, preserve input/header dimensions, and keep text
clear of its hit area. Long selected text fades out toward an opaque clear-button
area so captions cannot paint beneath the ×, including in compact list headers.
Keep the button and its focus indicator visible and clickable. Clearing does not
submit filters automatically.
Selecting a suggestion updates the field; Apply filters remains the submission
action. Unselected typed primary Search uses literal ID/name substring matching;
existing exact name/reference filters retain their API meaning. The artifact Type
field suggests at most ten distinct types by the newest artifact of each type;
selecting it retains the exact type value. State/availability selects stay as-is.

Use Pipeline ID as the UI label wherever a definition ID is presented, including
related filters, detail fields, table headings and help text. Keep canonical
`definition_id` fields, `definition_` IDs and definition/version routes unchanged;
the selected immutable version remains the operand.

Components filter order is Pipeline ID, Component ID. Limit Component ID options
to the selected pipeline/definition. Runs order is Search, Experiment ID,
Pipeline ID, State (omit Experiment ID inside an experiment). A selected
experiment limits Pipeline ID options to distinct definitions used by its live
Runs, including unsuccessful or pending Runs; it does not include unused
definitions. Primary Run Search respects selected experiment/pipeline context.
Executions order is Search, Run ID, Task ID, State. A selected Run limits Task ID
options to Tasks in that Run; primary execution Search respects selected
Run/Task context. State always offers its complete valid set. Apply these scopes
before computing the ten-result limit and omitted count. Changing/clearing an
upstream selection clears dependent selections and invalidates their pending
responses. Unselected name fragments are not treated as canonical parent IDs.

Support keyboard focus, Up/Down navigation, Enter selection, Escape dismissal,
and accessible combobox/listbox roles and active option state. Keep suggestion
lists within the viewport without clipping against fixed list headers. Debounce
typing; stale responses after edits, blur, navigation or sign-out must not replace
the current options. Show empty/loading/unavailable states without preventing
manual entry. Resolve only project-scoped live metadata, with authenticated,
bounded requests and no artifact payload reads or browser credential persistence.
Verify ID/name matching, recency rather than name ordering, ten-result limits,
empty-field options, mouse/keyboard selection, stale-response isolation,
failure recovery, exact selected values and desktop/narrow list layouts.

## Validation

Verify exact sidebar section/item ordering, named groups, all seven destinations,
detail/alias highlighting and keyboard access. Verify the unboxed project name is
beneath the logo without a visible label, footer utilities sit between two
dividers above bottom-aligned status/connect, no global top bar remains, and list/detail/graph content receives
the reclaimed height. Check full long project IDs, sign-in/out and unavailable
status, keyboard access and independently scrolling navigation at short heights.
Inspect desktop/narrow section
headings, footer utilities and contained scrolling without unintended sidebar/page overflow.

Verify fixed top/bottom regions and sticky column headings across all record-table
screens, including empty results, vertical/horizontal overflow, keyboard scrolling
and narrow viewports. Exercise cursor navigation, filter resets, bounded local
paging, honest counts and failed-refresh recovery; preserve cleanup byte estimates,
selection/deletion protections and graph workspace behavior.

Verify non-graph detail fixed headers/tabs and independent information scrolling
for components, artifacts, tasks/executions, service information and pipeline/Run
information tabs. Check keyboard access, narrow/long content, tab URLs/history,
refresh position/error recovery and preservation of data/actions. Retain embedded
list pagination and graph zoom/pan/selection behavior.

Verify first/default Contents and explicit Overview/Lineage navigation; large CSV
bounded reads, quoted/multiline/UTF-8 data, page continuity, exact values and changed
cursor rejection; JSON collapse/highlighting/lazy batches and exact large numbers;
image fit/size/limits; directory paging/breadcrumbs/history/empty folders; metadata,
unsupported, malformed and truncated states. Exercise authentication, traversal,
symlink/open races, unregistered entries, retirement, checksum changes and S3
conditional/range behavior. Check desktop/narrow scrolling, keyboard access and
safe rendering of adversarial names, cells and JSON. Record actual provider/browser
coverage separately from mocked responses.

Verify auth/no-token journeys, public shell versus protected data, unknown assets,
traversal rejection, security headers, origin checks and packaged asset presence.
Exercise catalog/version upload, typed Run creation, validation/idempotency,
cancellation, graph hierarchy, task/attempt links, logs paging, metrics comparison,
artifact registration/pinning/lineage and error/empty states. Use actual browser
interaction against a disposable service plus API tests. Include XSS-shaped
names/logs/metadata and verify text rendering. Validate desktop and narrow layouts,
keyboard interaction, navigation and no external network dependencies. Record
browser/platform and actual execution coverage separately from fixture records.
Verify top-to-bottom dependency flow and connector attachment in pipeline and Run
screens, focused subpipelines and All tasks, including parallel branches and
desktop/narrow viewports; preserve hierarchy, selection and pan/zoom behavior.
Verify viewport-filling Graph tabs, persistent sidebar/resource headers and independent
graph/inspector scrolling. Assert stable graph DOM identity and zoom/pan during
selection, inspector tabs, close and history navigation; assert viewport retention
on live/explicit refresh and correct reset for changed versions/scopes. Exercise
narrow drawers, keyboard scrolling, long titles/actions, non-Graph tabs and normal
list screens without clipped controls or page-level overflow.
Verify actual background drag gestures on pipeline and Run screens and nested/All
tasks views, both axes/directions and multiple zoom levels. Check bounded offsets,
grab/grabbing feedback, no node selection after background drag, release outside
the viewport, cancellation/lost capture/blur cleanup, and subsequent node/control,
wheel and keyboard interactions. Retain native touch behavior and graph identity,
zoom and dragged position during inspector selection and refresh.
