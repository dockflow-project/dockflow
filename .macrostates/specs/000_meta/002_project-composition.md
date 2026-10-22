# Project composition

A specification project combines multiple specification packages into one
project-specific specification set.

The project composition lives at the root of `.macrostates/specs/` and should
contain:

- `main.md`: the human-readable project specification entrypoint.
- `composition.yaml`: the machine-readable package composition.
- `composition.lock.yaml`: verified provenance and content inventory for imported
  tagged Git snapshots, when that source mechanism is used.

`composition.yaml` is the conventional filename. `composition.yml` is also
accepted; use exactly one manifest per project. References to `composition.yaml`
in these rules also apply to that alternative spelling.

## Project kickoff

For a new project whose packages have not yet been imported, read [Project
kickoff](annex_project-kick-off.md). It explains how the definer copies the
`resources/project-kickoff.md` resource to
`.macrostates/specs/project-kickoff.md` and points to the copied file from
`main.md`. The short resource introduces Macrostates and its Meta clone source;
the annex owns selection, validation and import steps. When no composition
exists yet, the annex requires discussion of the definer's intent and
technologies before preparing a compatible package selection. Read [Official
packages](annex_official-packages.md) when discovering candidates. The initial
entrypoint may contain just that kickoff instruction and any known project
intent. After kickoff, it must satisfy the normal composition rules below. This
temporary starting state does not require copying package folders.

## Repository agent entrypoint

A repository may include a root `AGENTS.md` file for tools or agents that look
for repository-level instructions before reading project files.

When present, root `AGENTS.md` should be extremely small and reusable. It should
point implementers to `.macrostates/specs/main.md` and tell them to follow the
specification composition, reading order, and authority rules defined there.

Root `AGENTS.md` should not describe the project, duplicate package rules, or
contain project-specific implementation instructions. Those belong in the
appropriate specification package or implementation documentation.

## README authority

`README.md` authority depends on where the file lives and what role metadata
assigns to it.

A package-level `README.md` is authoritative for that specification package
when the package's `package.yaml` declares it as the package entrypoint.

A repository-root `README.md` is repository documentation for people and tools
encountering the repository. It should not be treated as a specification
document merely because specification packages use package-level `README.md`
entrypoints.

If a project needs a root `README.md` update because package entrypoints changed,
that update should follow the repository documentation rules selected by the
project.

## Project entrypoint

The root `.macrostates/specs/main.md` describes the project-specific
specification set. It should be readable by humans and implementers before they
enter individual packages.

It should include:

- The project name or purpose.
- The specification packages used by the project.
- The selected version of each package.
- The selected local path of each package.
- The source or provenance of each package when relevant.
- The authority order between packages.
- The project-level reading order.
- The authority placement of directory-scoped specifications when present.
- Any project-specific vocabulary or interpretation rules.

The root `.macrostates/specs/main.md` may summarize package selection, but it
should not duplicate the detailed rules inside each package. When package
details matter, link or point to the package entrypoint.

## Directory-scoped specifications

Any implementation directory inside a repository may contain a
`.macrostates/specs/` subdirectory with `main.md` as its entrypoint. This
supports repositories with multiple packages, applications or other components
without requiring a separate specification package or project composition for
every directory.

For example:

```text
.macrostates/
  specs/
    main.md
    composition.yaml
    000_meta/
apps/
  reporting/
    .macrostates/
      specs/
        main.md
        interfaces.md
    src/
```

Here, `apps/reporting/.macrostates/specs/main.md` owns specifications only for
`apps/reporting/` and its descendants, not the entire repository. The scope root
is the directory containing `.macrostates/`, here `apps/reporting/`; neither
`.macrostates/` nor its `specs/` directory is the scope root. A deeper directory
may also have its own `.macrostates/specs/main.md`; each scope remains limited
to its own root and descendants.

### Repository dependence and scope

Directory-scoped specifications belong to their enclosing repository project.
They may rely on its selected packages, vocabulary and requirements, and are not
portable, independently versioned specification packages. Do not list them as
packages in `composition.yaml` or require `package.yaml` or a local composition
manifest. Additional documents may be organized freely inside the local
`.macrostates/specs/`; `main.md` must identify the scope, purpose and reading
order, and link to the documents that carry requirements.

Directory specifications must not define requirements, behavior, ownership,
authority or required changes outside their scope root. They must not govern
ancestor directories, siblings or repository-wide policy. This limit cannot be
expanded by local wording, relative paths, linked documents or filesystem links.
They may reference external interfaces and enclosing specifications as context,
and define how their own component consumes or implements those interfaces;
they must not impose obligations on the external component. Requirements that
span directories belong in specifications with an enclosing scope.

### Discovery and authority

Before changing files, inspect the directories along the path from the enclosing
project root to each target directory for `.macrostates/specs/main.md`. Read
applicable entrypoints from outermost to innermost and follow their local
reading orders. Apply this also to new files and directories through their
existing ancestors. A scope applies only to targets within that scope; do not
load sibling scopes merely because they exist. Work spanning several scopes must
satisfy each applicable set for its own targets.

Directory specifications have the same normative status as selected specification
packages: they are definer-owned intended requirements, not implementation notes
or advisory documentation. The enclosing project entrypoint defines their
placement in its authority order. Local reading order does not establish priority
over enclosing specifications or packages, and a local entrypoint cannot elevate
its own authority or expand its scope. If the enclosing authority rules do not
resolve a conflict, ask the definer rather than assuming the nearest directory
wins. Existing enclosing requirements continue to apply within their scope.

A directory specification does not by itself establish a subproject or grant an
independent lifecycle. An explicitly separate project composition remains a
distinct context, not a directory specification set. The selected project rules
own subproject identification, lifecycle and integration; this directory mechanism
does not replace those rules.

## Composition metadata

The root `.macrostates/specs/composition.yaml` records the same package
composition in a structured form for validation, automation, and comparison
across projects.

It should include:

- Project metadata.
- Package names.
- Package versions.
- Package paths.
- Package entrypoints.
- Package sources when relevant.
- Project authority order when it should be machine-readable.
- Project reading order when it should be machine-readable.

New compositions using Meta 2 declare top-level `schema_version: 1`. This
identifies the established composition field format independently of package
versions. Record complete `reading_order` and `authority_order` lists using
selected package names or relative package entrypoints, each package exactly once.
Reading order does not establish authority. Adopt these declarations explicitly
when migrating an unversioned composition to Meta 2.

### Composition version

Project metadata may include `project.version`, identifying the complete composed
specification baseline rather than any individual package or its implementation:

```yaml
project:
  name: example
  entrypoint: main.md
  version: "specs-6.4.2"
```

Meta defines the field and its scope, not its versioning policy. The selected
policy may distinguish a last finalized baseline from accepted unreleased work;
then this field alone must not claim that current files equal the finalized
snapshot. A selected package
or the explicit project contract defines whether the field is required, its format,
bump rules and any relationship to an implementation version. The example prefix
is illustrative; Meta does not require it for all compositions. Record the policy
owner in the human-readable project entrypoint so an implementer can locate it.
Meta does not depend on that policy package.

The snapshot includes the project entrypoint, composition, selected package
contents and applicable repository-specific directory specifications. Independently
composed subprojects retain their own specification snapshots; the parent snapshot
includes its requirements for their integration. File edits and package-selection
changes must be assessed under the selected policy even when they do not change
the effective project contract.
The policy defines finalized revision boundaries; Git can identify intermediate
work. A composition version must not replace package versions, dependency
constraints or package source release selectors. Do not use `package_version`
for the composition or derive it from the project-local package's version.

If a composition version is summarized elsewhere, keep the summary synchronized
with `project.version`. Do not infer an implementation's version or conformance
merely from this field. Projects adopting a new policy must identify their
transition and any pending implementation work explicitly.

### Package selection

Package entries should use this shape:

```yaml
packages:
  - name: process
    version: 5.0.0
    path: 001_process/
    entrypoint: README.md
```

`composition.yaml` should not replace package-level `package.yaml` files. It
records which package versions this project selected; each package still owns
its own metadata. Required and optional dependency requirements belong only in
the selected package's `package.yaml`. Do not duplicate `dependencies` or
`optional_dependencies` in new or migrated composition entries.

Read dependency requirements from every selected package's metadata. Every
required dependency must be selected and satisfy its declared version constraint.
Check an optional dependency's constraint only when that package is selected;
an optional declaration does not select a package by itself. Report missing
dependencies, incompatible versions, cycles and inconsistent package metadata.

For backward compatibility, existing compositions may retain matching dependency
copies during migration. These copies are non-authoritative and must never
override package metadata. Report mismatches rather than choosing one silently.
Migration removes those redundant fields after verifying package requirements
against the selected versions; it does not edit package requirements.

The package `path` may include ordering prefixes, grouping prefixes, or any
other project-local browsing convention. The path is the only field needed to
record where the package lives in the project.

## Package sources

A package entry may include `source` metadata that records where the local copy
comes from and how it should be synchronized.

Use `source` in `composition.yaml`, not in package-level `package.yaml`, because
source is a relationship between a specific project and its local package copy.
The same package version may be obtained from different places in different
projects.

Use `source.type: local` for packages owned only by the current project:

```yaml
packages:
  - name: project-local-specs
    version: 1.0.0
    path: 900_project-local-specs/
    entrypoint: README.md
    source:
      type: local
```

Use `source.type: git-archive` for tagged snapshots from a Git repository,
independently of its hosting service:

```yaml
packages:
  - name: example-package
    version: 2.0.0
    path: 020_example-package/
    entrypoint: README.md
    source:
      type: git-archive
      repository: https://git.example.org/specs/example-package.git
      tag: v2.0.0
```

`repository` identifies the canonical Git URL or an explicitly selected local
repository path. Authentication uses the Git transport's configured mechanism;
credentials must not be embedded in the composition. Local paths are explicit
local provenance and need not be usable on another machine. Prefer a portable
Git URL when the composition is shared. Source access is separate from offline
validation and may require transport configuration.

Resolve the explicit `refs/tags/<tag>`, verify tagged package metadata, and
extract a Git archive at its resolved commit. Strip only an enclosing archive
root when present. There is no build step or nested Git repository. Track all
package files under the declared path and record canonical provenance and
inventory in `.macrostates/specs/composition.lock.yaml`; see [Package integrity
locks](annex_package-lock.md). Never substitute a moving branch head or `latest`
for a release. Reject unsafe archive content before installing it. Resolution,
metadata validation, import and lock must refer to the same commit.

The optional legacy `source.type: github-archive` uses its provider's tagged
archive service with the same `repository` and `tag` fields and integrity rules.
Existing selections remain supported; a source-type conversion is explicit and
must preserve verified package bytes and provenance. No provider account or
provider-specific API is required for the generic Git mechanism. Git subtree
remains a separate supported mechanism rather than an implicit conversion.

Imported external packages are immutable in a consuming project. Verify their
file bytes, inventory and executable flags against the lock. Propose changes in
the canonical package repository under an explicit specification request, then
publish a new version and deliberately update consumers. Project-owned
`source.type: local` packages remain editable. An explicitly authorized fork or
source conversion must record its new provenance; rewriting a lock must never
legitimize unexplained local edits.

Git subtree remains an explicitly selected alternative, including established
projects whose maintenance depends on subtree history:

```yaml
packages:
  - name: meta
    version: 2.2.0
    path: 000_meta/
    entrypoint: README.md
    source:
      type: git-subtree
      repository: https://git.example.org/specs/meta.git
      branch: main
      tag: v2.2.0
      prefix: .macrostates/specs/000_meta
```

For `git-archive` and `github-archive`, `repository` and `tag` are required. For `git-subtree`,
`repository`, `branch`, `tag` and `prefix` are required. The prefix is relative
to the project Git root and must identify the exact installed package directory.
Archive installation must not silently convert a subtree. Preserve established
provenance during an authorized source or layout migration. Specification
imports and vendored application/library source are separate mechanisms;
changing one does not convert the other.

`tag` selects the release to import and must be `v<version>`, matching the
package's selected version. Resolve it explicitly as `refs/tags/<tag>` in the
source repository, then verify the tagged `package.yaml` name and version.
For Git subtree, `branch` records the development branch used for checking future updates and
publishing authorized changes; it does not select the installed release.

Do not include `source.commit` in composition metadata. Resolved commit IDs belong in the separate integrity lock or transient
verification data, never as an additional composition selector. A missing tag or mismatched package
version is a release metadata gap: report it and stop the affected import rather
than falling back to a branch or inventing a release tag.

During an approved update, import the selected release tag, validate the result,
and update `version` and `source.tag` together. Changing a selected tag is a
deliberate synchronization operation, not an ordinary kickoff rerun.

When migrating a legacy composition, replace `source.commit` or a branch-only
selection with the corresponding verified release tag. If the release has not
yet been tagged, record the pending publication in workflow documentation; do
not claim the declared tag is available or importable. Local package edits may
select the next planned version and tag during explicit specification work, but
release publication must verify and create that tag before consumers import it.

Package source and package version are separate concepts. The source describes
where the local package files came from and how to update or push them. The
version describes the semantic specification package version selected by the
project.

If a package is intended to be distributed from an external source but that
source does not exist yet, omit `source` until the source is real. Do not invent
placeholder repositories.

A project may select both a package and its optional dependency when it wants
their integration rules to apply. The optional requirement and its constraint
remain in the dependent package's `package.yaml`, not in the composition.

## Consistency

The root `.macrostates/specs/main.md`, root
`.macrostates/specs/composition.yaml`, and each package's `package.yaml` should
agree about package names, versions and entrypoints. Dependency requirements are
validated from each `package.yaml` against the composition's selected versions;
missing composition dependency copies are not a metadata gap. Legacy copies, if
present, must agree with package metadata. Package paths are owned by the
project composition and should point to the local directory that contains the
matching `package.yaml`.

Package source metadata is owned only by `composition.yaml`; it is not expected
to appear in package-level `package.yaml`.

When changing a package version, update:

- The package's own `package.yaml`.
- The package entry in root `.macrostates/specs/main.md`.
- The package entry in root `.macrostates/specs/composition.yaml`.
- Any package-level dependency requirement that intentionally changes as a result.

If these files disagree, treat it as a specification metadata gap. Ask the
definer or repair it during explicit specification work before relying on the
inconsistent metadata.

### Recommended validation tool

The Macrostates CLI is strongly recommended for supported composition inspection
and specification checks. Prefer it when an available version supports the
project's selected package releases, metadata formats and source mechanism.
Read [Macrostates CLI](annex_cli.md) when choosing commands, arranging tool use,
or performing equivalent manual checks.

CLI installation and use are optional. A project remains valid without the CLI;
its absence or incomplete version support should not prevent work that can be
verified manually. Apply the same specification requirements with either method,
and report missing verification evidence rather than claiming an unchecked result.
Use manual checks when the tool is unavailable or incompatible, or when the
requested scope requires inspection beyond its coverage. Tool output supplements
reading the selected specifications and applying their authority rules.

The selected project rules own when verification is required. Match checks to
the affected scope and reuse relevant evidence for unchanged files when its
baseline remains valid. A new session or an unrelated code change alone does
not require an exhaustive comparison of every installed package.

CLI availability does not select packages, change their versions or authority,
authorize file changes, or migrate a composition. Follow the existing setup and
source rules unless the project explicitly adopts another supported convention.
The CLI is an optional external tool, not a specification-package dependency.

## Package independence

Project composition may combine independent packages, but it should not make a
package depend on another package implicitly.

If one package needs concepts, authority, or rules from another package, record
that dependency in the dependent package's `package.yaml` with a version
constraint.

If packages are merely used together by the project, list them together in
`composition.yaml` without adding package-level dependencies between them.
