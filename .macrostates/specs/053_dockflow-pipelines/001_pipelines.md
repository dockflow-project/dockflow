# Product model and boundaries

## Purpose and profile

This package defines the complete initial-release target for Dockflow Pipelines.
Specification selection and runtime qualification are separate. Incremental
milestones may implement a smaller advertised profile;
[Acceptance](011_acceptance.md) defines the gates for claiming the full target.

Dockflow executes compiled Kubeflow Pipelines (KFP) definitions locally through
KFP DockerRunner. It adds durable Runs, artifact storage integration, SQL execution history, lineage, task reuse, historical selection, recovery, a CLI and a service.
One configured repository/project and its state are managed per instance.
Different projects use separate instances; no machine-wide discovery or cache.

The same compiled definition and prepared component images must be usable by
Dockflow and KFP within the declared compatibility profile. Backend endpoints,
credentials, available hardware and data locations are deployment settings.
Portability of definitions does not transfer databases, local files, credentials,
history or unsupported Kubernetes policies between platforms.

## Domain concepts

| Concept | Contract |
| --- | --- |
| Component | Native KFP definition of computation, interface and executor. |
| Pipeline | A compiled KFP root graph composing components and dependencies. |
| Pipeline registration | A project-unique named catalog entry with a stable pipeline ID, an explicit configuration/API origin and a current immutable version. |
| Definition version | Immutable accepted compiled bytes plus parsed identity and validation profile. |
| Run | One independent submission with fixed definition, input bindings, resolved parameters and policies. |
| Task | A component invocation within that Run, addressed by its qualified compiled task path. |
| Attempt | An actual execution of a Task, including each separately recorded retry. |
| Artifact | Typed data/metadata with stable identity, provenance and one or more availability records. |
| Experiment | Optional grouping of Runs; it does not determine cache equivalence. |

A reused Task references its original producer and has no fabricated process
attempt. A skipped conditional Task has no outputs or attempt. State/events evolve;
the accepted invocation and historical input choices do not change.

Runnables are a concept of consuming applications, not a Dockflow abstraction.
Do not provide a Runnable registry, authoring language, compile command or image
build command. Users compile with KFP and build/publish images before invoking
Dockflow. No runtime Git access, consumer Python imports or source-tree mounting
is required for normal component execution.

## Ownership

The Pipelines core owns validation, planning, submission, lifecycle, storage,
reuse, metadata, recovery and cleanup. CLI and HTTP adapters call that same core
and return equivalent structured results. Importing/constructing either adapter
must not execute tasks, create state, contact infrastructure or discover/import
arbitrary consumer Python.

Application Analysis, Dataset and Model business domains, model
serving, cloud execution adapters, Kubernetes deployment, multi-node scheduling,
enterprise authentication and hostile multi-tenant isolation are outside the
initial release. Opaque application correlation IDs may be recorded as metadata.

The first-party web interface is part of the existing Pipelines service, as
defined in [Web interface](013_web-interface.md). It uses the same core and
project ownership, without introducing a separate execution service.

## Execution modes

Direct CLI execution is the default and starts no HTTP service or Compose stack.
A Docker daemon is still required. A service uses the same core and executes
accepted work independently of request connections. Selecting a service requires
an explicit endpoint through a CLI option, environment or client configuration.
Installation never deploys infrastructure or starts Docker.

SQLite local deployment has one execution owner, active Run and task attempt per
project database. PostgreSQL deployment permits concurrent Runs across isolated
coordinators with fenced per-Run ownership and shared metadata transactions. Each
coordinator executes one Run at a time and tasks remain sequential within a Run.
The [execution contract](005_execution-and-lifecycle.md) owns claims, admission,
recovery and maintenance. A persistent service retains a bounded durable queue;
multiple PostgreSQL services may claim different queued Runs.

## Identifiers and records

Public IDs are lowercase prefixes followed by a canonical UUIDv4:
project IDs are explicit stable configuration values; other prefixes are
pipeline_, component_, definition_, run_, task_, attempt_, artifact_, experiment_.
Public IDs never encode internal database keys, host paths or mutable display names.
SHA-256 digests identify bytes/normalized content separately from public IDs.

A registered pipeline/component retains its catalog ID across configured refreshes.
Configured name removal makes that registration inactive without deleting history;
reintroducing the same name restores that configuration-owned catalog identity.
A changed configured source creates a new immutable definition version; unchanged
accepted bytes/profile within that catalog reuse the existing snapshot.

The KFP upload API can instead create a named pipeline and append explicitly named
versions. Configuration-owned and API-owned registrations share the project's
pipeline-name namespace but cannot overwrite one another. API registrations do
not depend on server source files and remain available across configuration
refreshes/restarts. Pipeline names are unique per project; uploaded version names
are unique within their pipeline. A newly accepted uploaded version becomes its
pipeline's current default. Version mutation, registration deletion and explicit
default-version changes are outside the initial API profile.

An uploaded version's `definition_id` is also its KFP `pipeline_version_id`.
Its pipeline association, version name, original bytes and embedded contracts
are immutable. Identical bytes under different pipelines or uploaded version
names receive distinct version IDs; deduplication must not move an existing
snapshot to another registration or rewrite historical Runs. Content digests
remain usable for computational equivalence independently of these catalog IDs.

Inline/unregistered compiled submissions receive an immutable definition ID with
null pipeline catalog ID and no invented alias. Do not attach or move a registered
snapshot implicitly merely because its content matches an inline submission.
Embedded component IDs are scoped to the accepted parent definition and compiled
component keys. Uploading the complete pipeline records those component contracts
automatically, including interfaces, executors and image references. The component
inspection APIs expose them; no separate component registration/upload API or
component image upload is required. Component images remain externally prepared
registry objects. Runs retain their exact accepted definition IDs when the
pipeline's default version later changes.

## Package and CLI integration

The distribution is dockflow-pipelines, import package dockflow_pipelines,
workspace member packages/pipelines. Shared application releases require the
same exact dockflow-cli release. Only dockflow-cli owns the dockflow executable.
Pipelines exports a Typer application through:

~~~toml
[project.entry-points."dockflow_cli.modules"]
pipelines = "dockflow_pipelines.cli:app"
~~~

Declare the selected Typer dependency directly when importing it; consume only
the shared CLI's public registration contract. All feature commands and options
belong under dockflow pipelines. Follow its offline help, stdout/stderr and
0/1/2 exit conventions. [CLI](009_cli.md) defines the feature grammar.

Keep base installation and remote-client operations independent of PostgreSQL drivers, Docker,
KFP execution and service-server imports. The runtime extra installs qualified
execution/metadata dependencies; service adds the HTTP server; s3 adds the storage
adapter. The service image includes runtime, service and s3 functionality.
A direct command without its required extra reports an actionable installation
error rather than selecting a service or a different executor silently.

Shared licensing, Python/platform targets, dependency/build and coordinated
release policy remain owned by the general Dockflow package. Runtime constraints
do not narrow those targets silently; qualification gaps are explicit in
[Review and qualification](012_review-and-qualification.md).
