# Artifacts and publication

## Native KFP contract

An artifact represents typed data consumed or produced by a pipeline. Preserve
the compiled KFP artifact type, including schema title/version, named bindings,
and component-supplied JSON metadata. Parameters remain typed small values;
do not silently turn them into artifacts or treat strings as filesystem paths.
See [KFP compatibility](004_kfp-compatibility.md) for the accepted interfaces.

Keep four identities distinct: the public artifact ID, its durable content URI,
its KFP runtime representation, and the local path used by one execution.
Materialization at another path does not create another artifact. Equal contents
do not erase distinct producing provenance. KFP artifact names and named task
outputs are retained; neither is assumed to be a globally unique public ID.

| KFP information | Dockflow treatment |
| --- | --- |
| Artifact type | Preserve and validate against the consuming compiled input contract. |
| Name and metadata | Preserve observed values; record named input/output bindings separately. |
| Runtime URI and local path | Supply through qualified KFP runtime conventions; map to the execution workspace. |
| Durable content location | Record independently in the artifact descriptor, with its storage backend. |
| Producing task output | Record the exact Run, Task, attempt, definition and output name. |

Components use standard KFP artifact paths and executor metadata. They must not
need a Dockflow Python package, custom artifact subclass, or storage client just
to read/write supported artifacts. The execution adapter owns materialization
and publication. Do not assume that assigning an `s3://` URI makes DockerRunner
download data or yields a usable local path. Record the source/durable URI even
when the qualified runtime uses a workspace-local execution URI.

The initial payload kinds are one regular file, a directory tree, and
metadata-only. A directory may contain many files and empty subdirectories.
`system.Metrics` and `system.ClassificationMetrics` may be metadata-only when
their executor metadata is valid; their absence of files is intentional. Other
accepted artifact types require a payload initially. Type compatibility is not
content-schema validation: a Dataset does not, by itself, prove Parquet validity
or a particular column schema. Application-specific validation belongs in
components unless a separately qualified validation contract is added.

## Registration and external data

External artifacts predate their importing execution. Support two explicit
operations, with interfaces in [CLI](009_cli.md) and [API](010_service-api.md):

- **Register a reference:** create a descriptor for existing contents, leaving
  ownership and contents with the external source.
- **Import a managed copy:** copy existing contents into immutable managed
  storage, retaining their external origin and source location.

Neither operation invents a computational producer. Record registration/import
time, supplied type, optional version label, user metadata and verified content
fingerprint. A managed copy is the recommended default when retaining a stable
snapshot matters; reference registration is available when duplication is
undesirable. The two commands must make their different ownership explicit.

Supported initial external locations are absolute `file://` URIs and `s3://`
locations accessible through the configured adapter. Service filesystem URIs
refer to the service's filesystem. Admit file references only under
`artifacts.external_roots` and remote references only under
`artifacts.allowed_uri_prefixes`; the managed store is always an admitted source.
Both external allowlists default to empty. Match normalized URI scheme,
authority and path segments, not a string prefix. Use the configured S3 endpoint;
an input URI cannot select another endpoint. Registration is not permission to
read arbitrary host paths. Reject unsupported schemes before dispatch and do
not treat credential-bearing URIs as safe catalog metadata.

Registration inventories and hashes the selected contents. A supplied version
label or object ETag alone is not proof of content integrity. Record an available
immutable provider version in addition to the digest. The caller must provide a
stable source while registering; reject observed source changes or incomplete
reads. Re-read source inventories/provider versions before and after copying
and reject observed mutation. Before use, materialize into staging and verify
that the copied bytes match the registered fingerprint. Changed source data
needs a new registration; never silently rewrite an existing identity to match
its new contents.

Directory registrations cover an explicit directory or S3 prefix snapshot,
including its file inventory. Later additions are not implicitly inputs to that
artifact. Zero-byte files and empty filesystem directories are valid. An empty
S3 prefix without a recognized descriptor is missing, rather than evidence of
an intentionally empty directory.

Support the standard compiled KFP importer executor within the compatibility
profile. It resolves its declared URI, type and metadata through this same
contract and records an import event. It may select an already registered exact
source snapshot; otherwise it registers the verified external snapshot. Honor
the supported importer's reimport semantics without changing source provenance.
An importer is represented in the graph but is not a Docker computation attempt.
It must not claim to have generated the imported data. Portable compiled IR
uses normal importer URI inputs; Dockflow IDs are resolved into those inputs by
submission configuration, rather than requiring a Dockflow URI scheme in IR.

## External publication through parameters and importers

A component wrapper may publish files/directories to its own configured storage
root and return the immutable URI as an ordinary string output parameter. A
standard typed KFP importer registers that URI, and downstream components consume
its typed artifact. The admitted IR remains ordinary containers, parameters,
nested graphs and importers; it requires no custom executor or managed-output
URI mutation. A URI parameter alone is not a registered artifact.

The external publisher owns payload integrity, publication records and retention.
Dockflow's source admission, importer reimport/fingerprint checks, materialization
and lineage rules still apply. Configure storage access and any trusted task
mounts explicitly; never infer credentials or host mounts from a URI. Preserve
parameter dependency and importer lineage without inventing a managed producer.
Do not declare a conventional output artifact for the same custom-published bytes.
Other conventional outputs, including metadata-only metrics, may coexist.

Cache hits retain their original URI. Publication destination/context must be
represented in task inputs when it should affect reuse. Publication identity does
not replace the orchestrator's cache key. Provider-specific publishing and path
helpers remain reusable libraries. Pipelines uses Dockflow Artifacts to verify
publication backups; component wrappers may choose their own publisher. Its normal cleanup never assumes ownership of these external
payloads.

## Descriptors and content identities

Artifact descriptors are versioned JSON with `schema_version: 1`. Require the
project/public artifact IDs; KFP schema title/version; origin (`external` or
`produced`); payload kind; descriptor URI and nullable content URI;
source URI/provider version when relevant;
size/inventory/content fingerprints; user metadata; registration/publication
timestamps; and exact producing bindings for produced outputs. Record storage
ownership (`reference` or `managed`) independently of origin. A copied external
dataset is externally originated and managed.

Reserve descriptor-level Dockflow fields and the `dockflow` metadata namespace.
Reject user collisions rather than overwriting user metadata. JSON values must
follow [canonicalization](008_reuse-and-selection.md), including finite numbers
and portable JSON integers within `[-(2^53-1), 2^53-1]`.
Preserve user metadata as a separate object and snapshot it for each binding.
Metadata edits create a new versioned record; they do not rewrite an already
consumed contract or previously published component output.

Use SHA-256 and record the algorithm with each digest. Stream file bytes when
hashing. A file fingerprint hashes its exact bytes. A directory fingerprint
hashes a canonical JSON inventory of relative paths, entry kinds, byte sizes
and file SHA-256 digests, ordered by UTF-8 path bytes; include empty directories.
Ignore timestamps, host ownership and absolute paths. Metadata-only content
fingerprints hash canonical user metadata with its KFP type. Reuse signatures
also include type and relevant metadata, rather than assuming equal bytes
imply equal artifact contracts. Managed-output hashing is enabled by default
and cannot be disabled while retaining historical-reuse eligibility.

The exact directory fingerprint view is an object with kind=directory and
entries as an array. A file entry has path, kind=file, size_bytes and sha256;
an empty-directory entry has path and kind=directory. Paths are relative POSIX
strings, sorted by UTF-8 bytes; include only files and empty directories, not
redundant parent directory entries. An empty root has entries=[]. Hash this view
using dockflow-json-v1. The metadata-only view is an object with kind=metadata,
type={schema_title,schema_version} and metadata equal to the user metadata object;
hash it with the same canonical format. These exact keys and enum strings are
part of fingerprint format version 1.

The authoritative descriptor is a SQL artifact resource keyed by its public
artifact ID. Managed descriptors additionally record
`storage_layout: "kfp-v2"` and `managed_path`, the root-relative publication path.
Produced descriptors retain `pipeline_name` and `task_name` in the producer binding
alongside the Run, Task, attempt, definition and output identities.

### KFP-equivalent publication layout

Generated contents use the native KFP 2.17 hierarchy:

```text
<managed-root>/<pipeline-name>/<run-id>/<task-name>/<attempt-uuid>/<output-name>
```

The pipeline name is the compiled `pipelineInfo.name`, independent of catalog
aliases/display names. The task name is the compiled leaf task key; nested tasks
with the same key remain distinct through their attempt UUIDs. The UUID is the
UUID part of the actual Dockflow attempt ID, shared by all outputs of that
attempt. Keep the complete Dockflow Run ID in the run segment. New attempts/runs
get new destinations; a reused output keeps its original producing URI and ID.
Do not copy reused contents into the consuming Run's durable artifact directory.

The output-name location is the file itself or the directory tree. There is no
additional artifact-ID or `payload` segment for produced outputs. For directory
outputs, retain the internal filenames/empty directories exactly. Metadata-only
artifacts have a null content URI and no fabricated payload. Parameters stay in
execution metadata and never acquire artifact paths. Existing typed KFP wrapper
interfaces and runtime-owned transfers remain unchanged. This layout applies to
managed outputs; separately published external references follow the external
publication contract above.

For filesystem storage, `artifacts.managed_root` selects the base directly;
otherwise use `<artifacts.root>/managed` as before. For S3 the base is
`s3://<bucket>/<configured-prefix>` with no implicit `managed/` child. This
matches KFP's relative hierarchy, not its private metadata schema, URI scheme,
exact generated identifiers or container-local staging paths.

Store recovery descriptors and publication reservations in the same SQL database
as execution state and cache coordination. Scope them by project and storage
identity; never write descriptor or reservation sidecars into the artifact root.
The journal/output-set commitment still determines whether outputs are consumable;
a recovery descriptor alone cannot reconstruct a Run. Keep only payloads,
disposable staging and `.dockflow/storage.json` in storage. Validate this identity
marker before accepting SQL records for that root.

Administrative managed imports have no producing Run/Task: place their contents
at `<managed-root>/.dockflow/dockflow-pipelines/<artifact-id>/payload`, preserving external
provenance. Registered references retain their original contents and need no
managed-store payload folder.

Pipeline names must be safe single segments using ASCII letters/digits,
underscores, hyphens and interior periods, starting with a letter/digit/underscore/
hyphen and not ending in a period. Artifact binding names and task keys use ASCII
letters/digits/underscores/hyphens. Reject unsafe names before dispatch; storage
also validates producer segments before publication. Absolute paths, separators,
dot segments and URI escapes cannot select another destination. `.dockflow` is
reserved for store metadata. Do not follow destination symlinks or overwrite an
existing output. One owner governs ordinary journal-backed publication. Coordinated cache outputs
use isolated immutable paths under the [cache protocol](014_cache-coordination.md);
its registry uses the same database and project as execution state.

### Existing data and backups

Artifact bookkeeping uses the unified schema; no migration from older SQL or
sidecar formats is required. Do not silently adopt or delete existing state.
Filesystem and S3 backups copy the entire owned payload hierarchy and identity
marker into `managed/`, alongside a consistent project SQL snapshot containing
publication claims/manifests and recovery descriptors. Restore those original
relative payload keys and SQL records under exclusive maintenance. Refuse nonempty
targets and preserve project, store-identity and content integrity checks.

## Preparing a task

Resolve each named input to an exact artifact descriptor, then validate its KFP
type, publication state and accessibility. Distinguish missing, inaccessible,
incompatible and corrupt inputs in errors. Record the exact binding before
execution; never discover replacement data by filename similarity.

Materialize inputs under the active Run's execution root, preserving their
internal relative paths. Filesystem storage uses copying or an equivalent
isolated snapshot; object storage downloads the declared inventory. References
to another Run cannot rely on a path outside DockerRunner's visible root.
Copying is the initial default; writable hard links into managed or external
source data are forbidden. A verified staging cache may avoid redundant transfer
only when it preserves immutable input contents and rechecks readiness.

Verify copied contents against their descriptors before dispatch. Inputs are
logically immutable. Use read-only mounts where the qualified runner supports
them; otherwise isolate copies from durable storage and detect input mutation
before accepting the result. Input modification fails the task and cannot
produce reusable outputs. This protects data consistency, not hostile-code
isolation. Apply the shared-volume/path rules in
[execution](005_execution-and-lifecycle.md) in direct and inner-daemon modes.

Prepare separate writable output locations for each attempt and declared output
name. Bind KFP placeholders/executor input to those locations without rewriting
the portable component interface. Collect output parameters and executor
artifact metadata using the qualified KFP mechanism. Raw stdout is a log, not an
implicit output parameter or artifact.

## Validating and publishing outputs

An attempt progresses through execution, validation, staging and publication.
Process exit zero alone is insufficient. After execution:

1. Validate all required artifact and parameter outputs against the compiled
   contract. Reject missing payloads, malformed executor metadata, unsupported
   file kinds and inconsistent output bindings. Metadata-only outputs follow
   their explicit contract rather than a missing-file exception.
2. Allocate fresh public artifact identities for the actual attempt's outputs,
   compute inventories/digests, and prepare their descriptors. Inputs remain
   unchanged. A retry cannot overwrite an earlier attempt's published artifacts.
3. Publish every required payload to its unique immutable destination and retain
   its recovery descriptor in SQL. Filesystem publication uses temporary siblings and atomic rename
   on the destination filesystem. S3 uploads to unique prefixes and verifies the
   complete inventory; it does not assume an atomic multi-object rename.
4. Durably commit the attempt's complete output set as an SQL domain record
   keyed by the attempt ID, atomically with its accepted journal event. Require `schema_version`, project/Run/Task/attempt IDs,
   exact declared output-name-to-artifact-ID/descriptor-digest mappings, output
   parameter values, owner-allocated acceptance sequence and publication time.
   Write this marker only after every required output is durable. An output-free
   task commits an explicit empty set.
5. Record attempt success and reconcile SQL lineage/query state. Downstream
   dispatch and historical reuse require a consistent committed output set.

The control-state output-set marker is the authoritative commit boundary. A
per-artifact descriptor appearing early does not make a partial output set
eligible for consumption. No transaction spans object storage, artifact storage and SQL.
The owner serializes interruption/cancellation intent with output-set commit.
If stop intent is durable first, no new output-set commit is allowed; completed
uploads remain unpublished diagnostic/orphaned data. If the commit is durable
first, retain the attempt's successful result and reconcile its index, while
the Run may stop before dispatching downstream work. Stop intent never deletes
valid committed outputs or changes their producing provenance.
If an index update fails after the marker is durable, preserve the committed
result, pause dispatch and request reconciliation; do not rerun the computation
or falsely present it as an incomplete upload. Recovery is idempotent.

Failed/interrupted staging remains diagnostic data, never a published result.
Unreferenced uploads are orphans and may be reported for explicit cleanup.
Publication must not overwrite a different committed object or accept an
existing ID with mismatching contents. Direct component writes to arbitrary
external URIs are application side effects and do not bypass this publication
contract or become managed outputs implicitly.

## Safe materialization and retention

Reject absolute/escaping inventory paths, dot segments, backslashes, NULs,
duplicate entries and path collisions on the target filesystem. Require regular
files/directories; symlinks, devices, sockets and FIFOs are unsupported initially.
Do not follow links while registering, copying or publishing. Check source and
destination containment and refuse overlapping managed/work/external roots
that could overwrite inputs or recursively copy state into itself.

Cleanup is explicit and defaults to dry-run. No automatic deletion is enabled
initially. The initial clean operation targets only disposable work for terminal
Runs and recognized uncommitted orphan data with proven project ownership. It
does not delete committed artifact contents, logs, definitions or control history.
Published-artifact expiry/deletion requires a future explicit retention contract;
loss observed outside Dockflow is still recorded as unavailable. Protect active input leases, retained pins and publication in progress;
recheck those protections while holding ownership before applying a plan. Never
delete reference-registered external contents. Deleting a managed copy does not
authorize deleting its external source. Preserve historical provenance and
record contents as unavailable when bytes are removed or lost. See
[reuse and selection](008_reuse-and-selection.md) for eligibility and
[acceptance](011_acceptance.md) for interruption/corruption coverage.

## Upstream references

KFP's native artifact properties and immutability guidance are described in
[artifact handling](https://www.kubeflow.org/docs/components/pipelines/user-guides/data-handling/artifacts/).
The standard external-input construct is the
[KFP importer](https://www.kubeflow.org/docs/components/pipelines/user-guides/components/importer-component/).
The storage lifecycle above is Dockflow's additional contract, not a claim that
DockerRunner already supplies it.

The relative output layout follows KFP 2.17's
[run prefix construction](https://github.com/kubeflow/pipelines/blob/2.17.0/backend/src/v2/metadata/client.go)
and [output provisioning](https://github.com/kubeflow/pipelines/blob/2.17.0/backend/src/v2/driver/driver.go).

## Coordinated output sets

The [cache protocol](014_cache-coordination.md) specializes publication for
cacheable executions: versioned immutable attempt locations, portable complete
manifests and fenced registry commitment precede reusable discovery. Execution
output-set journals retain their producing-Run role. Registry publication and
imported cross-state producer facts must survive journal/index reconciliation.

## Database descriptor identities

Descriptors use `dockflow://PROJECT_ID/artifacts/ARTIFACT_ID` as their stable
metadata URI. This is an identity resolved through Dockflow, not a payload
download URL. Exact descriptors and provenance live in SQL; content_uri continues
to identify filesystem/S3 payloads. No descriptor identity depends on a worker's
local state directory.
