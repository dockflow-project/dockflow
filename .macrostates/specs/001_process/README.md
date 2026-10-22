# Process specification package

This package describes how specification-driven work should proceed. It is
intended to be reusable across projects.

## Macrostates

This package is part of [Macrostates](https://github.com/orgs/Macrostates), a
project for composing reusable specification packages into specs-driven
development projects.

## Quick reference

This section summarizes rules expanded in the package documents below. Use it
for orientation, but apply the detailed rules in the referenced documents when
doing the work.

Implementation entrypoints and topic documents describe the current architecture,
behavior, rationale and gaps. Workflow chronology, decision history and dated
validation retain their separate roles; do not accumulate release notes in the
current-state overview. See [Artifacts](002_artifacts.md#implementation-documents).

Before changing any project file, the implementer must check workflow records
and ensure an open workflow record covers the change. See
[Artifacts](002_artifacts.md) for workflow record structure and
[Execution](003_execution.md) for when and how to use workflow records.

In Git repositories, the implementer must verify its branch before any file
change, including workflow records, and never apply changes while checked out on
the primary branch, normally `main`. Use a suitable development branch. When a
new branch is needed, suggest it to the definer and create it once authorized.
Existing authorization remains valid. See
[Branch responsibility](003_execution.md#branch-responsibility).

New workflow filenames use `YYYY-MM-DD__<time-id>__short-descriptive-name.md`,
with the UTC date followed by a six-character Base32 ID encoding only milliseconds
since midnight. Existing legacy filenames remain valid. See
[Workflow records](002_artifacts.md#workflow-records) for encoding and collisions.

On every request, compare its objective with the workflow's original scope.
Track distinct objectives separately, even when they share a screen or origin.
An instruction to perform new work authorizes its tracking record; closure is a
separate decision. Show `Delivery state: awaiting_acceptance` when implementation
and applicable checks are finished. See
[Scope check for every request](003_execution.md#scope-check-for-every-request).

Workflow closure requires explicit definer confirmation, including completion,
abandonment, and supersession. When work appears done, suggest closure and keep
the workflow open until the definer confirms. See [Execution](003_execution.md).

Finalized specifications use `specs-MAJOR.MINOR.PATCH` and implementations use
`imp-MAJOR.MINOR.PATCH`, sharing contract Major.Minor with independent patches.
Feature branches retain starting numbers and compute commit-based development
identities. Committed change records describe independent impact and evidence;
release preparation collects them and proposes official baselines through reviewed
integration. Accepted pending changes on primary are explicitly unreleased, not
an unchanged historical release. See [Concepts](001_concepts.md#contract-based-versioning),
[Artifacts](002_artifacts.md#version-declarations) and
[Execution](003_execution.md#versioning-and-integration).

Applications may adopt technology/project release policies. Without an explicit
policy, a stable application version is numeric finalized `imp-*`. Monorepos may
version and release applications independently while preserving exact baseline
provenance. New repository baselines do not automatically publish applications.

The Macrostates CLI is strongly recommended for supported specification checks
and remains optional. Use relevant manual equivalents when needed, preserving
the selected requirements and reporting coverage. Meta owns tool guidance;
[Specification verification](003_execution.md#specification-verification) defines
when checks fit a workflow and a proposed commit.

Branch creation, synchronization, integration preparation and release preparation
have distinct scopes. Use reviewed integration through pull/merge requests where
available or a native Git equivalent; no hosting service is mandatory.

Before proposal submission, the implementer requests explicit definer closure
with a short numbered summary of **all open workflows** and explains the closure
prerequisite. The submitted/integrated tree must contain no open workflows.
Proposal-triggered CI/review can begin after submission, but all required checks
and reviews must pass before integration. Later corrections receive their own
workflows, closed before merge. See
[Integration preparation](003_execution.md#integration-preparation) and
[Development branch merge](003_execution.md#development-branch-merge).

Specification edits stay within the project context of the request. After
committing, inspect other package copies and suggest applicable pulls; obtain
explicit definer approval before updating another context. See
[Execution](003_execution.md) for scope and synchronization rules.

## Core and annexes

This package uses progressive disclosure. Core documents are mandatory reading
at the beginning of each working session because they describe the normal path
and the checks needed before changing files.

Annex documents describe rare branches, recovery procedures, and extended
handling. Read an annex only when a core document says the situation applies.

## Scope

- Core specification-driven development concepts.
- Definer and implementer responsibilities.
- Definer support during process execution.
- Documentation ownership and authority.
- Common workflows and workflow continuity.
- Project baseline, development and pending identities, impact records and release preparation.
- Optional application release policies, defaults and monorepo provenance.
- Development-branch synchronization and platform-independent reviewed integration.
- Explicit definer closure and separate proposal/merge readiness gates.
- Project scaffolding during specification.
- Workflow execution against specifications.
- Subproject coordination inside a parent project.
- Discovery of directory-scoped specifications and identification of subprojects.
- Gaps, decisions, completion checks, and quality expectations.
- Proportionate specification verification with optional CLI assistance.

Project-specific requirements belong in a project package, not here.

## Reading order

Read the core documents in this order:

1. [Concepts](001_concepts.md)
2. [Artifacts](002_artifacts.md)
3. [Execution](003_execution.md)

Conditional annexes:

- [Versioning schemas and examples](annex_versioning.md): read when creating
  change records, preparing releases, declaring deliverables or migrating version
  artifacts. The core rules still apply when using equivalent manual tooling.

- [Project state](annex_project-state.md): read when project phase or project
  artifacts appear inconsistent.
- [Conflicts](annex_conflicts.md): read when ambiguity, authority conflict, or
  workflow conflict is found.
- [Exceptions](annex_exceptions.md): read when an `Exception` workflow is
  needed.

## License

This specification package, including its documentation, metadata, and bundled
resources, is licensed under the [MIT License](LICENSE).

Copyright (c) 2026 Lucas Lopez.

## AI assistance

This project was developed with AI assistance.
