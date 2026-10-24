# Dependencies, workspace, and builds

## Published dependencies

Each distribution declares the direct runtime dependencies it imports or needs
for supported behavior in its own `pyproject.toml`. Keep runtime dependencies
minimal. Separate development tools, tests, and optional integrations from the
base runtime; do not make the shared CLI depend on feature modules.

Published metadata uses tested dependency ranges rather than freezing the entire
consumer environment. Set a lower bound at the earliest version actually
qualified for the required behavior. Use the next major as the default upper
compatibility boundary for dependencies at 1.0 or later, and the next minor for
0.x dependencies. Narrower or broader bounds require compatibility evidence and
a recorded reason; do not assume every upstream release follows semantic
versioning perfectly.

Initially constrain KFP to one qualified minor release line because Dockflow
depends on its local execution behavior. Pipelines owns the actual selected
line, minimum patch, and feature tests. Do not select a KFP release just from a
Python classifier or use this policy to invent the missing Pipelines contract.

For each coordinated Dockflow release, Pipelines requires the same exact
`dockflow-cli` application version. Release preparation synchronizes and checks
that dependency, including prerelease versions. Workspace development resolves
the local member, while published metadata contains a normal distribution
requirement with no local path, Git URL, or workspace-only source.

## Locks and dependency changes

Commit one root `uv.lock` for the workspace when implementation creates it. It
records exact resolved development/CI dependencies, including transitive ones.
CI uses locked resolution and fails if dependency metadata and the lock disagree;
ordinary builds must not upgrade dependencies or rewrite the lock implicitly.

Service image builds install the selected runtime subset from the same reviewed
locked resolution, with the image's platform/Python selection explicit. Pin
third-party service/base images to tested immutable digest identities, using a
multi-platform index digest where appropriate. Keep version labels readable and
update digests deliberately.

Update dependency metadata and the lock together when ranges change. Review
within-range lock refreshes as scoped maintenance; investigate compatibility or
security fixes promptly. Qualification covers supported Python/platforms, clean
artifact installation, CLI discovery, and affected execution boundaries. Exercise
minimum direct dependency versions where practical and the locked configuration;
do not claim that a passing lock proves every allowed combination.

Follow the selected Python Project rules for new-dependency authorization. The
definer has selected uv and `uv_build` for this setup; this policy does not select
additional runtime libraries, services, or tool-specific versions. Keep private
index credentials and machine-local authentication out of tracked metadata.

## Workspace and environment

Use a single uv workspace with members `packages/cli`, `packages/pipelines`
`packages/artifacts` and `packages/database`,
one root lock, and the normal root `.venv` application environment. The repository
root is a development workspace, not a published distribution. Keep each
member's metadata and `src/` import boundary independently buildable.

Pin Python 3.13 as the workspace default, retaining the 3.12 compatibility target.
Run application tooling through uv; configure Ruff, Pyright, pytest, coverage,
and pre-commit under the selected Python Project conventions during
implementation. A separate pinned environment may bootstrap optional Macrostates
verification before the application workspace exists.

## Packaging and verification

Use `uv build` as the build interface and `uv_build` as the backend for all
pure Python distributions. Pin a reviewed backend compatibility range in each
member's build requirements and record the actual build toolchain in release
evidence. Custom build requirements or extension modules require deliberate
reassessment of this choice.

Write wheels and source distributions under ignored `dist/`. Include intended
source, resources, license notices, README/metadata, and all inputs needed for a
standalone source-distribution rebuild. Exclude local environments, credentials,
scratch data, workflow records, and development-only artifacts.

Verify wheel installation in a clean environment outside the workspace, plugin
registration, declared dependencies, and rebuilding each source distribution
without its original checkout or Git metadata. Version discovery must not depend
on network access. Ordinary builds do not assign versions or mutate source,
locks, release declarations, Git refs, or publication state.

References: [uv workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/)
and [uv build backend](https://docs.astral.sh/uv/concepts/build-backend/).

Pipelines and Artifacts require the exact shared application version of
`dockflow-database`. The common library has a standard-library SQLite core and a
lazy optional PostgreSQL driver. It must not import CLI, Pipelines or Artifacts.
Database drivers, physical schema and immutable artifact records have one owner
there; domain repositories retain their execution/publication policies.

Pipelines also requires the exact shared Artifacts application version so offline
backups validate standalone completion manifests against their copied payloads.
Artifacts remains independent from Pipelines and CLI.
