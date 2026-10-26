# Artifact Contents qualification

- Date: 2026-10-25
- Attribution: Implementer
- Scope: Pipelines 013 Contents, with artifact/API references in 006 and 010.
- Delivery: unpublished source preview, awaiting Definer testing.
- Branch: `feature/deletion-and-storage-cleanup`.

## Delivered behavior

Contents is the first/default artifact tab, before Overview and Lineage. The
authenticated read-only API provides bounded CSV pages, collapsible highlighted
JSON, raster images, registered-directory browsing and explicit text/unsupported
states. CSV continuations bind byte offsets and logical row positions to the
registered payload and current source identity. Directory entries come from the
recorded inventory; file reads enforce current source scopes and safe membership.
JSON retains exact numeric spelling, escaped strings and duplicate properties,
with lazy 100-child batches and in-memory expansion retention. Images use generated
raster data URLs. Text truncation and format limits are visible. Partial reads
do not claim full checksum verification; complete bounded reads verify SHA-256.

Filesystem opens walk non-following directory descriptors and check source
mutation. S3 uses conditional/versioned byte ranges and rejects nonconforming
responses. No SQL transaction or execution mutex spans storage transfer, and
retirement is rechecked before returning the response. Responses contain no
storage credentials; payload text never becomes executable markup.

## Measured results

| Check | Observed result |
| --- | --- |
| Preview, web/API, registration and deletion regression selection | 148 passed; 30 optional backend cases skipped with infrastructure unconfigured; three existing dependency warnings. Includes 38 preview/path/race/schema cases. |
| New storage/security coverage | CSV LF/CRLF, BOM, multiple delimiters, quoted/multiline UTF-8 values, bounded reads and partial-record continuation; cursor tampering/restart/scope/change; JSON precision/duplicates/surrogates, malformed/oversized/deep content; raster canvas headers/limits; text truncation; directory membership/paging/empty folders; auth/query rejection; symlink/FIFO/parent-swap/mutation/retirement protections passed. |
| Actual S3 preview integration | Two cases passed against private disposable MinIO, with versioning disabled/enabled. Real conditional ranges, nested directory CSV continuation and percent-escaped JSON names/checksums passed. Test buckets were uniquely created and removed. |
| Dedicated Contents browser probe | Six grouped journeys passed on unauthenticated and token-protected fixtures and the final example preview. Actual preview API reads; no page errors or external requests. |
| Large CSV browser behavior | Generated 250,000-row, approximately 11.25 MiB CSV displayed 50 current rows; next response remained below 64 KiB and began at row 51, with no repeated/lost rows. Sticky headings, fixed controls/footer and multiline display were inspected. |
| JSON browser behavior | Exact large integer text, literal adversarial markup, highlighted/collapsible branches, 100-child batches and expanded-state/scroll retention on refresh passed. No injected image elements appeared. |
| Image/directory/text browser behavior | Decoded PNG dimensions, authenticated raster data URL, actual-size/fit controls; nested JSON/CSV opening, breadcrumbs, Back, empty folders, unsupported/malformed files, explicit text truncation and usable Overview/Lineage passed. |
| Established browser journey | Fourteen journeys passed on a separate fixture, with actual Docker execution, upload/version/idempotency, reuse, logs, comparison, artifact pin/import/lineage, failure/cancellation and navigation. No page errors or external requests. |
| Shared graph/list probes | Eight graph groups and eleven list groups passed. The list probe now waits for Run-result refresh completion before interacting with local pagination. |
| JavaScript regressions | 34 checks across all six existing files passed. New viewer interactions are qualified by the real browser probe. |
| Static/reference/specification checks | Ruff lint/format, Pyright, frontend formatting, generated API reference consistency, composition/import integrity and whitespace passed. |
| Visual review | Desktop and narrow CSV, highlighted JSON, images and directory/empty views inspected; captures discarded after review. |

Browser qualification is Chromium 140 on Linux at 1440-by-1000 and 390-by-844.
The actual object provider was MinIO RELEASE.2025-10-15T17-29-55Z, source commit
`9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a`, in an isolated local HTTP test
container. Real SeaweedFS, additional S3 providers, PostgreSQL preview paths and
other browsers/devices were not newly qualified. Provider-adversarial response
tests are mocked and are distinct from the real MinIO cases. JPEG/GIF/WebP canvas
headers are unit-tested; actual browser decoding was exercised with PNG.

## Reproduction and delivery

See [browser qualification](../../../CONTRIBUTING.md#browser-qualification) for
`tools/web_fixture.py --contents`, optional token protection and
`tools/contents_browser_smoke.py --url FIXTURE_URL`. The generated data includes
CSV, JSON, PNG, directory and text artifacts. Real S3 tests are in
`packages/pipelines/tests/integration/test_contents_storage.py` and require an
explicit disposable endpoint plus standard test credentials. The
[UI guide](../../../docs/ui.md#artifacts-and-lineage) describes formats and limits.

The existing manual preview was restarted on the same configuration/data with
the new API. Both successful example Runs and all four original artifacts remain.
Five explicitly manual Preview samples were added for inspection; they inherit
the existing explicit-only deletion/retention classification. The original orphan
sample remains. No existing resources/files were reset or deleted. Read-only
browser checks passed on this final preview. Temporary captures were removed;
retained receipts contain neutral results only, without runtime identifiers.

Local specifications/composition, generated API reference, usage and current
architecture align. Application and finalized project versions remain unchanged;
the capability response advertises artifact_contents. No distribution rebuild,
commit, integration, tag or publication occurred. Sixteen workflows remain open;
Definer testing, acceptance and explicit closure remain pending.
