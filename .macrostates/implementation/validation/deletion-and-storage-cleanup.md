# Deletion and storage cleanup qualification

- Date: 2026-10-25 12:04 UTC
- Attribution: Implementer
- Delivery: unpublished development implementation, awaiting Definer testing.
- Scope: Pipelines 015/A40 and associated Artifacts publication ownership.
- Branch: `feature/deletion-and-storage-cleanup`.

## Delivered behavior

Native API, Python client, CLI and packaged browser share dependency-protected
resource retirement and reviewed storage plans. Artifact records and bytes share
one eligibility gate. Retained execution inputs/outputs, complete output-set
commits, pins, active work and publication ownership protect data. Manual
registrations/imports, retained files and standalone publications are never bulk
orphans or automatic-retention candidates. Directory-artifact selection expands
to the complete associated payload and checks all aliases.

Filesystem and S3 inventories report complete paginated logical-byte totals,
classifications, blockers and cross-page selection. Every manual storage mutation
requires exact DANGER. Plans revalidate identity/references and have durable
partial/retry results. Cache pointers retire without deleting fencing history.
The first accepted resource retirement advances project mapping to 2, preventing
older runtimes from ignoring deletion; current replay/rebuild and backups retain
that marker. Optional retention defaults to disabled and uses the same checks.

## Validation results

| Check | Observed result |
| --- | --- |
| Full suite, CPython 3.13.17, real Docker/PostgreSQL/S3 available | 879 passed, 14 environment-gated skips, 5 warnings. |
| Full suite, CPython 3.12.15, same provider matrix | 879 passed, 14 environment-gated skips, 5 warnings. |
| Final focused deletion/storage suite, each interpreter | 70 passed; covers subsequent integrity/request/retry refinements. |
| Existing packaged Chromium journey with real Docker tasks | 14 journeys passed; no page errors or external requests. |
| Cleanup Chromium journey | 6 journeys passed, including record/file deletion, pin/manual protection and exact DANGER. |
| Browser visual review | Desktop and narrow layouts inspected; horizontally scrollable file table and persistent totals remain usable. |
| JavaScript unit suites | 6 files passed, including cross-page overlapping-alias deselection. |
| Ruff lint/format and Pyright | Passed. |
| Generated API reference, application versions, composition/import integrity, diff whitespace | Passed. |
| Offline runtime CA verification | Passed. |
| Four wheels and source distributions | Built; clean standalone/base installs and independent source rebuilds passed. |
| Baseline-runtime probe | The baseline refuses mapping 2; the current runtime reopens it without resurrecting retired resources. |

Full-suite runs cover the unchanged broader product; the final focused suites
cover the delivered deletion code after the last refinements. Skipped scenarios
retain their existing opt-in environment requirements and are not claimed as
qualified by these results. Provider services and buckets were disposable and
isolated from existing project data. Qualification is Linux x86-64; it does not
establish native multi-host, macOS/Windows or SeaweedFS-version qualification.

Real S3 tests include enabled-versioning inventories, directory markers, prefix
boundaries, replacement versions, lost deletion acknowledgments, retry, object-lock
and suspended-versioning refusal. A tested provider ignored If-Match; qualification
now refuses such unversioned cleanup before selected data is touched. Enabled
versioning permits exact-version deletion and preserves newer objects. Temporary
capability probes are confined to fresh reserved keys.

Browser coverage includes orphan selection that excludes manual/pinned artifacts,
explicit manual database-snapshot deletion, blocked pin deletion, execution
retirement, Run retirement with independent artifacts, and narrow layouts.
Captured screenshots were inspected and then discarded; retained receipts omit
runtime fixture IDs, private paths, endpoints, connection strings and raw logs.

The classification-help refinement was checked against the local source preview:
all seven descriptions remain hidden until the question-mark button is activated;
Escape and the close button dismiss the dialog and restore focus. Desktop and
narrow layouts passed without page overflow or browser errors. The narrow dialog
was visually inspected. All six JavaScript test files, frontend formatting,
composition validation and diff whitespace checks passed. Selection and deletion
behavior were unchanged, so provider suites were not repeated for this UI copy
change. The specification and cleanup guide describe the on-demand help.

## Reproduction and artifact binding

Use CONTRIBUTING's standard checks with disposable providers and the commands in
[the cleanup guide](../../../docs/cleanup.md). Browser fixtures use
`tools/web_fixture.py --cleanup`; the new probe is
`tools/cleanup_browser_smoke.py --url SERVICE_URL --output OUTPUT_DIRECTORY`.
The fixture must be fresh and disposable. The probe refuses ordinary projects.

The local package receipt is `tmp/deletion-candidate/dist/verification.json`.
The verified Pipelines wheel SHA-256 before the classification-help refinement is
`89fcb1023cb9e9f18555d43589d0a34c465c8f02e8d9c4e970c36cf7909ef8b2`.
That receipt covers the earlier package candidate; the help refinement is available
in the source preview and has not been rebuilt into that wheel.
The distribution version remains the starting `VERSION` value: these are local
unpublished development artifacts, not a new stable application release. No
baseline finalization, commit, tag, remote integration or publication occurred.

## Delivery limits and acceptance

Deletion is logical retirement with replay/provenance markers; secure erasure and
physical SQL compaction are outside this delivery. Storage operations require
idle, reconciled project maintenance ownership. Other PostgreSQL coordinators may
need to stop before that gate can be acquired. Scans/apply execute synchronously;
clients should inspect/retry their retained plan ID after response uncertainty.
S3 object-lock and suspended-versioning buckets are refused; unversioned deletion
requires demonstrated conditional-delete enforcement. Retention never overrides
manual origin, pins or retained execution history. Independent storage TTL does
not participate in these protections.

The Definer's manual testing and acceptance remain open. A separate fresh local
fixture under `tmp/deletion-user-test` contains a successful real Run, a manual
database snapshot, a pinned dataset and an orphan file. Keep this fixture while
testing. No existing project data was changed. Publication remains unauthorized.
