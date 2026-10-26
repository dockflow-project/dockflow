# Artifact upload validation

## Scope and delivery

The unpublished development working tree implements the
[upload contract](../../specs/053_dockflow-pipelines/006_artifacts.md#upload-and-register):
one client-file upload and manual managed registration, with keep/extract ZIP
choices. The existing URI reference/import operations remain available. Web,
native multipart API, standard-library Python client and direct/endpoint CLI use
the same bounded staging and managed publication behavior.

The additive specification and implementation changes have Minor impact. The
application and finalized project versions remain unchanged. This receipt records
implementation checks, not Definer acceptance, a release or publication.

## Measured results

| Check | Result |
| --- | --- |
| Focused backend/API/CLI regressions | 261 passed, 30 optional backend cases skipped, three existing dependency warnings. Includes upload, redirect/client, interfaces, Contents, web, KFP registration and deletion suites. |
| Upload-specific behavior | Manual origin/ownership without Run/producer; type/metadata/revision; exact bytes; distinct submissions; CSV filename/preview; stored/deflated ZIP keep/extract; nested/empty directories and empty file/archive; direct and actual authenticated HTTP Python/CLI uploads passed. |
| Input and archive safety | Traversal/absolute/drive/backslash paths, duplicate/case/Unicode collisions, file/directory conflicts, nonportable names, symbolic/special entries, corruption/CRC/truncation, unsupported compression/encryption, ZIP/request/options budgets, malformed/incomplete/extra multipart, duplicate JSON keys, invalid UTF-8, auth/Origin, busy/unready owner and nonregular direct sources passed. |
| Transfer and failure behavior | SQL transaction depth remained zero during hashing/publication. Private staging was removed after success, invalid ZIP and injected publication failure. Invalid inputs created no artifact/published payload; injected storage failure returned an error without a new artifact. |
| Real S3 integration | Four cases passed against disposable MinIO: existing conditional Contents reads and new file/kept-ZIP/extracted-directory publication, each with bucket versioning disabled/enabled. Uploaded records, inventory, hashes, nested JSON and empty directory materialization verified. Unique buckets and contents were removed. |
| Upload browser probe | Six groups passed with and without bearer authentication. One pending request disables submission; ZIP default/extract, filename heading, automatic Contents, error/file-selection preservation, type switching/reset, nested CSV/empty folders and narrow usability passed. Four successful submissions added exactly four artifacts; one failed submission added none; pre-existing records/Runs remained. |
| Established Contents browser probe | Six read-only groups passed on the authenticated fixture, covering CSV pagination, exact/lazy JSON, actual PNG decoding, directory/history/errors and fixed narrow layouts. |
| Established full browser journey | Fourteen groups passed on a disposable fixture with actual Docker execution, pipeline/version upload, Run idempotency/reuse/logs/comparison, failure/cancellation, URI artifact import/pin/lineage, narrow navigation and API explorer. |
| JavaScript checks | All six existing test files passed. |
| Static and documentation checks | Ruff lint/format, Pyright, frontend formatting, generated API reference, Macrostates composition/import checks and whitespace passed. |
| Visual and final-preview checks | Desktop and narrow upload/ZIP forms inspected; captures discarded. The existing preview restarted in place, exposing upload capabilities/route/form with both ZIP options while preserving its two successful Runs and nine artifacts. No upload was submitted to that preview. |

Browser coverage is Chromium 140 on Linux, using desktop 1440-by-1000 and narrow
390-by-844 viewports. The actual object provider was cached MinIO
RELEASE.2025-10-15T17-29-55Z, public source commit
`9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a`. Real SeaweedFS, additional S3
providers, PostgreSQL upload paths and other browsers/platforms were not newly
qualified. Resource-limit tests use lowered isolated budgets; these are boundary
checks, not maximum-size performance/load qualification. Local HTTP tests exercise
real multipart transport and authentication; existing configured TLS/redirect
policy is shared, with upload redirect-refusal and endpoint-prefix tests added.

Durable partial-publication recovery uses the existing protected claims and
descriptor protocol; this feature does not introduce a new distributed storage/
SQL transaction. The injected failure checks do not claim a provider outage matrix.
The native API's existing bounded request buffering remains in use.

## Reproduction and pending acceptance

Backend tests are in `packages/pipelines/tests/integration/test_artifact_uploads.py`
and upload transport tests extend `packages/pipelines/tests/unit/test_client_redirects.py`.
Opt-in provider cases extend `packages/pipelines/tests/integration/test_contents_storage.py`,
using its disposable endpoint/credential setup. See
[browser qualification](../../../CONTRIBUTING.md#browser-qualification) for
`tools/upload_browser_smoke.py` and fresh fixture setup. Browser probes mutate
only explicitly identified disposable fixtures. Neutral receipts retain check
descriptions only; captures, disposable credentials and QA services were removed.

Specifications/composition, generated OpenAPI, API/CLI/artifact/UI guides and the
current architecture were updated. No existing example records/files were reset
or deleted. No distribution rebuild, commit, integration, tag or publication
occurred. Eighteen workflows remain independently open, awaiting Definer testing
and explicit acceptance/closure.
