# Configuration and backends

## Single model and validation

Use the same versioned TOML settings model in direct execution and service mode.
Execution mode and backend selection are independent. Components/pipelines are
compiled KFP definitions; image builds and compilation happen before Dockflow.
All settings/options are owned by Pipelines, not the shared executable.

The repository file is .dockflow-pipelines.toml with schema_version=1.
Unknown fields, duplicate/invalid values, unsupported schemas/backends and
inconsistent resource paths fail before persistent mutation. Do not interpolate
shell expressions or implicitly expand environment references in file strings.
Credentials are supplied through documented provider mechanisms, never committed.

Direct configuration selection is explicit --config, DOCKFLOW_PIPELINES_CONFIG,
then the nearest ancestor .dockflow-pipelines.toml from the current directory.
Failure of an explicit selection is an error; never fall back. Execution requires
a project configuration. Help/version require none and perform no runtime I/O.

The service requires --config or DOCKFLOW_PIPELINES_CONFIG and never searches its
working directory. It uses the same schema in a standalone deployment file;
implicit inheritance, arbitrary merges and hot reload are not supported.
Resolve settings at command/service startup. A running service retains its
effective configuration until restart; each Run captures its non-secret settings.

For each exposed setting precedence is explicit option, documented environment,
selected file, then default. Group --endpoint, DOCKFLOW_PIPELINES_ENDPOINT or
client.endpoint selects a service explicitly. --local overrides environment/file
endpoints and conflicts with explicit --endpoint. Without an endpoint select
direct execution; do not discover/start a service from lock files.

## Identity and path semantics

project.id is a required stable non-secret string of 1–128 ASCII letters, digits,
dots, underscores or hyphens, starting with a letter/digit. Commit it with project
configuration. Never infer identity from checkout location. When existing state
has a different project ID, stop before attaching to it.

A fresh project may select one stable project ID and a common persistent state
store from its first operation. Direct/service mode does not require different
project IDs or independent histories. The acquisition-specific `owner_id` in
SQL ownership diagnostics is a coordinator diagnostic and must not replace `project.id`.
Using a common store requires equivalent access to its configured metadata,
artifact and execution locations; changing mode does not remap historical file
URIs or migrate backend data. A service and direct process never own that state
concurrently; use the explicit service endpoint while the service owns it.

project.root defaults to the configuration file's directory. Resolve a relative
root against that directory. Resolve every other relative filesystem setting
against the resulting project root, regardless of process working directory.
Derived defaults follow the resolved state.directory. Normalize absolute paths
before ownership checks; server paths are server filesystem paths, not host paths.
Same-host bind-mount aliases still refer to the same underlying database ownership lock;
different path strings do not create independent writer permission. Qualification
requires local filesystem semantics as described in
[Execution](005_execution-and-lifecycle.md).

Configured control-state, work and managed artifact directories must be distinct,
with no overlap that lets work cleanup delete control state, published artifacts
or input sources. State defaults may contain db/ and work/ as documented; cleanup
must target their exact owned children. Work cannot equal or contain state,
metadata or the managed artifact root. Never follow input symlinks to bypass
declared source roots. Show resolved roots/mode before execution or deletion.

## Schema and defaults

All fields below are optional except schema_version and project.id.
Definition maps may be empty for direct file submission but entries must be
explicit; no recursive Python discovery is supported.

| Table | Fields and defaults |
| --- | --- |
| project | id required; root = configuration directory. |
| definitions | pipelines and components are name-to-compiled-file maps; empty by default. Names match [a-z][a-z0-9_-]{0,63}. |
| state | directory = ./.dockflow; backend = sqlite; database = state.sqlite beneath state; dsn_env required only for postgresql. |
| metadata | Legacy backend/directory settings are rejected; use state.backend and state.database. |
| execution | work_directory = work/ beneath state; task_parallelism = 1; timeout_seconds = 0; shutdown_grace_seconds = 30. |
| execution resources | cpu_limit and memory_limit_bytes omitted means no extra quota. Supplied values must be finite positive CPU cores / positive integer bytes. |
| images | pull_policy = if-missing; admitted values if-missing, always, never. |
| artifacts | backend = filesystem; managed_root optionally selects the exact managed directory; otherwise root = ./artifacts with managed contents below root/managed. external_roots = []; allowed_uri_prefixes = []. |
| artifacts S3 | endpoint and bucket required for s3; prefix = ""; tls_verify = true; allow_insecure_http = false. Filesystem root and managed_root are invalid with s3. |
| reuse | scope = global; scope_key absent. Scope is global, keyed, run or none; keyed requires a nonempty key. |
| policies | file absent; optional definition-keyed JSON policy described below. |
| client | endpoint absent; poll_interval_seconds = 1, finite positive. |
| client authentication | token_file and ca_file absent; tls_verify = true. Read the bearer token from its secret file; ca_file supplies additional trusted HTTPS roots. |
| service | host = 127.0.0.1; port = 8080; queue_capacity = 100; request_max_bytes = 16777216. |
| service authentication | token_file absent for the trusted private profile; otherwise require a secret-file bearer token and TLS termination under the service contract. |

Reject task_parallelism other than 1 initially. Queue capacity is a positive
integer counting waiting Runs, excluding the active Run. Ports are 1–65535.
Timeout zero means unlimited; other timeout/grace settings are nonnegative integer
seconds. Set service host to 0.0.0.0 explicitly inside the published container;
Compose host publication remains loopback by default.

Local file references require file:// URIs resolved to allowed external_roots;
remote inputs require a configured allowed_uri_prefixes entry. The managed store
is always an admitted source. Match URI scheme/authority and normalized path
segments, not a naive string prefix. A reference outside admitted sources is
rejected with a configuration explanation; it is never silently uploaded.
External roots may be mounted read-only in service mode.

For filesystem storage, `artifacts.managed_root` is the exact directory containing
the pipeline/run/task/attempt/output hierarchy; do not append `managed/`.
Resolve it against project.root.
The existing `artifacts.root` setting retains its parent-directory meaning, and
omitting both settings retains `./artifacts/managed`. Reject explicit root and
managed_root together, including combinations from file/environment/options.
Precedence applies within each setting, not across these alternative layouts.
Effective inspection exposes the resolved managed_root in either layout.

Managed storage must not overlap control state, metadata, work or external input
roots. Legacy root configurations retain protection of their whole base directory.
Publication, source admission, materialization protection, backup and restore
must all use the resolved managed directory. Changing a setting does not relocate
existing artifact URIs; use fresh state or a separately supported migration.
Reference artifacts keep their contents at their source and need no payload
directory. S3 uses bucket/prefix as its exact managed root, with the same
relative output hierarchy and separate recovery metadata described in
[artifacts](006_artifacts.md).

Filesystem and S3 providers satisfy the same [artifact contract](006_artifacts.md).
For S3 use the configured endpoint/bucket/prefix; do not infer an endpoint from an
artifact URI that supplies a different service. HTTP is allowed only when
allow_insecure_http explicitly selects that configured endpoint. tls_verify=false
is an explicit development relaxation recorded in effective configuration.

Use standard AWS-compatible credential discovery for the S3 adapter, including
AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, optional AWS_SESSION_TOKEN and selected
AWS_PROFILE/shared credential files. Registry access uses the Docker SDK's
documented credential configuration. Never forward these credentials to tasks
unless a separate task environment explicitly requires them.

Direct execution uses the Docker SDK's environment-based daemon connection
(DOCKER_HOST and supported TLS variables). Do not assume the SDK reads the active
Docker CLI context. The Compose profile supplies its dedicated inner socket.
Validate effective connection and image availability at execution preflight.

No build-context/image-build setting belongs in runtime configuration.
Components supply image references. Pull only according to images.pull_policy,
reject a missing image when policy=never, and record the actual image digest/ID
and platform before cache matching or execution. No implicit build, push,
repository scanning or image-reference rewriting occurs.

## Environment mapping

Prefix the following names with DOCKFLOW_PIPELINES_:

| Suffix | Setting |
| --- | --- |
| CONFIG | Configuration-file selection, not an ordinary field. |
| ENDPOINT | client.endpoint |
| PROJECT_ROOT | project.root |
| STATE_DIRECTORY / STATE_BACKEND / STATE_DATABASE / STATE_DSN_ENV | state.directory / state.backend / state.database / state.dsn_env |

| WORK_DIRECTORY | execution.work_directory |
| TIMEOUT_SECONDS / SHUTDOWN_GRACE_SECONDS | execution.timeout_seconds / execution.shutdown_grace_seconds |
| CPU_LIMIT / MEMORY_LIMIT_BYTES | execution.cpu_limit / execution.memory_limit_bytes |
| IMAGE_PULL_POLICY | images.pull_policy |
| ARTIFACTS_BACKEND / ARTIFACTS_ROOT | artifacts.backend / artifacts.root |
| ARTIFACTS_MANAGED_ROOT | artifacts.managed_root |
| S3_ENDPOINT / S3_BUCKET / S3_PREFIX | artifacts.endpoint / artifacts.bucket / artifacts.prefix |
| S3_TLS_VERIFY / S3_ALLOW_INSECURE_HTTP | artifacts.tls_verify / artifacts.allow_insecure_http |
| REUSE_SCOPE / REUSE_SCOPE_KEY | reuse.scope / reuse.scope_key |
| HOST / PORT | service.host / service.port |
| QUEUE_CAPACITY / REQUEST_MAX_BYTES | service.queue_capacity / service.request_max_bytes |
| POLL_INTERVAL_SECONDS | client.poll_interval_seconds |
| CLIENT_TOKEN_FILE / CLIENT_CA_FILE / CLIENT_TLS_VERIFY | client.token_file / client.ca_file / client.tls_verify |
| SERVICE_TOKEN_FILE | service.token_file |

Booleans accept only true/false (case-insensitive). Integers use decimal;
finite decimal CPU/poll values preserve their numeric type. Empty values are
invalid except S3_PREFIX, which may be empty. Do not interpret arbitrary prefixed
variables as nested settings. Record the source of each effective setting in
redacted inspection; never print secrets.

## Effective configuration inspection

Each newly admitted Run records `effective_configuration`, exposed by
`GET /dockflow/v1/runs/{run_id}` and `dockflow pipelines --json runs show RUN_ID`.
The CLI retains its normal JSON envelope: the snapshot is at
`result.effective_configuration`; native API resources expose it directly.
It contains the resolved non-secret settings and a `sources` object keyed by
TOML setting paths, such as `project.id`, `execution.timeout_seconds` and
`artifacts.managed_root`. Tables of registrations and mount lists are settings
as a whole, not separate provenance entries for each alias/list element.

Origin values are `file`, `environment`, `option`, `default` or `derived`.
Precedence selects the origin; converting a relative path to an absolute path
preserves its winning origin. Derived database/work locations and the managed
child of a legacy artifact root use `derived` when not explicitly configured.
Absent optional settings have no entry. `schema_version` has origin `file`;
`config_path` records selection by `option`, `environment` or `discovery`.
Resolved project/state/metadata/work paths are also exposed through the existing
`root`, `state`, `state_storage` and `work_directory` snapshot fields.

Token-file paths may be recorded, but token contents, provider credential values
and mounted file contents must never enter this snapshot or its origin mapping.
Inspection returns a detached value and never reloads current configuration to
reinterpret an accepted Run. Every new Run includes its origin mapping; the
current fresh-state format requires no backfill or migration.

## Definitions, policies and catalog refresh

Configuration's definition maps identify compiled files only; the KFP upload API
is a separate explicit registration source, not another configuration field.
Persist each registration's origin (`configuration` or `api`) and immutable
version associations. Both origins share the project pipeline-name namespace.
Reject a conflicting configured/API name without replacing the existing entry;
uploading a version into a configuration-owned pipeline is also a conflict.
Configured aliases retain their restricted name grammar; uploaded display/version
names use the API's Unicode name constraints instead.

Before using a configuration-owned registration, validate the requested source
and compare accepted content/profile within that catalog. Changed bytes create a
version after validation; previous versions and Runs stay unchanged. Explicit
definitions refresh reconciles only configuration-owned registrations, reporting
invalid/missing entries without erasing historical records. Removed/missing file
registrations become unavailable. A requested missing configured definition fails
even if a historical snapshot exists; select that historical version explicitly.
No background watcher or arbitrary-directory auto-registration exists.

API-owned pipelines and uploaded versions are retained independently of the
definition maps. Refresh must neither mark them unavailable for lack of a local
file nor change their default/version IDs. Their default resolves from the latest
committed upload, while a supplied version ID fixes a historical choice. Deleting
or rewriting an uploaded pipeline/version is not initially supported. Empty
definition maps therefore support a service populated entirely through uploads.

An optional policies.file is JSON with schema_version=1, definition_sha256 equal
to the exact accepted compiled-byte hash, and tasks keyed by qualified task path.
Each task may contain scope, scope_key, cache_safe and retry_safe only. Unknown
tasks/fields and stale definition hashes are rejected. cache_safe=false disables
reuse; true never overrides compiled cache disablement. retry_safe=true declares
that automatic repetition is safe under the component contract. Policies cannot
change graph edges, executors, computational parameters or artifact bindings.
[Reuse](008_reuse-and-selection.md) defines resolution and provenance.

## Client/service boundary

A remote CLI sends compiled IR or registered version references and execution
arguments. Server configuration owns daemon, storage, state, limits and paths.
A client path operand is read by the client and transmitted as compiled content;
it is not treated as a server path. Artifact reference registration is interpreted
in the executor's namespace; arbitrary artifact-byte client uploads remain
deferred. The bounded KFP multipart definition-upload API transports compiled
YAML/JSON only; it provides no dataset, component-image or source-tree transfer.

A service command never routes execution to client.endpoint. A mutating direct
command encountering service ownership stops and reports the explicit endpoint;
it does not auto-switch. SQLite and runtime dependencies are unnecessary for
remote-only client operations.

## Examples

Local .dockflow-pipelines.toml, with externally prepared compiled definitions
and images:

~~~toml
schema_version = 1
[project]
id = "example-project"
root = "."
[definitions.pipelines]
training = "pipelines/training.yaml"
[definitions.components]
prepare = "components/prepare.yaml"
[state]
directory = ".dockflow"
[execution]
work_directory = ".dockflow/work"
task_parallelism = 1
[images]
pull_policy = "if-missing"
[artifacts]
backend = "filesystem"
root = "artifacts"
external_roots = ["data"]
[reuse]
scope = "global"
~~~

Service configuration supplied through DOCKFLOW_PIPELINES_CONFIG=/etc/dockflow/pipelines.toml:

~~~toml
schema_version = 1
[project]
id = "example-project"
root = "/project"
[definitions.pipelines]
training = "pipelines/training.yaml"
[state]
directory = "/var/lib/dockflow"
[execution]
work_directory = "/execution"
task_parallelism = 1
[images]
pull_policy = "if-missing"
[artifacts]
backend = "s3"
endpoint = "http://minio:9000"
bucket = "dockflow-artifacts"
prefix = "example-project/"
allow_insecure_http = true
external_roots = ["/inputs"]
allowed_uri_prefixes = ["s3://source-data/training/"]
[service]
host = "0.0.0.0"
port = 8080
queue_capacity = 100
~~~

The two modes share compiled definitions. The service example's configured
definitions are mounted under /project; alternatively omit its definitions map
and register the same compiled documents through the KFP API. Embedded components
use images available to its daemon; source-data must exist on the configured S3 endpoint.
Do not create example databases, buckets, credentials or deployments merely by
loading these examples. [Acceptance](011_acceptance.md) owns verification.

## Explicit task storage mounts

`execution.task_mounts` is an optional array of tables with `source`, optional
absolute `target` (defaults to the resolved source path), and boolean `read_only`
(default true). Resolve relative sources against project.root. At most 32 mounts
are supported; reject duplicate sources/targets and root or traversing targets.
At execution, sources must be existing regular files/directories without symlink
ancestry. Targets must not overlap KFP runtime mounts or one another. Mount paths
and modes participate in execution signatures; file contents are not read into
configuration, journals or signatures. Mounted mutable data is not a tracked
artifact: pass dataset/model inputs through artifact bindings, and invalidate
reuse explicitly after changing publication settings.

Only trusted owner configuration can grant mounts. Compiled definitions and API
submissions cannot request them. They support custom publication roots and
read-only secret configuration files without embedding credentials in IR. The
Docker daemon must see sources at the same paths as the owner; service deployments
must arrange matching bind mounts/shared volumes. No implicit host-directory or
Docker socket access is granted. Existing execution defaults are unchanged.

## Distributed cache extension

The optional `[cache]` table and `DOCKFLOW_PIPELINES_CACHE_*` mapping are owned by
[Cache coordination](014_cache-coordination.md#20-dockflow-configuration-and-existing-contracts).
Cache tables and execution-state tables MUST occupy the same physical database,
selected only by `[state]`. Cache policy does not define another connection.

## Database state configuration

[Metadata and recovery](007_metadata-and-recovery.md) owns SQL authority and
ownership. Effective configuration exposes state_storage with only backend,
resolved SQLite database path or DSN environment-variable name. The old metadata
table is rejected to prevent interpreting a former MLMD index as authoritative
SQL history. Default SQLite needs no additional service or native metadata SDK.
PostgreSQL configuration is:

```toml
[state]
backend = "postgresql"
dsn_env = "DOCKFLOW_STATE_DSN"
directory = ".dockflow"
```

Both repositories MUST use the same database abstraction and state connection
configuration. Reject `cache.backend`, `cache.registry` and `cache.dsn_env`,
including their former environment overrides; no split-database mode is supported.
For disposable cross-host environments, select PostgreSQL and commonly accessible
artifact storage. Work directories remain local and disposable.


## Run ownership configuration

`state.backend=sqlite` selects the local one-owner model; `postgresql` selects
cross-host synchronization through the same configured database for state/cache.
No independent execution deployment-mode flag is supported. PostgreSQL requires
commonly accessible artifact storage and a Docker daemon usable by each active
coordinator. Database access does not grant access to another daemon.

`execution.run_lease_seconds` defaults to 120 and `run_heartbeat_seconds` to 30.
Both must be finite and positive; lease must exceed heartbeat plus the ten-second
database-timeout safety margin. The corresponding environment variables are
DOCKFLOW_PIPELINES_RUN_LEASE_SECONDS and DOCKFLOW_PIPELINES_RUN_HEARTBEAT_SECONDS.
These govern PostgreSQL Run ownership; SQLite retains lifetime local ownership.
One Run per coordinator and sequential tasks per Run remain the initial local
limits; multiple PostgreSQL coordinators provide concurrent Runs.

Capabilities expose active_runs=1 with active_runs_scope=project for SQLite and
active_runs_scope=coordinator for PostgreSQL; concurrent_postgresql_runs identifies
the distributed feature. Direct PostgreSQL submissions reserve their Run in the
admission transaction so queue workers cannot steal that Run before foreground
execution begins. Only that pinned coordinator may adopt its live reservation;
after expiry another coordinator may claim accepted unstarted work.


Configured CPU and byte-memory caps must remain positive when converted to
Docker nanocores/bytes and fit signed 64-bit limits. Reject underflow and
unrepresentable quotas during configuration loading.
