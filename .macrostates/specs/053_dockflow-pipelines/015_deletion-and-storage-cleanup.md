# Deletion, storage cleanup and retention

## Shared authority and eligibility

This document owns destructive lifecycle operations. It specializes the original
preserve-history and disabled-eviction defaults in 006, 007 and 014 only for
explicitly planned deletion and configured retention. All other publication,
integrity, fencing and execution-ownership contracts remain applicable.

Run, execution (attempt) and artifact deletion MUST be available through native
HTTP, Python and CLI operations and the packaged browser. Deleted resources are
excluded from normal lists and historical reuse/manual selection. Detail requests
return 410 with a truthful deletion explanation. Journal-backed deletion markers
preserve minimal producer identities for surviving lineage; IDs are never reused.
Projection rebuild and startup MUST NOT resurrect deleted resources or outputs.
The first accepted resource retirement atomically advances project mapping version
from 1 to 2; the new runtime accepts either version, while older runtimes must
refuse version 2 instead of ignoring deletion events. Preserve this marker through
backup/rebuild. This is an explicit destructive-operation format transition, not
an implicit startup migration.
Deletion is logical retirement, not secure erasure or SQL-space reclamation;
journal/checkpoint compaction is not implied. Logs of deleted executions are not
returned by public log routes. Old backups retain their historical data and scope.

Only terminal, reconciled Runs/executions may be deleted. A Run deletion retires
its Tasks/attempts together, leaving produced artifacts independently registered.
Other retained Runs' explicit historical-attempt selections or reused producer
bindings block deletion of the referenced execution and its containing Run.
Deleting one execution leaves its parent Run outcome historically unchanged.

Artifact records and their storage files have ONE eligibility decision. A pin,
retained Run/Task/attempt input or output binding, explicit/manual invocation
binding, live consumer, unresolved publication, or incomplete ownership information
blocks BOTH record and file deletion. There is no force bypass. References from
resources included in one Run-deletion operation may be retired together, but
artifact deletion remains a separate explicit operation after those references
are gone. Producer identity alone does not constitute a live consumer binding.
Cache selections must be invalidated before retirement, preserving attempt,
fence, retry and publication history. A cache entry by itself is not a permanent
retention pin. Cache manifests from all project namespaces participate in storage
ownership and protection, including publications absent from the artifact catalog.

Artifact deletion defaults to keeping storage bytes and asks explicitly whether
to delete them. The same blockers apply to both choices. Kept files remain known
retained files, excluded from automatic and orphan cleanup until explicitly
selected. Metadata-only artifacts have no fabricated files. External references
may be unregistered, but their source files MUST NOT be deleted by these tools.
Managed imports may delete only their managed copy, never the original source.
All associated records must pass eligibility before deleting shared physical bytes.

## Manual origin

Persist artifact creation origin as manual or execution. Explicit registration,
managed import and administrative UI/API/CLI creation are manual, including a
database snapshot without any producing Run. KFP importer/external artifacts
with uncertain creation origin are conservatively manual. Derive legacy origin
conservatively from existing producer/origin fields; absence of a producer NEVER
establishes orphanhood. Manual artifacts and their files require explicit artifact
or file selection even if unreferenced. Exclude them from retention and bulk
orphan selection. A durable completed standalone publication is known owned data,
not an orphan merely because it has no Pipelines catalog entry.

## Storage inventory and classifications

Inventory only the configured managed filesystem root or S3 bucket/prefix, or
an explicitly selected contained subdirectory/prefix. Do not expose arbitrary
server filesystem browsing, follow symlinks, cross mounts, or infer ownership of
an unrelated shared bucket. Scope deletion to an exclusively Dockflow-owned
root/prefix bound to its persistent storage identity. Display resolved locations.

Match complete relative file/object identities against artifact inventories,
publication reservations/manifests, all cache manifests, pending deletion plans,
retained-file records and system metadata. Preserve directory membership and
shared aliases. Classify entries as execution_artifact, manual_artifact,
publication, retained_file, orphan, protected or unknown, with associated IDs,
logical byte size and explicit blockers. Protect storage identity, active work,
publication in progress, symlinks/nonregular files and uncertain ownership.
Unknown/inaccessible is not orphan. Interrupted or incomplete scans cannot produce
an all-orphans deletion plan. Bulk orphan selection includes only proven eligible
orphans in a complete scan, not manual artifacts or unreferenced publications.

File selection belonging to a directory artifact expands to its entire artifact
payload; no partial deletion may silently leave a registered incomplete artifact.
Validate all overlapping aliases before retirement. Individual orphan files may
be selected independently. S3 directory marker objects must be inventoried too.

Persist completed scans with stable row IDs and page results. Every page reports
whole-scan totals, including selected bytes, eligible-orphan bytes, all distinct
artifact bytes and protected artifact bytes. Selection across pages uses the
complete scan, not the currently loaded page. Deduplicate physical identities;
unknown sizes and partial totals are labelled. Estimates describe logical bytes
selected for removal, not guaranteed freed disk/billed capacity. Filesystem hard
links/snapshots and S3 object versions may retain physical storage. Enabled-versioning S3 buckets inventory all payload versions and delete exact
VersionIds; version IDs distinguish rows and byte totals. Delete markers carry no
payload and remain outside file cleanup. Suspended versioning and object-lock
buckets are refused. Unversioned providers must demonstrate conditional
DeleteObject enforcement using a fresh reserved probe object before touching
selected data; refuse providers that ignore If-Match, with an enable-versioning
explanation. Never treat the S3 protocol label as proof of conditional behavior.

## Plans, confirmation and recovery

Every destructive request first creates a durable plan containing target IDs,
exact files/objects, observed identity/version, byte totals, blockers, selection,
project/store identity, dependency revisions, creation and expiry. Plans expire
after 30 minutes before application. A stale plan fails without new deletion.
The client cannot supply arbitrary paths or replacement object manifests to apply.

All manual storage deletion requires exact confirmation text DANGER in a dialog
or explicit CLI/API field bound to the plan ID. Record-only deletion requires an
explicit apply action. Never infer file deletion from omitted options. Server-side
authorization, Origin/token controls and validation apply to every adapter.

Application uses project-wide exclusive maintenance ownership, rejects queued,
active or unresolved work and coordinates standalone publishers. Revalidate all
references, pins, storage identity and file/object identity immediately before
retirement/deletion. External noncooperating writers are outside this exclusive
ownership contract; observed changes still fail closed. Do not hold a SQL
transaction across storage transfers. Persist a durable job before retirement,
atomically invalidate cache selections and mark affected resources unavailable
for new use, then remove exact eligible files. Preserve cache fences and source
provenance. Record per-object completion/failure. Repeated application resumes the
same job without broadening its selection; already absent objects are reported.
Changed/replaced objects are never removed on retry. Partial failure leaves an
inspectable job and retired resources; no false success or automatic resurrection.

## Adapters and browser

Native routes under /dockflow/v1:

- POST /storage/scan: optional relative prefix; persist a complete inventory.
- POST /storage/scan/show: scan_id, optional page_size/page_token and selection.
- POST /deletions/plan: resource targets or a completed scan selection/orphans.
- POST /deletions/show: plan_id; current plan/job progress and result.
- POST /deletions/apply: plan_id and confirmation; validate and execute/resume.
- POST /retention: apply=false previews policy; apply=true executes eligible work.

The Python Client operates on these same native contracts. CLI exposes runs delete,
executions delete, artifacts delete, storage scan/show, storage plan/apply/show and
retention. Destructive resource commands preview unless --apply is supplied;
--delete-files is explicit; --confirm DANGER is mandatory for manual byte deletion.
Expose native capabilities and generated OpenAPI request/response contracts.
KFP delete/archive endpoints remain outside the bounded compatibility profile;
no upstream cascade semantics are inferred from native deletion support.

Expose Cleanup under the Storage sidebar section, opening the Storage cleanup
screen; also link to that screen from Artifacts. Show configured location, scan
state/time, refresh/rescan, classification/artifact filters, paginated selectable
rows, blockers and associated artifact links.
Use the shared fixed list workspace from 013: top title/filter/actions, scrolling
files with sticky column headings, and a bottom bar with pagination and byte
estimates. Keep estimates visible while rows scroll. Deletion-job inspection and
retention tools open from top actions; scan/filter options may collapse on narrow
screens without hiding the selection estimates or pagination.
Add a question-mark button beside the Classification filter that opens a
dismissible, keyboard-accessible explanation of all seven classifications,
including explicit-only manual artifacts, intentionally retained files and
eligible orphans. Keep these descriptions hidden until the button is activated.
Always display selected, eligible orphan, all artifact and protected artifact
logical-byte estimates, including on
empty pages. Select all eligible orphans operates across the full scan. Review
selection creates a server plan before a DANGER confirmation dialog; protected
rows are disabled. Display all expanded artifact files and partial failure results.
Manual artifact badges and deletion actions appear in the catalog/details;
Run/execution details expose record deletion with dependency explanations.

## Deployment retention

artifacts.retention_days defaults to -1 (disabled), otherwise a positive integer.
artifacts.retention_interval_seconds defaults to 3600 and must be positive.
ARTIFACT_RETENTION_DAYS supplies a portable deployment override; the namespaced
DOCKFLOW_PIPELINES_ARTIFACT_RETENTION_DAYS wins when both are present. Existing
option > environment > file > default precedence remains. Reject zero, booleans,
nonintegral values and values below -1. Service polling runs only while idle;
exclusive maintenance serializes competing coordinators. Direct CLI can invoke
the same policy. Scheduling failure is reported without silently disabling it.

Age is measured from committed publication UTC time. Only execution-produced,
managed, unpinned artifacts old enough AND passing all reference/ownership checks
are eligible. Retained Runs/executions protect their artifacts regardless of age.
Manual/external artifacts, retained files, unknown objects and system metadata
are never automatically expired. Orphan cleanup remains explicit. Retention uses
the same plan, retirement and durable job logic; explicit deployment configuration
is standing authorization, so unattended retention does not demand interactive
DANGER on every tick. Manual retention application still requires DANGER.
Report enabled policy, last check/result and next-check timing in the cleanup UI.
Storage-provider expiry is independent and cannot honor Dockflow pins/references;
exclude the managed root from uncoordinated expiry when these guarantees matter.

## Acceptance (A40)

Verify dependency blockers and transitive Run/execution deletion; retained manual
artifacts and shared aliases; replay/rebuild/backup of deletion state; complete
paginated scan totals and selection expansion; incomplete listing, unknown owner,
external reference, publication/cache-only protection; exact DANGER enforcement
across UI/API/CLI; stale identities, replaced objects, symlinks/mount boundaries,
S3 exact-version deletion, conditional-delete qualification and suspended-versioning refusal; interrupted/partial apply and idempotent resumption; cache
retirement with unchanged fences; retention age/precedence/default/manual
exclusions; both SQL backends and filesystem/S3 storage; packaged browser flows
and generated OpenAPI. Test only disposable data; deliver an unpublished local
build and manual testing steps before any publication.
