# Dockflow specifications

Dockflow is a modular Python monorepo. Its first deliverables are a shared CLI
and Docker-based execution of supported KFP-compatible pipelines without
Kubernetes. Local requirements are organized into
[general Dockflow](051_dockflow/README.md),
[Dockflow CLI](052_dockflow-cli/README.md),
[Dockflow Pipelines](053_dockflow-pipelines/README.md), and
[Dockflow Artifacts](054_dockflow-artifacts/README.md) packages.

The specification set defines the accepted product contracts. The composition
records the selected project baseline; implemented scope and current qualification
limits are described in the [implementation overview](../implementation/main.md).
The first bounded milestone remains recorded in the
[initial release review](../implementation/validation/initial-release.md).
Reviewed integration finalizes the baseline declarations. Annotated tags and
versioned distributions are published separately under the
[shared release policy](051_dockflow/004_releases.md); specification acceptance
alone does not establish that publication has occurred.

## Selected packages and reading order

Read Meta's entrypoint and core documents first, then this entrypoint, then the
remaining packages in the order below. Follow each package's core reading order
and consult conditional annexes when the task makes them relevant.

| Order | Package | Version | Entrypoint | Purpose |
| --- | --- | --- | --- | --- |
| 1 | meta | 3.0.0 | [000_meta/README.md](000_meta/README.md) | Composition, authority, package integrity. |
| 2 | process | 5.1.0 | [001_process/README.md](001_process/README.md) | Workflow tracking and project baselines. |
| 3 | repository-1 | 4.0.0 | [010_repository-1/README.md](010_repository-1/README.md) | Repository hygiene and reviewed Git integration. |
| 4 | docker-1 | 3.0.0 | [011_docker-1/README.md](011_docker-1/README.md) | Container image and runtime conventions. |
| 5 | python-1 | 2.1.1 | [020_python-1/README.md](020_python-1/README.md) | Python language conventions. |
| 6 | python-project-1 | 3.0.0 | [030_python-project-1/README.md](030_python-project-1/README.md) | Application layout, tooling, testing, and packaging. |
| 7 | dockflow | 1.0.0 | [051_dockflow/README.md](051_dockflow/README.md) | Shared identity, compatibility, dependencies, builds, and releases. |
| 8 | dockflow-cli | 0.2.1 | [052_dockflow-cli/README.md](052_dockflow-cli/README.md) | Shared executable, discovery, and registration contract. |
| 9 | dockflow-pipelines | 11.0.0 | [053_dockflow-pipelines/README.md](053_dockflow-pipelines/README.md) | Complete initial product, execution ownership, artifact, persistence, upload/version API, and deployment contracts. |
| 10 | dockflow-artifacts | 3.1.0 | [054_dockflow-artifacts/README.md](054_dockflow-artifacts/README.md) | Reusable publication, integrity and KFP integration. |

Python Project supplies the project conventions for applications, CLI, and
service tooling; Python supplies the language conventions. Dockflow's local
package specializes the layout for the monorepo and defines the intended shared
distribution release policy. The tool packages depend on those shared rules;
Pipelines also depends on the CLI registration contract. All four are local
specification packages in one composition, with one project phase and lifecycle.

The general package governs repository-wide requirements. The CLI package owns
the `packages/cli/` component and the shared executable/registration
interface. The Pipelines package owns the `packages/pipelines/`
component and its corresponding deployment and integration artifacts. The Artifacts package owns `packages/artifacts/` and is independently installable
without CLI or Pipelines runtime dependencies. Its specification declares the
Pipelines contract used by the optional integration. Tool packages specialize their own responsibilities and do not redefine shared rules
or change another tool's contract.

## Authority

Highest to lowest: **meta**, **process**, **dockflow**, **dockflow-cli**,
**dockflow-pipelines**, **dockflow-artifacts**, **python-project-1**, **python-1**, **docker-1**,
**repository-1**. Reading order
and numbered directories do not establish authority. More specialized Python
and project requirements govern the corresponding generic conventions.

Future directory-scoped specifications apply only inside their enclosing
directory, below the selected packages in this authority order. They may
specialize an explicitly delegated choice; they cannot override enclosing rules,
expand their scope, or establish independent project lifecycles. Read applicable
ancestor entrypoints before changing a directory.

The explicit anonymous-authoring instruction in repository-root `AGENTS.md`
takes precedence over conflicting imported Process attribution defaults. The
[documentation policy](051_dockflow/006_documentation.md) defines document
locations and maintenance without modifying those imported snapshots.

## Provenance and ownership

[composition.yaml](composition.yaml) pins exact package versions and canonical
Git repositories/tags. External packages are unchanged, tracked `git-archive`
snapshots. [composition.lock.yaml](composition.lock.yaml) records resolved
commits, SHA-256 inventories, and executable flags. Preserve their license files.
The `dockflow`, `dockflow-cli`, `dockflow-pipelines` and `dockflow-artifacts` packages use
`source.type: local` and are editable during explicitly requested specification
work. Their initial package versions do not assign application release versions.

Process owns project phase, workflow records, and `specs-*` / `imp-*` baseline
policy. These identities are separate from reusable package versions and
Dockflow distribution versions. Source, tests, and tooling stay outside
`.macrostates/`; current-state documentation lives under
[implementation](../implementation/main.md).

For an explicitly requested future kickoff or recovery only, consult
[Project kickoff](project-kickoff.md). It does not rerun setup on ordinary
sessions. The repository-root README is user documentation, not a specification.
