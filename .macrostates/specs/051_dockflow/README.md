# General Dockflow requirements

This project-owned package defines shared identity, licensing, monorepo
boundaries, Python/platform support, dependency/build policy, and application
releases for Dockflow. It applies across the repository. Implementation and
qualification evidence are maintained separately from these requirements.

## Reading order

1. [Project and repository](001_project.md)
2. [Python and platform compatibility](002_compatibility.md)
3. [Dependencies, workspace, and builds](003_dependencies-and-build.md)
4. [Shared application releases](004_releases.md)
5. [Publication scope and qualification gates](005_open-decisions.md)
6. [Documentation boundaries and maintenance](006_documentation.md)

## Tool packages

The root composition also selects separate local packages for
[Dockflow CLI](../052_dockflow-cli/README.md),
[Dockflow Pipelines](../053_dockflow-pipelines/README.md) and
[Dockflow Artifacts](../054_dockflow-artifacts/README.md). Those packages own
their tool requirements and depend on the shared rules here. These links locate
the selected tools; they do not make the general package depend on those tools.
The four local specification packages belong to one project lifecycle and composition.

## Scope and interpretation

Dockflow is the umbrella project. Dockflow Pipelines is its first functional
module. A Python distribution, import package, terminal executable, and CLI
module are distinct identities.

The distributions share one monorepo, application release policy and project
lifecycle. The selected specification composition defines their requirements.

Do not infer missing product behavior from illustrative paths, versions, or
examples. Follow the owning contract before changing the affected surface.
The selected defaults are the current policy and may be revised through
deliberate specification work when needs change; they are not automatic upgrade
instructions.
