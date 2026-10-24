# Dockflow implementation

## Phase and identity

Project phase: **active**. The Definer accepted the first bounded implementation
baseline and this phase transition on 2026-10-22. The
[release declaration](release.yaml) proposes `imp-0.1.1` against `specs-0.1.0`;
selected specification package versions belong to the
[composition](../specs/composition.yaml). The
[initial release review](validation/initial-release.md) records delivered scope,
qualification evidence and explicit limits.

Application version `0.1.1` is the coordinated security maintenance candidate.
Only the earlier CLI 0.1.0 was uploaded; its image candidate was withdrawn.
The [release plan](release-plan.yaml) collects accepted patch maintenance against
unchanged `specs-0.1.0`; reviewed integration finalizes `imp-0.1.1`.
Existing 0.1.0 tags and uploaded files retain their original identities.
Annotated tags, exact-candidate approval and registry uploads are separate gates.
Git commits identify source snapshots independently. The closed
[release preparation](workflows/history/2026-10-22__15R7ZS__pypi-release.md) records
acceptance and local qualification. Subsequent CI, integration and publication
evidence belongs to the hosting system and release assets. Earlier workflows
remain in [history](workflows/history/). Imported specification snapshots remain
unchanged.

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
Base client imports remain independent of optional Docker/KFP/PostgreSQL/server extras.

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

SQLite retains one project owner and a durable FIFO queue, with one active Run
and attempt. PostgreSQL permits independent coordinators to claim different Runs;
each coordinator dispatches one Run at a time. Each Run receives a spawned worker process for KFP's process-global
state. Workers call owner-side state/artifact operations over constrained RPC;
HTTP request threads do not reinitialize KFP. Shutdown records stop intent,
confirms termination and retains queued work. Startup reconciles uncertain prior
containers before dispatch. SQLite direct CLI refuses unresolved/queued execution until explicit recovery;
PostgreSQL direct submissions reserve their own Run during atomic admission. No automatic crash rerun is implied.

## Persistence and artifacts

`packages/database` now owns the common SQLite/PostgreSQL drivers, physical schema,
maintenance gates and immutable artifact-record repository. Pipelines and standalone
Artifacts use that package. Publication claims/manifests and recovery descriptors
are SQL-only; artifact storage retains payloads and `.dockflow/storage.json`.
The physical schema is version 4; no existing-data migration is supplied.
Standalone filesystem publication defaults to a SQLite file beside its root;
remote stores require explicit database configuration. Project backups preserve
these records and the managed root, verify completed publications and refuse
additional unrepresented roots. See the [artifact-record validation](validation/database-artifact-records.md)
for qualification and limits.

Domain repositories now use numeric journal sequences, one resource projection,
explicit definition/attempt identities and named project metadata. File-shaped
control keys, the optional SQLIndex wrapper and Pipelines database/error import
facades are removed. Definition/log snapshots validate explicit IDs; rebuild
repairs all domain projections and removes orphaned resource rows without losing
numeric aliases, publication facts or cache history. The
[cleanup validation](validation/domain-persistence-cleanup.md) records qualification.

`metadata.py` coordinates a database-authoritative accepted journal, resource
projections, complete output-set commits, source snapshots, logs and maintenance.
`state_database.py` uses the shared database adapter for state transactions,
query projections, persistent KFP numeric aliases and execution ownership. SQLite uses
a stable local database inode; PostgreSQL uses shared maintenance sessions and
fenced per-Run leases across isolated coordinators. Journal and projections commit atomically. Native MLMD and JSON
history trees are no longer runtime stores/dependencies. Fresh state is required;
old file history is intentionally not migrated. See the
[database-state validation](validation/database-execution-state.md) for measured
coverage and deployment limits. PostgreSQL environments retain
full shared history without a local durable state directory. SQLite retains its
single owner; PostgreSQL executes different Runs concurrently across coordinators.

`canonical.py` owns typed canonical JSON hashing; `reuse.py` owns equivalent
signature selection and integrity checks. `artifacts.py` provides filesystem and
S3-compatible managed stores, external references/imports, inventory checking and
explicit pins. Ordinary managed outputs use pipeline/run/task/attempt-UUID/output paths below the
resolved managed_root or S3 bucket/prefix; coordinated outputs use the reserved
cache namespace described below. Recovery descriptors live in SQL. Administrative
managed imports keep their payloads under `.dockflow/dockflow-pipelines`; the
supported `artifacts.root` setting retains its `managed/` child. Reuse keeps the
original producer URI. Admission, publication and backup/restore share the
resolved root and explicit current layout. Unsupported earlier layouts are
rejected. Reference payloads remain at their sources. Owner-side transfers keep storage credentials out of ordinary
task containers. See [persistence](../../docs/persistence.md) and
[artifacts](../../docs/artifacts.md) for recovery and URI/path limits.

The [cleanup validation](validation/domain-persistence-cleanup.md) records the
current implementation and qualification. Earlier dated receipts retain their
historical scope; their split connections, import facades and file-shaped SQL
records no longer describe the current implementation.

## Coordinated artifact cache

`dockflow_database.database` supplies common SQLite/PostgreSQL connections, dialect, durability,
schema initialization, clock, row locks and driver failure classification.
`dockflow_database.database_schema` defines the shared versioned physical schema.
`cache_registry.py` implements coordination in the same configured database as
execution history. Entry locking serializes reuse, idempotent
claims, database-clock leases, monotonic fences, complete publication and durable
retry episodes. SQLite uses local WAL/FULL synchronization; PostgreSQL uses a
fresh locking statement after unique insertion and bounded primary transactions.
Independent local staging roots connected to the same database/project share
history and cache. SQLite retains a project owner; PostgreSQL uses per-Run owners.

`cache.py` bounds waits and supervises heartbeats independently through execution,
validation and transfer. `cache_storage.py` defines portable complete manifests.
`artifacts.py` binds a persistent store identity, seals unique versioned outputs,
uses conditional S3 writes and recovers identical finalization acknowledgments.
The engine verifies an entire manifest before recording a hit. Cache production
bypasses legacy historical discovery; omitted prerequisites can resolve without
claiming computation. Publication passes through the journal owner to order it
against stop intent. Registry success survives a later journal/projection failure;
atomic cache-provenance import retains original producer/artifact IDs without
creating a consumer attempt. Original local producer metadata is preserved during
cache-backed recovery.

CLI/API inspection exposes the selected artifact, lease/producer history,
freshness and shared retry state. Invalidation/reset require expected identities
and preserve bytes and fences. Signature and storage namespaces isolate legacy
writers; unregistered historical results are misses, while explicit manual
historical inputs retain full verification. Configured scope policy and actual
store identity must agree before dispatch; registry failure has no unlocked fallback.

Published cache eviction and automated orphan cleanup remain disabled. SQLite is
local-host only; PostgreSQL requires common artifact access. Coordinated S3 files
are limited to 5 GiB each. Project backup exports history and all project cache namespaces in one consistent
SQL snapshot, plus cache-only managed bytes and store identity. Restoring older
history requires stopped workers and a fresh cache namespace before dispatch. Physical multi-host and non-Linux native
qualification remain outside the recorded local evidence. See the
[cache qualification receipt](validation/distributed-artifact-cache.md) and
[configuration guide](../../docs/configuration.md#coordinated-artifact-cache).

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

Unreleased graph presentation renders one native DAG level at a time. Subpipeline
nodes expose their exact task details and open into child graphs; breadcrumbs,
deep links and browser history preserve scope. An explicit All tasks view retains
the full dependency/containment projection. Both views are bounded to 1,000 visible
nodes. Execution, persisted task identity, attempts, reuse and lineage are
unchanged. This specializes the existing nested-graph UI contract; it introduces
no specification baseline or API change. See the
[active amendment](workflows/history/2026-10-22__1X7CB4__collapsed-pipeline-graphs.md).

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

Execution qualification remains narrower than the full release target:
native macOS/Windows execution, ARM64 runtime builds, intended Docker Desktop variants,
exhaustive crash injection and full KFP parity need separate evidence. Distributed
network-filesystem locking, hostile multitenancy, GPUs, Kubernetes plugins,
parallel loops, recurring jobs and artifact payload previews/downloads remain
outside this delivered profile. The initial versioned release retains these limits; publication remains pending.

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
set. Python 3.13.17, uv 0.13.5 and gRPC 1.84.1 address the CA incident.
`tools/check_ca_trust.py` verifies the effective certifi/gRPC bundles and
pip/ensurepip data; service builds also check dormant SDK and system bundles.
The official publisher uses its upstream patched certifi/Sigstore runtime. S3 defaults use maintained certifi, retaining explicit custom
CA configuration. Rebuilt executor/registry stores remove the affected roots
without a registry-major migration. See the [installation instructions](../../docs/installation.md#kfp-dependency-override).

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

Publication claims/manifests and recovery descriptors reside in SQL. Artifact
storage retains the store identity, payloads and disposable staging. Administrative
imports and coordinated cache payloads retain their reserved `.dockflow` locations.
Managed descriptors use the explicit `kfp-v2` or `cache-v1` layout; earlier layouts
and database formats require fresh state. Selected
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

## Release automation

Root VERSION synchronizes distribution versions, the exact Pipelines→CLI
requirement, workspace metadata and the service label. Package READMEs use
absolute public documentation links so their PyPI rendering works independently
of a checkout. The required KFP/urllib3 override remains an explicit installation
policy; wheel metadata does not silently patch upstream requirements.

The candidate workflow builds and verifies package artifacts, supplies those
wheels to the service Dockerfile through a named build context, smoke-tests the
result, and saves that exact image with a SHA-256 manifest. The publishing
workflow checks successful canonical-main candidate provenance and the manually
reviewed manifest hash before protected OIDC jobs. CLI publishes first;
Pipelines and Artifacts use distinct environments, as required for pending PyPI
project creation. Image/release publication follows all package uploads.

`tools/release.py` verifies bundle inventories, hashes, exact source/baseline tags
and existing PyPI file identity. `tools/verify_service_image.py` owns disposable
engine/volume/image qualification resources. `tools/publish_release_record.py`
loads the preserved image and refuses conflicting registry/release identities.
Publication uses the official pinned PyPA v1.14.3 action, whose upstream CA fix
covers the effective certifi/Sigstore trust path. No custom publisher is retained.
Application/implementation tags bind the exact candidate commit; an unchanged
specification tag must be ancestral with an identical specification tree.
See CONTRIBUTING for release operations and workflow records for verification
and approval state.


## Concurrent PostgreSQL execution

`state.backend` selects SQLite single ownership or PostgreSQL per-Run coordination.
`run_ownership.py` implements database-time leases, renewals and fenced authority;
`state_database.py` checks authority at transaction entry and before commitment.
A durable project counter allocates journal sequences. Admission, idempotency,
queue limits, catalog changes and cancellation use short project transactions.
Direct admission reserves its Run atomically so background services cannot claim
it first. Each coordinator retains one active Run and tasks remain sequential.

Scheduler recovery skips live remote Runs and handles only abandoned claims,
verifying and retiring their original Docker handles. A failed recovery leaves
that Run unresolved without globally blocking unrelated PostgreSQL execution.
Maintenance gates exclude other coordinators and independent cache transactions.
Portable backup retains project counters but excludes operational Run claims.
Committed cache observations preserve immutable producer facts without changing
another Run owner's live execution records.

The [concurrent execution receipt](validation/concurrent-postgresql-runs.md)
records current tests and deployment qualification. Earlier state/cache/unified
receipts retain their dated measurements; their PostgreSQL single-owner model
is superseded by this feature. No migration or application release is implied.


## Conformance corrections

The [conformance correction record](validation/conformance-corrections.md) maps
all eight review findings and the design recommendations to current contracts,
implementation and qualification. Scheduler supervision now revokes admission on
failure. Named definitions follow the catalog pointer. Versioned immutable
execution choices bind to current deployment access, and shared lifecycle
transitions complete recovery Tasks while preserving committed output sets.

Selective repositories push resource paging/filtering, queue eligibility,
idempotency/catalog/signature lookups and log ranges into SQL on both backends.
Physical schema 5 retains canonical JSON text, normalized input/log projections
and query indexes. Portable backups identify `dockflow-sql-v4`. Checks compare
all derived projections and the authoritative counter; rebuild preserves aliases,
publication records and cache fences. Fresh state is required; no migration is
provided. Compiled-source capture and filesystem publication now enforce their
bounded/stable and ancestor-durability boundaries.
