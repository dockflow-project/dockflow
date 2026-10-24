# KFP compatibility profile

## Compiled boundary and versions

Accept KFP v2 IR in YAML or JSON representing a PipelineSpec or compiled component, using
the qualified upstream schema. Do not accept v1 component YAML, Argo Workflow
YAML, Python entrypoints, pickles or arbitrary YAML constructors. Parse safely,
reject duplicate keys, unsupported tags, non-finite numeric values and ambiguous
types, and retain original bytes. Validate before stateful acceptance/dispatch.

The initial qualification candidates are KFP SDK 2.17.0 (one 2.17 minor line)
with SQLite/PostgreSQL execution state. SDK, backend API and IR schema identities are distinct. Use the
KFP backend 2.17.0 v2beta1 protobuf/OpenAPI definitions for the HTTP subset.
The expected compiler schema is 2.1.0; admit additional schema/SDK versions only
through an explicit tested capability update. These selections are candidates,
not a claim that dependency ranges or platforms have been qualified.

Use KFP's compiled-component loader and local execution machinery wherever
possible, behind one version-specific integration adapter. Prove loading a
compiled root pipeline, nested components and primitive component IR without
importing consumer Python. Compilation remains external to Dockflow. A compiled primitive
component submitted through the same run file/definition interface executes as
a single-task Run. This does not require an independently authored wrapper graph.

Do not implement another independently authored graph. A normalized execution
plan may be derived from IR for policy, inspection and lifecycle integration.
Preserve graph semantics and task paths. Local policies are a separate recorded
profile keyed to definition SHA-256 and qualified task paths, never a rewrite
of executable IR. Policy/configuration cannot silently discard unsupported fields.

KFP pipeline/version upload accepts those same qualified compiled documents and
retains the uploaded source bytes; it is registration, not compilation or Run
submission. Validate schema, graph, interfaces, defaults and supported executable
features before catalog acceptance. Required runtime parameters/artifact inputs
may remain unbound until Run submission. Index embedded component contracts from
the accepted document without importing consumer code or contacting an image
registry. Multipart framing adds no new admitted IR features.

## Required full initial-release target

| Capability | Required behavior |
| --- | --- |
| Executors | KFP container executors with image, command, argument and supported environment bindings. |
| Components | Container, containerized Python and lightweight Python definitions compiled to supported container executors. |
| Parameters | Strings, booleans, integers within plus/minus (2^53 - 1), finite float64 values and supported JSON object/list types; preserve declared types/defaults. |
| Artifacts | Named scalar artifact inputs/outputs, files/directories and declared metadata-only types under the artifact contract. |
| Graphs | Static acyclic graphs, explicit dependencies and nested graph components. |
| Imports | Standard KFP importer executor with URI, artifact type, metadata and reimport semantics. |
| Branches | If/Elif/Else scalar conditions and compatible OneOf convergence, including import-or-acquire graphs. |
| Policies | Per-task cache disablement, declared bounded retry, supported CPU/memory limits and confirmed cancellation. |

Initial task execution is serial, including independent ready tasks; deterministic
qualified-task-path ordering breaks ties. Dependency and branch semantics remain
unchanged. A smaller DAG-only milestone must reject conditionals and label that
limitation; it cannot claim the complete initial target.

Explicitly defer loops/ParallelFor, Collected/artifact lists, ExitHandler,
arbitrary expressions, Kubernetes platform plugins, PVC provisioning, accelerators,
distributed workers within one Run, OCI modelcar sidecars and overrides of framework-managed
output artifact URIs/paths. Reject definitions requiring these features.
External publication through a URI parameter and standard typed importer is
admitted under the [external publication contract](006_artifacts.md#external-publication-through-parameters-and-importers). Upstream support for a feature does not qualify Dockflow automatically.

Evaluate only a parsed allowlist of supported upstream scalar condition
operators; never use eval or execute expression text as Python/shell. The
compatibility manifest must enumerate the exact accepted expression forms.
A nonmatching branch is skipped; missing outputs do not become empty artifacts.
OneOf resolves only the selected compatible branch and its actual producer.

## Execution and artifact adapter

Use DockerRunner for task execution, image handling and native invocation
mechanics. Add the minimum integration necessary to observe attempts, bind staged
artifacts, manage cancellation and enforce the durable publication boundary
before dependent tasks proceed. Do not fork KFP or replace its executor solely
to avoid proving adapter behavior. Unsupported hooks are a qualification failure,
requiring an implementation/design adjustment before release claims.

Cache coordination between independent serial Dockflow instances follows
[Cache coordination](014_cache-coordination.md); it does not extend this IR profile
with distributed task executors.

Default KFP's independent local cache off when Dockflow governs reuse; a native
cache hit must never bypass lineage/publication checks. Reusing upstream cache
mechanisms internally requires tests proving the same durable contract.

KFP artifact .uri/.path conventions and executor JSON differ by version.
Retain canonical storage URIs in the catalog and provide a tested local execution
view under the active pipeline root. A local runtime URI may differ from durable
storage URI, but the relationship must be recorded and never leak as a new
artifact identity. Preserve types and user metadata. Verify all supported KFP
artifact/path placeholders for both Python and non-Python containers.

Generated managed contents follow KFP's pipeline/run/task/UUID/output hierarchy
as specified in [artifacts](006_artifacts.md). This does not require matching
container-local work paths or changing the compiled typed artifact interface.

Components with conventional artifact inputs/outputs consume/write supplied local paths. Reading a supported
artifact URI directly is only qualified when that scheme and credentials/access
are available inside the task; do not assume an S3-to-path string conversion
downloads data. A wrapper may publish external bytes using separately configured
access and return a URI parameter; that does not override a managed output.
Stage historical typed inputs within the active runner-visible root.

An importer registers existing data; it does not prove the data immutable.
Honor reimport=True as a new import record and reimport=False as eligible
metadata reuse, subject to verified source version/fingerprint and access.
Download/materialization is separate. Do not run an importer as an invented
user container computation or attribute external bytes to a generated producer.

## Validation and capability evidence

Check references, cycles, executor kinds, input/output names, types, defaults,
placeholders, conditions, resource/retry/cache policy and definition size before
acceptance. Unknown executable semantics are rejected with task/field location;
descriptive metadata may be retained. An unsupported requirement must not become
an apparently successful relaxed run.

Publish a machine-readable capabilities response containing candidate/qualified
SDK, IR and backend API versions; Docker/database versions; admitted feature flags;
storage/execution/platform support; and limitations. A field is supported only
after the [acceptance checks](011_acceptance.md) pass for the named combination.

Qualification must compare the same compiled fixtures and images on Dockflow and
a reference KFP deployment. Compare declared parameter values, artifact contents
and types, branch choices and failure semantics. Backend-generated IDs, task
filesystem paths, timestamps and runtime infrastructure may differ.

## Upstream references

- [IR YAML](https://www.kubeflow.org/docs/components/pipelines/concepts/ir-yaml/)
- [KFP 2.17 component loader](https://kubeflow-pipelines.readthedocs.io/en/release-2.17/source/components.html)
- [KFP 2.17 local API](https://kubeflow-pipelines.readthedocs.io/en/release-2.17/source/local.html)
- [KFP 2.17 release](https://github.com/kubeflow/pipelines/releases/tag/2.17.0)
- [KFP importer](https://www.kubeflow.org/docs/components/pipelines/user-guides/components/importer-component/)

References document upstream mechanisms, not completed Dockflow tests. Versioned
source and probes take precedence over assumptions from stale high-level guides.

## Strict scalar validation and source capture

Validate exact boolean/integer types for executable fields, including caching,
optional inputs, importer reimport and retry count. Validate resource strings
with field-specific units and finite positive values; invalid zero limits cannot
erase configured quotas. CPU nanocores and memory bytes must fit a positive
signed 64-bit Docker limit. Reject conflicting resource aliases and invalid retry
backoff factors before registration or Run acceptance. Keep this validation pure
and usable without execution extras.

Capture compiled files through one bounded regular-file reader before parsing.
Reject symlink ancestry and nonregular sources without blocking on them; check
open-file identity and observed changes before/after capture. Read at most the
allowed size plus one byte. Preserve lexical source paths until these checks;
canonicalization must not hide a source symlink.
