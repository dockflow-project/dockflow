# Annex: versioning schemas and examples

Read when creating change records, planning/preparing a release, declaring
application version sources, or adopting Process 5. The core Concepts, Artifacts
and Execution rules govern authority, impact and gates. Examples below are
hypothetical; hashes must be actual verified values in a project.

## Artifact and state summary

| Artifact | Purpose |
| --- | --- |
| `specs/composition.yaml` project.version | Last finalized `specs-*` baseline, or candidate on a release-preparation branch |
| `implementation/release.yaml` schema 2 | Last finalized `imp-*` and exact specification baseline, or prepared candidate |
| `implementation/work/*.yaml` | Per-work captured origin, without a global active-branch pointer |
| `implementation/changes/*.yaml` | Pending scope, original provenance, impact and conformance evidence |
| `implementation/changes/history/*.yaml` | Consumed records preserved unchanged |
| `implementation/release-plan.yaml` | Exact candidate input/output binding and consumed scope |
| `implementation/deliverables.yaml` | Optional application version-source policy and release provenance |
| `implementation/workflows/` and `history/` | Work execution, acceptance and explicit closure evidence |

Paths are relative to `.macrostates/`. Change records are not workflow statuses.
A source-only canonical package repository does not need these Process artifacts
unless it explicitly adopts a composed project. A specification-only composed
project can use change records without an implementation baseline.

Current source may be development, accepted-unreleased, a release candidate or a
finalized snapshot. Tracked baseline numbers alone do not establish that state.
Use pending records, candidate scope, exact Git/review evidence and dirty-state
inspection. Preserve enough application metadata for archive builds without Git;
unavailable identity is preferable to a guessed finalized claim.

## Work origin schema

Before feature edits, capture one immutable origin per stable work ID in
`.macrostates/implementation/work/<id>.yaml`, for example using supported CLI
`start-work` assistance. This is provenance, not an open workflow or a global
current-branch file:

```yaml
schema_version: 1
id: offline-mode
origin:
  commit: "1111111111111111111111111111111111111111"
  specification: "specs-0.3.0"
  implementation: "imp-0.3.1"
```

All fields are required; `implementation: null` is explicit before an implementation
exists. Read the declared baselines at the selected original commit. Preserve the
record through synchronization and consumption; never overwrite another work's
origin. Late change declaration selects its captured work or an explicitly verified
original commit. If origin cannot be established, ask for it rather than silently
capturing current HEAD. A new branch may inherit provenance records as history;
none becomes its active work unless explicitly selected.

## Change record schema

Schema 1 requires all fields below. Empty collections are explicit, not omitted.
Safe IDs are lowercase ASCII identifiers suitable for a single filename; do not
include path separators, whitespace or option-like prefixes. IDs must be unique
across pending and consumed records. Optional extension fields are retained rather
than silently discarded.

```yaml
schema_version: 1
id: offline-mode
summary: Support the required offline inspection mode.
origin:
  commit: "1111111111111111111111111111111111111111"
  specification: "specs-0.3.0"
  implementation: "imp-0.3.1"
impact:
  specification: minor
  implementation: minor
deliverables:
  - command-line
requirements:
  - requirement: Offline inspection must not require network access.
    implementation: Inspection reads the locally selected package metadata.
    verification: Tests exercise inspection with network access unavailable.
evidence:
  - Recorded test results identify the tested source and environment.
gaps: []
```

- `origin.commit` is the full original Git commit ID, not a current self-hash.
  Specification and implementation values name the starting baselines;
  `implementation: null` is explicit before an implementation exists.
- Both impact values are one of `none`, `patch`, `minor`, `major`.
- `deliverables` is a list of affected safe IDs; an empty list means no application
  release impact is declared, not permission to ignore shared-code dependencies.
- Each requirement item has nonempty `requirement`, `implementation`, and
  `verification` strings. Meaning and coverage remain subject to review.
- `evidence` and `gaps` are lists of nonempty strings. Development records may
  initially lack evidence or list gaps. Before integration, version-affecting
  records need evidence and semantic contract changes need requirement coverage.
  Unresolved required gaps block integration and finalization.

Track coherent change scope, not every edit. Capture a unique per-work origin
before feature edits, using CLI work-start assistance or an equivalent manual
record. A late change declaration uses that captured origin, or an explicitly
selected original commit whose declarations are verified. It must not silently
use current HEAD after development or synchronization as the original start.
No global current-branch file may override another work's provenance or be
inherited as active work by new branches. A later upstream sync never rewrites
origin. Current source/target validation is separate dated evidence. Concurrent
branches choose distinct IDs and reconcile real scope collisions deliberately.
Do not resolve collisions by overwriting or silently dropping another record.

## Release plan schema

A read-only schema-1 plan has `status: planned`. Preparation stores the same
reviewed input/output binding with `status: candidate` and `release_date`. The
record contains:

```yaml
schema_version: 1
status: candidate
integration_ref: "upstream/main"
integration_target: "5555555555555555555555555555555555555555"
target_commit: "2222222222222222222222222222222222222222"
target_tree: "3333333333333333333333333333333333333333"
baselines:
  specification: "specs-0.3.0"
  implementation: "imp-0.3.1"
  implementation_specification: "specs-0.3.0"
records:
  - id: offline-mode
    sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
history_records: []
declarations:
  composition_sha256: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  release_sha256: "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
candidate:
  specification: "specs-0.4.0"
  implementation: "imp-0.4.0"
  implementation_specification: "specs-0.4.0"
impact:
  specification: minor
  implementation: minor
deliverables:
  - command-line
release_date: "2026-10-13"
```

`integration_ref` stores the explicit target Git reference used for planning,
for example `upstream/main`; `integration_target` binds its resolved full commit
identity. A supported `release-plan --target upstream/main` can select an
authoritative cached remote-tracking target without a local primary mirror.
Without an explicit target, resolve the configured primary from the available
local/cached remote refs; a detached CI checkout may have only a remote primary
ref. Report that refs are cached: inspection and planning never implicitly fetch.
`target_commit` and `target_tree` bind the exact source HEAD/tree being planned;
this source may contain release-workflow records already committed on the release
branch, so it need not equal `integration_target`. None is the resulting prepared
commit's own hash. `records` lists the consumed pending
IDs and byte SHA-256 values. `history_records` binds already consumed records;
`declarations` binds the original composition and implementation declaration
bytes. Missing implementation values and its byte hash are explicitly null for
a specification-only project. `candidate` distinguishes the current composed
specification from the exact specification implemented by its implementation.

A specification-only editorial release may advance the composition while leaving
the implementation declaration and its exact earlier specification unchanged.
With a contract shift, candidate implementation/specification Major.Minor must
match. A specification-only project rejects implementation-impact records.
No-bump scope does not create another official release identity.

Preparation rechecks the same stored `integration_ref` against its
`integration_target`, plus the exact source identity, declarations, complete
pending/history scope and record bytes. Default release checking follows the
stored target ref; an explicitly chosen override must satisfy the same identity
and integration gates. A ref unavailable in another clone/CI environment is
missing readiness evidence, not permission to substitute a different target.
Fetch explicitly under the project synchronization policy when current remote
state is required; cached inspection alone does not prove remote currency.
Changed, additional or deleted records, stale commits,
gaps or conflicting active candidates require reassessment. Archive included
records unchanged. Candidate output and archive moves form one coherent operation;
interruption must remain visible and recoverable.

A stored candidate plan can remain as historical evidence after finalization.
Reviewed integration and authorized tag evidence determine finalization; do not
require a post-merge direct edit to turn a marker into a release. Later release
planning must recognize that previous integrated candidate as historical rather
than preventing all future releases. An active unintegrated candidate must not be
mistaken for the finalized baseline or finalized by an unrelated feature merge.

## Deliverable schema

The generic optional schema-1 declaration contains a `deliverables` mapping keyed
by stable safe IDs. The project can instead specify technology-native authoritative
files with an explicit mapping; do not maintain competing hand-edited versions.

```yaml
schema_version: 1
deliverables:
  python-library:
    strategy: implementation
    version_scheme: pep440
  android-app:
    strategy: implementation
    android:
      version_code: 84
  independently-versioned-app:
    strategy: independent
    version: "7.3.25"
    version_scheme: project-defined
    specification: "specs-4.12.0"
    implementation: "imp-4.12.3"
    release_date: "2026-10-13"
    source:
      tag: android-7.3.25-84
```

`strategy: implementation`, or absent application policy, derives a stable
application version from the numeric finalized `imp-*`. `strategy: independent`
uses the project's declared version source, scheme and release conditions.
Technologies own relevant extensions such as Android's integer counter. Declare
independent application versions explicitly; baseline preparation cannot infer
the correct application bump or silently change it.

Every actual application release preserves its version, exact specification and
implementation baselines, release date when required, and exact source identity.
Use `source: {tag: <immutable-tag>}` in a tracked candidate declaration when the
commit does not yet exist. Resolve and verify that tag at authorized publication,
and preserve its exact commit in release evidence. A post-commit receipt can use
`source: {commit: <full-commit-id>}` directly. At least one is required for a
release source; both can be retained when the resolved tag and recorded commit
agree. Do not place a file's own eventual commit hash inside that file. A
candidate tag need not exist before authorization to create it, but publication
must not claim provenance while its source is unresolved. Do not overwrite earlier
release provenance when an unrelated application changes. Baseline references on
an unreleased draft are proposals, not evidence of publication.

## Application-only publication after baseline finalization

Suppose `specs-0.4.0` and `imp-0.4.0` identify integrated annotated baseline commit
`B`. An independently versioned application subsequently prepares version
`7.3.26` at commit `A`, changing only its declared version/counter/date/provenance
and required closed workflow/change records. Its source tag identifies `A`; its
specification and implementation references still identify `B`. Never move the
baseline tags to `A` or allocate another baseline merely to publish this metadata.

The implementer records `none` impact on both Macrostates sides, actual validation
evidence and no gaps. Local preparation and reviewed integration still apply,
including definer-confirmed closure. The additional no-impact record stays pending;
Baseline release planning does not finalize an all-none set. A future genuine baseline release
can consume it alongside version-affecting work.

Verification has two scopes: prove the immutable integrated baseline plan,
declarations, consumed history and specification/source binding at `B`; then
prove `A` contains only permitted release metadata/bookkeeping changes and matches
the application's authoritative identity/source policy. Previously consumed records
remain byte-identical. Pending version-affecting records, runtime/build-logic changes
or effective specification changes block reusing the baseline for this flow.
Structural no-impact declarations alone do not establish that classification.

Default application numbering and technology constraints still apply. Reusing an
implementation-derived display version is valid only when the technology's complete
release identity distinguishes the new release, such as a higher Android counter.
An immutable distribution index version cannot be reused for changed artifacts;
select an appropriate explicit application policy rather than moving old tags.

## Worked branch and release sequence

1. Primary has finalized `specs-0.3.0` and `imp-0.3.1`. Two development branches
   start from it. Each records its original commit/baselines and distinct change ID.
2. One fixes specified behavior; the other introduces a compatible command. They
   do not allocate official versions while their computed commit suffixes change.
   Their original identity baselines remain stable; synchronization may import
   newer finalized declarations. Updating either from primary changes its current identity, not origin.
3. Each completes its scoped workflows and integration preparation. The implementer
   presents a numbered summary of every open workflow, asks the definer to close
   them, and explains this prerequisite for proposal submission. Closing preparation
   means local preparation is done, not that external review passed.
4. Both reviewed feature integrations satisfy their effective requirements. Primary
   now contains pending records and an unreleased identity, with no open workflows.
5. An authorized release branch plans the combined scope against current primary.
   The compatible contract addition determines `specs-0.4.0` / `imp-0.4.0`; the fix
   does not add another patch after this contract reset.
6. Preparation archives both records, proposes declarations and closes its workflows
   with definer confirmation before submitting reviewed finalization. If primary
   changes, recalculate scope and validation against the new target.
7. Authorized integration finalizes the baseline. Annotated tags and selected
   application distributions are created only under their separate authorization.

A repo containing a default-versioned Python library and an independent Android
app can then publish library `0.4.0` while Android keeps its previous release until
its own policy requests another release. Android may alternatively default its
`versionName` to `0.4.0`; its counter remains independently managed.

## Migration and manual equivalents

Retain support for old selected policies and declaration schemas. Explicit adoption
inventories existing tags, applications, accepted baselines and open/closed workflow
evidence. Preserve all published identities and distribution ordering. Record any
prefix translation of verified snapshots and separately classify new process or
product requirements; translation alone is not conformance.

Initialization of a new project creates a specification seed and no implementation.
First bootstrapping requires explicit establishment and acceptance of the first
conforming implementation baseline; use a documented manual declaration/review
procedure if the installed CLI only supports planning against an existing
implementation. Creating change/work records is not implementation acceptance.

For manual operation, inspect Git refs and current combined trees, author the same
records, calculate highest impact, bind exact inputs, prepare coherent candidate
files on a release branch, perform required checks and request definer-confirmed
closure. Use the project's review procedure, verify resulting integration and
create annotated tags only when authorized. Tool absence does not waive a gate;
unsupported automation must report its actual coverage rather than guess.
