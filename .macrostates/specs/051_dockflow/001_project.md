# Project and repository

## Identity and scope

The project is **Dockflow**, maintained in `dockflow-project/dockflow` on GitHub.
Prepare authored content for a public, open source repository: portable paths,
synthetic examples, explicit dependencies, and no private organization or
machine-specific assumptions. Dockflow uses the MIT license, identified as
`MIT` in package metadata. The repository-root [LICENSE](../../../LICENSE) owns
the full terms and uses the attribution "Copyright (c) 2026 Dockflow
contributors". Preserve upstream specification license notices and attribution.

Deliver the shared CLI, Dockflow Pipelines, Dockflow Artifacts and their shared
Dockflow Core library. Pipelines executes
supported KFP-compatible workflows with Docker, without Kubernetes. Serving is a
possible future module with no current package or implementation deliverable.

## Monorepo and package boundaries

Use one repository with separate installable distributions:

| Directory | Distribution | Import package | Responsibility |
| --- | --- | --- | --- |
| `packages/core/` | `dockflow-core` | `dockflow_core` | Domain-independent shared primitives under the [Core boundary](007_core.md). |
| `packages/cli/` | `dockflow-cli` | `dockflow_cli` | Executable ownership and module discovery. |
| `packages/pipelines/` | `dockflow-pipelines` | `dockflow_pipelines` | Pipeline commands, application logic, and execution integration. |
| `packages/artifacts/` | `dockflow-artifacts` | `dockflow_artifacts` | Reusable artifact publication, integrity and optional KFP authoring integration. |

Each distribution has its own `pyproject.toml`, `src/` layout, declared
dependencies, and package-level tests. Cross-package integration tests belong
under repository-root `tests/integration/`. Do not create future module
placeholders solely to illustrate expansion.

This explicitly specializes the repository-root `src/` examples in Python
Project: the `src/` boundary applies within each distribution.
The distributions are components of one project, with one phase, composition,
and workflow system. They are not independently composed subprojects.

Apply the shared [Python/platform policy](002_compatibility.md) and
[dependency, workspace, and build policy](003_dependencies-and-build.md) to all
distributions. Published metadata and artifacts must work outside the development
workspace.

## Shared application releases

All first-party distributions share one application version and release history.
The [release policy](004_releases.md) owns the version authority, synchronized
metadata, semantic versioning, prereleases, destinations, qualification, and
publication procedure. It preserves Process's separate baseline and integration
gates. No application version is assigned by the initial specification seed.
