# Distributed artifact-cache coordination

This document owns Dockflow cache coordination, registry persistence, lease and
retry semantics, immutable cache publication, configuration and conformance.
Execution journals and their database owner remain governed by [Execution](005_execution-and-lifecycle.md).

## 1. Objective

Implement persistent coordination of artifact production and reuse across concurrent Dockflow runs. When several runs need the same cacheable artifact, Dockflow must atomically decide whether each run should reuse an existing artifact, become its producer, wait for another producer, or receive a bounded failure.

Implement this in Dockflow's cache, execution, configuration, persistence, and diagnostic code. The names in this specification describe responsibilities; adapt them to the actual repository structure after inspecting it. Do not assume that any proposed module or command already exists.

“MUST” identifies an acceptance requirement. “SHOULD” identifies a default that may be changed with a documented reason and equivalent correctness. All requirements apply to both backends unless explicitly qualified.

## 2. Problem

Dockflow already reuses cached artifacts. A simple cache-existence check does not coordinate work that is still running:

1. Run A needs artifact K, sees no usable artifact, and starts producing it.
2. Run B needs K before A finishes and also sees no usable artifact.
3. Without coordination, B starts duplicate work or tries to consume incomplete output.

Checking for a file and then creating a lock is another race unless acquisition is atomic. Process-local locks do not cover independent processes or hosts. A persistent “running” flag becomes stale after a crash. A lease alone does not prevent an old producer from completing after another producer has taken over.

The implementation must handle concurrent starts, crashes, pauses, lost connectivity, retries, partial writes, corrupt or missing artifacts, cancellation, and process restarts. A failed producer attempt must not be confused with an invalid artifact.

## 3. Proposed solution

Introduce a persistent cache registry as Dockflow's authority for coordination and published artifact metadata. For each scoped cache key:

- A short database transaction performs **atomic claim-or-reuse**.
- A usable published artifact is returned for reuse.
- Otherwise, one eligible requester receives a producer attempt, a lease, and a monotonically increasing fencing token.
- Other requesters wait, periodically rechecking persistent state.
- The producer writes to an isolated attempt location, validates a complete immutable artifact, and conditionally publishes its descriptor.
- Expired attempts can be replaced. Old producers cannot publish, renew, invalidate, or modify the replacement's state.
- Failure and retry eligibility are persisted so concurrent waiters share one retry budget.

Support SQLite for concurrent processes on one host and PostgreSQL for workers sharing a registry across hosts. Artifact bytes remain managed by Dockflow's storage layer. Registry sharing alone does not make artifact bytes accessible across hosts.

### Example

```text
Run A: resolve K -> PRODUCE(attempt A1, fence 1)
Run B: resolve K -> WAIT(attempt A1)
Run C: resolve K -> WAIT(attempt A1)
A1: compute -> validate -> finalize immutable bytes -> conditional publish
Run B: resolve K -> REUSE(artifact R1)
Run C: resolve K -> REUSE(artifact R1)

If A1 expires instead:
Run B: resolve K -> record A1 expired; respect retry backoff
Run B or C, when eligible: -> PRODUCE(attempt A2, fence 2)
A1 resumes: publish(fence 1) -> OWNERSHIP_LOST
A2 publishes R2; remaining runs reuse R2
```

## 4. Correctness guarantees and boundaries

The implementation MUST preserve these invariants:

1. There is one coordination entry for each `(scope_id, cache_key)`.
2. At most one attempt is the registry-authorized, unexpired producer for that entry.
3. New production starts only after a committed claim. There is no check-then-act gap.
4. Consumers never receive staging paths or partially published output.
5. A published descriptor references a complete, validated, immutable output set.
6. Every owner mutation checks entry identity, attempt identity, fencing token, active state, and lease validity in the database transaction.
7. A superseded producer cannot change a newer attempt or its published artifact, including through storage writes.
8. Producer failure, cancellation, or lease expiry does not itself invalidate an already valid artifact.
9. Waiters eventually reuse, claim eligible work, time out, cancel, or receive a terminal error; they never wait indefinitely by default.
10. Crashes do not require manual removal of “running” flags.
11. Registry, artifact validity, and retry decisions survive restarts.
12. Equivalent actions and error classifications have the same observable semantics on both backends.

This is an at-most-one-current-owner guarantee, not exactly-once execution. A paused producer may still consume resources after its lease expires while its replacement runs. Fencing and isolated immutable storage make its late result harmless. Cache coordination does not provide exactly-once side effects inside a step; only eligible cacheable steps may use this mechanism.

Liveness assumes the registry and artifact storage eventually become available and at least one requester remains active. During an outage, bounded errors are acceptable; unauthorized production and publication are not.

## 5. Identity, keys, and scopes

### 5.1 Cache identity

Use a unique composite identity `(scope_id, cache_key)`. Generate the key with a versioned, deterministic canonical representation and a collision-resistant digest, such as SHA-256:

```text
cache_key = digest(canonical_encode({
  key_schema_version,
  step_implementation_identity,
  resolved_execution_environment_identity,
  normalized_parameters,
  declared_input_content_digests,
  upstream_output_manifest_digests,
  relevant_declared_environment,
  output_contract_version,
  validation_contract_version,
  explicit_cache_salt
}))
```

MUST:

- Include every input known to affect output, including resolved immutable execution identities and relevant platform differences.
- Define canonical map ordering, type handling, defaults, numeric encoding, and path treatment. Preserve order where semantically meaningful.
- Use input contents or immutable content identities, rather than modification times or mutable labels alone.
- Include the complete expected output set and validation contract directly or through a versioned contract identity.
- Exclude run IDs, attempt IDs, timestamps, and worker IDs from normal reuse keys.
- Avoid storing secrets in key material, manifests, logs, or error text. If a secret affects output, use a scoped, stable keyed fingerprint or explicit nonsecret revision; otherwise disable caching for that step.
- Prevent accidental cross-project reuse through an explicit namespace. A project identifier must remain stable across checkout paths and workers.
- Treat a key schema change as a separate namespace of keys; never silently reinterpret old entries.

If a step is nondeterministic, has undeclared inputs, or cannot safely reuse outputs, require an explicit cache policy or mark it uncacheable. Uncacheable execution does not publish reusable results.

### 5.2 Scope

Support:

| Scope | Registry and storage boundary | Intended use |
| --- | --- | --- |
| Local project | Stable project namespace, one local SQLite file, local artifact root | Independent processes on one host |
| Shared project | Stable project namespace in a shared PostgreSQL registry and a commonly accessible Dockflow artifact store | Workers on different hosts |
| Explicit isolated namespace | Additional configured namespace or salt | Deliberately separate caches |

Workers only coordinate if they use the same registry, scope identity, key schema, and compatible storage configuration. Reject inconsistent scope-level policy or storage identities at startup; do not silently partition a requested shared cache. Different machine-local SQLite files are different coordination domains.

## 6. Persistent data model

Use a versioned schema, explicit constraints, and backend-specific type mappings.
The initial unified format starts fresh; legacy split databases are rejected and
require no migration. Later schema upgrades require explicit offline tooling. Persist UTC timestamps with sufficient subsecond precision. Store digests as stable binary or textual values. The following is a logical schema, not a required ORM design.

### 6.1 `cache_entries`

| Field | Requirement |
| --- | --- |
| `scope_id`, `cache_key` | Composite primary key or unique constraint |
| `key_schema_version`, `key_metadata` | Version and sanitized diagnostic provenance |
| `generation` | Nonnegative monotonic fencing counter; increment for every claim and explicit revocation |
| `current_attempt_id` | Nullable pointer to the current producer attempt |
| `published_artifact_id` | Nullable pointer to the selected published artifact |
| `episode_id`, `attempts_started` | Persistent retry episode and attempts charged to it |
| `next_retry_at` | Earliest permitted next claim, using registry time |
| `blocked_reason` | Nullable terminal reason for the current episode |
| `policy_fingerprint` | Identifies the scope's effective production/retry policy |
| `revision`, `created_at`, `updated_at` | Monotonic change revision and diagnostic timestamps |

An entry is a coordination record, not an artifact status. Do not use a single `RUNNING/SUCCESS/FAILED` column to represent both production and artifact usability. A displayed summary may be derived from separate fields.

### 6.2 `producer_attempts`

| Field | Requirement |
| --- | --- |
| `attempt_id` | Globally unique, immutable identifier |
| `scope_id`, `cache_key`, `episode_id` | Entry and retry-episode references |
| `fencing_token` | Generation allocated by the claim |
| `owner_id`, `run_id`, `step_id` | Process-instance owner and execution provenance |
| `claim_request_id` | Unique idempotency identifier for claim recovery |
| `state` | `RUNNING`, `VALIDATING`, `SUCCEEDED`, `FAILED`, `CANCELLED`, or `EXPIRED` |
| `lease_expires_at`, `heartbeat_at` | Authoritative ownership deadlines |
| `started_at`, `finished_at` | Attempt lifecycle timestamps |
| `staging_locator`, `artifact_id` | Attempt-isolated location and optional published result |
| `error_code`, `error_summary`, `retryable` | Sanitized structured failure information |

`RUNNING` and `VALIDATING` are active states. Use a unique constraint on entry plus fencing token. Where supported, use a partial unique index to prevent multiple active attempt rows for one entry; expire the previous attempt before inserting its successor in the same transaction. Constraints supplement the ownership protocol.

Terminal attempts are immutable except for explicitly permitted audit annotations. Worker restarts use a new owner instance identity and never inherit authority merely by reusing a run ID.

### 6.3 `artifacts`

| Field | Requirement |
| --- | --- |
| `artifact_id` | Immutable, unique output-set identifier |
| `scope_id`, `cache_key`, `producer_attempt_id` | Identity and provenance |
| `state` | `AVAILABLE` or `INVALID` for the initial implementation |
| `storage_identity`, `immutable_locator` | Storage domain and immutable output location |
| `manifest`, `manifest_digest` | Versioned manifest and its digest |
| `validation_version`, `validated_at` | Contract and successful validation metadata |
| `published_at`, `valid_until` | Publication time and optional cache freshness deadline |
| `invalidated_at`, `invalidation_reason` | Separate validity history |

The manifest MUST identify the complete output set, relative paths, output types, sizes, checksums, and required metadata. A directory or multiple outputs form one publication unit. Store no absolute producer-local paths as portable shared artifact locations.

### 6.4 Relationships and invariants

Enforce at most one published artifact record per producer attempt, and enforce uniqueness of claim request identifiers within the registry. A replay must match the original entry, owner, and request payload; mismatched reuse of an identifier is an error. Use foreign keys and checks where practical. Validate cross-row invariants inside the locked transaction. Published pointers must reference artifacts for the same entry; an attempt must belong to the entry that owns it. Add indexes for active lease expiry, entry attempt history, retry eligibility, and artifact lookup.

Do not delete coordination rows in a way that resets fencing generations. Retain tombstones or a durable high-water mark if compaction is later added. Do not reuse attempt or artifact identifiers.

## 7. Two independent state machines

### 7.1 Producer lifecycle

```text
atomic claim -> RUNNING -> VALIDATING -> SUCCEEDED
                  |           |
                  +-----------+-> FAILED
                  +-----------+-> CANCELLED
                  +-----------+-> EXPIRED
```

Expiry may be discovered lazily by the next requester; a dedicated sweeper is optional. Terminalization is conditional and idempotent. A terminal or superseded attempt cannot return to an active state.

### 7.2 Artifact lifecycle

```text
private staged bytes -> complete validated immutable bytes
    -> fenced registry publication as AVAILABLE
AVAILABLE -> INVALID      [explicit invalidation or confirmed corruption/loss]
AVAILABLE -> freshness expiry for new resolutions [valid_until]
```

Unpublished bytes have no reusable artifact status. A successful exit code, an existing directory, or an attempt marked successful without a committed descriptor is insufficient for reuse.

A failed attempt does not prove any older artifact invalid. Likewise, successful historical production does not prove that its bytes still exist or meet the current contract. Evaluate artifact validity independently.

For the initial implementation, normal resolution reuses a valid artifact and does not start a refresh alongside it. Rebuilding a fresh artifact requires explicit invalidation first or a distinct key/salt. Background refresh is outside this implementation's required scope.

## 8. Atomic claim-or-reuse

Provide one internal operation with an explicit result union:

```text
resolve_or_claim(identity, owner, claim_request_id, requester_deadline)
  -> REUSE(artifact_descriptor, entry_revision)
   | PRODUCE(attempt_id, owner_id, fencing_token, lease_expires_at)
   | WAIT(observed_attempt_id?, entry_revision, reason, recheck_after)
   | BLOCKED(error_code, episode_id, last_attempt_summary)
   | ERROR(error_code, retryable)
```

`WAIT` covers an active producer and a persisted retry cooldown. `REUSE` means the registry considers the descriptor eligible; byte verification during materialization must still succeed before the step is reported as a cache hit.

### 8.1 Required transaction protocol

```text
begin short write-capable transaction
  ensure the entry exists using its unique identity
  exclusively lock the entry / acquire equivalent write serialization
  read current registry time after acquiring the lock

  recover an existing claim_request_id, if this is a replay:
    return its current ownership outcome; do not allocate another attempt

  if selected artifact is AVAILABLE, contract-compatible and fresh:
    return REUSE(descriptor)

  if selected artifact has just expired:
    detach it for new resolutions and open one new retry episode
    keep immutable artifact history and bytes

  if current attempt is active and its lease is unexpired:
    return WAIT(active producer)

  if current attempt is active but expired:
    mark it EXPIRED, clear current owner pointer, record retry eligibility
    preserve the attempt charged at claim time; do not charge it twice

  if current episode is blocked or its attempt budget is exhausted:
    persist a terminal blocked reason if not already recorded
    return BLOCKED

  if registry time is earlier than next_retry_at:
    return WAIT(retry cooldown)

  increment generation and attempts_started
  insert a fresh RUNNING attempt with the new fence and lease
  set current_attempt_id; increment entry revision
  return PRODUCE(ownership)
commit
```

Results are delivered only after a successful commit. Rollback grants no ownership. When a normal entry is first created, initialize exactly one retry episode. Rechecking an unusable artifact must not repeatedly reset that episode.

For every returned result, document its transaction linearization point. Never hold a database transaction open while computing, validating, hashing, transferring bytes, or waiting. There must be no advisory read followed by an unguarded claim.

### 8.2 Claim idempotency and ambiguous commit

Generate `claim_request_id` before submitting the claim and retain it while recovering that request. If the connection fails around commit, query/replay using the same identifier and owner identity. Start work only after confirming a committed, still-current, unexpired claim.

Replaying a successfully published claim returns its committed artifact outcome without reselecting an invalidated or replaced artifact. Replaying an expired or superseded unpublished claim returns ownership lost; it never resurrects the attempt. A deliberate later claim uses a new request identifier. Recovering an uncertain database transaction must not consume another production attempt.

### 8.3 Other internal operations

Provide equivalents of:

- `renew_lease(ownership)`
- `begin_validation(ownership)`
- `publish(ownership, immutable_descriptor)`
- `finish_failed(ownership, error)`
- `finish_cancelled(ownership, reason)`
- `inspect(identity)`
- `invalidate(identity, expected_artifact_id, reason)`
- `reset_retry_episode(identity, expected_revision, reason)`

Keep these internal to Dockflow. All mutations use the same per-entry serialization and lock ordering. Pass the full ownership tuple rather than only a cache key.

## 9. Leases, heartbeats, and fencing

### 9.1 Lease semantics

Suggested defaults:

| Setting | Default |
| --- | --- |
| Producer lease | 120 seconds |
| Heartbeat interval | 30 seconds |
| Initial waiter poll interval | 250 milliseconds |
| Maximum waiter poll interval | 5 seconds |
| Default requester wait timeout | 30 minutes |
| Maximum attempts per retry episode | 3, including the first |
| Production retry backoff | Exponential from 1 second, capped at 30 seconds, with persisted jitter |

Validate that heartbeat intervals and transaction timeouts leave room for renewal before lease expiry. Timing settings must be configurable and documented; correctness must not depend on these particular defaults.

- The database decides lease expiry. A lease is valid only when `lease_expires_at > registry_now`.
- Heartbeats run independently of a long-running computation and continue through validation and storage finalization.
- Renewal requires the complete matching ownership tuple, active state, and an unexpired lease. An expired lease cannot be revived.
- Read authoritative current time after acquiring the entry lock. PostgreSQL must use a current clock value rather than a transaction-start timestamp for this decision.
- Return remaining lease information. Client monotonic clocks govern local wait budgets and conservative self-stop deadlines, not shared ownership decisions.
- On unconfirmed renewals, retry within the known safe ownership window; stop publishing and stop or cancel work when that window is exhausted. Account conservatively for request latency and a safety margin.
- Database errors do not mean “lease is free.” There is no automatic uncoordinated fallback.

Clock jumps may cause early takeover or delayed recovery. Fencing must preserve publication safety regardless; document the database clock assumption and test large clock changes. Heartbeat timers must not depend on a worker's wall-clock setting.

### 9.2 Fenced mutations

For renewal, state transitions, failure reporting, and publication, require all of:

```text
entry.current_attempt_id == supplied.attempt_id
entry.generation == supplied.fencing_token
attempt.owner_id == supplied.owner_id
attempt.fencing_token == supplied.fencing_token
attempt.state in {RUNNING, VALIDATING}, as appropriate
attempt.lease_expires_at > registry_now
```

Evaluate under the entry lock and recheck in the conditional write where appropriate. Zero matched rows returns `OWNERSHIP_LOST`; it never falls back to an unconditional update. An expiry observer may mark the old attempt `EXPIRED` without pretending to be its owner, under the same serialized protocol.

A lost producer may write only to its private attempt location. It must not overwrite a canonical key directory, update a shared “latest” file, delete another attempt's bytes, or change registry pointers. The fence protects metadata; immutable attempt-specific storage protects bytes.

## 10. Produce, validate, finalize, publish

Implement this order:

1. Obtain a confirmed `PRODUCE` result before starting cacheable execution.
2. Create an attempt-specific staging location under a Dockflow-controlled root. Avoid path traversal and unsafe symlink resolution.
3. Execute the step with outputs confined to that location and heartbeat independently.
4. Enter `VALIDATING` through a fenced mutation.
5. Validate the complete output contract: required paths, types, format or schema checks, sizes, and content digests. Reject missing or unexpected outputs according to the contract.
6. Seal bytes against mutation by the producer workload. Compute the final manifest over the sealed content; prevent modification between validation and publication.
7. Finalize to a unique immutable location containing the attempt/artifact identity. Ensure required bytes and metadata are durably written according to the configured storage contract. The storage layer must guarantee that participating workers can read the finalized immutable output before its descriptor becomes eligible for publication.
8. In a short registry transaction, lock the entry, check ownership and fresh lease time, insert the `AVAILABLE` descriptor, mark the attempt `SUCCEEDED`, select the artifact pointer, clear current ownership, and update the revision atomically.
9. Commit before reporting success or signaling waiters. The producing run may materialize the same published descriptor.

On a local filesystem, a same-filesystem atomic rename can expose a finalized directory; ensure required file and directory durability and never replace another attempt's directory. Where a storage implementation cannot atomically finalize a directory, use immutable files plus a complete verified manifest. Consumers discover bytes only through the committed registry descriptor.

The registry and artifact storage are not one transaction. Safety comes from finalizing immutable bytes first and publishing their pointer second. Do not attempt to roll back a committed publication by deleting its bytes.

### 10.1 Publication idempotency

Repeating publication of the same already-successful attempt and identical descriptor returns its committed result, including after an uncertain response. This read-only acknowledgment does not require a still-live producer lease. A different descriptor for the same attempt is a conflict. A historical successful artifact can be acknowledged without reselecting it after invalidation or later replacement.

### 10.2 Crash windows

| Crash point | Required outcome |
| --- | --- |
| Before claim commit | No ownership or execution |
| After claim commit, before execution | Lease expires; a later requester can retry |
| During staging or validation | No reusable artifact; replacement follows expiry/backoff |
| After immutable finalization, before publication | Unreferenced bytes; not a cache hit |
| After publication commit, before acknowledgment | Replay discovers committed publication; no duplicate attempt |
| Old producer resumes after takeover | Its owner mutations fail; private bytes remain unreferenced |

## 11. Reuse, validation, and invalidation

Before reporting a cache hit or making outputs available to a dependent step:

- Confirm the descriptor's key, scope, manifest version, validation contract, storage identity, and freshness eligibility.
- Materialize into a private consumer location or use a storage primitive that guarantees an immutable verified view.
- Verify the complete manifest and digests. Do not expose partly copied outputs as a successful hit.
- Preserve published bytes as read-only; dependent steps must not modify shared cache contents.

A confirmed missing or corrupt artifact is conditionally invalidated by its exact `artifact_id`. Clear the selected pointer only if it still points to that artifact. A delayed report about an older artifact must never invalidate a newer one. Open one new retry episode only when the selected artifact transitions from usable to unusable, under the entry lock.

A timeout, permission error, or temporary storage outage is an access failure, not proof of corruption. Retry access within the requester's budget or return `ARTIFACT_UNAVAILABLE`; do not automatically invalidate or start duplicate production.

An explicit administrative invalidation records its reason, conditionally invalidates the selected artifact, revokes any current producer by advancing the generation and terminalizing that attempt, and opens one new episode in a single transaction. A stale expected artifact/revision returns a conflict. Never blindly clear whatever is current.

Freshness expiry affects new resolutions. A consumer that already selected and verified an immutable snapshot may complete with it even if its freshness deadline passes during consumption. Lease lifetime and artifact freshness lifetime are independent.

## 12. Waiting, failure, cancellation, and retries

### 12.1 Waiters

Use a deadline-aware resolution loop. Poll with exponential backoff and jitter, capped by the next known lease/retry event and the requester's remaining budget. A heartbeat-only revision need not reset the polling backoff.

Optional change notifications are wake-up hints only. Always reread persistent state after waking, reconnecting, or timing out a notification wait. Lost notifications must not block progress. Never hold a transaction, connection, execution slot, or producer lease merely to wait for another producer.

Waiters follow the entry rather than a single attempt ID so they survive producer replacement. If several waiters become eligible simultaneously, atomic claim decides one winner. A wait timeout fails that request with `CACHE_WAIT_TIMEOUT`; it does not steal a live lease or cancel the producer.

Within one pipeline, resolve upstream dependencies before claiming downstream production. Do not hold producer leases while waiting for inputs that another claimed step must generate. Preserve dependency-cycle detection and prevent a step from waiting on its own unresolved cache entry.

### 12.2 Shared retry episodes

An episode is one bounded effort to obtain a usable artifact. Persist the attempt limit, policy identity, attempt count, cooldown, and terminal reason. Charge an attempt once when its claim commits, including attempts later cancelled or expired.

- A retryable failure/expiry schedules one persisted backoff deadline. All waiters observe the same value.
- When fewer than the maximum attempts have been started, one requester may claim after cooldown.
- When the maximum is reached, terminalize the last attempt and block the episode.
- A nonretryable production or validation failure blocks the episode immediately.
- Successful publication resolves the episode. Later loss, expiry, or explicit invalidation of that selected artifact opens a new episode exactly once.
- Restarting a requester, changing its wait budget, or arriving after a failure does not reset the shared attempt count.
- An explicit retry-reset operation may open a new episode only when there is no live producer and no reusable artifact; use an expected revision and log the reason.

Requesters may choose whether to keep waiting for eligible retries or fail promptly after observing a failed attempt. This changes their own behavior, not the shared budget or another producer's authority. Budget and production policy are scope-level settings; reject conflicting worker policies rather than accepting whichever requester arrives last.

### 12.3 Failure categories

| Category | Required handling |
| --- | --- |
| Retryable execution failure | Fenced attempt failure, shared backoff, bounded retry |
| Deterministic contract/validation failure | Default nonretryable; preserve diagnostics |
| Owner crash or lease expiry | Mark `EXPIRED`; bounded retry after persisted cooldown |
| Producer cancellation | Fenced `CANCELLED`; default eligible for bounded retry |
| Waiter cancellation | Stop only that waiter |
| Ownership loss | Stop owner actions; discard publication eligibility |
| Registry unavailable | Bounded infrastructure error; no unlocked fallback |
| Storage temporarily unavailable | Bounded access/finalization retry; no corruption inference |
| Confirmed corruption or missing published bytes | Conditional artifact invalidation and new resolution episode |

If a producer's initiating run is cancelled, Dockflow may cancel that producer and release it through a fenced transition. Other runs can replace it under the shared retry policy. Continuing production independently of the initiating run is optional, not required. A cancelled run cannot erase another run's reusable artifact.

Infrastructure transaction retries are separate from production retries. Retrying a rolled-back database transaction must not increment the production count. Retrying storage finalization within one live attempt also does not allocate another producer.

## 13. SQLite local backend

MUST implement:

- A durable database on a local filesystem with one configured path shared by local Dockflow processes.
- Write-ahead logging, foreign keys enabled per connection, a documented busy timeout, and an explicit durability setting appropriate for persistent metadata.
- `BEGIN IMMEDIATE` before reading state that may be mutated by claim, renewal, publication, expiry, or invalidation.
- Short transactions and bounded handling of busy/locked conditions, with rollback or whole-transaction restart as appropriate to the actual error and driver behavior.
- A database-evaluated current timestamp sampled after write serialization is acquired.
- Schema migration serialization, a schema version check, restart recovery, and documented database/WAL backup handling.

SQLite permits concurrent readers but one writer; use the writer transaction to serialize entry decisions. Do not keep it open during artifact operations. This backend offers concurrent local process coordination, not cross-host distributed coordination. Its WAL database must not be placed on a network filesystem. These constraints follow SQLite's [transaction documentation](https://www.sqlite.org/lang_transaction.html) and [WAL documentation](https://www.sqlite.org/wal.html).

Reject a shared multi-host configuration using SQLite. Validate known unsupported paths and clearly document the local-filesystem requirement where filesystem detection cannot be reliable. Never silently create separate SQLite files for workers expected to coordinate.

## 14. PostgreSQL shared backend

MUST implement:

- A common schema and compatible scope configuration for all participating workers.
- Unique entry creation using `INSERT ... ON CONFLICT DO NOTHING`, followed by a separate `SELECT ... FOR UPDATE` in the same transaction.
- `READ COMMITTED` or a documented stronger isolation level with necessary full-transaction retries. Under `READ COMMITTED`, the separate locking statement must obtain a fresh view after a competing insert commits.
- Row locks and conditional writes for the complete claim/renew/publish protocol. A preflight `SELECT` alone is insufficient.
- `clock_timestamp()` sampled after the row lock for lease and cooldown decisions; do not use transaction-start `now()` as a current lease clock.
- Bounded lock and statement timeouts, small connection pools, rollback on errors, and bounded retry of retryable serialization/deadlock failures.
- Primary-authoritative coordination reads and writes; delayed replicas must not determine reuse eligibility or ownership.
- Stable lock order: entry first, then its attempt/artifact rows. Prefer one key per transaction; sort keys if a maintenance operation must touch several.
- Durable committed registry state and a documented database recovery assumption. Restoring a registry to older history requires all workers to stop and a fresh coordination namespace before resuming, so pre-restore tokens cannot remain authoritative.

The creation and locking behavior is grounded in PostgreSQL's [INSERT documentation](https://www.postgresql.org/docs/18/sql-insert.html) and [row-lock documentation](https://www.postgresql.org/docs/18/explicit-locking.html). The distinction between transaction-start and current clock time is documented in [date/time functions](https://www.postgresql.org/docs/18/functions-datetime.html).

Do not use session or advisory locks as the sole durable ownership record. Do not use `SKIP LOCKED` to treat a contended requested key as missing. The registry state and fencing protocol must survive connection loss.

Shared workers also require access to the same immutable artifacts through Dockflow's configured storage. Reject a shared descriptor whose storage identity cannot be resolved by the participating worker; a local path on another host is insufficient.

## 15. Integration, configuration, and diagnostics

### 15.1 Integration

Inspect existing cache lookup, key generation, execution scheduling, output materialization, validation, and cancellation paths before changing code. Route every cacheable read/write path through the new protocol; do not leave a legacy direct-write path that can overwrite published output.

Introduce narrow internal boundaries for registry persistence, lease supervision, immutable artifact storage, and pipeline integration. Prefer existing project conventions and dependencies. Keep retry/state semantics centralized rather than duplicating them in backend implementations.

Use the single state database connection configuration and expose cache policy for project/scope identity, storage identity, lease/heartbeat intervals, wait deadlines, polling, retry limits/backoff, and artifact freshness. Keep credentials out of logs and saved manifests. Validate incompatible or unsafe combinations before executing steps.

### 15.2 Compatibility and migration

- Preserve ordinary cache reuse and output behavior for single-process runs.
- Version registry and key formats explicitly.
- Treat legacy cache files without registry metadata as untrusted candidates. Either validate and import them under a claimed attempt using the normal fenced publication path, or treat them as a cache miss. Never import by file existence alone.
- Document the selected legacy-cache policy and its effect on hit rates.
- Do not allow old, uncoordinated writers to share a writable artifact namespace with the new implementation. Use a new versioned root or require a coordinated migration.
- Do not switch to another backend automatically when the configured registry is unavailable.

### 15.3 Diagnostics

Add structured events for hit, miss, claim, wait, validation, publish, failure, cancellation, expiry, takeover, rejected stale mutation, invalidation, retry scheduling, and exhausted budget. Include safe scope/key identifiers, attempt ID, fence, run/step IDs, durations, and reason codes.

Provide a Dockflow inspection surface showing the selected artifact, validity/freshness, current producer, lease deadline, attempt history, retry episode, next eligible retry, and terminal reason. Follow the project's command conventions. Logs must distinguish a cache waiter from an executing producer.

Provide counters or equivalent diagnostics for actual cache hits after verification, claims, waits, takeovers, stale publications, validation failures, retry exhaustion, and registry contention. Keep operational metrics low-cardinality; full keys belong in structured diagnostics rather than metric labels.

## 16. Retention and cleanup

The initial implementation MUST preserve published artifact bytes and registry fencing history. Automated eviction of published artifacts is not required and must remain disabled until consumer-retention coordination exists. Metadata invalidation does not delete bytes that an existing consumer may be reading.

Temporary/unreferenced attempt output may be cleaned only after a conservative age threshold and a registry check proving that the owning attempt is terminal or superseded. An outage is not permission to clean. A stale process can recreate its own orphan files; it still cannot publish them.

Never delete an artifact referenced by any committed descriptor during orphan cleanup. Serialize orphan eligibility with the entry, and establish that an attempt can no longer publish before deleting its finalized output. An age threshold alone is insufficient. Cleanup must tolerate repeated invocation and partial deletion.

If published eviction is added during implementation, it MUST include consumer pins or an equivalent retention protocol, atomic retirement that prevents new readers, rechecking active consumers, and race tests. Do not substitute a timing grace period for that protocol.

## 17. Test requirements

Use a backend conformance suite plus real independent processes and database connections. Thread-only mocks cannot demonstrate cross-process correctness. PostgreSQL integration tests must use a real shared database. Use barriers and fault injection to control race points; use generous bounded deadlines instead of fragile sleep-only assertions.

### 17.1 Identity and ordinary behavior

1. Identical semantic inputs produce the same key across runs and processes.
2. Parameter/input/content/environment/contract changes produce different keys.
3. Scope and key schema changes isolate entries; secret data is absent from diagnostics.
4. A single run claims, validates, publishes, then reuses after restart without recomputation.
5. Uncacheable execution does not create reusable registry output.
6. A multi-output artifact is reused only when its entire manifest verifies.

### 17.2 Concurrency and backend conformance

7. Start at least 20 independent processes at a barrier on one empty key. With healthy heartbeats and no injected expiry, exactly one execution occurs and all successful consumers receive the same published manifest.
8. Different keys can execute concurrently. SQLite may serialize metadata writes but must not serialize the whole computation.
9. Race initial row insertion and claim creation. No duplicate entries, fences, or active attempts appear.
10. Race heartbeat, expiry observation, takeover, failure, and publication. Outcomes agree with serialized ownership.
11. PostgreSQL workers using distinct process-local directories share one producer and materialize identical bytes through the configured common storage.
12. Verify backend-specific busy/lock/deadlock handling does not duplicate a production attempt or corrupt budget counts.

### 17.3 Crashes, leases, and stale workers

13. Kill a producer at each crash window in section 10.2; verify recovery and absence of partial hits.
14. Pause a producer past expiry; claim a replacement, then resume the old producer. Old renewal, failure, cancellation, state change, and publication are all rejected.
15. Attempt stale writes to storage; they cannot overwrite or delete replacement bytes.
16. Kill the producer with no sweeper running. A later requester discovers expiry and recovers.
17. Keep a slow healthy producer alive beyond several original lease durations. Heartbeats prevent takeover.
18. Lose renewal responses and inject worker clock skew/database clock changes. No stale publication succeeds.
19. Drop the connection around claim commit and publication commit. Idempotent recovery identifies the committed outcome without an extra attempt.

### 17.4 Validity and storage

20. Leave finalized bytes without a registry publication. No requester reuses them by existence alone.
21. Corrupt or remove one published output. Verification rejects it and conditionally invalidates that exact artifact.
22. Report corruption from an old artifact after a newer publication. The newer pointer remains valid.
23. Inject a transient storage access error. It does not invalidate the artifact or trigger duplicate production.
24. Submit a late failed producer callback while a valid artifact is selected. Its validity is unchanged.
25. Fail validation and interrupt finalization. Consumers never observe a partial output set.
26. Verify filesystem traversal/symlink defenses and inability of producer work to mutate sealed artifacts.
27. Pass freshness expiry during an already verified consumer read. Snapshot behavior follows section 11.

### 17.5 Wait, retry, cancellation, and maintenance

28. Have many waiters observe one retryable failure. Exactly one retry starts after the shared cooldown; the budget is charged once.
29. Fail or expire every attempt. All waiters eventually observe the same exhausted episode with no extra claim.
30. Restart waiting processes during cooldown and after exhaustion. They do not reset the retry count.
31. Test nonretryable validation failure, explicit episode reset, and conflicting worker policy settings.
32. Time out or cancel one waiter. The producer and other waiters continue.
33. Cancel the initiating producer run. A replacement can proceed under the documented bounded policy.
34. Remove all optional notifications; polling still observes completion and takeover.
35. Race invalidation with publication and reuse; stale revisions cannot revoke newer work.
36. Run orphan cleanup concurrently with finalization/publication. It never deletes publishable active output or committed artifact bytes.
37. Reopen the unified schema and reject unsupported split databases; legacy
    writers cannot corrupt the new namespace.
38. Reject SQLite multi-host/network-filesystem configurations where detectable and fail clearly on inaccessible shared artifact storage.

Include invariant assertions after fault tests: unique identity, monotonic fences, at most one authorized unexpired producer, valid cross-row references, consistent terminal attempts, and no selected unvalidated artifact. Repeat the main contention and takeover scenarios enough to exercise scheduling variation, with bounded runtime suitable for the project's test environment.

## 18. Acceptance criteria

Implementation is complete when all of the following are demonstrated:

- Concurrent Dockflow runs needing the same key share one healthy producer and reuse its validated artifact.
- Claim-or-reuse is atomic and durable on SQLite and PostgreSQL, verified with independent processes.
- Artifact validity and producer attempt state are separate in persistence and behavior.
- Leases recover crashed producers; healthy long-running work renews correctly.
- Fences and immutable attempt locations reject all stale producer mutations and protect newer bytes.
- No artifact is discoverable as reusable before complete validation, finalization, and committed publication.
- Claims and publications recover safely from ambiguous commit responses.
- Waits, infrastructure retries, production retries, and cancellation are bounded and independently classified.
- Retry budgets/cooldowns survive restarts and cannot be multiplied by concurrent waiters.
- Cache identity includes semantic dependencies and respects stable project scope boundaries.
- Missing/corrupt output is handled by artifact-specific invalidation; transient access failures do not poison the cache.
- PostgreSQL mode works across processes representing separate hosts with common artifact access.
- SQLite mode coordinates local processes and rejects unsupported multi-host usage.
- Published retention and orphan cleanup cannot break in-flight or future authorized reuse.
- Existing single-process behavior and a documented legacy-cache migration path remain usable.
- Diagnostics explain who is producing, who is waiting, why a retry is blocked, and why a stale action was rejected.
- Automated conformance, integration, crash, and contention tests pass on both backends.
- Project documentation describes configuration, guarantees, recovery, storage requirements, and operational limits.

## 19. Integration and qualification sequence

1. Inspect the Dockflow repository and map existing execution/cache behavior to this specification. Record material design deviations in project documentation.
2. Add versioned persistence models and migrations for both backends, with internal result/error types and constraints.
3. Implement atomic resolution, idempotent claims, lease supervision, fenced terminal transitions, and shared retry episodes.
4. Implement sealed immutable output manifests, validation, conditional publication, verified materialization, and artifact-specific invalidation.
5. Integrate scheduler waiting, cancellation, configuration validation, legacy-cache handling, inspection, and structured diagnostics.
6. Add and run the conformance, multiprocess contention, PostgreSQL integration, and fault-injection tests described above.
7. Deliver repository changes, migration/configuration documentation, test results, and a concise statement of any remaining limitations. Do not mark cross-host coordination complete based only on local tests.

The completed feature must make Dockflow itself responsible for discovering reusable artifacts, coordinating concurrent production, surviving producer failure, and safely publishing validated results.

## 20. Dockflow configuration and existing contracts

Execution state and cache coordination use one physical database and the shared
backend abstraction specified by [Metadata and recovery](007_metadata-and-recovery.md).
Environments using the same database and project share history and cache.
SQLite has one project execution owner; PostgreSQL has fenced per-Run owners. Separate databases have separate coordination domains. Cache
leases never grant execution ownership or confirm old-container termination.

`[cache]` is optional in schema-1 configuration and contains policy only. Backend
and connection settings belong exclusively to `[state]`; cache.backend,
cache.registry and cache.dsn_env and their former environment overrides MUST be
rejected. SQLite defaults to the same state.sqlite beneath `.dockflow` for both
domains. PostgreSQL uses only state.dsn_env. No automatic backend fallback.

Policy defaults are namespace=`default`, topology=`local`, shared_filesystem=false,
lease_seconds=120, heartbeat_seconds=30, wait_seconds=1800, poll_seconds=0.25,
poll_max_seconds=5, max_attempts=3, backoff_seconds=1, backoff_max_seconds=30,
transaction_timeout_seconds=5, infrastructure_attempts=4, freshness_seconds=0.
Numeric durations are finite and positive except freshness and backoff, which
may be zero. Counts are integers from 1 to 100. Require heartbeat plus twice the
transaction timeout below the lease. Topology `shared` requires PostgreSQL and
an explicit stable nonsecret storage_identity. Filesystem shared storage also
requires shared_filesystem=true. The local store label defaults to a digest of
configured storage; persisted scope policy binds it to the actual store token.
Namespace is a safe identifier. Scope derives from project ID and namespace,
never checkout path. Persist the scope's project ID for isolated export/restore.

Policy fields accept corresponding DOCKFLOW_PIPELINES_CACHE_ environment names.
Configuration loading, imports and help never create a database. SQLite storage
must be on a local filesystem outside work and managed artifact storage.

Coordinated signatures use `dockflow-task-signature-v2`, preserving typed
`dockflow-json-v1` encoding and dependency-local inputs from [Reuse](008_reuse-and-selection.md).
They include output/validation versions and actual immutable image/platform
identity. Cache-ineligible tasks bypass the registry. Legacy historical
results without registry publication are cache misses; explicit manual historical
selection still verifies the original committed output set. New coordinated
payloads use a separate `cache-v1` namespace in managed storage, isolated from
old writers. Original producer/artifact IDs and KFP types survive cross-state
binding. Registry descriptors contain store-relative locations; workers resolve
these against their own matching storage configuration. Imported producer facts
are recorded as external cache provenance, without fabricated local execution.

The registry is authoritative for *cache reuse and ownership*. The journal's
output-set marker remains authoritative for its producing Run. Cache publication
requires a complete validated sealed output set and confirmed local stop check;
a later journal projection failure does not undo registry publication. Recovery
must not replay an unpublished local output set into the cache without its live
ownership tuple. Existing pins and cleanup never remove published cache bytes.
Published cache eviction and automatic orphan cleanup are disabled initially.

Expose `cache show KEY`, `cache invalidate KEY --artifact-id ID --reason TEXT`
and `cache reset KEY --revision INTEGER --reason TEXT` under `dockflow pipelines`.
The same core operations are available at `GET /dockflow/v1/cache/{key}`,
`POST /dockflow/v1/cache/{key}/invalidate` with `artifact_id, reason`, and
`POST /dockflow/v1/cache/{key}/reset` with `revision, reason`. Inspection returns
entry, attempts and artifact history, with no credentials or producer-local paths.
Maintenance is conditional at the registry, across connections to the same project database;
it does not delete bytes or history. Errors use Dockflow's existing envelope.

The configured store label is bound to a persistent random store identity, read
from a versioned store record. Different stores with the same label must fail
scope registration before execution. Never infer shared byte access from a
PostgreSQL connection alone. Cache file finalization syncs bytes and directory
entries and reserves each output location without replacement; S3 uses conditional
writes. Initially each coordinated S3 output file is limited to 5 GiB; larger
outputs require disabling caching. Normal uncacheable transfers retain their
existing storage contract.

An omitted prerequisite may resolve/reuse or wait for a selected cache result,
but may not claim production. Publication is serialized with the producing
state owner's stop intent. A registry commitment that precedes later journal
failure remains authoritative cache provenance and can repair its local producer
snapshot after normal execution/index reconciliation, without recomputation.
