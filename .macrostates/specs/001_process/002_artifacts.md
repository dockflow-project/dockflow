# Work artifacts

Work artifacts are the files used to define, implement, explain, and resume
specification-driven work.

## Specification documents

The project-root `.macrostates/specs/` contains the composition and
specification packages defined by Meta. Implementation directories may also
contain repository-specific `.macrostates/specs/main.md` entrypoints and related
directory-scoped specifications under the selected Meta package's
`002_project-composition.md`, section `Directory-scoped specifications`. These
local documents are not specification packages. All specification documents
describe intended behavior and are definer-owned.

Implementers must not edit specifications unless the definer deliberately asks
for specification work. Routine implementation, testing, cleanup, documentation,
or wrap-up work must not change specifications by default.

Do not edit specifications merely to make incomplete implementation appear
compliant. When the desired behavior changes, update the relevant specification
only as an explicit specification change.

## Layout adoption

Process 5 retains Meta 2's `.macrostates/` layout. Move specification and
implementation artifacts together during explicitly requested adoption. Preserve
workflow/decision history and pending acceptance, update links, build consumers
and agent pointers, and validate the result. Moving files does not accept a
phase or baseline. Projects selecting earlier releases retain their own artifact
paths. Application source and tests stay outside these documentation
directories.

## Implementation documents

`.macrostates/implementation/` contains implementation documents. Implementation
documents describe what the system currently is and are implementer-owned.

Implementers should maintain implementation documentation alongside code and
keep it honest about partial support, known gaps, and important operational
details.

Definers should not normally alter implementation documentation directly. In the
exceptional case where a definer changes implementation without another
implementer, that definer is acting as the implementer and should update
implementation documentation according to the same rules.

Implementation documentation may describe code structure, runtime behavior,
manual verification steps, local limitations, and current deviations from the
specifications.

The main implementation entrypoint should be:

```text
.macrostates/implementation/
  main.md
```

`.macrostates/implementation/main.md` is the current-state architecture
entrypoint: a reader should be able to understand what is implemented now, how
its major parts work together, and why significant choices apply, without
reconstructing a sequence of deliveries. Organize it by present responsibilities
and behavior, not by release, date, request, or workflow. It should include:

- Project phase.
- Current implementation summary and applicable version/declaration references.
- Implemented capabilities.
- Known gaps.
- Important files or modules, their responsibilities and interactions.
- Verification guidance.
- Links to topic documents and decision records.

Additional implementation documents may be created when a topic is substantial
enough to deserve its own file. For example, a project that serves an API and
also runs a background data process may document those areas separately.

Topic implementation documents should usually include:

- Current behavior.
- Important files or modules.
- Verification guidance.
- Known gaps.
- Related decisions.

### Current state and historical records

Keep the main entrypoint and topic descriptions consolidated as the implementation
changes. Replace or remove obsolete descriptions rather than appending a newer
account beside them. Explain important current rationale directly or link to the
applicable decision. Retain older-version details here only when they explain a
currently supported compatibility path, operating constraint or unresolved gap;
state that scope explicitly.

Use the existing artifact roles for history:

- Workflow records own requests, progress, delivery/acceptance, closure and the
  sequence of work. Link to them rather than copying their chronology into the
  current-state description.
- Decision records preserve the context and rationale of a choice. Mark obsolete
  decisions or portions as superseded and point to their replacement or current
  implementation description; do not rewrite their historical evidence as current.
- Validation evidence records what actually ran against which candidate and
  environment, including failures and limitations. A dated result is historical
  evidence, not an automatically current pass or open-work statement. Reusable
  verification guidance describes current commands and prerequisites separately
  from those results.

Current gaps and verification limits still belong in the current-state documents;
removing chronology must not hide incomplete behavior or missing qualification.
Refer to authoritative version declarations instead of adding competing release
metadata. Workflow links may provide navigation without turning the entrypoint
into a second status ledger. Preserve useful links when consolidating; existing
history need not be duplicated or moved solely to refresh the overview.

## Version declarations

The composition's authoritative finalized specification baseline is
`project.version` in `.macrostates/specs/composition.yaml` (or Meta's single
allowed alternative spelling). Process 5 uses `specs-MAJOR.MINOR.PATCH`.
The baseline covers the root entrypoint, composition, selected package content
and applicable directory-scoped specifications. Pending records distinguish
current changed files from that earlier snapshot; this field alone is not a
current-tree release claim. Package selection versions and source tags remain
independent Meta-owned fields.

Once an implementation baseline exists, its declaration is
`.macrostates/implementation/release.yaml` with schema 2:

```yaml
schema_version: 2
version: "imp-6.4.8"
specification: "specs-6.4.2"
release_date: "2026-10-13"
```

All fields are required. Validate schema, exact prefixes, numeric forms,
Major.Minor alignment and a quoted valid calendar date. The specification is the
exact finalized baseline used to validate the implementation. Finalization assigns
the date; rebuilds retain it. A date is not proof of publication. Never fall back
to another version source when a declaration is malformed.

A release-preparation branch proposes these declarations alongside its candidate
release plan. On ordinary branches they remain last finalized baselines; change
records and computed state describe unfinished or unreleased work. Never rewrite
a historical application's release provenance solely because the repository
baseline advanced. An unchanged implementation may continue referencing an older
specification patch at the same Major.Minor after purely editorial finalization.

Application build consumers use their authoritative release declarations. The
Macrostates-default stable application version derives from finalized `imp-*`;
an independent policy owns its separate source. Clean source-distribution builds
must receive sufficient captured declarations to identify their application
version without Git, installed specifications or network. Development builds must
have honest development metadata rather than silently reuse the last stable
application identity. Ordinary builds never mutate declarations, create tags,
commit files or publish.

### Work origins

Record original work provenance before feature edits in
`.macrostates/implementation/work/<id>.yaml`, schema 1 with `id` and `origin`
(commit, specification and implementation-or-null). Each stable ID owns one
capture; this is not a workflow status or active-branch pointer. See
[the origin schema](annex_versioning.md#work-origin-schema). Change creation uses
that record or an explicitly selected original commit with verified declarations.
Synchronization never rewrites origin, and inherited records never select new work
implicitly. Capturing origin itself remains within an open setup/feature workflow.

### Change records

Pending changes live in `.macrostates/implementation/changes/<id>.yaml`, with
consumed records preserved in `changes/history/`. These are release-intent and
conformance records, not workflow status. Use schema 1 with a unique safe ID,
summary, immutable original commit/baselines, separate impact declarations,
affected deliverables, requirement coverage, verification evidence and gaps.
See [the complete schema](annex_versioning.md#change-record-schema).

Create one record per coherent scope; concurrent branches must not overwrite or
reuse IDs. Reject duplicates across pending/history. Impact values are
`none`, `patch`, `minor` or `major`. Required empty collections are explicit.
Record no-bump decisions; version-affecting records require evidence before
integration. Semantic contract changes require requirement-to-implementation and
verification coverage. Unresolved required gaps block integration/finalization.
Tooling validates structure and consistency; the implementer assesses meaning,
coverage and the actual combined result. Read inherited requirements rather than
assuming a numeric dependency minimum proves compatibility.

Capture original provenance per work before feature edits. Late change creation
requires that capture or an explicitly selected original commit verified against
its declarations; do not silently substitute the current HEAD. No global active
branch record is inherited as new work. Original provenance does not change
after merge/rebase. Current integration target
and validation evidence are separate. Archive records unchanged when consumed;
retain their IDs, bytes and origin, with release scope in the plan.
Creating this bookkeeping before an implementation exists does not invent one.

### Release plans

A read-only release plan binds the exact source HEAD/tree, finalized declarations,
pending IDs and their byte hashes. It separately records `integration_ref`, the
selected local or cached remote target ref, and `integration_target`, its resolved
commit. Planning never implicitly fetches; preparation rechecks that same ref and
source rather than substituting a local mirror. Preparation on a release branch
refuses stale inputs, gaps or conflicting candidates and updates declarations,
archives the included records and stores
`.macrostates/implementation/release-plan.yaml` coherently. Preserve recovery
evidence if interrupted; never bless a partially written candidate by rerunning.
The schema-1 candidate record identifies its original target, consumed scope,
proposed baselines and assigned date; see
[the schema](annex_versioning.md#release-plan-schema).

Do not store the resulting commit's own hash. A candidate record may remain as
historical evidence after reviewed integration; its integration is established by
Git/review evidence, not by blindly treating `status: candidate` as publication.
A changed target requires reassessment/replanning. Another feature integration
must not accidentally finalize an existing candidate's version declarations.

### Application declarations

Optional `.macrostates/implementation/deliverables.yaml` describes deliverable
identity, version source and provenance under schema 1. Each deliverable has
`strategy: implementation` or `strategy: independent`; absent policy defaults to
numeric finalized `imp-*`. An independent policy supplies its version and scheme
or names a technology-owned authoritative declaration and build integration.
Extensions are owned by selected technology/project specifications.

Application releases preserve exact specification/implementation references and
source identity. A candidate can declare `source: {tag: <immutable-tag>}` for later
authorized publication verification; a post-commit receipt can record
`source: {commit: <full-commit-id>}`. Do not embed the candidate file's eventual
own commit hash in that file. Publication resolves the tag and preserves the
actual commit in release evidence. Unreleased drafts must not be mistaken for finalized releases.
An independent application's version is never assigned merely because Macrostates
preparation advanced its own baseline. The project can use technology-native
files instead of this generic declaration when it specifies an unambiguous
mapping and provenance; avoid competing hand-edited sources.

The [schema and monorepo example](annex_versioning.md#deliverable-schema) show
how defaults and independent Android counters coexist. Release history preserves
older application declarations when later baselines leave those applications
unchanged.

Application-only release preparation may update permitted identity/provenance
metadata after a referenced Macrostates baseline is finalized. Create a ready
`none`/`none` change record with actual verification evidence and no required gaps;
close its workflows through definer confirmation before reviewed integration.
The new record stays pending without inventing a no-bump Macrostates release or
altering old consumed records. A later genuine baseline release can consume it.
Verify the historical baseline at its exact integrated annotated tag and distinguish
that source from the new application's metadata-only source commit. An independent
application release is not a new Macrostates candidate plan.

## Subproject artifacts

Subprojects may have their own artifacts, but this process does not require all
subprojects to use the same artifact structure as the parent project.

A subproject may have local `.macrostates/specs/`,
`.macrostates/implementation/`, workflow records, decision records, metadata,
generated documentation, or a different lifecycle defined by another tool or
project convention. A subproject may also have no local specifications or
lifecycle artifacts at all.

The existence of a local `.macrostates/specs/main.md` does not by itself
establish a subproject. Repository-specific directory specifications remain in
the enclosing project's artifact and versioning context unless a separate
project context is established under [Concepts](001_concepts.md#subprojects).

When subproject artifacts exist, the implementer should inspect and respect
them before changing subproject-internal files. When they do not exist, the
implementer should not invent a full subproject process unless the definer asks
for it or the parent specifications require it.

Parent project workflow records still apply to repository file changes inside
subprojects. If a subproject also has its own workflow or lifecycle records, the
implementer should keep the parent and subproject records coherent enough that
work can be resumed from either context.

## Decision records

`.macrostates/implementation/decisions/` contains ADRs for meaningful
implementation choices not settled by the specifications. ADRs are part of
implementation documentation and follow the same ownership rules.

Decision records should be specific enough that a later maintainer can
understand why the choice was made and what would justify changing it.

An ADR should include:

- Context.
- Decision.
- Consequences.
- Status.

Optional sections may include considered alternatives, follow-up work, and links
to related specifications or implementation notes.

Decision record filenames should use this format:

```text
.macrostates/implementation/
  decisions/
    0001-short-descriptive-name.md
```

Use monotonically increasing zero-padded numbers. Do not renumber existing
decision records.

Use lowercase descriptive words separated by hyphens after the number.

Decision record statuses should be explicit. Common statuses are:

- `proposed`
- `accepted`
- `superseded`
- `deprecated`

Prefer superseding an old decision over rewriting its history.

## Workflow records

Workflow records track active and completed specification-driven workflows so
work can resume coherently across sessions and branches.

Workflow records are implementation documentation. They are implementer-owned and
must not override specifications, code, tests, or the project-local
specification entrypoint.

Any project file change requires an open workflow record. Read-only inspection,
analysis, or explanation may happen without a workflow record, but creating,
editing, moving, renaming, deleting, or generating any file in the project must
first be covered by an open workflow record.

Workflow records live under:

```text
.macrostates/implementation/
  workflows/
    <open-workflow>.md
    history/
      <closed-workflow>.md
```

Open workflows live directly in `./.macrostates/implementation/workflows/`.

Closed workflows live in `./.macrostates/implementation/workflows/history/`.

The `history/` directory may usually be ignored during session startup unless
the definer asks for historical context or an open workflow references a closed
workflow.

Each workflow entry has its own Markdown file. New workflow filenames use this
format, with double underscores separating the date, compact time ID and name:

```text
<yyyy-mm-dd>__<time-id>__<short-descriptive-name>.md
```

Use the workflow's creation instant in UTC. Keep its calendar date in the
`yyyy-mm-dd` prefix. The time ID encodes only milliseconds elapsed since UTC
midnight, from `0` through `86399999`, as exactly six uppercase Crockford Base32
characters, zero-padded on the left. Use this alphabet in the stated order:

```text
0123456789ABCDEFGHJKMNPQRSTVWXYZ
```

Encode the integer `((hour * 60 + minute) * 60 + second) * 1000 + millisecond`
in base 32. For example, `11:14:00.000 UTC` becomes `16J460`. Six characters are
the minimum fixed width for representing an entire day's milliseconds in this
alphabet; five characters cover only `33554432` values. This is a custom compact
time ID, not a standard ULID. It contains no date, counter or random data, and
must not receive a separate randomness or disambiguation suffix.

Keep the assigned date and time ID stable when resuming, pausing, closing or
moving a workflow into `history/`. Lexical sorting orders these filenames by UTC
date and millisecond of day. Clock differences can affect this ordering, so it
does not establish causality or workflow authority. Continue recording
human-readable `Started at` separately.

The time-only ID is not globally unique: independent workflows created in the
same UTC millisecond can share a date/time prefix. Different descriptive names
remain distinct filenames. Before writing, check open records and `history/` for
the full destination filename and never overwrite another record. If different
workflows have the same full filename, choose descriptive names that distinguish
their actual scopes and repair references. Preserve the encoded creation time;
do not invent a later time or silently add random characters. Apply the same
collision handling when reconciling concurrent branch additions.

The descriptive name must be lowercase words separated by hyphens. It should be
short enough to scan while still identifying the work.

Examples:

```text
2026-10-07__16J460__initial-specification.md
2026-10-07__16J558__storage-conflict-amendment.md
2026-10-08__000000__api-doc-refresh.md
```

Existing date-based, date/counter and full-ULID filenames remain valid; adopting this
convention does not require renaming them or rewriting historical records.
Readers and tooling must continue to discover legacy records. If migration is
explicitly requested, record the old-to-new filename mapping and update references
to moved files. Derive each migrated date and time ID from the recorded
`Started at`, using its known timezone and available precision, converted to UTC. For
minute-only records, encode the recorded minute with seconds and milliseconds set
to zero; do not claim those finer components were measured. Clarify an unknown
timezone when it affects ordering. Retain already conforming date/time prefixes
and the original human-readable start times. A mixed legacy/current directory
does not have a single chronological lexical order until legacy records are
migrated.

Each workflow entry should include:

- Project phase.
- Workflow type.
- Status.
- Change depth.
- Branch or worktree context when known.
- Requested by.
- Implementer.
- Started at.
- Last updated at.
- Original request.
- Objective, scope and acceptance criteria.
- Delivery state.
- Work done.
- Files touched when useful.
- Remaining work.
- Blockers, conflicts, or unresolved questions.
- Suggested next step.

Use the smallest useful amount of detail. The entry should help resume work
without becoming a duplicate implementation log.

`Requested by` should identify the definer as specifically as practical. Prefer
this format:

```text
Name Lastname (email@example.com) - Obtained from <source>
```

A handle or stable local identifier may be used when name or email are
unavailable.

When the project uses Git, prefer repository-local Git identity information when
available. If repository-local Git identity is unavailable, the implementer may
use another confident source, such as explicitly provided definer identity or
global Git configuration. If the implementer cannot identify the definer
confidently, it should ask for a name, email, handle, or preferred identifier
before creating the workflow record.

`Implementer` identifies who performs the work, independently of `Requested by`:

- For a person, record their name. If unavailable, record a known handle or an
  explicitly unknown name rather than attributing the work to the requester.
- For a model, record its name and version or exact model identifier as exposed
  by the execution environment. Include relevant available parameters, such as
  reasoning/effort level, and the agent or tool used when useful for provenance.
  A tool name alone does not identify its underlying model.
- State the source of the identity and parameters, such as the person's own
  identification or session/runtime metadata. Mark unavailable values as unknown
  or not exposed; do not infer an exact revision or effort level from a family
  name, defaults, output style, or another session's configuration. Missing
  metadata does not block otherwise authorized work.

Use a compact field, for example `Person — NAME` or
`Model — NAME; version/identifier: VALUE; effort: VALUE; agent: TOOL; source: SOURCE`.
Record only relevant non-secret configuration, never credentials or private
prompts. When multiple implementers contribute or a model/version/configuration
changes, retain the earlier attribution and append a dated entry identifying
the contributor, changed parameters and work scope. Do not overwrite history
with the last implementer's identity or imply it performed all prior work.

Include this field in new records. When resuming an older workflow, add the
current implementer for the resumed work and mark earlier attribution unknown
unless reliable evidence exists. Do not rewrite archived workflows merely to
backfill identities.

`Started at` and `Last updated at` should include date and time to minute
precision using this format:

```text
YYYY-MM-DD HH:mm
```

Use these workflow statuses:

- `in_progress`
- `paused`
- `blocked`
- `completed`
- `abandoned`
- `superseded`

Open statuses are `in_progress`, `paused`, and `blocked`.

Closed statuses are `completed`, `abandoned`, and `superseded`. Assigning any
closed status requires explicit definer confirmation for the identified workflow.
Record that confirmation and its scope in the workflow before moving it to
history. An implementer's assessment that the work is done is not confirmation.

While awaiting confirmation, keep the workflow in its open location with an open
status, normally `in_progress`. Record that the requested work and checks are
finished, that definer review and closure confirmation remain, and any suggested
next step. Do not invent a closed or completed status to represent pending review.

Track delivery separately from workflow status using `Delivery state`:

- `implementing`: requested work or applicable implementation checks remain.
- `awaiting_acceptance`: requested work and applicable checks are finished;
  definer review, explicitly listed device acceptance checks or closure remain.
- `accepted`: the definer has accepted the result; closure still requires its
  own explicit confirmation unless already included in that instruction.

Use this field in new records and add it to existing records when resuming or
reviewing them. It supplements the established statuses; it does not introduce
a new closed status or imply acceptance from passing checks. Put delivery state
near status so an open record awaiting review is easy to distinguish from active
implementation. Record remaining acceptance checks and closure separately from
implementation tasks. An open record must not become a catch-all for new work;
apply [the per-request scope check](003_execution.md#scope-check-for-every-request).

Only workflows with open statuses should remain directly under
`./.macrostates/implementation/workflows/`. When a workflow receives a closed
status, move its file to `./.macrostates/implementation/workflows/history/`.

When a workflow is superseded by a broader workflow, the superseding workflow
should identify the superseded record and summarize the inherited work. The
superseded workflow should identify the superseding record, use status
`superseded`, and move to `./.macrostates/implementation/workflows/history/`.

Use these change depths:

- `small`: narrow, localized, and easy to validate.
- `medium`: touches several files, behaviors, or documentation areas, but has a
  bounded scope.
- `large`: introduces or changes a major feature, public behavior, architecture,
  persisted data, or several connected areas.
- `systemic`: affects project-wide structure, authority, compatibility,
  workflow, or assumptions used by many future changes.

When unsure, choose the deeper level until the work is better understood.

Change depth helps decide whether adjacent requests belong in the same
workflow. Several small related requests in the same area may be consolidated
into a broader tuning workflow. A request with a different depth, substantially
different area, or different impact profile should usually get a separate
workflow.

At the beginning of a work session, before touching files, the implementer must
check for open workflow entries in `./.macrostates/implementation/workflows/`.

If open workflows exist, the implementer must summarize them to the definer
before starting new work. The summary should identify:

- The active workflow type and request.
- The change depth.
- What was done.
- What remains.
- Any blockers, conflicts, or unresolved questions.
- Whether the definer's new request appears to continue, interrupt, or conflict
  with the open workflow.
- The recommended next step.

If the definer's new request conflicts with an open workflow, the implementer
should ask the definer whether to continue, pause, close, abandon, or supersede
the open workflow before touching affected files.

If an open workflow has `large` or `systemic` depth, the implementer should warn
more strongly before starting unrelated work. The warning should explain the
likely risk, such as losing context, mixing incompatible changes, leaving broad
work in an unclear state, or making future review harder.

When multiple workflows are open, each prompt should consider how the planned
actions affect all open workflows. If the planned action may conflict with,
obscure, or increase risk for any open workflow, the implementer must warn the
definer again before proceeding.

Implementers should update workflow records when starting, pausing, blocking,
completing, abandoning, or superseding a workflow.

Implementers should also update the relevant workflow entry when meaningful
progress is made, when remaining work changes, or when a conflict or blocker is
found.

Workflow records should not be updated so frequently that they obscure the useful
state of the work.

## Other documentation

Other specification packages may define other documentation types, such as
repository usage documentation, operations guides, reference material, or
generated API documentation.

This package does not grant permission to create or reorganize those documents.
Follow the specification package that owns the documentation type.

Other documentation must not be treated as specification documentation unless an
owning specification package explicitly grants that role. Do not change
implementation or specifications merely to match non-authoritative
documentation.

Code comments should explain local complexity or non-obvious constraints. They
should not be the only place broad product intent or externally observable
behavior is documented.
