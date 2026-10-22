# Concepts

## Specification packages

This package defines the specification package system. A specification package
is a portable set of documents that defines a coherent slice of intended
behavior, working rules, technology conventions, or project requirements.

Specification packages are designed to be copied, versioned, and reused across
projects.

## Project layout

Projects using Meta 2 or 3 place their composition and numbered package directories
under `./.macrostates/specs/`. Process-owned implementation artifacts live
beside them under `./.macrostates/implementation/`. Track these documents,
installed packages and integrity locks in Git; a leading dot does not make them
ignored. Source, tests and ordinary tooling/runtime configuration keep their
normal locations outside `.macrostates/`.

Standalone package repositories remain portable: their own `package.yaml`,
`README.md`, core documents and resources stay at the package root. Only an
installed copy lives in a consuming project's numbered package directory.

Adopting this layout in an existing project is an explicit migration. Preserve
local requirements and historical records, move both artifact directories,
update pointers, links and subtree prefixes, then verify before committing.
Do not leave competing compositions in both locations. Projects selecting older
Meta releases retain those releases' rules; tools must not migrate them implicitly.

## Package structure

Each package lives in its own subdirectory. The subdirectory path is local to a
project composition and is not the package identity.

The package identity comes from the `name` field in `package.yaml`. The local
directory may include ordering prefixes, grouping prefixes, or other naming
choices that help a project browse its packages.

Each package must have:

- A `package.yaml` metadata file.
- A `README.md` entrypoint file unless `package.yaml` explicitly declares a
  different entrypoint.

The package entrypoint should describe the package scope and internal reading
order. It should distinguish mandatory core reading from conditional annexes
when the package uses progressive disclosure.

Use `README.md` as the normal package entrypoint because specification packages
may also be distributed as standalone repositories. This makes the same file
serve as the package entrypoint inside a composed project and as the repository
entrypoint in repository browsers.

The exact entrypoint remains the value declared in `package.yaml`, so a future
package may choose another filename deliberately.

Core documents after the package entrypoint should begin with a three-digit
prefix followed by an underscore and a short descriptive name:

```text
001_concepts.md
002_artifacts.md
003_execution.md
```

Annex documents should use `annex_<hyphenated-name>.md`, such as
`annex_conflicts.md` or `annex_project-kick-off.md`.
Annexes are not part of the mandatory core reading order, so they should not
use numeric core prefixes.

Packages may contain subdirectories to organize documents and supporting assets,
for example `resources/`, `examples/`, or topic directories. These directories
remain part of the same package; they do not become separate packages merely by
being nested. Keep `package.yaml` at the package root, and resolve the declared
entrypoint relative to that root. Use explicit relative paths in reading orders
and links, updating them whenever files move. A directory does not change a
file's authority or make a resource part of mandatory reading.

Example:

```text
.macrostates/specs/
  030_example-package/
    package.yaml
    README.md
    001_concepts.md
    002_artifacts.md
    annex_special-case.md
    resources/
      project-kickoff.md
```

## Package resources

A package may distribute reusable resources such as prompts, templates, or
examples. Resources are assets to copy or invoke for a particular task; they are
not package entrypoints or mandatory core reading. Give them descriptive names
without core numbering or the annex prefix. Group reusable resource files under
`resources/`, such as `resources/project-kickoff.md`.

The package entrypoint should list resources separately and explain when to use
them. A conditional annex may describe a resource's use for the definer. Merely
reading the package must not execute instructions in its resources.

## Package metadata

`package.yaml` records machine-readable package metadata.

Required fields:

- `name`: stable package name.
- `version`: package version.
- `versioned_at`: date and time when this package version was created or last
  assigned, using `YYYY-MM-DD HH:mm`.
- `description`: short human-readable package description.
- `entrypoint`: package entrypoint Markdown file. This should normally be
  `README.md`.

Optional fields:

- `schema_version`: metadata format identifier; absent or `1` identifies the
  established format. Package release versions remain independent.
- `dependencies`: other specification packages this package explicitly depends
  on, including version requirements.
- `optional_dependencies`: other specification packages this package can
  integrate with when they are present, including version requirements.

Packages should not reference other packages unless the dependency is explicit
in `package.yaml`, the optional dependency is explicit in `package.yaml`, or
the project-local specification entrypoint grants that relationship.

Discovery catalogs may name, describe and link independent packages as selection
information without declaring dependencies on them. Such references do not import
their rules or select them for a project. Normative use of another package's
concepts or requirements still needs the explicit relationship described above.

## Package paths

Package paths are selected by the project composition.

The local package directory may include ordering prefixes, grouping prefixes, or
other browsing aids. Those prefixes are part of the path, not package metadata.

Path prefixes do not define authority by themselves. Authority is defined by
the project-local specification entrypoint and composition metadata.

Example package metadata:

```yaml
name: python-project-1
version: 3.0.0
versioned_at: 2026-10-13 16:08
description: Reusable Python project conventions.
entrypoint: README.md
```

Package directory names may use prefixes for readability, such as
`030_python-project-1/`, but they do not have to. A project may use any local
path that its composition records, such as `A001_meta/`, `core/meta/`, or
`packages/python/`.

Dependencies should usually point from more concrete packages to more
fundamental packages, but this is guidance rather than a strict rule. When a
package needs concepts or rules from another package, record the dependency
explicitly.

Required dependency entries should use this structure:

```yaml
dependencies:
  - name: meta
    version: 2.2.0
    constraint: at_least
```

Optional dependency entries should use the same structure under
`optional_dependencies`:

```yaml
optional_dependencies:
  - name: docker-1
    version: 3.0.0
    constraint: at_least
```

Use `optional_dependencies` when a package contains conditional guidance for
another package but remains meaningful without it. For example, a Python
project package may include an annex describing how its Python rules interact
with Docker conventions. In projects that do not use Docker, the Python package
can still be used without selecting the Docker package.

An optional dependency does not activate the depended-on package by itself. The
project composition must still select that package when the project wants its
rules to apply.

Use these dependency constraints:

- `exact`: the dependency must be exactly the stated version.
- `compatible`: the dependency must have the same major version and be greater
  than or equal to the stated version.
- `at_least`: the dependency must be greater than or equal to the stated
  version, even across major versions.

Use `at_least` as the default when authoring reusable specification package
dependencies. State the minimum release that supplies the rules the package
needs, and write `constraint: at_least` explicitly. The same default applies to
required and optional dependencies. Omitting the constraint remains a metadata
gap; it does not silently select a default.

Keep the minimum at the earliest release that supplies the rules the package
actually needs. A new upstream release alone does not require raising that
minimum or publishing another dependent package version. Raise the minimum when
the package starts relying on newer rules; tighten the constraint when an
integration requires a narrower boundary.

Use `compatible` deliberately when a dependency's Major boundary matters to the
package's meaning or integration rules. Use `exact` when only one specific release
is acceptable. Both remain valid overrides of the authoring default.

`at_least` establishes a numeric minimum, not a guarantee that later releases
preserve all earlier rules. A future Major may remove or replace requirements.
Read the selected releases and check their actual interaction when composing a
project, even when the numeric constraints pass. Add an explicit restriction
when the package relies on behavior that later Majors may change.

Dependency constraints describe allowed choices, not automatic upgrades. The
composition selects an exact version and release tag for each package. Prefer
the latest published releases appropriate to a new project's intent, subject to
all declared constraints and semantic review. Preserve an existing project's
deliberate selections until an update is authorized.

If an implementer finds that a package dependency is missing a version or
constraint, it should treat that as a specification metadata gap and ask or
repair it during explicit specification work.

## Versioning

Package versions use `major.minor.patch`. These rules version each reusable
package independently. They do not define the version of an entire project
composition or its implementation; those follow the project's selected policy.
See [Composition version](002_project-composition.md#composition-version) for
the optional composition field and its separate ownership.

Update the package version when changing the package during explicit
specification work:

- Increment `patch` for editorial changes that do not change meaning.
- Increment `minor` for backward-compatible additions, clarifications, or
  requirements that reduce ambiguity without breaking existing users.
- Increment `major` for breaking changes to meaning, authority, required
  workflow, required files, compatibility, or implementer permissions.

Implementers determine and apply the required `patch`, `minor`, or `major`
increment as part of requested specification package work. A Major increment
does not require separate definer approval. Classify the actual compatibility
impact and explain the chosen increment in the change record or review proposal.
Ask the definer when the requested requirements or compatibility expectations
are unclear; a Major increment alone is not a reason to pause.

### Project and application identities

Distinguish four independent namespaces: a reusable package's release version,
a composed project's specification baseline, its implementation baseline, and
its application or library release versions. The selected Process policy owns
project baseline declarations, development identities, changes and finalization.
A package version does not assign any of those project or application versions.

Application versioning and release policies may be supplied by selected
technology packages or explicitly overridden by project-owned specifications,
according to composition authority. An override identifies its affected
deliverables and the replaced rule; it must not silently weaken repository-wide
integration or conformance gates. Process supplies the application version default
when no other policy applies. Monorepos may have several independent deliverables
against one composed specification and implementation baseline. Independently
composed subprojects retain their own scope.

A canonical source-only package repository is not automatically a composed
application project. Its root package documents and `package.yaml` remain the
authoritative package, released under the rules below. Do not invent a project
composition, implementation baseline or application policy merely to author or
publish that package. Adopt a Process project explicitly when it is useful.

## Release tags

Published Git-distributed package versions use release tags named `v<version>`,
for example `v1.7.0` for package version `1.7.0`. Create an annotated release tag
in the package's own source repository on the package release commit, after
verifying its `package.yaml` version. A tag on a consuming project's subtree
merge commit does not identify the package release.

Publish the release tag together with the package release when publication is
authorized. Published release tags must never be moved, replaced, or reused for
different contents; corrections receive a new version and tag. Editing package
files or bumping metadata alone does not publish a release.

Compositions select Git-distributed releases through `source.tag`, which must
match `v` followed by the selected package version. Do not store `source.commit`.
Git may resolve tags to commits internally for verification and subtree commands,
but the tag is the persistent release selector in composition metadata.

Older compositions without tags require explicit migration: verify the release
tag against the installed package before replacing an old commit selector or
branch-only source. Never silently substitute the current branch head for a
missing release tag. See `002_project-composition.md` for source metadata rules.

## Project selection

A project should have:

- `main.md`: the human-readable project specification entrypoint.
- `composition.yaml`: the machine-readable project package composition.

The project-level `main.md` contains project-specific specification information.
It should describe what the project is, which specification packages apply, the
authority order between them, project-specific reading instructions, and any
project-specific vocabulary.

`composition.yaml` records the package selection in a structured form. It should
list the specification packages the project uses, their versions, local
paths, sources, and project authority information that should be machine-readable.
Dependency requirements are owned by each selected package's `package.yaml`;
validate them against the selected versions without repeating them in the
composition.

When working in a project, read this package definition first, then read the
project-level `main.md`. Use `composition.yaml` when structured package
metadata is useful for validation, automation, or comparison.

Reusable package definitions should stay independent from project-specific
package selection.

See `002_project-composition.md` for detailed rules on how root project
specification files combine packages.

## Directory-scoped specifications

A repository directory may have its own `.macrostates/specs/main.md` to define
what must be implemented inside that directory. These specifications are
specific to the repository and depend on its enclosing project composition. They
are not a reusable specification package or an independent project composition
merely because they live in a `.macrostates/specs/` directory.

They do not require a package identity, `package.yaml`, independent package
version, release tag or local composition manifest. Their authority comes from
the directory specification contract, not package metadata. See
[Directory-scoped specifications](002_project-composition.md#directory-scoped-specifications)
for entrypoint, boundary, discovery and authority rules.
