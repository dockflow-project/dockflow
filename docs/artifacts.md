# Artifacts, lineage and reuse

[Documentation index](README.md)

## Register a reference or import a copy

An external dataset already exists before a computation. Dockflow can register
a reference to its current contents or import a managed snapshot. Registration
leaves the bytes at their source; import copies them into Dockflow's artifact
store while retaining their external provenance.

First permit the input directory in your project configuration:

```toml
[artifacts]
backend = "filesystem"
managed_root = "data/artifacts"
external_roots = ["data/external"]
```

Then supply an absolute URI under that directory:

```bash
dockflow pipelines --config PROJECT_CONFIG artifacts import \
  --uri file:///absolute/path/to/project/data/external/dataset.csv \
  --type system.Dataset --version dataset-v1
```

Use `artifacts register` with the same options to keep a reference instead.
Both inventory and hash the source. Keep it stable during the operation.
Changed reference contents need a new registration; an existing ID is not
silently repointed at new bytes.

Supported external schemes are `file://` and `s3://`. A remote service resolves
`file://` inside its own filesystem and allowed roots. Passing a client filename
does not upload that file. For remote S3 sources, configure `allowed_uri_prefixes`
and the appropriate S3 endpoint/credentials. Arbitrary HTTP dataset downloads
belong to your acquisition script or component, before registration.

## Bind data to a pipeline

For a declared root artifact input:

```bash
dockflow pipelines --config PROJECT_CONFIG run training --input dataset=ARTIFACT_ID
```

For a KFP importer-based graph, supply its declared URI parameter, with JSON
string quoting, rather than changing the graph's parameter into an artifact:

```bash
dockflow pipelines --config PROJECT_CONFIG run training \
  --parameter 'dataset_uri="file:///absolute/path/to/project/data/external/dataset.csv"'
```

The pipeline's interface determines which form applies. `definitions show`
exposes the compiled interface. A standard KFP importer records externally
originated data; it does not claim a computation produced those bytes.

## Materialization and publication

An artifact ID, durable URI and task-local path are distinct. Dockflow stages
verified input copies below the current execution root and passes those paths
to the component. It checks that the component has not changed input contents
before accepting outputs. This protects consistency; task images remain trusted
code, as described in [security](../SECURITY.md).

Outputs can be regular files, directory trees, or supported metadata-only
`system.Metrics`/`system.ClassificationMetrics`. Ordinary artifacts require a
payload. Symlinks, devices, sockets and FIFOs are unsupported. Type labels
describe a contract; `system.Dataset` does not validate a CSV's columns.

Exit zero is not enough for success. Dockflow validates all declared outputs,
publishes every payload/descriptor, then commits the complete output set. Only
that committed set can feed downstream tasks or reuse. Parameters remain typed
small values recorded separately from artifact data.

`artifacts.managed_root` selects the filesystem base for a KFP-equivalent
publication layout. With the configuration above, generated outputs live at:

```text
data/artifacts/<pipeline-name>/<run-id>/<task-name>/<attempt-uuid>/<output-name>
```

For example, a file output named `model` is the file at
`data/artifacts/sample-training/run_…/train-sample/<uuid>/model`. A directory output
named `model` contains its original files below that location. The final name
comes from the compiled artifact binding; Dockflow does not append `payload`
or change it to the component's temporary filename.

The pipeline name comes from the compiled definition, not its catalog alias.
The task name is the leaf task key. Outputs of one attempt share its UUID;
retries get a new UUID. Reused/imported references retain the original URI, so
one run can consume artifacts stored under earlier runs. Do not delete an older
run's artifact directory just because computation has moved to a newer run.

S3 uses the same relative layout directly under `s3://BUCKET/PREFIX/`, with no
implicit `managed/` child. Dockflow's recovery copies are separate:
`.dockflow/dockflow-pipelines/ARTIFACT_ID/artifact.json` under the managed root. Directory
artifacts may freely contain their own file named `artifact.json`. Metadata-only
artifacts have no payload and a null content URI. Parameters are recorded as
execution values, not stored as artifacts.

Administrative managed imports have no producing run; their copied bytes live
at `.dockflow/dockflow-pipelines/ARTIFACT_ID/payload` under the root. Reference artifacts
keep their original source contents and need no managed payload directory.
Always read `content_uri` from `artifacts show ARTIFACT_ID` instead of constructing
a path from an ID. The authoritative descriptors remain in Dockflow state.

For compatibility, `artifacts.root = "artifacts"` still resolves the base to
`artifacts/managed/`. Omitting both settings keeps that default; choose either
`root` or `managed_root`, not both. Existing artifacts remain readable at their
recorded URIs; changing the layout or configured root does not migrate history.
The structure matches native KFP's output organization while retaining Dockflow's
own IDs, descriptors, commit markers and execution staging.

## Inspect lineage and integrity

```bash
dockflow pipelines --config PROJECT_CONFIG artifacts show ARTIFACT_ID
dockflow pipelines --config PROJECT_CONFIG tasks show TASK_ID
dockflow pipelines --config PROJECT_CONFIG metadata check --verify-contents
```

Artifact records show their type, SHA-256 fingerprint, origin, producer, location,
availability and pin. Task records link named inputs and outputs to artifacts
and actual producing attempts. The browser and API provide producer/consumer
navigation. A reused result retains the original producer instead of creating a
fictional new computation.

Availability can be `available`, `missing`, `inaccessible`, `corrupt`, `deleted`
or `unknown`. Historical success and present availability are separate. Hashing
is required to establish content integrity; an ordinary metadata check does not
claim it rehashed every payload.

## Reuse and fresh execution

Each submission creates a Run. A task may reuse a prior successful committed
output set if its component, actual image identity/platform, parameters, typed
input identities/fingerprints, relevant environment/resources and adapter identity
match. The candidate's outputs must still be accessible and verified.

| Scope | Meaning |
| --- | --- |
| `global` | Eligible history within this project/store; the default. |
| `keyed` | Eligible history with the same supplied namespace key. |
| `run` | Eligible results within this Run's scope. |
| `none` | Execute selected tasks without historical substitution. |

Use `--scope keyed --scope-key development` or `--scope none` on `run`.
Compiled cache disablement and local `cache_safe = false` remain stronger than
these options. Cache flags absent from the compiled profile default to disabled.
Components with undeclared randomness, time, network state or other mutable
dependencies should disable caching or expose those values as inputs.

## Select historical inputs explicitly

```bash
dockflow pipelines --config PROJECT_CONFIG run training \
  --tasks train --bind train.dataset=ARTIFACT_ID
```

This intentionally selects a dataset for the task; it is recorded as a manual
input choice, not proof that the omitted producer's computation was equivalent.
`--use-execution prepare=ATTEMPT_ID` can select a historical producer's whole
named output set. `--from train` selects that task and descendants; `--tasks`
selects only the named tasks. These selection forms are mutually exclusive.

Omitted prerequisites must resolve to compatible, available historical results
before dispatch. Ordering-only dependencies still require compatible successful
history; binding data does not erase a control dependency. Partial execution
crossing unsupported conditional boundaries is rejected.

## Pins and cleanup

`artifacts pin ARTIFACT_ID` adds an explicit retention pin; `unpin` removes it.
Pins survive restarts and rebuilds. They do not repair missing bytes or make
incompatible results reusable. Current `clean` targets disposable terminal-run
work; it does not expire committed artifacts or delete external data. See
[operations](operations.md) and [persistence](persistence.md) for maintenance.

## Custom publication paths

The optional [Dockflow Artifacts library](artifact-library/README.md) lets a
component wrapper publish at a caller-chosen filesystem or S3 path, then return
a URI parameter to a typed KFP importer. This works with native KFP and Dockflow;
ordinary managed outputs continue using the default layout described above.

Custom publications are reference artifacts from the orchestrator's perspective.
Give the publishing container explicit storage access, and allow the same URI
root for the Dockflow owner. The custom store owns retention and backup; its
payloads are not automatically included in managed-only backups. Use trusted
[task mounts](configuration.md) for local storage/configuration and Kubernetes
Secrets in native deployments. Business scripts can remain independent of both
orchestrators. See [KFP integration](artifact-library/kfp.md) for the typed graph
adapter and its lineage behavior.
