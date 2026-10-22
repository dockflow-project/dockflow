# Annex: Macrostates CLI

Read this annex when using the CLI for project setup, composition inspection or
verification, or deciding how to perform equivalent checks manually. It is
conditional guidance; merely reading Meta does not run commands or install tools.

## Recommendation and ownership

The CLI is strongly recommended when it supports the project's selected versions
and conventions. Installation and use are optional. Use relevant manual checks
when it is unavailable, incompatible, or insufficient for the requested review.
Keep verification coverage and limitations visible with either method.

The selected specifications and project authority order define requirements.
The CLI checks the formats and policies implemented by its installed version.
A passing command does not establish semantic consistency, implementation
conformance, workflow approval or readiness beyond the checks actually performed.

The [CLI repository and README](https://github.com/Macrostates/macrostates-cli#readme)
own installation instructions, command options, supported versions, lock formats,
authentication and development details. Consult that documentation and
`macrostates --help`; do not assume a command or compatibility claim from a
different version. Record the CLI version when it matters to reproducibility.
No separate CLI specification package is required in a project composition.

## Choosing an operation

The following commands are supported by applicable CLI releases. Use them only for the scope and
formats that its documentation supports:

| Operation | CLI assistance | Manual equivalent |
| --- | --- | --- |
| Inspect composition | `macrostates info` | Read the entrypoint, composition and selected package metadata; identify versions, paths, sources, dependencies and explicit orders. |
| Check structure | `macrostates lint` | Compare selection with metadata; check dependency constraints, cycles, safe paths, entrypoints, references and reading/authority orders. |
| Check installed package integrity | `macrostates verify` | Compare package file contents, file inventory and executable flags against an understood verified baseline or the canonical selected release. |
| Check a proposed commit | `macrostates check --staged` | Inspect the exact staged composition, package files and declarations, and apply the relevant structural and integrity checks to that tree. |
| Record a verified baseline | `macrostates lock` | Verify existing files against the canonical selected release before recording provenance and integrity evidence in a documented format. |

`info`, `lint`, `verify` and `check` perform local inspection and validation.
Consult the installed version for any options requiring Git or source access.
`lock` contacts sources and writes a lockfile. `init` creates project files;
`install` downloads and writes supported archive-based packages. Use writing
commands within authorized setup or synchronization work; verification by itself
does not authorize changing package selections or replacing local files.

Meta 2 uses `.macrostates/specs/` and tracked release snapshots.
Generic `git-archive` imports work with configured Git transports; the legacy
provider archive adapter remains optional. The CLI supports this layout and its integrity lock. Git-subtree
selections remain an explicit alternative; `install` does not maintain them.
Follow the selected source's import/update procedure. Tool availability never
authorizes a layout or source migration; projects selecting older releases
retain their selected rules.

## Process assistance

When the selected Process policy defines change records, development identities,
branch synchronization and release preparation, use the installed CLI's help and
supported-policy documentation for those operations. Distinguish read-only
identity, change checking and release planning from writes such as creating a
change record, preparing declarations or synchronizing a development branch.
Never infer authorization to fetch, merge, rebase, commit, submit a proposal,
close workflows, tag or publish from a passing check.

Manual equivalents read the recorded origin, classify both specification and
implementation impact, inspect the actual combined target result, collect pending
records and calculate a release once. Validate stored declarations and exact
source identities, retain evidence, and follow definer-confirmed workflow closure.
A CLI can check structure and stale input; semantic impact and requirement
coverage remain implementer responsibilities. No hosting integration is required.

## Manual verification

For metadata and dependency checks, read each selected package's `package.yaml`.
Check its name, version and entrypoint against the composition. Validate required
dependencies and validate optional constraints only when the dependency is
selected. Use the constraints defined in [Concepts](001_concepts.md#package-metadata),
including cycle detection. Numbered folder names do not establish authority.

For integrity, compare the relevant files with the verified selected source tag
or a trusted, documented lock baseline. Include missing and additional files,
file bytes and executable flags. A clean Git working tree alone does not prove
that a package matches its source. Project-owned local specifications are
intentionally editable; check their structural consistency without requiring
them to equal a downloaded release.

If a lock is used, confirm that its package names, versions, paths, entrypoints
and sources match the current selection. Read its documented format before
interpreting hashes or resolved source identities. A lock may record verification
evidence separately; it does not replace `source.tag` or permit `source.commit`
in the composition. Never create or rewrite a baseline simply to accept
unexplained modifications. Compare extracted contents rather than compressed
archive bytes, which can change without changing the files.

Before a commit, inspect staged files rather than relying only on working-tree
checks; partially staged files may differ. Apply any declaration/version policy
owned by the project's selected rules. The CLI supports a bounded set of those
policies, so verify relevant requirements beyond its coverage manually.

If canonical source access, a trustworthy baseline or necessary format knowledge
is missing, report precisely which checks remain unverified. Obtain the missing
evidence for any readiness gate that requires it. Optional tooling does not
make required verification optional.

## Version support and reporting

Package release versions, composition and lock formats, and CLI versions are
separate. Preserve the project's deliberate selections. An unsupported format or
policy is a tool coverage gap: use an appropriate available tool version or
manual checks against the selected specifications. Do not downgrade packages,
reinterpret unknown fields or change versions solely to make a command pass.
Distinguish unsupported checks from actual failed integrity or metadata checks;
investigate failures rather than bypassing them through the manual fallback.

Record the method, checked scope and result in the owning workflow or normal
validation evidence. For CLI use, include relevant commands and tool version;
for manual work, identify the compared baseline and checks performed. Preserve
known limits and separately assess meaning, authority conflicts and implementation
behavior through specification reading, review and applicable tests.
