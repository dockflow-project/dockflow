# Annex: starting a new project

Read when the definer requests preparation of a project's Macrostates
specification set. Ordinary Meta reading does not activate kickoff. This sets up
specifications; it does not start application implementation.

Before writing project files, inspect agent instructions, Git state and workflow
rules. If selected rules are not installed, inspect their source documents and
establish required workflow records before edits.

## Prepare the starting files

Begin with `.macrostates/specs/`, a copy of [the kickoff
resource](resources/project-kickoff.md) at
`.macrostates/specs/project-kickoff.md`, and `.macrostates/specs/main.md`:

```markdown
# My project specifications

This repository will follow Macrostates. For the requested kickoff,
follow [Project kickoff](project-kickoff.md).
```

Include known intent. A composition may be supplied now or prepared after
discussion. The CLI is strongly recommended but optional; see
[CLI guidance](annex_cli.md) for supported operations and manual equivalents.
Package access is required regardless of tool choice.

## Obtain instructions and understand intent

Inspect [Macrostates](https://github.com/Macrostates) and the Meta source
`https://github.com/Macrostates/macrostates-meta.git`. Download or clone into a
temporary location, then read `README.md`, its core order and this annex. An
inspection clone is not an installed package; install only a verified published
release. Never copy its Git metadata into the project.

Read [the official catalog](annex_official-packages.md). Understand intended
product, application/library role, languages, deployment, containers and
constraints before proposing a selection. Explain packages, required companions
and compatibility limits. Ask for material unresolved choices; do not infer them
from examples. Meta and Process are the common foundation; Repository is usually
useful, while technology packages depend on intent. Python-library is the library
alternative to Python-project. Optional dependencies do not select packages.

For a new composition, prefer the latest verified published release of each
appropriate package. Check the complete dependency set and read the selected
rules together before proposing it. An `at_least` requirement permits later
Majors numerically; it does not establish that their changed rules work together.
Explicit `compatible` and `exact` requirements still restrict selection. Explain
any reason to choose an earlier release rather than silently weakening a constraint.

If no composition exists, settle choices and then prepare it. For an existing
composition, preserve deliberate versions, sources, intent and explicit orders.
Multiple spellings or layouts require an authority decision; do not merge or
choose silently. Read candidate metadata and documents before selecting versions,
even when the latest official releases are mutually compatible.

Use top-level `schema_version: 1`, project identity/entrypoint, selected packages,
complete reading/authority orders and real sources under
[Project composition](002_project-composition.md). Dependencies remain in
`package.yaml`. Normally use `git-archive` with a Git repository URL and
`v<version>` tag. The optional `github-archive` transport remains available for
explicitly selected provider archives; `git-subtree` sources also need branch
and exact prefix.
Never invent tags, repositories or `source.commit` selectors. Local requirements
need actual content or an explicit authoring request.

## Typical project structure

Include only selected packages. Numbers aid browsing and do not define authority.
Source and tooling stay outside Macrostates artifacts:

```text
AGENTS.md                         # pointer to .macrostates/specs/main.md
README.md
.macrostates/
  specs/
    main.md
    composition.yaml
    composition.lock.yaml         # verified external snapshot inventories
    project-kickoff.md             # conditional resource
    000_meta/
    001_process/
    010_repository-1/
    011_docker-1/                  # when selected
    020_python-1/                  # when selected
    030_python-project-1/          # application/project conventions
    031_python-library-1/          # library alternative when appropriate
    040_android-app-1/             # when selected
    050_domain-rules/              # when selected
    051_project/                  # project-owned requirements
  implementation/                # when required by selected Process
    main.md
    decisions/
    workflows/
      history/
src/
tests/
```

Track `.macrostates/`, package contents and locks in Git. Add a release
declaration under implementation when a baseline exists, following Process. This
example neither selects every technology nor imports another project's local
requirements.

## Execute the agreed kickoff

Explicit kickoff authorizes local initialization, fetches and commits needed
for reviewed imports. It does not authorize remote publication or application
implementation. Preserve existing phase, branch, identity and unrelated changes.

### 1. Inspect and validate

Read intended root instructions, entrypoint, manifest and workflow records. If
Git finds an enclosing repository, settle how the project relates to it before
initializing. Do not stage, discard or stash unrelated changes for an import.
Validate the entire selection before writing package destinations:

- Require unique names, versions, entrypoints and safe, non-overlapping paths
  relative to `.macrostates/specs/`. Reject escapes, symlinks and overwrites of
  kickoff/control files. Subtree prefixes must name the same destination from
  the Git root.
- Resolve exact source tags and verify tagged metadata/entrypoints. Missing
  access, tag/version mismatch, unsupported sources and legacy commit selectors
  are explicit gaps. Never fall back to branch heads or create tags at kickoff.
- Validate metadata-owned dependencies, required selection, applicable constraints
  and cycles. Optional constraints apply only when selected. Reject disagreement
  with legacy dependency copies and remove those copies during adoption.
- Validate complete reading/authority orders without inferring authority from
  numbers. Verify actual local content; a manifest cannot reconstruct it.

Resolve material ambiguities before writes. Quote arguments safely and treat
manifest values as data, not shell commands. If Git identity is missing, request
it rather than inventing an identity.

### 2. Import verified packages

For `git-archive`, resolve the declared tag through Git and extract an archive of
its exact commit. For optional `github-archive` selections, download the provider's
archive at the tag-resolved commit. Extract safely and validate all candidates
before replacing destinations. Preserve files
unchanged and record a verified format-1 lock. Refuse unexplained local changes.
`macrostates install` implements supported selections; manual imports follow
[the lock procedure](annex_package-lock.md). Verify already matching copies
before skipping. Reruns must not select newer releases or accept moved tags.
Updates require installed copies to match the previous baseline.

For explicitly selected `git-subtree`, use squashed imports at declared prefixes.
Require a clean index/tree for these Git operations and fetch verified release
commits before the equivalent of:

```text
git subtree add --prefix=<declared-prefix> <verified-local-commit> --squash
```

Retain repository, branch, tag and prefix in the manifest. A copied directory
does not establish subtree history. Verify files and provenance before skipping
existing destinations. Preserve successful imports after failures and report
recovery. Archive installation must not silently convert existing subtrees.

### 3. Finish, verify and report

Expand the entrypoint into project identity, selected versions/paths,
provenance, authority and reading order. Preserve intent/vocabulary without
duplicating package rules. Keep kickoff linked conditionally for requested
recovery, never as an instruction on every session. Create a minimal root
`AGENTS.md` pointer to `.macrostates/specs/main.md` if absent; preserve
unrelated existing instructions.

Follow Process for artifacts and phase. Setup does not accept an implementation
baseline. Recheck metadata, dependencies, paths, links, orders, release provenance,
locks and any subtree history. Inspect staged files before committing only
reviewed setup changes. Report installed/already matching packages, tags, files,
missing local content and blockers. Completion requires all selections and the
entrypoint to validate.
