# KFP compatibility and current limits

[Documentation index](README.md)

Dockflow executes a deliberately bounded KFP profile. It does not replace every
Kubeflow service or implement the entire KFP server API. Query the installation
or service you are actually using:

```bash
dockflow pipelines capabilities
dockflow pipelines --endpoint http://127.0.0.1:8080 capabilities
```

The initial profile is `dockflow-kfp-2.17-v1`: KFP SDK 2.17, compiled IR schema
2.1.0, KFP DockerRunner, SQLite/PostgreSQL and filesystem or S3-compatible artifacts.
SDK version, IR schema and HTTP backend API version are separate identities.
The current [qualification record](../.macrostates/implementation/main.md)
describes tested combinations and remaining platform gaps.

Version 0.1.1 releases this bounded profile. It does not qualify every intended
deployment target or claim complete KFP parity. Use the
[installation instructions](installation.md) and retain the limits below when
choosing an environment. Base-package CI covers Python 3.12/3.13 on Ubuntu 24.04
x86-64, macOS 14 ARM64 and Windows Server 2022 x86-64. Execution/service
qualification covers Linux x86-64 with Linux containers, separately from those
client installation checks.

## Pipeline definitions

| Supported by the current profile | Rejected or deferred |
| --- | --- |
| Compiled KFP v2 YAML/JSON pipeline or primitive component. | Python source entrypoints, v1 component YAML, Argo Workflow YAML, pickles. |
| Container executors with prepared images, commands, args and supported environment bindings. | Kubernetes platform plugins, PVC provisioning, accelerators, OCI modelcar sidecars. |
| Static DAGs and nested graph components. | `ParallelFor`, loops, `Collected`, artifact lists and `ExitHandler`. |
| Typed scalar parameters and supported JSON lists/objects. | NaN/infinity, integers outside ±(2^53−1), ambiguous/duplicate JSON/YAML keys. |
| Named scalar artifacts, file/directory payloads, supported metadata-only metrics and external publication through URI parameters/typed importers. | Overrides of framework-managed output artifact URIs/paths. |
| Standard KFP importer and supported scalar conditional branches/OneOf convergence. | Arbitrary expression execution or unrecognized condition syntax. |
| Cache policy, bounded retries, CPU/memory limits, cancellation and static partial selection. | Parallel task execution, distributed workers and multi-owner state. |

Unsupported executable semantics produce a validation error instead of being
silently dropped. Compilation alone does not establish that a feature is admitted;
run `definitions validate` before deployment.

The scalar condition grammar admits `inputs.parameter_values['name']` (or double
quotes), scalar JSON literals, `int`/`double`/`string`/`bool` casts, comparisons,
`!`, `&&`, `||` and parentheses. Expressions are parsed with an allowlist, never
executed as Python. The capabilities response describes the exact profile.

## Service compatibility

The bounded KFP v2beta1 adapter supports experiment creation/list/get,
pipeline upload/version upload/list/get, run creation/list/get and termination.
It accepts the documented official KFP 2.17 client calls. Unsupported fields,
nonempty Kubernetes namespaces, recurring schedules, deletion/archive operations,
remote package URLs and archive uploads are not supported. See [API](api.md).

Dockflow's browser interface uses its own native API plus the existing upload
adapter. It follows familiar KFP concepts while showing Dockflow's actual
capabilities. It is not the upstream KFP UI bundle and does not require the
upstream UI's larger backend surface.

## Runtime and deployment boundaries

SQLite has one coordinator/Run per project and serial tasks. PostgreSQL supports
multiple coordinators on isolated hosts, one active Run per coordinator, and
serial tasks within each Run.
The persistent service queues additional Runs. SQLite is part of control state;
there is no external database or Kubernetes requirement. Same-host filesystem
ownership is enforced by an OS lock; arbitrary network-filesystem SQLite sharing
is unsupported. PostgreSQL state uses shared maintenance sessions and fenced per-Run ownership and
preserves complete history without local history mounts.

The intended CLI platform range and actual runtime qualification are distinct.
The reference execution environment is Linux x86-64 with Python 3.12/3.13;
the service image uses Python 3.13. Native ARM64 execution, macOS/Windows
runtime combinations and Docker Desktop variants require their own evidence.
Configured CI jobs and successful cross-builds do not provide that evidence.
SQLite state needs no native metadata SDK. PostgreSQL requires its optional
driver. See the qualification record for tested combinations.
Docker images execute trusted user code; this profile is not a multi-tenant
sandbox. Database-backed execution-state qualification is recorded separately from
application release acceptance.
