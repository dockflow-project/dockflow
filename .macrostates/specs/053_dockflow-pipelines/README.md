# Dockflow Pipelines specification

## Scope

This package defines the Dockflow Pipelines contract. Its specification version
is independent of application versions and project baselines. Implementation
status, application/deployment qualification and publication are recorded in the
[implementation records](../../implementation/main.md); selecting this contract
does not establish those outcomes.

Dockflow Pipelines executes compiled native KFP definitions through DockerRunner,
directly from the CLI or through a generic Docker/Compose service. It provides
durable artifacts, unified SQLite/PostgreSQL state and cache, lineage, reuse, historical selection,
recovery and explicit operating contracts. Its KFP client-compatible upload API
registers compiled pipelines and immutable named versions with embedded component
contracts. Components/images and compilation remain owned by consuming projects;
the orchestrator image remains generic and unmodified.

This package owns packages/pipelines, its deployment artifacts and integration
acceptance. It consumes the [general Dockflow](../051_dockflow/README.md) policy
and [shared CLI](../052_dockflow-cli/README.md) registration contract. There is one
composition, project phase and workflow lifecycle.

## Core reading and review order

| Order | Document | Review focus |
| --- | --- | --- |
| 1 | [Product model](001_pipelines.md) | Scope, terminology, portability, modes and package boundaries. |
| 2 | [Deployment](002_local-execution.md) | Direct execution, generic image, Compose wiring and persistent data. |
| 3 | [Configuration](003_configuration-and-backends.md) | Exact TOML shape, discovery, precedence, paths, environment and examples. |
| 4 | [KFP profile](004_kfp-compatibility.md) | Compiled-only inputs, admitted features, adapter and qualification candidates. |
| 5 | [Execution](005_execution-and-lifecycle.md) | Database owner/Run, states, queue, retries, interruption and cancellation. |
| 6 | [Artifacts](006_artifacts.md) | KFP mapping, external registration/import, materialization and publication. |
| 7 | [Metadata and recovery](007_metadata-and-recovery.md) | SQL authority, journal/projections, backup and cleanup. |
| 8 | [Reuse and selection](008_reuse-and-selection.md) | Signatures, scopes, integrity, partial execution and manual historical inputs. |
| 9 | [CLI](009_cli.md) | Command grammar, direct/service behavior, structured output and maintenance. |
| 10 | [Service API](010_service-api.md) | Native models/routes, bounded KFP pipeline/version upload and upstream API compatibility. |
| 11 | [Acceptance](011_acceptance.md) | Required scenarios, incremental delivery and release evidence. |
| 12 | [Review and qualification](012_review-and-qualification.md) | Contract navigation, dependency/platform constraints and qualification evidence. |
| 13 | [Web interface](013_web-interface.md) | Packaged browser UX, screens, interactions, safety and browser qualification. |
| 14 | [Cache coordination](014_cache-coordination.md) | Atomic reuse/claim, distributed registry, leases, immutable publication and conformance. |

All documents are core. The review guide is a useful overview before detailed
reading; it links to topic owners instead of repeating their mutable defaults.
Implementation status and dated qualification belong in implementation records.

Implementation choices may vary within these contracts. Exact dependency/image
pins and platform results remain qualification work, not fabricated open-ended
product behavior. A smaller milestone must advertise its actual subset and reject
unsupported requests; only the completed required checks justify the full profile.
