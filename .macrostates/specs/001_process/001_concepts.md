# Concepts

## Specifications and implementation

Specifications describe intended behavior. Implementation documentation
describes current behavior. Decision records explain meaningful choices where
the specifications intentionally leave room.

A good specification is like a macrostate: it defines the properties that must
be true while leaving room for many acceptable microstates. An implementation is
one concrete microstate compatible with that specification.

Specifications should define everything the definer cares about: externally
observable behavior, compatibility, safety, ownership, and important operating
constraints. They should avoid prescribing private implementation details when
multiple implementations could satisfy the same intent.

## Roles

A **definer** owns intended behavior: requirements, product intent, authority
decisions, and specification changes.

An **implementer** realizes intended behavior: code, tests, implementation
documentation, decision records, and updates to non-authoritative documentation.

In normal use, the definer is a human and the implementer is an agent. The roles
are not tied to identity: a definer may be another agent, and an implementer may
be a human when explicitly acting in that role.

## Authority

When a reusable process rule conflicts with a project-local specification
entrypoint, the project-local authority order decides the conflict.

## Contract-based versioning

Macrostates identifies a project's finalized specification and implementation
baselines separately from its application releases:

- Specification: `specs-MAJOR.MINOR.PATCH`, for example `specs-6.4.2`.
- Implementation: `imp-MAJOR.MINOR.PATCH`, for example `imp-6.4.8`.
- Each numeric component is a non-negative decimal integer without leading zeroes.
- Shared `MAJOR.MINOR` identifies the effective project contract. Patch counters
  are independent; neither side must catch up with the other.

The contract includes effective requirements, compatibility commitments and
required operating/development behavior after applying composition authority.
This is contract-based versioning; it does not impose an application's release
schema. A large implementation rewrite preserving the contract or a fix restoring
already specified behavior has implementation patch impact only.

### Change impact and finalization

Ordinary development branches do not allocate new numeric versions. Their
development identities retain the recorded starting baselines, even when
synchronization imports newer finalized declarations. Record impact, including
`none`, separately for specifications and implementation:

| Change | Specification impact | Implementation impact |
| --- | --- | --- |
| Incompatible contract change, fully implemented | Major | Major |
| Compatible contract addition or change, fully implemented | Minor | Minor |
| Editorial restructuring or equivalent package selection | Patch | None |
| Implementation change preserving the contract | None | Patch |
| Changes to both sides preserving the contract | Patch | Patch |
| Tracking/tests/non-authoritative documentation with no delivery effect | None | None |
| Application release-identity/provenance bookkeeping with no contract, implementation behavior or build-logic change | None | None |

A package update is not automatically a contract change. Read the effective
requirements, including indirect dependency effects. Numeric compatibility and
matching declarations do not prove semantic consistency or conformance.

A release-preparation branch collects pending records against the latest
finalized baselines. The highest Major/Minor contract impact across either side
advances the shared contract once and resets lower components on both sides.
Without a contract shift, each side with patch impact advances its own patch
once, independently. Repeated edits, tests, branch updates and several fixes in
one release do not allocate additional numbers. Tracking-only records can be
integrated without manufacturing a release. A contradictory semantic impact
requires review rather than blindly trusting a field.

Release candidates propose official numbers; approved integration finalizes them.
Implementers classify Major, Minor or Patch impact from the actual changes. A
Major classification or baseline increase does not require separate definer
approval. Clarify unclear requirements or compatibility expectations with the
definer. Version assignment does not authorize additional scope, tag creation or
publication. Reusable package versions remain under Meta's
separate `major.minor.patch` and `v<version>` rules.

### Development, pending and candidate states

A development identity combines each recorded starting baseline, a work or branch
identifier and the current commit, for example:

```text
specs-0.3.0-branch.feature-x.gabc123
imp-0.3.1-branch.feature-x.gabc123
```

These are snapshot identities, not official releases or universal application
package versions. Compute the suffix; never store a commit's own hash in a tracked
declaration. Stable work IDs select provenance when a branch has several records.
Record the original starting commit and baselines once; synchronizing the branch
changes its current commit and validation target, not its original provenance.
An abbreviated display hash does not replace full commit IDs in evidence.

The primary branch represents accepted integrated work. Pending change records
identify accepted but unreleased changes. Its identity can be
`imp-0.3.1-unreleased.gdef456`: the numeric part names the last finalized baseline,
not the version of the modified current contents. A dirty working tree must be
identified as such. A source archive without Git metadata reports unavailable
snapshot identity or uses explicitly captured build provenance; never guess that
it is a clean finalized release.

Once an implementation exists, every integrated result must implement its current
effective contract. Provisional gaps may exist on development branches, including
drafts, but must not enter primary-branch integration or release finalization.
Last finalized declarations may retain an earlier contract pair while pending work
changes the current contract; the pending state and coverage must be explicit.
Matching Major.Minor is required for finalized/candidate baseline pairs, not as
permission to conceal pending requirements by changing numbers.

A candidate state is a release proposal tied to exact input and target identities.
It is not finalized until reviewed integration, and is not published merely
because candidate declarations or dates exist. The primary branch may contain
accepted pending records without open workflows: completed work awaiting release
is not an unfinished workflow.

Before an implementation exists, a specification-only project can finalize only
specification baselines. Creating change/history bookkeeping does not itself
create or accept an implementation. Incomplete first-implementation work follows
bootstrapping rules; an existing functioning implementation cannot escape
conformance by retaining a `bootstrapping` phase label.

### Applications and monorepos

Applications and libraries may define their own versioning, release cadence,
authoritative declaration and required tools through selected technology packages
or project-owned specifications. Project-local overrides follow composition
authority and identify affected deliverables and replaced requirements. Repository
integration policy remains coherent across the repository; per-application release
policies do not bypass its review, closure or conformance gates.

An explicit application policy is optional. If none applies, a stable application
release uses the numeric finalized implementation version without `imp-`, for
example `imp-4.12.3` becomes `4.12.3`. Development/unreleased suffixes must not
be published as stable releases. Technology-specific constraints still apply;
projects needing independent updates define a suitable policy. Android may use
that numeric version as `versionName` while retaining its separate `versionCode`.

A monorepo can share one composed specification/implementation baseline while
several deliverables have independent release versions. Each application release
records its own version, exact specification baseline, exact implementation
baseline and source identity. A post-commit receipt records the exact commit, or
a declared immutable source tag is resolved and verified at publication; a tracked
candidate declaration cannot contain its own eventual commit hash. A new repository baseline does not automatically
release all applications; unchanged published applications retain their original
provenance. Shared-code changes require reviewing all affected deliverables.

After a baseline is finalized, an application's policy may prepare another release
by changing only its identity metadata, such as version, installation counter,
release date or source receipt. These changes do not by themselves allocate new
Macrostates baselines. Record and review `none` impact on both sides, verify that
behavior, contract and build logic remain unchanged, and retain exact finalized
baseline references. The application's source commit can differ from the baseline
commit because of this reviewed metadata; its release provenance must identify
that distinction. Runtime or effective specification changes need ordinary impact
classification and cannot hide behind an application release policy.

Published application identities and platform update ordering remain immutable.
The numeric implementation default does not permit republishing changed artifacts
under an already published immutable application version. Independent numbering,
or a technology-owned additional identity such as Android's counter, follows the
selected application policy.
Independently composed subprojects retain their own baselines and integration
requirements rather than silently sharing a parent's identity.

See [Artifacts](002_artifacts.md#version-declarations),
[Execution](003_execution.md#versioning-and-integration), and
[Versioning schemas and examples](annex_versioning.md) for the concrete records,
preparation procedure and migration rules.

## Project phase

Project phase describes the broad development stage. It helps the implementer
choose the right workflow.

Use these phases:

- `specification`: the intended behavior or process baseline is still being
  defined, and no accepted implementation baseline exists.
- `bootstrapping`: an accepted specification baseline exists, and the first
  implementation baseline is being created.
- `active`: an implementation baseline exists, and ongoing work changes,
  extends, reviews, or realigns the project.
- `conflicting`: the project's artifacts disagree about its phase, history, or
  implementation state, so the implementer cannot safely treat the project as
  being in one of the normal phases without definer clarification.

The normal phase progression is `specification` to `bootstrapping` to `active`.
Once a project is active, multiple workflows may happen over time and may
occasionally overlap.

`conflicting` is not a normal development destination. It is a temporary
recovery state used when project files imply incompatible histories or phases.
The implementer should move a project out of `conflicting` only after the
definer and implementer agree on the intended state and the required recovery
work has been recorded.

During `specification`, multiple `Initial specification` workflows may be open
at the same time when different parts of the intended baseline are being shaped.
`Project scaffolding` workflows may also be open during `specification` when
repository or tooling setup is useful before the specification baseline is
complete.

During `active`, `Initial specification`, `Project scaffolding`, and `Project
bootstrapping` workflows should not be opened. Use the other workflow types for
ongoing changes, reviews, documentation refreshes, and realignment work.

Phase changes are deliberate. The implementer must warn the definer before a
workflow changes the project phase and must confirm that the definer wants to
proceed.

## Subprojects

A subproject is a bounded project-like unit that lives inside a parent project.

Identify a subproject from the definer's explicit designation, the enclosing
project's specifications, or established metadata and maintenance practices that
show a partly separate lifecycle. Evidence may include its own composition,
release policy, upstream repository or maintenance records. A directory name,
source package, build file or `.macrostates/specs/main.md` alone is not enough
to infer a separate lifecycle. No universal marker file or subproject registry
is required.

In particular, repository-specific directory specifications may describe an
ordinary component that remains entirely within the parent project's lifecycle.
Their scope and authority follow the selected Meta package's
`002_project-composition.md`, section `Directory-scoped specifications`.
Do not invent a separate phase, version or workflow system merely because a
component has local specifications. If the evidence leaves the boundary unclear
and it changes the applicable lifecycle or authority, ask the definer.

Subprojects may exist for many reasons: vendored libraries, generated
components, independently maintained modules, examples, tools, documentation
sites, infrastructure areas, or other parts of a repository whose lifecycle is
partly separate from the parent project.

A subproject may follow this specification-driven process, a different process,
or no explicit local process at all. It may have its own specifications,
implementation documentation, workflow records, or none of those artifacts.

When a subproject has its own rules, specifications, lifecycle, or maintenance
metadata, those local rules should be respected for subproject-internal work.
The parent project's specifications and process still govern how the subproject
is integrated, tracked, and changed within the parent repository.

The implementer does not need to read a subproject's internal specifications
merely because the parent project uses that subproject. When the requested work
only consumes the subproject through its public interface, use the subproject as
a dependency or component. Read public usage material such as its `README.md`,
examples, or API documentation when needed, but read internal specifications
only when changing files inside the subproject or when the requested work
depends on the subproject's own lifecycle rules.

Changing files inside a subproject is still changing files in the parent
project. Therefore, the parent project must still have an open workflow record
that covers the work unless another higher-authority specification explicitly
defines a different parent-level tracking mechanism.

Subprojects may sometimes be worked on while the parent project is in a
different phase. For example, a subproject may be specified or implemented while
the parent project is still in its own initial specification phase. In that
case, the implementer should follow the subproject's local lifecycle when one
exists, while also maintaining the parent project's workflow record and
integration state.

## Workflow types

Specification-driven development uses several workflows. Each workflow has
different permissions, expected outputs, and reasons to ask for definer input.

### Initial specification

Initial specification defines the desired system before a full implementation
exists.

Use this workflow while the project phase is `specification`. If no
implementation baseline exists and the definer is still shaping the intended
behavior or process baseline, use `Initial specification` even when editing
existing specification files.

Multiple initial specification workflows may be open at the same time while the
project phase is `specification`.

The definer owns intent, scope, priorities, and requirement choices. The
implementer may help draft, organize, and edit specification files because
specification work is the explicit task.

The implementer should keep changes focused on specifications and should not
implement behavior unless the definer explicitly changes the task.

If the work shifts from shaping specifications to preparing repository files,
tooling, or empty project structure, use `Project scaffolding` rather than
stretching an initial specification workflow.

Ask the definer when a requirement choice materially affects product behavior,
compatibility, safety, operations, or future implementation cost.

### Project scaffolding

Project scaffolding prepares the repository or development tooling while the
project remains in the `specification` phase.

Use this workflow when the definer wants useful setup before the specification
baseline is complete. Examples include initializing Git, updating
repository-root operational Markdown files such as `README.md` or `AGENTS.md`,
creating `.gitignore`, creating reserved directories, adding placeholder files
needed to keep directories tracked, or creating tool configuration files already
required by selected specification packages.

Project scaffolding does not change the project phase to `bootstrapping` and
does not create an accepted implementation baseline. It is a preparation
workflow, not the first implementation of product behavior.

The implementer may create or update repository and tooling artifacts needed for
future bootstrapping, but must keep the scope bounded. Do not implement domain
behavior, create application logic, or make irreversible architecture choices
unless the applicable specifications already require them or the definer
explicitly confirms them.

If scaffolding requires adding dependencies, choosing between materially
different tools, or creating files whose meaning is not settled by the
specifications, ask the definer before proceeding.

### Project bootstrapping

Project bootstrapping is the first comprehensive implementation of an existing
specification set.

Starting project bootstrapping changes the project phase from `specification` to
`bootstrapping`. The implementer must warn the definer about this phase change
and confirm before proceeding.

The implementer should read broadly enough to understand the full specification
composition, then implement autonomously in coherent steps. The implementer
should create or update code, tests, implementation documentation, decision
records, and non-authoritative documentation as needed by the applicable rules.

The implementer must not edit specifications during bootstrapping unless the
definer explicitly asks for specification work.

Ask the definer when specifications are contradictory, when authority rules do
not resolve a conflict, or when an ambiguity materially changes required
behavior.

Bootstrapping may include varied specification and implementation changes while
the first implementation baseline is being formed. The project remains in
`bootstrapping` until the definer accepts the first implementation baseline as
good enough. Only then should the implementer change the project phase to
`active`.

If bootstrapping reveals that the initial specification has substantial gaps or
problems, the definer may ask to revert the project to `specification`. In that
case, the implementer should remove or unwind the partial implementation as
directed, preserve workflow records, and change the project phase back to
`specification`.

### Implementation amendment

An implementation amendment changes the current implementation. It usually
preserves intended behavior, as with bug fixes, refactors, missing behavior,
test improvements, and cleanup. It may also reveal that the specifications need
to change: the definer may recognize that the implementation needed amendment
because the specified behavior was incomplete or should have been different.

The implementer should read the relevant specifications and current
implementation documentation, make the smallest coherent change, test it, and
update implementation documentation or decision records when needed.

The implementer must not edit specifications unless the definer explicitly asks
for a specification change.

Ask the definer when the requested amendment appears to conflict with the
specifications or would require changing intended behavior.

Before closing an implementation amendment, the implementer must ask the
definer whether a specification update should reflect the implementation
changes and, if so, to what extent. Record the definer's decision in the
workflow record and open or continue an explicit specification update workflow
if requested. Reflect the agreed intended behavior and constraints, without
unnecessarily prescribing private implementation details.

### Specification update

A specification update adds to or revises specifications after an accepted
specification baseline exists. It may define additional requirements or
functionality, change intended behavior, or reflect definer-approved changes
already made during an implementation amendment.

The definer owns the desired change. The implementer may help inspect current
specifications, identify affected areas, and edit specification files because
specification work is the explicit task.

The implementer should not implement the changed behavior unless the definer
explicitly asks for implementation work. A specification update may
intentionally create an implementation gap, but need not do so. When it reflects
an implementation amendment that already satisfies the updated specifications,
it creates no gap and requires no implementation update. A resulting gap may
remain in the working tree or on a development branch; it must not enter a
primary-branch commit after an implementation baseline exists. Follow the
integrated-state and existing-project adoption rules.

After closing a specification update, the implementer should recommend a
`Review or gap assessment` workflow to the definer when it would help determine
whether an implementation update is needed. Make this recommendation only when
the assessment would be useful, such as when the effect on existing
implementation is unclear.

Ask the definer when the update conflicts with existing specifications and
authority rules do not resolve the conflict.

### Implementation update

An implementation update brings the system back into alignment after a
specification update that creates a misalignment between the implementation and
the specifications.

The implementer should read the changed specifications and affected
implementation documentation, then update code, tests, implementation
documentation, decision records, and non-authoritative documentation as needed.

The implementer must not edit specifications during implementation update unless
the definer explicitly asks for specification work.

Ask the definer when implementation reveals a new ambiguity or conflict in the
specifications that materially affects behavior.

### Review or gap assessment

A review or gap assessment compares specifications, implementation
documentation, code, tests, and other relevant artifacts.

The implementer should report findings such as implemented behavior, missing
behavior, conflicts, ambiguities, obsolete documentation, missing tests, and
residual risk.

The implementer should not touch files unless the definer explicitly asks for
edits.

Ask the definer before expanding the review scope beyond the requested area when
doing so would materially increase time, cost, or noise.

### Documentation refresh

A documentation refresh updates non-authoritative documentation after behavior,
commands, generated references, or repository usage have changed.

The implementer should follow the rules of the specification package that owns
that documentation type. Some documentation can be edited directly; other
documentation may require changing an authoritative source and regenerating
derived files.

The implementer must not change specifications or implementation merely to match
non-authoritative documentation.

Ask the definer before creating new documentation files, splitting existing
documentation, or changing documentation ownership conventions.

### Development branch creation

Use this workflow when the definer requests creating a development branch to
establish an isolated working context. It records the starting branch, commit,
specification composition version and implementation version, and links the work
to be done there. It does not itself authorize feature changes or remote publication.
Specification and implementation work retain their corresponding workflow types.

When no suitable development branch exists, the implementer suggests creating
one to the definer and materializes it once authorized. Reuse a suitable existing
branch for related changes; each individual change does not need its own branch.
Branch setup can be delivered and proposed for closure as soon as its baseline
and links are recorded; it need not stay open for the lifetime of the branch.

### Development branch synchronization

Use this workflow when incorporating the authoritative target into a development
branch or synchronizing a fork's primary mirror. These are distinct operations.
The project specifies merge/rebase preferences and review facilities; no hosting
provider is required. Preserve original origins, resolve conflicts only on the
development branch, review inherited requirements and rerun affected checks.

### Integration preparation

Use this workflow to prepare a branch for a reviewed integration proposal. It
checks the actual combined source/target result, change records, conformance and
available local checks. It then requests explicit closure of all open workflows,
including preparation itself, with a short numbered summary and explains that
closure is required before submission. Definer confirmation remains mandatory.

The preparation may be completed before proposal-triggered CI and external review
exist. Those checks are merge prerequisites when required, not a reason to forbid
opening a draft proposal. After review corrections, complete and close new scoped
workflows before the merge gate. Git or review-system integration outcomes live
in the review record; do not leave a tracking workflow open on the integrated tree.

### Development branch merge

Use the project's reviewed integration mechanism: a pull/merge request when
available or an explicitly defined equivalent for native Git repositories.
Submission does not authorize merging. Before integration, verify source/target
identities, required reviews/checks and no open workflows in the combined tree.
Never directly author changes on the primary branch. Read-only integration and
review actions need not open a new tracked workflow; any corrective file edits do.

### Release preparation

Use this workflow when requested to finalize accumulated accepted changes.
Prepare a release branch from the latest primary state, review pending records,
calculate candidate baselines once and validate their provenance and conformance.
Close all workflows through explicit definer confirmation before submitting the
release proposal. Reviewed integration finalizes the candidates; tags and
application publication remain separately authorized.

### Exception

An exception workflow records work that must proceed even though the request
does not fit the normal process cleanly.

Use an exception workflow only when the definer explicitly asks for something
that skips, ignores, or contradicts the process and no ordinary workflow type can
honestly contain the work.

Also use an exception workflow when project state recovery is needed before
ordinary work can safely continue.

Read `annex_exceptions.md` before executing an exception workflow.
