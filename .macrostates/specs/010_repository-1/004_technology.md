# Repository technology

The repository uses Git for version control. Core branching and review rules do
not require a particular hosting platform, account, API or CI service.

## Branches and integration policy

Use one primary branch representing accepted integrated work, commonly `main` or
`trunk`. Develop authored changes on topic branches, including specifications,
source, tests, configuration, generated files and workflow records. Do not author
file edits while checked out on the primary branch; read-only inspection is valid.

Integrate through the repository's defined review procedure. Pull/merge requests
are suitable where available; native Git repositories may use documented review
records, exact source/target commits and an authorized integration operation.
No direct unreviewed authored commits or pushes to the primary branch are allowed.
A reviewed native merge or replication of accepted upstream history is distinct
from authoring changes directly on that branch.

Project-specific specifications may define or override merge strategy, review
facilities, required checks and application release tooling according to their
composition authority. In the absence of a stated preference, preserve shared
history with merge-based topic integration; do not silently rebase published work.
Use short-lived branches containing coherent related changes. Long-lived release
or maintenance branches require an explicit project policy.

When selected, Process owns baseline versions, change records, integration
preparation, workflow closure and release finalization. Application versions may
follow Process's default or an explicit selected application policy. Repository
policy remains coherent for all deliverables in a monorepo; independent release
cadences do not remove repository-wide review requirements.

## Autonomous implementer Git behavior

Identify the actual primary branch and verify a suitable development context
before every first write and after branch/worktree changes. A detached checkout is
not an editable topic branch. Reuse a suitable existing branch for related work.
When a new branch/switch is needed, explain it to the definer and materialize it
once authorized. Existing authorization remains valid.

Preserve local work. Never implicitly stash, discard, reset, transfer unrelated
edits, force-push or overwrite a branch. Autonomous branch creation/switching,
fetching, merge, rebase, deletion and remote publication must be within the
definer-authorized task or explicitly authorized workflow. Routine relevant
inspection is permitted. Implementation authorization alone does not imply remote
publication or application release.

A request to publish development changes covers the project's defined proposal
submission: publish the topic branch and open/update a review proposal when that
facility is used, or prepare its native equivalent. Submission does not authorize
integration, tagging or distribution. Perform an authorized integration through
that review procedure and verify the resulting primary state. Never bypass its
required checks or reviews because a command can update the branch directly.

## Updating from the primary branch

Distinguish three operations:

1. Fetching updates cached remote refs. Report whether observed refs were fetched
   or merely cached; cached refs alone do not prove latest remote state.
2. Synchronizing a fork's primary mirror copies accepted upstream history. It does
   not update a separate topic branch. Fast-forward when possible; divergent or
   locally edited state requires an explicit resolution rather than reset.
3. Incorporating updated primary work into a topic branch uses the project-selected
   merge/rebase strategy on that branch. Respect shared history and preserve
   conflicts for the implementer to resolve within approved scope.

Inspect a clean index/working tree and active operations before synchronization;
report blockers rather than hiding them with stashes. Verify target identity,
review changed requirements and shared dependencies, resolve semantic conflicts,
and rerun proportionate validation. Failed source access must be visible rather
than reported as a successful synchronization.

Retain each change record's original starting commit and baselines. Updating a
branch changes its current commit suffix and validation target, not its origin
or official numeric versions. For a release branch, changed target state makes
its plan stale: reassess included changes, impact and candidate declarations
before finalization. Do not silently fold additional feature work into a candidate
that was reviewed for another scope.

## Review and merge gates

When Process is selected, close all workflows under its explicit definer-confirmed
procedure before proposal submission. Pending change records are allowed on the
primary branch and do not count as open workflows. Later review corrections use
new scoped workflows which must close before integration.

Local proposal preparation and merge readiness are different gates. A draft
proposal may initiate external CI/review after local preparation and closure.
Required CI/review results can remain pending at submission but must pass before
integration. Without hosted facilities, equivalent local checks and recorded
review must establish the same evidence.

Validation binds exact source/target and their proposed combined tree. If either
moves, reassess affected evidence and rerun applicable checks. Use up-to-date
requirements, a merge queue, native hooks or a serialized manual procedure where
available. A tracked list of pending/merged proposals or a moving tag is not a
concurrency lock and cannot replace checking current refs.

## Release branches

When the selected Process policy uses release preparation, ordinary topic branches
record impact without allocating official baseline numbers. An authorized release
branch collects accepted pending changes from current primary, calculates candidate
versions and prepares reviewed finalization. One active release proposal may
finalize a version line at a time. Changes to its target require recalculation.

Finalizing repository baselines does not automatically publish applications.
Application release policy names affected deliverables, authoritative versions,
required tools/checks, provenance and publication authorization. In a monorepo,
application tags must use unambiguous namespaces. A provider-specific release
service is optional; Git annotated tags and documented release evidence suffice.

## Commits

Commits should be coherent, reviewable units of change.

Use conventional, descriptive commit messages. A commit message should make the
reason for the change understandable without requiring the reader to inspect the
entire diff first.

Do not mix unrelated behavior changes, cleanup, generated output, and
documentation updates in one commit unless they are part of the same coherent
change.

Before committing, avoid staging local-only files, generated files, temporary
files, secrets, credentials, or real account data.

## Tags and releases

Use Git tags for release points when the project publishes versions or stable
snapshots.

Release identifiers should be stable once published. If a published release has
a problem, prefer a follow-up release over rewriting history.

Release notes should describe user-facing or operator-facing changes, migration
notes, compatibility breaks, and known limitations relevant to the release.

## History

Do not rewrite shared history unless the project has explicitly agreed to do so.

Prefer preserving understandable history over making history artificially tidy
after work has been shared.

When a repository publishes subtrees or other split histories to external
repositories, treat those published split histories as shared history too. Do
not amend, rebase, replace, or otherwise rewrite commits that were used to
publish a subtree unless the workflow explicitly accounts for the downstream
subtree repositories and the definer approves the history rewrite.

After publishing a subtree for the first time, prefer follow-up commits over
amending the source commit. If a correction is needed after publication, make a
new commit and publish that new commit through the same subtree mechanism.

Subtree publication must also respect the destination review procedure. Publish
split history to a topic branch and prepare its reviewed integration when the
destination is primary; subtree commands do not authorize bypassing review.

If subtree history has already diverged, do not force-push the subtree
repository by default. First prefer repairing the relationship by pulling or
merging the current subtree repository history back into the parent repository,
then continue with normal subtree pulls and pushes. Force-push only when the
definer explicitly accepts rewriting the subtree repository history.
