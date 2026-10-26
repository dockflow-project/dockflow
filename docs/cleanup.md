# Delete records and clean managed storage

[Documentation index](README.md) · [Artifacts](artifacts.md) · [Operations](operations.md)

These operations are available in the unpublished development implementation.
Use a disposable project for initial testing. Native deletion does not extend the
bounded KFP-compatible API: KFP client delete/archive methods remain unsupported.

## What can be deleted

Delete a terminal Run, an execution attempt, or an artifact from its detail page.
A Run deletion includes its Tasks and attempts but keeps registered artifacts.
An execution selected by a retained Run or reused Task cannot be deleted until
that dependency is removed. Execution deletion leaves the parent Run's outcome
unchanged and excludes the deleted execution's logs from public log views.

An artifact record and its files share one eligibility check. Pins and retained
Run/Task/attempt inputs, outputs and manual bindings block both kinds of deletion.
Delete dependent records first; there is no force flag. The artifact dialog asks
whether to also delete managed storage files. Keeping bytes is explicit; those
files remain classified as retained files, not orphans. Registered external source
files are never deleted. An imported managed copy may be deleted independently
of its original source.

Manually registered/imported artifacts are labelled **Manually added**. A manually
added database snapshot remains protected from automatic retention and orphan
cleanup even when no Run consumes it. Its deletion must be explicitly selected.
Standalone publication claims/manifests also protect data without a producing Run.

Deletion retires resources from lists, reuse and selection. Detail requests return
HTTP 410; surviving artifact lineage identifies deleted producers. The accepted
journal and deletion markers remain for replay and provenance. This is not secure
erasure or physical database compaction. The first accepted resource deletion
advances the project mapping format; older runtimes cannot reopen that project. Restoring an older backup restores that
backup's historical records; it cannot recreate files removed after the backup.

## Storage cleanup screen

Open **Storage → Cleanup** in the sidebar, or follow the link from an artifact.
Scan the configured managed filesystem root or S3 bucket/prefix. An optional
relative directory/prefix narrows the scan; it never permits browsing/deleting an
arbitrary server directory. The root/prefix must be exclusively owned by this
Dockflow project and its cooperating publishers.

The title, scan controls and selection actions stay above the scrolling inventory;
column headings remain at the top of the rows. Pagination and all four byte
estimates stay visible in the bottom bar. Expand **Scan options and filters** for
the prefix and filters; this section starts collapsed on narrow screens.
**Deletion jobs** opens plan inspection/resumption, and **Preview retention** opens
the deployment policy and preview in a dialog.

Rows show relative paths, logical sizes, classification, associated artifact IDs,
object versions where applicable, and deletion blockers. Filters support exact
classification and artifact ID. Click **?** beside **Classification** to see an
explanation of each category, including orphans, retained files and manually added
artifacts. The explanations remain hidden until opened; close the dialog with
its close button or Escape.

Pages contain at most 200 rows. The totals cover
the complete scan, including selections across pages:

- Current selected bytes.
- All eligible orphan bytes.
- All distinct artifact payload bytes, including known retained files.
- Protected artifact payload bytes.

These are estimated logical bytes removed, not guaranteed reclaimed filesystem
space or reduced storage bills. Unknown sizes are excluded and reported. Hard
links, snapshots and object-store accounting can change the physical result.

**Select all eligible orphans** selects only proven unowned files from a complete
scan. It excludes manual artifacts, retained files, publications, storage identity,
unknown ownership, symlinks and mounted directories. A failed/incomplete listing
cannot authorize bulk orphan deletion. Selecting a file within a directory
artifact selects the complete artifact; partial directory-artifact deletion is
not supported. Every overlapping artifact alias must also be eligible.

Review the selection, its expanded files, dependencies, location and byte estimate.
Every manual storage deletion requires the exact text **DANGER**. The server
rechecks eligibility and identities before acting. Changed files or new references
invalidate a plan. New plans expire after 30 minutes. Apply requires an idle,
reconciled project without queued work and exclusive maintenance ownership; other
PostgreSQL coordinators may need to be stopped to release their maintenance gate.

A partial failure remains a durable deletion job. Its artifacts are unavailable
for new consumption while it is pending. Use its plan ID under **Deletion jobs**
to inspect and retry the remaining exact objects. Retrying does not delete a
replacement object or broaden the selection. Rescan after completion.

## CLI and Python

Every resource command previews by default:

```bash
dockflow pipelines --config PROJECT_CONFIG runs delete RUN_ID
dockflow pipelines --config PROJECT_CONFIG runs delete RUN_ID --apply

dockflow pipelines --config PROJECT_CONFIG executions delete ATTEMPT_ID --apply

dockflow pipelines --config PROJECT_CONFIG artifacts delete ARTIFACT_ID --delete-files
dockflow pipelines --config PROJECT_CONFIG artifacts delete ARTIFACT_ID \
  --delete-files --apply --confirm DANGER
```

Interactive artifact deletion asks about storage files; scripts must supply
`--delete-files` explicitly to request them. Record deletion can proceed only
when its dependency check passes, even when storage files will be kept.

```bash
dockflow pipelines --config PROJECT_CONFIG storage scan
dockflow pipelines --config PROJECT_CONFIG storage scan-show SCAN_ID --classification orphan
dockflow pipelines --config PROJECT_CONFIG storage plan SCAN_ID --orphans
dockflow pipelines --config PROJECT_CONFIG storage plan SCAN_ID --select ROW_ID
dockflow pipelines --config PROJECT_CONFIG storage show PLAN_ID
dockflow pipelines --config PROJECT_CONFIG storage apply PLAN_ID --confirm DANGER
```

Repeat `--select` for individual rows. Use the scan's returned row IDs, not paths.
Replace `--config PROJECT_CONFIG` with `--endpoint SERVICE_URL` for service calls;
use group `--json` for machine-readable output.

```python
from dockflow_pipelines.client import Client

client = Client("http://127.0.0.1:8080")
scan = client.operate("storage.scan", {})
plan = client.operate("deletions.plan", {"scan_id": scan["scan_id"], "orphans": True})
# Review plan["rows"], plan["estimated_bytes"] and plan["blockers"].
result = client.operate("deletions.apply", {
    "plan_id": plan["plan_id"], "confirmation": "DANGER",
})
```

The native API exposes the same operations at `POST /dockflow/v1/storage/scan`,
`/storage/scan/show`, `/deletions/plan`, `/deletions/show`, `/deletions/apply` and
`/retention`. See the [generated reference](reference/api.md) for request schemas.
An apply response can be `partial`; inspect its failures rather than equating
HTTP success with complete deletion. All routes retain service authentication and
browser Origin protections. Scans and deletion apply currently execute within the
request; clients that lose a response should inspect retained state or retry the
same plan ID, never assume that no files were deleted.

## S3 requirements

Enabled-versioning buckets scan all payload versions and delete exact VersionIds.
A newer version written after a plan is never substituted for the selected
version. Directory markers are included; delete markers have no payload and are
left in place. Artifact selections include their complete associated versions.

Unversioned buckets require a provider that enforces conditional `DeleteObject`
with `If-Match`. Dockflow checks that capability using a fresh reserved probe object
before touching selected data. A provider that ignores the condition is refused;
enable bucket versioning and rescan. Suspended versioning and object-lock buckets
are refused. Credentials need listing, HEAD/read, delete, bucket-versioning and
object-lock inspection access; versioned cleanup additionally needs version-list
and version-delete access. The unversioned capability probe needs conditional PUT.

## Optional retention

```toml
[artifacts]
retention_days = -1
retention_interval_seconds = 3600
```

`-1` disables automatic expiry. A positive number enables expiry of sufficiently
old, committed, execution-produced managed artifacts only when no retained
references, pins, manual aliases or active publications protect them. Age is
measured from publication time. Retention never deletes Runs/executions, manual
artifacts, external sources, retained files or orphan files. Retained execution
history can therefore keep old artifact files indefinitely.

Set `ARTIFACT_RETENTION_DAYS=30` in the service environment for deployment-wide
configuration. `DOCKFLOW_PIPELINES_ARTIFACT_RETENTION_DAYS` takes precedence if
both are present. Configuration options override environment, which overrides
the file. The service checks while idle using exclusive maintenance ownership;
the cleanup screen shows the policy and latest result or deferral.

```bash
dockflow pipelines --config PROJECT_CONFIG retention
dockflow pipelines --config PROJECT_CONFIG retention --apply --confirm DANGER
```

The first previews. Manual application requires DANGER. Enabling the deployment
policy authorizes its unattended scheduled deletions, which use the same plans
and dependency checks without an interactive prompt. Independent SeaweedFS/S3
expiry cannot respect Dockflow references or pins; exclude this managed root from
such expiry if these protections are required.

## Try the unpublished implementation

From a development checkout with the workspace installed and the fixture's
`python:3.13-slim` image available:

```bash
python tools/web_fixture.py --directory tmp/cleanup-manual-test --port 8080 --cleanup
```

The directory must not already exist. Open `http://127.0.0.1:8080/ui/`. The fixture
contains a manual database snapshot, a pinned manual dataset and an orphan file.
The fixture registers a test pipeline; create a Run from it to produce real Run,
execution and artifact records. Its `pipeline.json` is also available for upload tests. Try orphan cleanup, pin/dependency blockers,
record deletion, and finally artifact deletion. Stop with Ctrl+C. No publication
or change to existing project data is involved.
