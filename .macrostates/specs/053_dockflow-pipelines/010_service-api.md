# Service and HTTP API

## Service boundary

The service exposes the same application core as direct CLI execution. One
instance serves one configured project/state root and holds its exclusive
execution ownership lock. It admits a durable FIFO queue of at most 100 waiting
Runs by default, executes at most one Run, and rejects competing owners. Task
parallelism within that Run follows [Execution](005_execution-and-lifecycle.md).
Do not add a separate broker or let HTTP request threads reinitialize KFP's
process-global configuration. Use isolated run worker processes.

`dockflow pipelines --config PATH serve` explicitly starts the service. Default
bind is `127.0.0.1:8080`; the generic image explicitly binds `0.0.0.0:8080`, with
reference Compose publishing only `127.0.0.1:8080`. Container bind and host
publication are separate settings. The image supplies installed runtime/service
dependencies; project definitions/configuration and durable volumes are supplied
by deployment. Components remain in their separate images. No source checkout,
image build, Git operation or implicit infrastructure launch occurs on submission.

The initial trust model is a trusted single-project installation. Authentication
is disabled only for the loopback/private default deployment. For exposure beyond
that boundary, require a configured bearer token and TLS through a reverse proxy;
read the token from `service.token_file`. Compare secrets safely, reject missing/invalid
credentials, and redact them. A token grants project-level access; no user/RBAC,
Kubernetes authentication, public signup or multi-tenant sandbox is promised.
Disable CORS by default. The proxy must preserve the configured base path.
The reference Compose container's `0.0.0.0` bind with loopback-only host publication
remains the explicit trusted private profile; it does not itself require a token.
Clients use `client.token_file`, optional `client.ca_file`, and default-true
`client.tls_verify` according to Configuration. Static bearer access is a basic
project guard, not enterprise authentication.

The packaged [web interface](013_web-interface.md) exposes public static shell
and asset routes only; it does not expose project records through unauthenticated
HTML. The native data APIs and OpenAPI JSON retain bearer protection when enabled.
Reject mutation requests carrying a foreign browser Origin. CLI/KFP clients
without Origin retain the established HTTP contract. The read-only API explorer
is served locally at `/dockflow/v1/docs` without external CDN assets.

On shutdown, stop admission, interrupt active work under the execution contract,
and preserve queued Runs for restart. Default graceful shutdown budget is 30
seconds; persist recovery evidence before exit and reconcile unknown containers
on restart. Do not mark a Run succeeded because its worker disappeared.

## Wire conventions

The native JSON API prefix is `/dockflow/v1`. Names use `snake_case`; request and
response content type is `application/json; charset=utf-8`. Accept only UTF-8 JSON
objects as native request bodies. The two explicit KFP definition-upload routes
below are the sole multipart request exception; responses still use official JSON
resources/errors. Reject duplicate object keys, non-finite numbers,
unknown request fields, invalid enum values and unsupported executable semantics.
Portable integer JSON values are limited to `-(2^53-1)` through `2^53-1`,
including parameters and metadata; reject values outside this exact KFP range.
The default body-size ceiling is 16777216 bytes. Enforce it before parsing and
while receiving bodies, including all multipart framing/headers; reject oversize
requests with 413. Never trust Content-Length alone. There is no general artifact
or component-image binary-upload API, archive extraction or arbitrary URL-fetch API.

Public IDs and schema/hash rules follow [Metadata](007_metadata-and-recovery.md).
IDs identify resources in this project; never reinterpret another project's ID
as a filesystem path. Timestamps are UTC RFC3339 strings; unset timestamps/error
are `null`. JSON maps preserve parameter types; metadata is JSON, not executable
Python. Requests cannot override server backend credentials, Docker endpoint,
workspace, state root or artifact destination.

List queries accept `page_size` (default 50, range 1–200) and opaque `page_token`.
The response is `{items: [...], next_page_token: string|null}`. Sort by
`created_at` descending then public ID ascending; lists without creation times
use name then ID ascending. Tokens bind project, filters and ordering, represent
a stable pagination boundary, and reject tampering/mismatched queries. Concurrent
new records must not duplicate already returned records. Unspecified filtering
and sorting syntax is rejected rather than silently ignored.

All error responses have `{error: {code, message, details, request_id}}`, where
`code` is a stable uppercase machine code, `details` is an array of objects with
required `field` and `reason` strings, and `request_id` correlates redacted service
logs. Existing field/reason-only entries remain valid. An ownership-conflict
detail additionally has this typed shape:

```json
{
  "field": "state.directory",
  "reason": "owner_conflict",
  "state_directory": "/resolved/state",
  "owner_metadata_status": "valid",
  "owner": {
    "schema_version": 1,
    "owner_id": "ca75cabb-4b54-4a45-8c03-3e63304e1101",
    "hostname": "execution-environment",
    "pid": 123,
    "mode": "service",
    "project_id": "example-project",
    "acquired_at": "2026-10-19T19:29:00Z",
    "endpoint": "http://127.0.0.1:8080"
  }
}
```

`owner_metadata_status` is `valid`, `legacy`, `malformed`, `oversized`,
`unavailable` or `unsupported_schema`. The `owner` object contains only recognized,
validated diagnostic fields from the bounded read; fields not safely available
may be absent. Never include arbitrary file contents, unknown keys, credentials
or control-character injection in a contention response. The schema, lock
authority, supported filesystem scope and lifecycle belong to
[Execution](005_execution-and-lifecycle.md). Owner diagnostics are not a lease,
automatic endpoint routing or proof that a physical machine is alive.

A lock-capability/I/O failure uses `UNAVAILABLE` with a detail whose
`field` is `state.directory`, `reason` is `ownership_lock_unavailable`, and
additional fields are `state_directory` (string), `operation` (`open`, `acquire`,
`metadata_write` or `release`) and `errno` (integer or `null`). This describes
the failed OS operation without misreporting it as a competing owner or exposing
raw diagnostic contents.

Statuses:
400 `INVALID_ARGUMENT`, 401 `UNAUTHENTICATED`, 403 `PERMISSION_DENIED`, 404
`NOT_FOUND`, 409 `CONFLICT`/`OFFLINE_REQUIRED`, 410 `LOGS_UNAVAILABLE`,
413 `REQUEST_TOO_LARGE`, 422
`UNSUPPORTED_CAPABILITY`, 429 `QUEUE_FULL`, 500 `INTERNAL`, 503 `UNAVAILABLE`.
Do not return stack traces, secret values or an ordinary success body on errors.
Use 405 for an unsupported HTTP method on an existing resource and 501
`UNIMPLEMENTED` for known deliberately unsupported compatibility operations.

`Idempotency-Key` is supported on native Run creation. Keys are opaque ASCII
strings of 1–128 characters. Persist the key, canonical validated request digest,
and accepted Run ID atomically with queue admission. Same key and request returns
the original Run; same key with a different request returns 409. Preserve keys
with run records through restart and metadata reconstruction; no automatic expiry
initially. Failure before durable admission creates neither a Run nor a claimed
key. Missing keys create independent Runs; clients must retain keys across retries.

## Native request and resource models

Defaults below are applied before canonical request hashing. All unlisted request
fields are invalid. The implementation must publish OpenAPI 3.1 describing these
constraints and the complete response resources; it must not invent a different
wire contract while implementing the examples.

| Model | Fields and constraints |
| --- | --- |
| `RunCreate` | Exactly one of `definition_id` or `pipeline_spec` (compiled JSON object); optional `source_text` with `pipeline_spec`, `display_name`, `experiment_id`, and `description` (empty default, at most 4096 characters); `parameters` maps declared parameter names to JSON values (default `{}`); `inputs` maps supported root artifact names to artifact IDs (default `{}`); `selection`, `bindings`, `use_executions`, `reuse` below. |
| `Selection` | Default `{mode: "full"}`; `mode: "from"` requires `task`; `mode: "tasks"` requires nonempty unique `tasks` array. Other combinations are invalid. Selectors are exact slash-qualified compiled task paths from Execution. |
| `Bindings` | Object mapping `TASK.INPUT` to artifact IDs; default `{}`. The planner checks type, lineage availability and selected-graph prerequisites. |
| `UseExecutions` | Object mapping task names to successful historical attempt IDs; default `{}`. The planner checks complete compatible outputs and conflicts with explicit bindings. |
| `ReusePolicy` | `{scope: "global"|"keyed"|"run"|"none", key?: string}`; scope defaults to configured `reuse.scope`, otherwise `global`; for `keyed`, explicit `key` overrides configured `reuse.scope_key` and the result must be nonempty. Other scopes reject an explicit key and do not inherit a configured key. |
| `ArtifactCreate` | Required `operation` (`register` or `import`), absolute supported `uri`, and `type: {schema_title, schema_version}`; optional human data-revision `version` and `metadata` object (default `{}`). Reserved metadata namespace is forbidden. |
| `ExperimentCreate` | Required project-unique nonempty `display_name`; optional `description` (default empty). Names are 1–256 Unicode characters; descriptions at most 4096. |
| `MaintenanceRequest` | `{apply: boolean}` with `false` default; unknown fields rejected. Apply requires no active Run, pauses admission during the operation, and revalidates all safety conditions. |
| `ValidationRequest` | Exactly one of `definition_id` or compiled `pipeline_spec`; optional matching `source_text`, `parameters` and `inputs` maps to validate submission bindings without executing. |

When provided, `source_text` is the original UTF-8 YAML/JSON definition. Parse it
safely and require the same normalized compiled object as `pipeline_spec`; reject
conflicts. File-submitting CLI clients send it so the original source survives
transport. Without original text, retain the received compiled JSON representation
and identify its source format as JSON; do not claim to reconstruct an absent
compiler file's comments or formatting.

`Run` responses contain `run_id`, `project_id`, `definition_id`, `experiment_id`,
`display_name`, `state`, creation/start/finish timestamps, the resolved request
fields, `task_ids`, published `outputs` map, and nullable `error`. Expose
`idempotency_key` when present. Accepted Runs retain an immutable compiled snapshot
and required versioned `execution_choices` as defined by
[Execution](005_execution-and-lifecycle.md#supervision-and-accepted-execution-choices).
Expose `effective_configuration` as defined by
[configuration inspection](003_configuration-and-backends.md#effective-configuration-inspection),
including setting origins for newly admitted Runs. Native Run states are `queued`, `running`,
`cancelling`, `succeeded`, `failed`, `cancelled`, `interrupted`. Publication must
be committed before success.

`Task` responses contain `task_id`, `run_id`, `name`, `component_id`,
`definition_id`, `state`, input/output artifact maps, ordered `attempt_ids`,
reuse/source-producer information and nullable `error`. Task states are `pending`,
`running`, `reused`, `skipped`, `blocked`, `succeeded`, `failed`, `cancelled`,
`interrupted`. An `Attempt` contains its ID, task/run IDs, timestamps, execution
image identity, exit status, publication state, bindings, logs reference and error.
Never fabricate an attempt or new artifact producer for a reused task.

`Pipeline` is the stable named catalog resource, distinct from an immutable
`Definition`. It contains `pipeline_id`, `name`, current `definition_id`,
`available` and `created_at`; registration records also expose origin
(`configuration` or `api`), `default_version_id`, and their retained description/
version associations when present. The native current-version pointer follows
the same catalog as the KFP adapter. Reading a pipeline never refreshes source
files or changes its default. Discover its immutable versions through the
definitions list's exact `pipeline_id` filter.

`Definition` contains `definition_id`, `kind`, registration `name`, `sha256`,
`created_at`, `available`, parsed compiled document and compatibility diagnostics;
pipeline versions also expose stable catalog `pipeline_id` (null for unregistered
inline definitions), `registration_origin` (`configuration`, `api`, or null),
nullable `version_name`, version `description` (empty default), and nullable
`default_version_id` identifying its catalog's current default at inspection
time. The default pointer/availability are observations; they do not mutate the
snapshot's bytes, version name or association. Component entries expose
`component_id`. Registered names resolve to current immutable versions, including
API-owned names absent from the server's configured file maps.
Historical snapshots remain addressable after source edits/removal.

`Artifact` exposes `artifact_id`, `type`, `version`, `metadata`, `origin`, URI,
fingerprint, availability, publication state, producer/input provenance, creation
time and explicit pin state. It does not contain payload bytes. `Experiment`
contains `experiment_id`, `display_name`, `description`, `created_at` and latest
Run creation time. Read models preserve all mandatory lineage and integrity
fields defined by Artifacts and Metadata even where this overview abbreviates
their nested structure.

`ArtifactLineage` contains `artifact_id`, nullable original `producer`, `items`
(a page of Task resources whose recorded named inputs contain this artifact ID),
and nullable `next_page_token`. The producer retains its actual Run/Task/attempt/
definition/output references. An external artifact has no computational producer.
Reused outputs do not fabricate a new producer. Consumer results describe actual
recorded input bindings, not transitive dependence or an inferred execution.
Apply the ordinary bounded pagination and filter-bound token rules.

## Native routes

All paths below are relative to `/dockflow/v1`. `GET` returns 200. Native creates
return 201 except queued Run admission (202); replayed Run admission returns 200.
Idempotent state operations return the current resource with 200. There is no
delete-history route.

| Method and path | Request / result |
| --- | --- |
| `GET /capabilities` | Actual application/KFP versions, qualified profile/features/backends, service limits and project ID; never credentials. |
| `GET /pipelines` | Optional exact `name` filter; page of stable Pipeline catalog entries. |
| `GET /pipelines/{pipeline_id}` | Pipeline, including its current default/definition reference and source origin. |
| `GET /definitions` | Optional exact `name`, `pipeline_id` and `kind` (`pipeline` or `component`) filters; page of immutable definition versions. |
| `GET /definitions/{definition_id}` | Immutable Definition. |
| `POST /definitions/validate` | `ValidationRequest`; `{valid, diagnostics, required_capabilities}`; invalid syntax/types use 400 and unsupported semantics 422. |
| `POST /definitions/refresh` | Empty object; refresh configuration-owned server definitions; return added/updated/unavailable IDs and diagnostics; preserve API-owned entries/defaults. |
| `GET /components` | Optional exact `name` and `definition_id`; page of component definitions. |
| `GET /components/{component_id}` | Component catalog identity and definition, including contracts indexed from uploaded pipelines; historical snapshot via definition ID. |
| `POST /runs` | `RunCreate`; durable acceptance returns Run plus `Location` header. |
| `GET /runs` | Page; optional exact `state`, `experiment_id` and `definition_id`. |
| `GET /runs/{run_id}` | Run with resolved plan and current task references. |
| `POST /runs/{run_id}/cancel` | Empty object; queued Runs become cancelled; active work enters cancellation; terminal Runs remain unchanged. |
| `GET /tasks` | Page; optional exact `state`, `run_id` and `input_artifact_id`; the artifact filter matches recorded named input values. |
| `GET /tasks/{task_id}` | Task, including all ordered attempt references. |
| `GET /attempts` | Page; optional exact `state`, `run_id` and `task_id`. Attempt states are `running`, `publishing`, `succeeded`, `failed`, `cancelled` and `interrupted`. |
| `GET /attempts/{attempt_id}` | Attempt and its publication/error details. |
| `GET /artifacts` | Page; optional exact `type` title and `availability` (`available`, `missing`, `inaccessible`, `corrupt`, `deleted`, `unknown`). |
| `POST /artifacts` | `ArtifactCreate`; complete validation/fingerprinting or managed copy, then return Artifact. |
| `GET /artifacts/{artifact_id}` | Artifact and current availability observation. |
| `GET /artifacts/{artifact_id}/lineage` | `ArtifactLineage`: original producer plus paginated actual consumer Tasks; normal `page_size`/`page_token`, 404 for an unknown artifact. |
| `POST /artifacts/{artifact_id}/pin` / `/unpin` | Empty object; idempotent explicit retention pin update. |
| `GET /experiments` | Page; optional exact `name` filter. |
| `POST /experiments` | `ExperimentCreate`; duplicate display name returns 409. |
| `GET /experiments/{experiment_id}` | Experiment. |
| `GET /runs/{run_id}/logs` | Optional `task_id`, `attempt_id`, `cursor`, `limit_bytes`; bounded LogPage below. |
| `POST /metadata/check` | Optional `{verify_contents: boolean}` (false default); read-only consistency/recovery/availability report. |
| `POST /metadata/rebuild` | `MaintenanceRequest`; dry-run reconstruction plan only; `apply: true` returns 409 `OFFLINE_REQUIRED`. |
| `POST /clean` | `MaintenanceRequest`; eligible cleanup plan or applied report, including protected/deleted counts and roots. |

Definition refresh, upload registration and metadata/artifact mutation are serialized through the
owner. Reject mutating maintenance with 409 while a Run is active; do not race it
against publication. Immutable upload registration may occur while a Run is
active, serialized by the owner; it does not change any already accepted Run's
version or plan. Read-only checks/plans use consistent snapshots and label
changing/unverified observations. External URI registration/import observes the server's explicit
allowed roots/prefixes; no request can scan arbitrary server directories.
Applying a metadata rebuild requires stopping the service and invoking the
direct owner-exclusive operation; a running HTTP process cannot replace its
active projections through this route.

`LogPage` is `{entries, next_cursor, terminal}`. Each entry has increasing durable
`sequence`, UTC `timestamp`, `run_id`, nullable task/attempt IDs, `stream`
(`stdout`, `stderr`, `system`) and UTF-8 `text`. Use replacement markers for invalid
UTF-8. Default/max `limit_bytes` is 65536; fragment oversized lines and retain
their sequence continuity. `terminal` means the Run is terminal and this cursor
has drained retained logs. Return 404 for unknown Runs and 410 with
`LOGS_UNAVAILABLE` when requested logs were explicitly removed. Do not silently
return an empty successful stream for unavailable history. Clients poll; SSE,
WebSockets and infinite HTTP streams are outside the first profile.
The DockerRunner adapter persists stdout/stderr incrementally while tasks run.
Polling can therefore retrieve output before task completion; it remains a
bounded page API, not an SSE/WebSocket connection. Component-side buffering can
delay output until that component flushes. Retain emitted ANSI color sequences
in raw log text; clients may render colors or strip them for display.

`GET /health/live` and `GET /health/ready` are unprefixed deployment probes.
Liveness reports process health without contacting dependencies. Readiness
returns 200 only after configuration, ownership, recovery and required backend
checks permit admission; otherwise 503. Both responses contain `status` and
redacted diagnostic checks. Serve OpenAPI at `/dockflow/v1/openapi.json` with
native list filter/pagination parameters, log query parameters, the Run
`Idempotency-Key` header, request/response models and configured bearer scheme.
The packaged explorer and generated checked-in reference derive from that
contract; they must not introduce a competing handwritten schema.

## KFP client compatibility profile

This is a bounded adapter, not a claim to implement the full KFP server. The
initial qualification target is the KFP `2.17.0` v2beta1 HTTP contract. Preserve
its official wire names, resource envelopes, enum values and error model. Native
models above must not be returned from KFP routes. Before advertisement, compare
the implementation with the pinned official
[Run](https://github.com/kubeflow/pipelines/blob/2.17.0/backend/api/v2beta1/run.proto),
[Experiment](https://github.com/kubeflow/pipelines/blob/2.17.0/backend/api/v2beta1/experiment.proto)
and [Pipeline](https://github.com/kubeflow/pipelines/blob/2.17.0/backend/api/v2beta1/pipeline.proto)
schemas, generated clients and conformance fixtures.

| KFP operation | Exact method/path |
| --- | --- |
| Create/list/get Experiment | `POST /apis/v2beta1/experiments`, `GET /apis/v2beta1/experiments`, `GET /apis/v2beta1/experiments/{experiment_id}` |
| Create/list/get Run | `POST /apis/v2beta1/runs`, `GET /apis/v2beta1/runs`, `GET /apis/v2beta1/runs/{run_id}` |
| Terminate Run | `POST /apis/v2beta1/runs/{run_id}:terminate` |
| SDK connection health | `GET /apis/v2beta1/healthz` |
| Upload named Pipeline and initial version | `POST /apis/v2beta1/pipelines/upload` |
| Upload named PipelineVersion | `POST /apis/v2beta1/pipelines/upload_version` |
| List/get registered Pipeline | `GET /apis/v2beta1/pipelines`, `GET /apis/v2beta1/pipelines/{pipeline_id}` |
| List/get immutable PipelineVersion | `GET /apis/v2beta1/pipelines/{pipeline_id}/versions`, `GET /apis/v2beta1/pipelines/{pipeline_id}/versions/{pipeline_version_id}` |

KFP creates return 200 with the corresponding official resource; terminate
returns 200 `{}` after accepting cancellation. Experiment creation accepts only
`display_name`, `description`, and empty `namespace`. Run creation accepts only
`experiment_id`, `display_name`, `description`, exactly one of `pipeline_spec` or
`pipeline_version_reference`, and `runtime_config`. Reject client-supplied IDs,
output fields, Kubernetes service accounts, recurring-run/plugin fields and
deprecated pipeline-version-only sources. Omitted experiment uses `Default`.
The SDK health response uses the official `GetHealthzResponse` with
`multi_user: false` and `pipeline_store: "database"`. Its route and fields are
documented in the upstream
[Healthz schema](https://github.com/kubeflow/pipelines/blob/master/backend/api/v2beta1/healthz.proto);
verify them against the pinned 2.17 generated client during qualification.
It is separate from the deployment readiness probe.

### Compiled pipeline upload and catalog lifecycle

Support the pinned SDK's
[`Client.upload_pipeline` and `Client.upload_pipeline_version`](https://github.com/kubeflow/pipelines/blob/2.17.0/sdk/python/kfp/client/client.py)
using its exact generated upload requests and official response models. These
endpoints use `multipart/form-data` with a valid boundary
and exactly one file part named `uploadfile`. Accept raw, nonempty UTF-8 compiled
KFP YAML/JSON only. Retain its exact bytes and safely parse/validate it under the
same compiled compatibility profile. The filename is descriptive and is never a
server path or output destination; the per-part media type does not waive content
validation. No extra file/form fields, duplicate parts, URL references, tar/zip or
compressed packages, standalone Python/source-tree uploads, artifact payloads or image bytes are
accepted. A definition requiring runtime parameters can be registered before
those values are supplied for a Run.

Query fields are exact and case-sensitive; reject unknown or duplicate keys.
Both endpoints accept `name`, `display_name` and `description`. The two name keys
are aliases; if both appear, their values must be equal. Effective names are
nonblank strings of 1–256 Unicode characters and descriptions default to empty
with a 4096-character ceiling. Names are exact/case-sensitive; do not silently
trim, case-fold or impose the configuration alias grammar on them.

- Initial upload additionally accepts absent/empty `namespace`; a nonempty value
  is unsupported in this single-project service. If both name aliases are absent,
  use the compiled `pipelineInfo.name`, validated under the same name rules. Create
  a project-unique pipeline with stable `pipeline_id`, `registration_origin: api`, the supplied
  description and an initial version whose name is the effective pipeline name.
  The initial version retains the supplied description and becomes the default.
- Version upload requires `pipelineid` identifying an existing API-owned pipeline,
  and an explicit effective version name. It does not accept `namespace` or a
  pipeline-name query alias for `pipelineid`; the SDK may resolve a pipeline name
  through the supported lookup route first. Append a new immutable version with
  its own `definition_id`/`pipeline_version_id`, supplied version description and
  creation time. It becomes the pipeline's default; pipeline name/description,
  prior versions, embedded component contracts and admitted Runs remain unchanged.

Initial duplicate pipeline names and duplicate version names within a pipeline
return 409 `CONFLICT`, including identical-byte repeats. A configuration-owned
name is reserved even when its source is unavailable; neither initial nor version
upload may overwrite that ownership. Uploading a version into a configuration-owned
pipeline returns 409. Unknown pipeline IDs return 404. Different pipeline/version
associations may contain identical compiled bytes but must retain distinct
immutable version IDs; global content deduplication cannot reparent an earlier
snapshot. Configuration refresh cannot rewrite/deactivate API-owned catalog entries.

These creates return 200 with official `V2beta1Pipeline` or
`V2beta1PipelineVersion`, respectively, after durable owner-controlled acceptance
and index reconciliation. Persist source/version/component membership/default
changes atomically under [Metadata](007_metadata-and-recovery.md). Upload starts
no Run, builds/pulls no image and executes no project code. Auth/access controls
are the same as for Run submission. A later registration does not change the
immutable definition already fixed on an admitted Run. On response loss clients
can use pipeline/version lookup to distinguish accepted work from a rejected
request; upload does not inherit native Run `Idempotency-Key` semantics.

Malformed multipart, missing/empty file, invalid UTF-8 or compiled syntax,
invalid/unknown query fields and unequal aliases return 400 `INVALID_ARGUMENT`.
Unsupported compiled features, nonempty namespace and recognized tar/zip/gzip packages
return 422 `UNSUPPORTED_CAPABILITY`; excess total request bytes return 413
`REQUEST_TOO_LARGE`. Use the official KFP `google.rpc.Status` error body. Reject
requests before usable catalog mutation; partial/staged uploads are not versions.
If durable acceptance succeeded but projection/reconciliation failed, return 503
whose status message identifies the accepted pipeline/version IDs and hold
readiness/admission for recovery, rather than reporting success or pretending
acceptance never occurred.

No separate component-registry upload endpoint is introduced. Compiled pipeline
upload indexes its embedded component interfaces, executor/image references and
immutable identities for the existing component inspection APIs. A standalone
configured component remains supported through configuration; uploads do not
create another component authoring, build or publication protocol.

### Execution and resource projection

`pipeline_spec` carries the compiled object emitted by the qualified SDK. Accept
the pinned SDK's supported pipeline-document envelope and validate its embedded
IR/platform configuration under the same compatibility profile as native
submission. A version reference requires an existing matching `pipeline_id` and
`pipeline_version_id`; absence of a version chooses the current registered
snapshot at admission and records that exact choice. `runtime_config.parameters`
maps to native parameters. `pipeline_root` may be absent/empty or match the
configured published artifact root; reject arbitrary per-request storage changes.
For filesystem configurations this is explicit managed_root when selected, or
the legacy root base otherwise. The S3 bucket/prefix interpretation is unchanged.
Any further runtime-config fields require explicit profile support, not dropping.
Compiled caching settings are honored under Dockflow's equivalence/integrity
rules. Native partial-selection extensions are not smuggled into KFP fields.

Preserve public Run/Experiment IDs. Registered catalog `pipeline_id` is stable;
`pipeline_version_id` maps to `definition_id`. Pipeline display/name fields use
the registered pipeline name; uploaded versions use their own accepted version
name and expose their compiled spec, actual creation time and description.
Return storage state only where the official resource model defines it. No fake
Kubernetes pod/job identifiers are emitted. Official task execution/artifact integer references use persistent project-scoped
SQL aliases. Preserve them across rebuild, backup and restore; native public UUIDs
remain the canonical identities.

Map queued/pending to KFP `PENDING`, running to `RUNNING`, succeeded to
`SUCCEEDED`, failed/blocked/interrupted to `FAILED`, reused/skipped tasks to
`SKIPPED`, cancelling to `CANCELING`, and cancelled to `CANCELED`. Preserve the
native interrupted reason in the official error/status message. Run details,
task details, input/output artifact integer references and state history must
follow their official models; do not invent successful child executions.

Support official `page_size`, `page_token`, `sort_by` and route-specific
`experiment_id` queries. Empty/default sort is creation-descending; explicitly
support only `created_at`, `created_at asc`, `created_at desc`, and `display_name`
with optional `asc`/`desc`, with ID tie-breakers. Responses use their official
collection field (`runs`, `experiments`, `pipelines`, `pipeline_versions`),
`total_size`, `next_page_token`. Namespace must be absent/empty in this
single-project profile. For experiment/pipeline name lookup, support exactly one
official filter predicate: `operation: EQUALS` or its numeric enum value `1`,
`key: display_name`, and `stringValue: NAME`. Accept the protobuf JSON field alias
`string_value` as well; reject duplicate/conflicting aliases. Reject compound/other
filters. This subset is needed by the
SDK's experiment creation and named lookup, as described in its
[client implementation](https://github.com/kubeflow/pipelines/blob/2.17.0/sdk/python/kfp/client/client.py).

Return official `google.rpc.Status` JSON (`code`, `message`, `details`) on KFP
errors with HTTP status semantics matching the native error class. Unsupported
archive, delete, retry, JSON pipeline/version creation, version/default update,
recurring-run, visualization and MLMD-proxy operations return 501 `UNIMPLEMENTED`;
unknown routes return 404. Do not advertise
them through capabilities or ignore unknown executable fields. KFP SDK methods
requiring unsupported operations remain unsupported even if other SDK methods
work. Preserve KFP compatibility boundaries through future version changes.

Required end-to-end qualification includes the pinned SDK's experiment
create/list/get, `create_run_from_pipeline_package`, `run_pipeline` with inline
and registered-version sources, `upload_pipeline`, `upload_pipeline_version`,
run list/get/terminate/wait, and pipeline/version lookup. Exercise pagination,
name filters, duplicate-name conflicts, content-identical distinct associations,
configuration/API ownership, embedded component inspection, bounded malformed/
oversize uploads, restart/rebuild of uploaded defaults, errors, rejection of
unsupported fields, durable idempotency, interrupted publication, restart and
native/KFP views of the same Run. Until these pass, report the adapter as an
unqualified target rather than a working KFP endpoint.

The inspected 2.17 SDK wait helper does not recognize `CANCELED` among its
terminal states. Preserve the correct wire state; document this client limitation
and verify cancellation with `get_run` or the native CLI. Qualify SDK waiting for
successful/failed completion separately. Do not misreport cancelled execution as
failed merely to accommodate a client's polling behavior.

## Distributed cache extension

Cache inspection, invalidation and reset routes and payloads are owned by
[Cache coordination](014_cache-coordination.md#20-dockflow-configuration-and-existing-contracts),
using the same authentication, error and generated OpenAPI boundaries.
