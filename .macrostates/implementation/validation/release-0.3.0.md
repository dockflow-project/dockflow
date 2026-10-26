# Dockflow 0.3.0 release qualification

Roles: Definer and Implementer. The Definer explicitly accepted closure of all
open workflows and authorized committing, pushing, PR submission, reviewed merge
and release of every deliverable. This record covers local preparation; actual
integration, hosted checks, immutable tags and registry outcomes are established
by GitHub and the preserved release bundle.

## Scope and compatibility

Application 0.3.0 contains dependency-protected Run/execution/artifact deletion,
managed storage inventory/cleanup and optional retention, manual upload with ZIP
modes, artifact Contents viewers, and the accumulated graph/list/detail/sidebar,
name-reference and autocomplete improvements. Core, CLI, Artifacts and Pipelines
share the version, followed by the matching service image and GitHub release.

The first accepted retirement advances mapping format 1 to 2; older runtimes
refuse that project. Opening existing state alone performs no format migration.
Retain a pre-deletion backup when rollback is needed. Logical retirement is not
secure erasure or physical SQL compaction; backups retain their original scope.
Manual artifacts, retained dependencies, pins, active publications and uncertain
ownership remain protected. External source files are outside managed deletion.
S3 maintenance retains version/conditional-operation restrictions. See
[cleanup](../../../docs/cleanup.md) and [release notes](../../../CHANGELOG.md).

The original deletion change records a Major specification impact, and other
changes are additive. Preserve the original classifications and collect the
highest impact once: candidate specs-2.0.0 and imp-2.0.0. Application versioning is
independent and pre-1.0; the destructive-operation compatibility transition is
explicit in 0.3.0 notes. Original feature provenance remains
72f14612e6e9a791ce6c391e1c17a7c9a8d8fac4 with specs-1.0.0/imp-1.0.0.
The fetched origin/main at that same commit is the integration target. The stored
release plan will bind the exact committed input and collected record hashes;
no candidate embeds its own eventual commit hash.

## Local qualification

| Surface | Measured outcome |
| --- | --- |
| Full source regression | Python 3.13.17 on Linux: 1,033 passed, fourteen backend/profile-specific skips, five upstream warnings. Uses real isolated PostgreSQL, enabled-versioning S3 and Docker execution. Runtime source was unchanged by subsequent version/README synchronization. |
| PostgreSQL autocomplete | Direct authenticated API qualification passed for all eight collections, pipeline/component name joins, parent scopes, distinct types, literal matching and exact window counts under 0.3.0 metadata. |
| Static contracts | Ruff lint/format, Pyright, seven JavaScript test files, version synchronization, generated API drift and Macrostates composition/import integrity passed. |
| Dependency inputs | Only five workspace package versions changed in uv.lock; no third-party versions changed. The pinned dependency audit found no known vulnerabilities. Runtime CA trust checks passed. |
| Packaging | Four wheels and four source archives built and verified, clean Core/CLI/Artifacts/combined-base installs passed, optional runtime extras stayed absent from base installs, and every source archive rebuilt independently. Wheel inventories exclude repository specs/implementation records/tests/examples/tools. |
| Service preflight | Image built from those verified wheels; isolated Docker-in-Docker verification passed non-root readiness, packaged UI/OpenAPI, actual two-step execution/publication, reuse without duplicate artifacts, retained logs and restart with persistent state. The final hosted candidate is built separately from the exact merged source. |
| Authenticated browser | General journey fifteen groups; filter seven; sidebar four; Contents six; graph eight; manual upload six; name/reference eight. Actual executions and data are separate from explicitly local response/geometry projections. No page errors. |
| No-token browser | General journey fourteen groups and detail workspace nine groups passed. Cleanup six groups passed with actual deletion only in a disposable fixture, including DANGER, manual/pin protection and independent record preservation. |
| Large list workspace | Eleven read-only browser groups passed on existing 98-task example Runs; pagination/cleanup projections stay in the browser and stored user data is unchanged. |
| Visual/preview preservation | Earlier feature receipts record reviewed anonymous desktop/narrow/short layouts. Exported runtime captures are discarded; neutral check receipts omit runtime IDs. The existing user preview and its data remain intact. |

Local preflight artifacts are not publication approval identities. Hosted CI must
pass on the exact submitted/merged tree across its Python/platform matrix, then
the manual candidate workflow builds and preserves the actual wheels/sdists/image
once. Review its provenance, receipts and manifest before authorized tags and
publication. Do not rebuild artifacts during publication or mutate published refs.
No SeaweedFS-specific, physical multi-host, extra browser/platform or maximum-load
qualification is inferred from these checks.

## Feature closure inventory

The Definer's explicit all-workflow closure identifies the following twenty-four
open feature records. Their requested behavior is delivered, individual evidence
is linked from each record, and no required source gap remains. Archive them as
completed with role attribution; preserve original scope/provenance and retain
subsequent publication gates separately.

| Workflow | Outcome | Remaining |
| --- | --- | --- |
| [Deletion and storage cleanup: implementation](../workflows/history/2026-10-25__1767ZJ__deletion-and-storage-cleanup-implementation.md) | Delivered; Definer-authorized completion. | None; publication is a separate gate. |
| [Deletion and storage cleanup: specification](../workflows/history/2026-10-25__1767ZJ__deletion-and-storage-cleanup-specification.md) | Delivered; Definer-authorized completion. | None; publication is a separate gate. |
| [Top-to-bottom pipeline and Run graphs](../workflows/history/2026-10-25__1AQ2RC__top-to-bottom-graphs.md) | Delivered; Definer-authorized completion. | None; publication is a separate gate. |
| [Top-to-bottom graph requirement](../workflows/history/2026-10-25__1ARHHE__top-to-bottom-graph-requirement.md) | Delivered; Definer-authorized completion. | None; publication is a separate gate. |
| [Graph workspace implementation](../workflows/history/2026-10-25__1BE9E3__graph-workspace-implementation.md) | Delivered; Definer-authorized completion. | None; publication is a separate gate. |
| [Graph workspace specification](../workflows/history/2026-10-25__1BE9E3__graph-workspace-specification.md) | Delivered; Definer-authorized completion. | None; publication is a separate gate. |
| [Graph background pan implementation](../workflows/history/2026-10-25__1ZW1AR__graph-background-pan-implementation.md) | Delivered; Definer-authorized completion. | None; publication is a separate gate. |
| [Graph background pan specification](../workflows/history/2026-10-25__1ZW1AR__graph-background-pan-specification.md) | Delivered; Definer-authorized completion. | None; publication is a separate gate. |
| [Grouped sidebar implementation](../workflows/history/2026-10-25__20JZ7N__grouped-sidebar-implementation.md) | Delivered; Definer-authorized completion. | None; publication is a separate gate. |
| [Grouped sidebar specification](../workflows/history/2026-10-25__20JZ7N__grouped-sidebar-specification.md) | Delivered; Definer-authorized completion. | None; publication is a separate gate. |
| [Fixed list layout implementation](../workflows/history/2026-10-25__21WH81__fixed-list-layout-implementation.md) | Delivered; Definer-authorized completion. | None; publication is a separate gate. |
| [Fixed list layout specification](../workflows/history/2026-10-25__21WH81__fixed-list-layout-specification.md) | Delivered; Definer-authorized completion. | None; publication is a separate gate. |
| [Element detail layout implementation](../workflows/history/2026-10-25__26E2FC__element-detail-layout-implementation.md) | Delivered; Definer-authorized completion. | None; publication is a separate gate. |
| [Element detail layout specification](../workflows/history/2026-10-25__26E2FC__element-detail-layout-specification.md) | Delivered; Definer-authorized completion. | None; publication is a separate gate. |
| [Artifact contents implementation](../workflows/history/2026-10-25__272GXP__artifact-contents-implementation.md) | Delivered; Definer-authorized completion. | None; publication is a separate gate. |
| [Artifact contents specification](../workflows/history/2026-10-25__272GXP__artifact-contents-specification.md) | Delivered; Definer-authorized completion. | None; publication is a separate gate. |
| [Artifact upload implementation](../workflows/history/2026-10-25__28MDE8__artifact-upload-implementation.md) | Delivered; Definer-authorized completion. | None; publication is a separate gate. |
| [Artifact upload specification](../workflows/history/2026-10-25__28MDE8__artifact-upload-specification.md) | Delivered; Definer-authorized completion. | None; publication is a separate gate. |
| [Human-readable resource references implementation](../workflows/history/2026-10-26__102NMP__human-readable-references-implementation.md) | Delivered; Definer-authorized completion. | None; publication is a separate gate. |
| [Human-readable resource references specification](../workflows/history/2026-10-26__102NMP__human-readable-references-specification.md) | Delivered; Definer-authorized completion. | None; publication is a separate gate. |
| [Sidebar project context implementation](../workflows/history/2026-10-26__122DY1__sidebar-project-context-implementation.md) | Delivered; Definer-authorized completion. | None; publication is a separate gate. |
| [Sidebar project context specification](../workflows/history/2026-10-26__122DY1__sidebar-project-context-specification.md) | Delivered; Definer-authorized completion. | None; publication is a separate gate. |
| [Filter autocomplete implementation](../workflows/history/2026-10-26__141VAQ__filter-autocomplete-implementation.md) | Delivered; Definer-authorized completion. | None; publication is a separate gate. |
| [Filter autocomplete specification](../workflows/history/2026-10-26__141VAQ__filter-autocomplete-specification.md) | Delivered; Definer-authorized completion. | None; publication is a separate gate. |

The two necessary release/integration preparation records describe bounded local
input preparation and close before proposal submission under the same explicit
Definer authorization. They do not claim that CI, merge or upload already happened.
All closure/review prose precedes the clean release input commit. As in the
existing release-input-order procedure, subsequent mechanical plan calculation,
declaration preparation and strict validation run before PR submission; only
unchanged record archival and generated declaration/plan writes follow that input.

## External gates and disposition

The PR and exact-main CI, manual immutable candidate build, annotated application
and baseline tags, protected publishing environments, all four PyPI file hashes,
GHCR digest/anonymous access and GitHub release assets must be verified externally.
A successful local check or closed workflow is not an upload claim. Publication
uses the preserved artifact bundle and accounts for partial publication without
replacing immutable bytes. Disposable QA services/credentials are removed after
local checks; the user preview remains available.
