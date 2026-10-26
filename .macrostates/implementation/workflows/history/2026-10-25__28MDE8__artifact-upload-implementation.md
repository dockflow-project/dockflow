# Artifact upload implementation

- Project phase: `active`
- Workflow type: `Implementation update`
- Status: completed
- Delivery state: accepted
- Change depth: `medium`
- Branch: `feature/deletion-and-storage-cleanup`
- Requested by: Definer
- Implementer: Implementer
- Started at: 2026-10-25 21:09 (UTC)
- Last updated at: 2026-10-26 12:06 (UTC)

## Objective and authorization

Define and implement one upload-and-register operation through the web, native
API, Python client and CLI. A ZIP may remain an archive artifact or be safely
extracted into a new managed directory artifact. Uploaded artifacts are manual,
managed, immutable snapshots with no invented Run/producer and explicit-only
retention. Validate all input before publication; bound request and extraction
resources and reject unsafe archives. Preserve existing URI registration/import.

Use the already authorized development branch. Track independent Minor contract
and implementation impact. Preserve all existing preview data and pending work.
Keep changes unpublished for Definer testing. No commit, integration, tag,
release, publication or workflow closure is authorized by this objective.

## Delivered scope and checks

The artifact contract owns native file upload, manual managed origin, ZIP keep/
extract semantics, safe bounded staging/publication and failure behavior. CLI,
API, web, configuration boundary, package selection and acceptance references
align. The reusable specification change is additive Minor impact; finalized
project/application versions remain unchanged.

Implementation provides one browser upload/register action, native multipart
endpoint, direct/endpoint CLI and Python client. ZIPs default to exact archive
bytes or extract into an immutable directory artifact, preserving nested/empty
folders. Filenames are presentation metadata, never destination paths. Existing
URI import/reference, Contents, manual retention/dependency protection and
publication recovery remain available.

The [validation receipt](../../validation/artifact-upload.md) records 261 focused
passes (30 optional skips), four actual MinIO cases, six upload browser groups
with/without bearer authentication, six authenticated Contents groups, fourteen
existing browser journeys and static/schema/specification checks. Captures were
inspected and discarded; disposable provider/browser services and credentials
were removed. Qualification limits are explicit in the receipt.

The existing local preview was restarted without resetting data; its two
successful Runs and nine artifacts remain, and the upload form/route were checked
without submitting data. No distribution rebuild, commit, integration, tag or
publication occurred. The sixteen earlier workflows remain independently open;
all eighteen await Definer testing and explicit acceptance/closure.

## Definer-authorized completion and closure

The Definer explicitly authorized acceptance and closure of all open workflows,
committing, pushing, PR submission, reviewed merge and release. The requested
local scope is delivered and relevant validation passed; no required source gap
remains. All original feature provenance and classification are preserved.
[Release qualification](../../validation/release-0.3.0.md) records the combined
evidence and separates subsequent hosted CI, merge, immutable candidate and
publication outcomes. No upload is claimed by this closure.

- Closure authorized by: Definer; explicit all-workflow closure and release instruction
- Closed at: 2026-10-26 12:06 (UTC)
