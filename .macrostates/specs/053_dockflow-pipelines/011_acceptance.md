# Acceptance and delivery

## Meaning of acceptance

The full initial-release contract is the set of required behaviors in this
package, not the ability to start a container or run one happy-path task.
Structural specification checks do not qualify an implementation.
Before advertising a capability, record exact source commit, application/spec
identities, SDK/IR/API/database/engine/image versions, Python/OS/architecture and test
results for the combination. Preserve failure evidence and known limitations.

A smaller milestone may be released only with an accurate capabilities manifest,
clear limitations and rejection of unsupported semantics. It must not claim
complete initial-profile support. Package installation/help and actual execution
have separate qualification surfaces.

## Required scenarios

| ID | Scenario and observable evidence |
| --- | --- |
| A01 | Built CLI/Pipelines wheels install outside the workspace, registration/help/version work offline, no service starts, no workspace/path dependencies leak. |
| A02 | One consuming repository's unchanged compiled KFP fixture/images execute on reference KFP, direct Dockflow and the Compose service; declared outputs/types/branch behavior agree. |
| A03 | Compiled primitive/root/nested graph loading uses no consumer Python imports; invalid schemas, tags, cycles, placeholders and unsupported executable fields reject before dispatch. |
| A04 | Parameters preserve strings/bools/safe integers/finite doubles/JSON types and defaults; no shell injection, float rounding or silent type coercion. |
| A05 | File/directory, empty-directory and metadata-only artifact outputs preserve type/metadata/contents; named bindings and executor placeholders resolve correctly. |
| A06 | External reference registration, managed import and standard importer provenance remain distinct; mutable source changes are detected, and file paths are evaluated in the executor namespace. |
| A07 | Filesystem and MinIO profiles materialize inputs and publish complete outputs; missing/corrupt/partial outputs never become reusable results. |
| A08 | Crash injection before/during payload transfer, output-set commit and SQL projection reconciles idempotently with stable IDs, correct stop/commit ordering and no duplicated computation. |
| A09 | Repeated Runs reuse equivalent task results; changed implementation/image/input/parameter misses; downstream-only changes preserve upstream reuse; explicit KFP disablement wins. |
| A10 | global/keyed/run/none scope, missing keys, nondeterministic resolver behavior, stale unavailable candidates and deterministic producer selection match the reuse contract. |
| A11 | Partial static-graph selection resolves omitted prerequisites, records manual/historical choices and protects pins; unresolved/ambiguous/conditional-boundary selections reject. |
| A12 | Reference/managed paths, URI prefixes, symlinks, special files and forbidden nested paths are handled as specified; cleanup cannot delete external inputs, source code or protected artifacts. |
| A12a | An explicit filesystem managed_root stores imports and outputs directly below that directory; default/root layouts remain compatible. Relative paths, environment precedence, conflicting/S3 roots, overlap rejection, managed-source admission, backup/restore and legacy backups are exercised. Reference registration creates no payload folder. |
| A13 | Competing CLI/service writers fail before control/index mutation, including same-host bind-mount aliases; stable SQLite database inode or pinned PostgreSQL session and fresh owner UUID/hostname/PID/mode/project/time/endpoint diagnostics preserve exclusive ownership. One active Run/attempt, bounded durable FIFO queue and full queue rejection survive restart. |
| A14 | Ctrl+C, cancellation, timeout, abrupt process loss and service shutdown retain evidence, confirm container stops and block replacement while execution is uncertain. |
| A15 | Retry default zero and admitted bounded retries preserve attempt history and isolated writes; unsafe external effects and unchanged validation failures do not auto-repeat. |
| A16 | Conditional import/acquire and OneOf converge correctly; skipped tasks have no fabricated attempts/results; unsupported loops/platform/GPU requirements reject. |
| A17 | CLI/API produce equivalent core results, explicit endpoint/local precedence and no client path/server-config confusion. Help/client-only operations need no runtime extras. |
| A18 | Native API models/error codes/pagination/idempotency/log cursors enforce the documented contract; client disconnect does not cancel accepted work. |
| A19 | Each advertised KFP 2.17 client method passes actual request/schema/error/status/filter tests; cancellation uses truthful CANCELED status despite upstream waiter limitations. |
| A20 | metadata check/rebuild and offline replacement, backup/restore, availability transitions and retained history reconstruct the same IDs/lineage without pretending missing bytes exist. |
| A21 | Same compiled image references work under admitted pull policies; missing images, registry trust, inner/outer networking and actual image digest/platform recording are verified. |
| A22 | Unmodified generic service image accepts arbitrary compatible consuming definitions through configured read-only mounts or KFP upload, with separately registry-pushed images; health/readiness, state volumes and ordinary shutdown preserve data, without a project-specific long-running service. |
| A23 | Every advertised Python/platform/artifact combination passes its required native checks; runtime images have reproducible evidence and no emulation-only claim. |
| A24 | Logging, redacted configuration and its file/environment/option/default/derived origins, provider credentials and error output meet their contracts; inspect newly admitted Run snapshots through CLI/API, retain their admission-time origins after settings change, and read older records without inventing missing provenance; secrets do not enter manifests, cache signatures, task environment or exported logs by accident. |
| A25 | Actual pinned KFP SDK uploads a raw compiled YAML/JSON pipeline and a named new version, inspects embedded components, then executes by returned IDs/default; original bytes, names, associations and defaults survive refresh, restart and metadata rebuild. |
| A26 | Upload bounds, malformed/duplicate multipart/query fields, UTF-8/syntax errors, unsupported archives/URLs/namespaces/features, duplicate names, and configuration/API ownership conflicts reject without usable partial catalog entries; same bytes in different pipeline/version associations retain distinct immutable IDs and historical Runs. |
| A27 | Inject failure before/after durable registration and during index projection; pipeline/version/component membership and default recover together, accepted IDs remain inspectable, and no dangling default, duplicate entry or changed admitted Run appears. |
| A28 | Normal release and abrupt coordinator death permit a new acquisition with a fresh owner UUID while retaining the lock inode. A surviving task container, retained nonterminal/queued Run or unresolved/reconciliation-required Run/attempt still prevents new direct Run acceptance until explicit service reconciliation/draining; no replacement or implicit rerun occurs. Held locks remain exclusive despite stale/legacy/truncated/malformed/oversized diagnostic contents or another PID namespace. Busy errors expose only validated structured owner fields and an actionable endpoint; unsupported locking/I/O failures fail closed with a distinct diagnostic. No stale-age/PID/hostname takeover or network-filesystem guarantee is implied. |
| A29 | Packaged browser UI and API explorer load without CDN/network assets from installed distributions and the generic service. Actual browser journeys cover no-token and bearer authentication, memory-only sign-out, public shell/protected records, exact filters/pagination, pipeline/version upload and configuration-origin restrictions, typed create/clone/validate/idempotent Run submission, confirmed cancellation, nested graphs and task/attempt links, cursor-bounded logs during execution with manual browser refresh, scalar comparison with absent values, artifact import/register/pins and actual producer/consumer lineage. Verify stale-response/polling behavior, empty/error/recovery states, text-only rendering of XSS-shaped content, Origin rejection, desktop/narrow layout and keyboard navigation. Native pipeline/task/attempt/lineage queries and generated OpenAPI filters/models match observed responses. Record fixture versus actual execution coverage, browser/platform and limitations separately. |
| A30 | Foreground local run displays persisted stdout/stderr on stderr by default, including component traces and failed-task diagnostics. Human none/trimmed/full modes keep Run identity/state/key/error, bound verbose generated metadata only in trimmed mode, and leave ordinary component messages intact unless separately hidden. Independent Dockflow/component visibility switches cover all four combinations, task separators/stream headings, partial-line flushing, host warnings/errors and failure exit status. Hiding Dockflow output also hides recognized container-side KFP INFO lookup/loading/input-JSON/output-file messages in every detail mode, across arbitrary chunks; ordinary user logs sharing the KFP formatter, warnings/errors, unknown messages and malformed/oversized metadata remain visible when component output is enabled. Both disabled silence normal successful human output. Machine JSON remains complete and isolated on stdout. No display option changes retained logs, artifacts, Run records, execution identity or API submissions. Qualify successful/failing Docker tasks, arbitrary user JSON, incomplete executor metadata, a disconnected terminal, offline option validation and scoped logger restoration. |
| A31 | Flushed stdout/stderr is durable and visible before a real task container exits, both in direct execution and through service-worker log pages. Silent/noisy tasks remain cancellable; final tails, split UTF-8 and stream attribution survive capture. A disconnected attach can recover from verified retained logs; changed/truncated prefixes fail explicitly. Recovery appends unsaved tails once. Streamed metadata respects none/trimmed/full presentation across chunk boundaries. Terminal colors, redirected/NO_COLOR plain text and browser color stripping leave durable records unchanged. |

Golden fixtures cover canonical digest encoding, directory inventories, definition
snapshots, artifact descriptors, output-set commits, recovery events, native
requests/responses, multipart upload boundaries and KFP wire/state mappings. Include corrupted and truncated
records, not only successful serialization round trips. Tests must exercise the
observable contract; avoid tests that merely duplicate implementation structure.

## Incremental delivery

1. Prove compiled KFP loading, DockerRunner adaptation, URI/path binding,
   confirmed exit/stop handling, SQLite/PostgreSQL writes and dependency installation.
2. Deliver direct execution of a static pipeline with durable artifacts,
   manifests/logs, ownership, inspection and failure recovery.
3. Add verified reuse, scopes, manual historical bindings, partial static
   execution, pins and safe cleanup/rebuild.
4. Complete admitted importer/conditional/retry/resource semantics and persistent
   service queue, native API and reference Compose image.
5. Qualify the selected KFP REST/client subset, upload/version catalog lifecycle
   and end-to-end portability with the unmodified generic service image.
6. Deliver and validate the first-party browser interface and offline API explorer
   against the same persistent service/API, with truthful feature and log limits.
7. Qualify built distributions/images on advertised platforms, then apply shared
   release/publishing approval and provenance gates.

The order may be adjusted without weakening acceptance. A failed adapter or
platform spike changes implementation/qualification plans; it does not silently
remove product semantics. A material contract change returns to specification
review. Record implementation coverage and completed qualification in
[implementation records](../../implementation/main.md), separately from these
standing acceptance requirements.

## External publication integration coverage

Compile a wrapper-produced URI through a standard typed importer, load the same
IR in Dockflow and verify named dependencies/types. Qualify filesystem and S3
access, unchanged typed URIs on reuse, explicit destination/context changes,
external ownership and importer lineage. Verify that normal managed outputs and
external publications coexist without duplicate durable copies or managed-output
URI overrides. Provider-specific publication integrity is qualified separately
by its library; the generic Pipelines importer contract remains independent.

## Managed output layout regression coverage

Verify filesystem and S3 pipeline/run/task/UUID/output destinations for files and
directories, shared UUIDs within a task attempt, distinct retry destinations,
metadata-only outputs, and original-URI reuse/import. Preserve user filenames
including artifact.json inside directory payloads. Reject path traversal and
destination symlinks/collisions. Exercise backup/restore of the new layout and
legacy descriptor-driven reads without relocating identities. Qualify actual
Docker execution and an example training/inference workflow using recorded URIs.

## Distributed cache extension

A32 requires the independent-process backend conformance, contention, crash,
stale-owner, storage, retry and migration scenarios in
[Cache coordination](014_cache-coordination.md#17-test-requirements).
Real PostgreSQL evidence is required before claiming shared-host support.

## Database-authoritative state acceptance

A33 requires SQLite and real PostgreSQL tests for complete retained Run history,
exact definition bytes, log ordering, artifact descriptors/lineage, queue and
idempotency across fresh isolated environments with different local state roots.
No PostgreSQL history may depend on local JSON/MLMD files. Validate project
isolation, numeric KFP aliases, SQL rollback of partial registration/output-set
projections, process contention/death, session loss and stale mutation refusal.
Portable backup/export and empty-project restore must preserve identities on both
backends; unknown/corrupt schemas and legacy file history fail explicitly.
A new daemon cannot resolve an unfinished attempt from another daemon. Recovery
retires stopped container handles before dispatch so stale workers cannot start
them after reconciliation. Database ownership does not promise exactly-once
component side effects. No historical file migration is required.


### A34: Unified database

Exercise SQLite and real PostgreSQL through the shared adapter. Verify both
initialization orders create one complete versioned schema, cache operations
progress with state ownership held, restart retains both domains, alternate
cache connections are rejected, and unknown/incomplete schemas fail closed.
Export and restore one project with all cache namespaces and fences, excluding
other projects, preserving cache-only bytes and store identity. Existing cache
conformance and execution/recovery suites remain required.


### A35: Concurrent PostgreSQL Runs

Exercise independent PostgreSQL processes in one project, including simultaneous
admission, idempotency, queue-capacity enforcement, different concurrent Runs and
competing claims for one Run. Verify database-time expiry, renewal, increasing
fences, stale mutation/publication rejection, cancellation from another process,
crashed-owner recovery and live-Run isolation. Preserve correct-daemon checks and
refuse unconfirmed replacement execution. Maintenance excludes all coordinators
and cache transactions. Run the same local SQLite regressions to preserve one
owner/Run behavior. Test actual direct and service worker paths and complete
artifact/provenance outcomes; protocol-only tests do not establish runtime support.

A35 also exercises committed-cache reuse while its producing Run is still live:
the consumer retains complete provenance without altering the producer lifecycle.
Concurrent same-key execution must produce one actual computation and a waiting
consumer; later reuse must preserve original producer and artifact identities.

### A36. SQL artifact bookkeeping

Publish and reuse filesystem/S3 artifacts with SQLite and PostgreSQL. Confirm
reservations, completion manifests and recovery descriptors persist only in the
unified database; storage retains payloads and its identity marker. Test retries,
partial transfers, concurrent/conflicting writers and stale execution fences.
Back up/restore publication records and both journal-backed and cache-only bytes.
Standalone Artifacts shares the same adapter without importing Pipelines or CLI.

### A37. Domain persistence cleanup

Exercise direct domain repositories on SQLite and PostgreSQL with numeric event
sequences, a single resource projection, exact source bytes, output commitments,
cache observations and retained log snapshots. Verify atomic rollback of events,
counters and projections, corruption/orphan detection, projection rebuild and
stable KFP aliases. Verify read-only checks, fenced execution, service recovery,
cache reuse and project backup/restore without virtual filesystem metadata keys
or compatibility import shims. Real payload/executor/backup files remain supported.

### A38. Conformance corrections and selective repositories

Inject queue-read, periodic-recovery and worker-start failures and verify dead
schedulers revoke readiness/admission while retaining accepted work. Exercise
A/B/A source rollback through direct and remote named submissions. Execute queued
Runs after restart with different coordinator settings and retain admitted limits;
refuse incompatible mounts/caps explicitly. Reconcile crashes before container
creation, after creation and after output commitment with consistent Run/Task/
Attempt outcomes. Reject malformed scalar IR before persistent acceptance.

Inject corruption and orphan rows into every derived domain repository and repair
them through rebuild without losing stable aliases. Verify stable bounded source
capture with symlinks, nonregular files, oversize data and observed mutation.
Exercise indexed SQL filtering/paging, queue selection and log ranges with unrelated
large history, both database backends, stable tokens and backup/rebuild consistency.
