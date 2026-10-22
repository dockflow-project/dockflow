# Dockflow implementation

## Phase and identity

Project phase: **bootstrapping**. The working specification is reviewed and
adopted for continued implementation; its selected package versions belong to
the [composition](../specs/composition.yaml). This working acceptance does not
finalize a project baseline. The composition's `specs-0.1.0` remains an
unfinalized seed; no finalized specification or implementation baseline exists.
Git commits identify source snapshots independently of baseline finalization.
Application identity remains `0.1.0.dev0` from root `VERSION`.

The selected first-publication scope is an MIT-licensed **source development
preview**, installed from a checkout. It does not include package/image uploads
or imply a stable release or full platform qualification. Source publication,
reviewed integration and baseline finalization remain separate operations.
Imported specification snapshots are unchanged and integrity-locked.

All delivered workflows through the source-readiness review are closed under the
Definer's explicit authorization, with their records in
[workflow history](workflows/history/). Closure accepts their delivered scope;
it does not invent baseline tags or qualify previously untested targets.
Future work starts a new workflow. See the
[readiness receipt](validation/source-publication-readiness.md) for current
checks and the remaining hosting prerequisite.

[User documentation](../../docs/README.md) is the entrypoint for installation,
authoring, CLI/API/browser use, configuration, deployment and operations.
[Architecture](../../docs/architecture.md) explains current boundaries;
[CONTRIBUTING](../../CONTRIBUTING.md) defines reproducible development checks.

Workflow and qualification records are anonymized technical summaries. Personal
attribution, machine-specific locations and unrelated project identities are
omitted; obsolete raw scratch outputs and build archives were discarded. See
[qualification record scope](validation/README.md) for historical hashes,
normalized fixture labels and evidence availability. Imported specification
licenses and provenance retain their canonical content.

## Components and execution

`packages/cli` owns the shared executable and entry-point discovery. Importing
installed modules or requesting help does not initialize runtime infrastructure.
`packages/pipelines` owns compiled KFP validation, invocation planning, durable
execution and management, artifacts, reuse and the CLI/HTTP/browser adapters.
Base client imports remain independent of optional Docker/KFP/MLMD/server extras.

`definitions.py` validates a bounded KFP 2.17 IR profile. Consumer code is compiled
and component images built externally; Dockflow neither imports consumer Python
nor builds their images. `core.py` fixes accepted invocation/version/input/policy
choices. `engine.py` evaluates the admitted static/nested graph, importer and
condition profile; `executor.py` connects KFP DockerRunner to owned containers,
resources, stop confirmation and publication. Reused tasks link to the original
producer without fabricated attempts. Task stdout/stderr are retained during execution. `container_logs.py` attaches
before start, bounds its reader queue and forwards decoded chunks on the execution
thread. A retained-log pass verifies the streamed prefix and captures missing
tails without replay. Cancellation remains on the coordinator thread.

The service holds one state owner and a durable FIFO queue, with one active Run
and attempt. Each Run receives a spawned worker process for KFP's process-global
state. Workers call owner-side state/artifact operations over constrained RPC;
HTTP request threads do not reinitialize KFP. Shutdown records stop intent,
confirms termination and retains queued work. Startup reconciles uncertain prior
containers before dispatch. Direct CLI refuses unresolved/queued execution until
explicit service recovery and draining. No automatic crash rerun is implied.

## Persistence and artifacts

`metadata.py` coordinates authoritative accepted journal records, atomic
projections, output-set commits, recovery and safe maintenance. `records.py`
contains pure record identity/timestamp primitives. `ownership.py` owns stable
local OS locking and bounded diagnostic owner UUID/hostname/PID/project/mode/time/
endpoint fields; metadata is never a lease or takeover token. `mlmd_index.py`
is the lazy MLMD/SQLite projection adapter. Existing `metadata` import names
remain aliases, and persisted records/wire contracts retain their identity.

The accepted record stream and committed artifact outputs are authoritative;
MLMD/SQLite is a reconstructible query/lineage index. Accepted-but-unindexed work
holds admission for reconciliation rather than pretending it never happened.
`canonical.py` owns typed canonical JSON hashing; `reuse.py` owns equivalent
signature selection and integrity checks. `artifacts.py` provides filesystem and
S3-compatible managed stores, external references/imports, inventory checking and
explicit pins. Managed outputs use pipeline/run/task/attempt-UUID/output paths below the
resolved managed_root or S3 bucket/prefix, with recovery descriptors under
.dockflow/dockflow-pipelines. Administrative managed imports stay in that metadata area;
legacy root retains its managed child. Reuse keeps the original producer URI.
Admission, publication and backup/restore share the resolved directory and
retain descriptor-driven access to earlier layouts. Reference payloads remain at their sources. Owner-side transfers keep storage credentials out of ordinary
task containers. See [persistence](../../docs/persistence.md) and
[artifacts](../../docs/artifacts.md) for recovery and URI/path limits.

## HTTP and browser interfaces

Service admission validates a single well-formed Host header and bases protected
route decisions on the ASGI path with segment-aware root-path handling. Host URL
reconstruction cannot grant a public-route exemption. The standard-library remote
client rejects HTTP redirects, including same-origin redirects and HTTPS
downgrades, before forwarding credentials or replaying a request. Clients must
configure the canonical endpoint. Optional token and trusted-local defaults remain
unchanged.

CLI and native `/dockflow/v1` HTTP adapters call the same core. Foreground local
execution forwards durably captured component log lines to stderr while each
container runs. Colors are preserved on a terminal and removed on redirection or
NO_COLOR; browser log display strips color escapes without changing stored text.
`console.py` owns human presentation: `run --output none|trimmed|full`, a
bounded preview limit, and narrowly recognized KFP executor-input/task-output
display. Default trimmed results show Run identity/state and output IDs/scalars;
full inspection and machine JSON retain complete records. Independent run flags
control Dockflow progress/human results and component stdout/stderr. Hiding
Dockflow output also filters narrowly recognized container-side KFP INFO
bookkeeping and validated executor-input JSON, even in full detail mode. Unknown
messages and user logging sharing KFP's formatter remain visible; malformed or
oversized metadata fails open. Both flags default
to visible; hiding both silences successful human runs while host warnings and
failure diagnostics remain. Full logs remain durable, and explicit JSON always
returns its complete result. These choices do not
change execution inputs, persistence or API behavior. Native APIs expose
strict JSON, structured errors, durable Run idempotency, bounded pages and log
cursors, catalog/definition/component/task/attempt inspection and original
artifact producer plus paginated consumer tasks. OpenAPI 3.1 describes these
contracts. The bounded KFP v2beta1 adapter accepts compiled pipeline/version
multipart uploads and official client resource envelopes. Versions/components/
source/default membership are accepted atomically; configured and API-owned
catalogs cannot overwrite each other. Runs retain their selected immutable version.
Unsupported KFP recurring, archive, retry, visualization and MLMD-proxy APIs are
still explicitly rejected. KFP 2.17's waiter does not recognize `CANCELED`; inspect
that truthful status with get_run or the native CLI.

`web.py` serves packaged static assets and read-only artifact lineage. Browser
JavaScript is split into transport/auth, safe DOM helpers, graph projection,
forms, read views, navigation and a read-only OpenAPI explorer. `/` redirects to
`/ui/`; `/dockflow/v1/docs` works without external CDN assets. Pipelines/versions,
experiments, Runs, graph/task/attempt details, retained logs, artifact provenance,
scalar result comparison, submission/cloning/cancellation, upload and supported
artifact/experiment operations reuse public APIs. No additional service, frontend
runtime, database or executor is introduced. The UI is independent of the
upstream KFP frontend and does not imply full KFP backend parity.

Static shells contain no project data and can load before authentication. API
bearer tokens remain in page memory; protected records still require auth.
Same-origin mutation checks, text-only rendering and a restrictive script CSP
protect the browser boundary. Root-path-aware relative resources support ASGI
proxy prefixes. Visible active Runs poll conservatively; logs use manual cursors.
See [UI guide](../../docs/ui.md) for interactions and explicit display limits.

## Deployment and self-contained example

The generic Ubuntu/Python service image supplies runtime, service and S3 extras.
Reference Compose uses an isolated Docker engine, SQLite state, MinIO and registry.
The seven explicit volumes are `dockflow-state`, `dockflow-execution`,
`docker-socket`, `docker-state`, `docker-containerd`, `artifacts`, `registry-data`.
Component images stay separately prepared. Filesystem artifact deployments and
remote CLI access are supported with correct permissions and shared task paths.
The host Docker socket is not forwarded by the reference stack.

[examples/quickstart](../../examples/quickstart/README.md) supplies independent
standard-library component scripts, thin KFP wrappers, compiled definitions and a
component Dockerfile. The user tutorial proves direct execution, reuse and the
same project's persistent service without another repository. External consuming
projects are optional integrations; their historical workflows retain separate
provenance and are not build/runtime dependencies of Dockflow.

## Qualification and evidence

Run the commands in CONTRIBUTING, including generated API drift checks, Python
regression/provider tests, dependency-free Node tests and optional disposable
real-browser/Docker qualification. Built wheels/sdists must include the static UI
and remain usable without the source tree or Git. Structural specification checks
do not establish runtime conformance.

Current development qualification remains narrower than the full release target:
native macOS/Windows, ARM64/native MLMD builds, intended Docker Desktop variants,
exhaustive crash injection and full KFP parity need separate evidence. Distributed
network-filesystem locking, hostile multitenancy, GPUs, Kubernetes plugins,
parallel loops, recurring jobs and artifact payload previews/downloads remain
outside this delivered profile. No stable application release is claimed.

Dated evidence and requests live in [validation](validation/) and
[workflows](workflows/), including architecture, web interface, documentation,
readiness and next-capability workstreams. Their delivered scope was reviewed and closed under explicit authorization;
qualification limits remain recorded. Successful checks alone do not authorize
future workflow closure.
Task-specific review reports are kept under ignored `tmp/reviews/`, separate from
product documentation. They are not application/specification authorities.

The qualified service dependency set is FastAPI 0.136.3 with Starlette 1.9.0.
Starlette is declared directly because the service imports its parser and HTTP
utilities. The workspace lock includes certifi 2026.10.19, pytest 9.1.1 and
urllib3 2.8.0. KFP 2.17.0 still pins urllib3 2.7.0 upstream: the workspace uses an
explicit uv override and standalone KFP installations use
`tools/runtime-overrides.txt`. This is a tested installation exception, not an
upstream metadata/source modification; ordinary pip resolution retains the old
pin. Dependency audits use the exported lock and CI checks the full third-party
set. See the [installation instructions](../../docs/installation.md#kfp-dependency-override).

## Configuration inspection

New Run records expose a detached `effective_configuration.sources` map alongside
non-secret settings. It records file/environment/option/default/derived origins
and how the config file was selected. Native Run inspection and CLI JSON retain
admission-time provenance. Older snapshots without it remain readable without
backfilling guessed origins. OpenAPI documents the additive response field.

## Artifact library

`packages/artifacts` is the independently installable `dockflow-artifacts`
workspace member. It provides immutable publication and integrity checking on
filesystem/S3 stores, with optional standard KFP importer graph components. It
shares root VERSION, lock, tooling and release policy. It has no runtime dependency on
the CLI, Pipelines service or business component code. Its specification declares
the Pipelines contract used by the optional integration. S3 client construction
and credential discovery are deferred until explicit publication/verification;
configuration and package import do not initiate storage connections.

Publishing wrappers return URI parameters; `importer_component` creates a typed
importer in a nested graph, so native KFP 2.17 can resolve upstream-produced URIs
as parent inputs. Custom payloads are external references from the orchestrator's
perspective; publication manifests and retention belong to the custom store.
Ordinary managed output layout and ownership remain unchanged.

`execution.task_mounts` is trusted owner configuration, defaulting to read-only,
for explicit filesystem storage or secret delivery. Mounts cannot mask execution
paths. Mount paths/modes enter reuse identity; secret file contents do not. Change
inputs or disable reuse after changing external configuration that affects output.

The [library guide](../../docs/artifact-library/README.md) explains the API and
storage/KFP contracts. The [completed workflow](workflows/history/2026-10-20__1S3F02__artifact-library.md)
records publication, path-policy and integration delivery. Dated receipts retain
the tested mode/platform scope without making external integration fixtures a
source dependency.

## Exploration paths and package bookkeeping

Custom publication offers `publication_id`, `fingerprint` and `step_path`.
The path policy is `<exploration>/<pipeline>/step_<padded-number>__<component>__<publication-id>/<filename>`.
Pipelines supply their name, exploration (default global), ordered step number
and digit width computed from the total computational step count. Wrappers
supply component names/versions, resolved parameters, input fingerprints and
filenames. Context is passed as actual task inputs. Same inputs retain the same
path on native cache hits; changed inputs select another component directory.
Publication remains immutable and never provides its own execution cache.
Qualification fixtures derive component versions from script/wrapper/runtime build inputs.

Both artifact-root namespaces are now inside `.dockflow`: `dockflow-artifacts`
for publication claims/manifests/staging, and `dockflow-pipelines` for managed
recovery descriptors/imports. They are separate from project-root control state.
New managed descriptors use kfp-v2; earlier layouts remain readable/restorable.
Legacy publisher control roots must be explicitly reset or replaced. Selected
specification versions are recorded in the [composition](../specs/composition.yaml);
shared application VERSION remains a separate authority.

The [deterministic-publication qualification](validation/deterministic-publication-paths.json)
records local, Compose and native KFP path/hash parity and cache reuse. The
[specification consistency receipt](validation/specification-consistency-remediation.md)
records the subsequent configuration, S3 lifecycle and metadata corrections.
The [source-readiness receipt](validation/source-publication-readiness.md) owns
current publication checks and workflow closure, without repeating historical
test counts as evidence for later source.

Specification composition and immutable imported inventories are now checked by
CI using the pinned Macrostates tool. Package verification records observable Git
provenance and distinguishes missing provenance from a clean checkout; it does
not infer baseline acceptance or publication. The private-reporting policy is
selected in [SECURITY.md](../../SECURITY.md); enabling and verifying the hosting
setting belongs to the public-hosting setup and must be verified before
announcing the preview.
