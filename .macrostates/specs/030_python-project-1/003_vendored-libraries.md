# Vendored libraries

Vendored libraries are reusable Python libraries whose canonical ownership is
outside the consuming project, but whose source is intentionally included in the
consuming repository.

Vendoring is exceptional. Ordinary third-party dependencies should normally be
installed through the dependency management mechanism instead of copied into the
repository.

The Implementer should not choose vendoring as an implementation convenience.
Vendored libraries should be added only when requested by the Definer or when a
specification document explicitly requires them.

Vendored libraries are normally owned and maintained outside the consuming
project, often by the Definer. The reason to include them by subtree is
convenience for the consuming project, not a transfer of ownership into the
consuming project's ordinary source tree.

## Location

Vendored libraries should live under the top-level `./vendor/` directory.

The `./vendor/` directory is reserved for source-managed external library
projects. It is distinct from `./src/`, which contains source owned by the
consuming project.

A typical layout is:

```text
src/
  <application_package>/
tests/
  unit/
  integration/
  contract/
vendor/
  <library-repository-name>/
    pyproject.toml
    src/
      <library_import_namespace>/
    tests/
    README.md
    LICENSE
```

## Complete library projects

Each vendored library should be included as a complete standalone Python
project, not merely as a copied import package.

When applicable, a vendored library should retain:

- its own `pyproject.toml`;
- its own `src/` layout;
- its own tests;
- its own README or documentation;
- its own license;
- its own package metadata.

This keeps the library independently understandable, testable, buildable, and
publishable.

## Source management

Vendored internal libraries should normally be maintained with Git subtree.

Do not use Git submodules for this convention unless a project-specific
specification explicitly chooses them. Do not manually copy library source
between repositories as a normal maintenance process.

The intended source-management model is:

```text
canonical library repository
  <-> Git subtree
consuming project ./vendor/<library-repository-name>/
```

This means a normal clone of the consuming repository contains the vendored
source immediately, without submodule initialization or recursive clone steps.

Each consuming project decides independently when to update its vendored copy.
Different consuming projects may intentionally carry different revisions of the
same vendored library.

Vendored libraries must not be treated as ordinary project source merely because
their files are present in the consuming repository. Their canonical repository,
subtree relationship, and independent lifecycle remain part of the project
state.

## Subtree manifest

Existing vendored Git subtrees should be recorded in `./vendor/subtrees.toml`.

The manifest preserves the subtree maintenance information that is not fully
recoverable from a normal clone of the consuming repository. The vendored source
files are present after cloning, but the operational knowledge needed to pull
from or push to the canonical library repository must be recorded explicitly.

Use this format:

```toml
[[subtree]]
path = "vendor/logging-library"
repository = "https://git.example.org/example/logging-library.git"
branch = "main"

[[subtree]]
path = "vendor/protocol-library"
repository = "https://git.example.org/example/protocol-library.git"
branch = "main"
```

Each `path` should point to the vendored library directory inside `./vendor/`.
Each `repository` should be the canonical upstream Git repository. Each
`branch` should be the upstream branch normally used for subtree pull and push
operations.

When vendored libraries exist, `./vendor/subtrees.toml` should exist and should
describe every vendored subtree unless another specs package explicitly defines
a different manifest location.

## Vendored library records

When a library is vendored, implementation documentation should record enough
information to maintain it intentionally.

For each vendored library, record at least:

- the local path;
- the canonical upstream Git repository;
- the Git subtree prefix;
- the corresponding `./vendor/subtrees.toml` entry;
- how upstream changes are pulled into the consuming repository;
- how local vendored changes are propagated back upstream, when allowed.

The exact location for this documentation is defined by the process and
project-specific specs packages.

## Nested specifications

Vendored libraries are a Python-specific form of subproject as defined by the
process specs package.

Vendored libraries may have their own `./.macrostates/specs/` directory, their
own lifecycle rules, a different process, or no local specifications at all.
When local vendored-library specifications or lifecycle rules exist, they have
authority over the library's internal behavior, structure, and lifecycle. The
consuming project's specifications still govern how the consuming project
integrates, records, and maintains the vendored dependency.

The Implementer should not read a vendored library's internal specifications
merely because the consuming project imports or uses that library. For ordinary
usage, treat the vendored library as a dependency and read only public usage
material when needed, such as the vendored library's `README.md`, examples, API
documentation, or package metadata.

Read the vendored library's internal specifications, workflow records, or
lifecycle artifacts when changing files inside that vendored library, when
diagnosing vendored-library lifecycle or subtree maintenance problems, or when a
requested consuming-project change depends on those internal rules.

For example, if `./vendor/logging-library/.macrostates/specs/` exists and the
Implementer is asked to change `./vendor/logging-library/src/`, the Implementer
should inspect and follow the vendored library specifications before applying
the consuming project's general Python conventions to that library.

## Standalone subproject boundary

A vendored library that is intended to have its own canonical repository should
be self-contained inside its subtree. Its source, tests, package metadata,
documentation, implementation notes, workflow records, and local specifications
should be meaningful when the library directory is viewed as the root of its own
repository.

Vendored library specifications must not depend on specification packages,
implementation documents, workflow records, paths, or authority rules that live
only in the consuming project. A consuming project's specifications govern how
that project vendors, integrates, and records the dependency; they should not be
used as hidden inputs for the vendored library's own specification composition.

When a vendored library reuses specification packages that are also used by the
consuming project, include those needed packages inside the vendored library's
own `./.macrostates/specs/` directory. Obtain them from the canonical
specification release sources selected by that library's composition, normally
tracked immutable release snapshots with its own integrity lock. Explicit Git-subtree
selections retain their separate repository/prefix relationships. This does not
change Git subtree maintenance of the vendored library's executable source.

For example, if both a consuming project and `./vendor/logging-library/` use the
Macrostates `meta` package, both repositories may contain a local
`.macrostates/specs/000_meta/` package copy. The vendored library's
`.macrostates/specs/main.md` and `.macrostates/specs/composition.yaml` should
point to the copy inside the vendored library, not to the consuming project's
`./.macrostates/specs/000_meta/`.

Do not add the consuming project's project-shaped specification package to a
vendored library merely because the consuming project uses it. A reusable
library should select library-appropriate specifications that can stand on their
own. If a Python library convention package exists, it should sit beside
project-shaped Python specifications and may depend on lower-level Python rules,
but it should not depend on the consuming project's Python project package.

Vendored libraries are also an exception to the consuming project's project
phase boundaries. A vendored library may be treated as an independent project
for specification and implementation work, even while the consuming project is
still in its initial specification phase.

For example, the Definer may have existing code that they want to turn into a
vendored library before the consuming project has been bootstrapped. The Definer
may place that code under `./vendor/<library-repository-name>/`, create or
modify the vendored library's own specs, and ask the Implementer to work on that
library as a bounded vendored-library project. In that case, the Implementer
should follow the vendored library's own specs for library work while still
maintaining the consuming project's vendor manifest, workflow records, and
integration notes required by this package and the process package.

## Maintenance responsibility

The Implementer is responsible for keeping vendored library state visible and
healthy within the consuming project.

When starting or continuing relevant workflows, the Implementer should notice
whether vendored libraries exist and whether their maintenance state may affect
the requested work.

The Implementer should warn the Definer and suggest an appropriate action when:

- local changes were made under `./vendor/` and may need to be propagated back
  to the canonical library repository;
- upstream library changes may need to be pulled into the consuming repository;
- vendored library metadata or maintenance records are missing, stale, or
  inconsistent;
- a vendored library appears to have been edited as ordinary consuming-project
  code rather than as an upstream-owned library;
- expected vendored library source is missing from the working tree;
- `./vendor/subtrees.toml` is missing, incomplete, or inconsistent with the
  vendored library directories;
- the uv workspace no longer includes a vendored library that the consuming
  project depends on;
- the consuming project imports vendored code through the `vendor` path instead
  of through the library's declared package namespace.

If the repository was cloned and a vendored subtree appears to be missing, the
Implementer should treat that as a project-state problem, not silently replace
the library source. The Implementer should inspect the repository state, report
the inconsistency, and ask the Definer how the project should be restored unless
existing specifications already define the recovery path.

If the Implementer changes vendored library code while working inside the
consuming repository, the final response should make that explicit and say
whether propagation back to the canonical repository is recommended or still
pending.

When a vendored subtree has been modified or appears to need an upstream update,
the Implementer is responsible for checking whether the Git subtree maintenance
state is initialized and usable in the current clone. If it is not, the
Implementer should use `./vendor/subtrees.toml` and the implementation
documentation to suggest or perform the appropriate initialization or recovery
steps allowed by the active workflow.

Vendored libraries should not be allowed to decay into untracked forks. If the
subtree relationship cannot be maintained, the Implementer should document the
problem and ask the Definer whether to restore subtree maintenance, convert the
library into ordinary project-owned source, or remove the vendored dependency.

## Imports

Python imports must be independent of vendoring.

Consuming code should import vendored libraries as normal installed Python
distributions. It should not import through the repository layout.

Avoid imports like:

```python
from vendor.some_library import Something
```

Prefer imports based on the library's declared Python package namespace:

```python
from shared_namespace.some_library import Something
```

Do not use manual `sys.path` manipulation or repository-specific `PYTHONPATH`
changes to make vendored libraries importable.

## Namespaces

Repository names, distribution names, and import namespaces are related but
separate concepts.

The import namespace should describe the logical Python API, not the physical
repository location.

When multiple independently maintained distributions contribute to the same
top-level namespace, use modern implicit namespace packages when practical. In
that case, the shared namespace directory should normally omit `__init__.py`,
while concrete child packages may define their own `__init__.py`.

## uv workspace integration

Vendored Python libraries should be integrated into the consuming project's
development environment through a `uv` workspace when practical.

Each vendored library remains its own Python project with its own
`pyproject.toml`. The consuming repository acts as the workspace root and
declares vendored libraries as workspace members.

The consuming project should depend on the vendored library by its declared
distribution name, not by filesystem-relative imports.

Workspace integration should make vendored libraries behave like ordinary
editable Python dependencies during development. Changes made under
`./vendor/<library-repository-name>/` should be visible to the consuming project
without manual reinstall steps when the workspace is configured correctly.

## Adding vendored libraries

Before adding a vendored library, the Definer must request it or approve an
explicit specification that requires it.

The Implementer should almost never suggest adding a vendored library. A
suggestion may be appropriate only when the existing specifications or the
Definer's stated intent already point toward an internally owned reusable
library whose source should travel with the consuming repository.

The confirmation should include why vendoring is preferred over an ordinary
dependency, where the library will live, who owns the canonical library, and
whether Git subtree maintenance is expected.

Adding or updating vendored library source should be handled as a meaningful
workflow change because it affects both dependency behavior and repository
history.

When adding a vendored library, the Implementer should add or update
`./vendor/subtrees.toml` together with the vendored source and implementation
maintenance records.
