# Review guide and qualification

## Contract navigation

The topic documents own the product requirements. This guide locates those
contracts and owns dependency/platform qualification constraints; it does not
repeat mutable defaults or report implementation completion. Earlier drafts and
private consumer materials are not parallel authorities or runtime dependencies.
Private data structures, HTTP frameworks, storage SDKs and locking libraries may
vary within the public contracts and shared dependency policy.

| Review subject | Authoritative contract |
| --- | --- |
| Product boundary, terminology and modes | [Product](001_pipelines.md) |
| Generic service, component image provision, Compose and volumes | [Deployment](002_local-execution.md) |
| Settings, defaults, precedence, origins, storage access and catalog refresh | [Configuration](003_configuration-and-backends.md) |
| SDK/backend/IR versions, admitted graph features and adapter | [KFP profile](004_kfp-compatibility.md) |
| Ownership, concurrency, queue, retry, cancellation and interruption | [Execution](005_execution-and-lifecycle.md) |
| Registration, managed and external publication, integrity and retention | [Artifacts](006_artifacts.md) |
| SQL, durable records, reconstruction, backup and cleanup | [Metadata and recovery](007_metadata-and-recovery.md) |
| Cache scopes, historical prerequisites and partial selection | [Reuse and selection](008_reuse-and-selection.md) |
| Commands, Run inspection, output and maintenance | [CLI](009_cli.md) |
| Native resource models, upload/version catalog and KFP API | [Service API](010_service-api.md) |
| Browser screens, interactions, access and display limits | [Web interface](013_web-interface.md) |
| Required scenarios and incremental qualification | [Acceptance](011_acceptance.md) |

Shared compatibility, dependencies and release gates belong to the
[general package](../051_dockflow/README.md); executable registration belongs to
[CLI](../052_dockflow-cli/README.md). Specification identities are recorded in
package metadata and the composition. Current implementation, dated test results
and acceptance status belong to the [implementation records](../../implementation/main.md).

## Dependency and platform qualification constraints

Use the SDK/backend/IR and database candidates selected in the
[KFP profile](004_kfp-compatibility.md#compiled-boundary-and-versions), together
with the [shared Python/platform policy](../051_dockflow/002_compatibility.md).
These are qualification targets, not evidence that any version combination has
passed. The initial Linux reference uses Ubuntu 24.04 x86-64. Where wheels are
unavailable, reproducible dependency/source-build evidence is required.

SQLite uses the Python standard library. Qualify the optional PostgreSQL driver,
server, transaction/session ownership, durability, backup/restore and connection
failure behavior on each advertised runtime. Provider availability and configured
CI alone do not qualify execution on a different physical host or platform.

Exact Docker/DinD/MinIO/registry/service-base images and runtime dependency
bounds must be pinned to immutable identities during implementation and refreshed
under shared policy. No arbitrary image digest is fabricated here. Package
namespace availability, GHCR access and trusted publishers are release gates.

## Applying the acceptance scenarios

[Acceptance](011_acceptance.md) owns the complete scenario list and required
evidence. Use the following groups to organize a review without replacing or
weakening individual scenarios:

| Evidence area | Scenarios |
| --- | --- |
| Compiled loading, parameters, graph semantics and native reference parity | A02–A04, A16 |
| Artifact path binding, contents, publication, external imports and recovery | A05–A08, A12/A12a, A20; managed/external publication coverage sections |
| Cache, selection and deterministic reuse | A09–A11 |
| Owner identity, lock aliases, abrupt loss, queue, stop and retry | A13–A15, A28 |
| CLI/API parity, truthful cancellation and KFP wire compatibility | A17–A19 |
| Generic image, registries, uploads and atomic catalog recovery | A21–A22, A25–A27 |
| Installation and native platform/source-build qualification | A01, A23 |
| Configuration provenance, credentials and logging | A24 |
| Actual browser interaction, security and generated API consistency | A29 |
| Presentation controls, incremental logs and retained tails | A30–A31 |

Keep fixture-only results separate from real execution and browser journeys.
Each advertised combination needs its own evidence; a passing structural check
or image build is insufficient. If evidence contradicts a required behavior,
record the gap and correct implementation or propose a specific contract change.
Do not silently substitute the executor, metadata engine or input format, or
reduce the portability promise.

## References

- [KFP 2.17 release](https://github.com/kubeflow/pipelines/releases/tag/2.17.0)
- [KFP 2.17 SDK distribution](https://pypi.org/project/kfp/2.17.0/)
