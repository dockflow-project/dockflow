# Execution, ownership and lifecycle

## Admission, ownership and scheduling

`state.backend` selects the coordination model in direct CLI and service modes.
SQLite is local deployment: one database, one lifetime execution owner, one active
Run and one task attempt. PostgreSQL is distributed deployment: multiple
coordinators on isolated hosts share one project database and artifact store,
with one authorized execution owner per Run. Each coordinator dispatches one Run
at a time initially, and each Run executes tasks sequentially. Different Runs
may execute concurrently. No additional deployment-mode flag or broker is needed.

Each coordinator uses its own pinned database session. PostgreSQL coordinators
hold a shared project maintenance gate rather than an exclusive execution lock.
Short project transactions serialize accepted journal sequence allocation,
resource aliases, admission/idempotency, catalog updates and stop/publication
ordering. No transaction spans execution or artifact transfer. Lost or uncertain
session commits fail closed and never transparently reconnect that coordinator.
SQLite retains its stable database-inode ownership lock.

PostgreSQL Run claims MUST be atomic and persist project/Run identity, random
coordinator owner ID, monotonically increasing fencing generation, active state
and database-time lease deadline. A valid current claim excludes other claimants.
Heartbeats renew only the matching unexpired claim; failure revokes local execution
authority. Every execution mutation and cache publication checks current owner,
fence and deadline. An old worker may not write after expiry or takeover, renew a
replacement, or mutate a different Run. Operational claims do not become restored
execution authority. Lease expiry alone does not prove container termination.

A direct PostgreSQL submission may execute its own newly accepted Run while other
Runs are active or awaiting reconciliation. Re-executing a terminal or abandoned
Run is not an implicit retry. Services atomically claim eligible queued Runs,
skipping Runs owned by another coordinator and preserving acceptance order among
claimable work. Persist up to 100 waiting Runs by default before acknowledgement;
serialize capacity checks and idempotency so concurrent callers cannot over-admit
or duplicate one request. Client disconnect does not cancel accepted work.
SQLite direct admission retains its busy/unresolved-project guard and serial FIFO
service queue.

Resolve the Default Experiment and immutable definition snapshots within durable
admission transactions. Validation, help and reads never initialize project data.
Workers retain isolated process-global KFP configuration and act through their
coordinator's constrained RPC, carrying that Run's authority. Multiple service
instances and direct processes may share PostgreSQL without changing the artifact
store identity or creating another state/cache database.

Recovery after coordinator loss MUST first claim the expired/released abandoned
Run with a newer fence. A surviving authorized coordinator may reconcile its own
failed worker under its current claim.
Never recover, interrupt or rewrite a live Run owned by another coordinator.
Reconcile only that Run's recorded handles, outputs and logs against the original
Docker daemon, retire stopped handles, and preserve unresolved activity when its
daemon cannot be reached. Failure to reconcile one Run does not stop unrelated
PostgreSQL Runs. No automatic rerun of abandoned computation is implied. SQLite
reacquisition still requires project-wide reconciliation before dispatch.

Migrations, restore, projection rebuild and destructive cleanup require an
exclusive project maintenance gate. Refuse while another coordinator holds a
shared gate; independent cache transactions also respect that gate. Preview
operations remain read-only. Ownership diagnostics remain informational and
credential-free; never discover another service automatically.

## Immutable invocation and states

Before acceptance, resolve definition version, defaults/types, parameters,
artifact bindings, selection, scope/key, resource and retry policies, image
references and non-secret effective configuration. Save the exact submission.
Resolve mutable image references to the actual execution image identity before
using a cache signature or launching its task; record the final binding.

Independent submissions always create new Run IDs, including identical inputs.
A retried network request with the same valid idempotency key refers to the same
accepted submission. Invocation fields remain immutable; observations/events
and availability evolve.

| Object | States |
| --- | --- |
| Run | queued, running, cancelling, succeeded, failed, cancelled, interrupted |
| Task | pending, running, reused, skipped, blocked, succeeded, failed, cancelled, interrupted |
| Attempt | running, publishing, succeeded, failed, cancelled, interrupted |

Qualified task paths are slash-separated compiled task keys from outermost to
innermost DAG, for example prepare/normalize. Selectors must use that full path;
no display-name matching occurs. TASK.INPUT bindings split on the final dot,
after validating the task path and declared input name.

Importer tasks may succeed with disposition imported after verified source
registration and durable output binding; they have no container attempt.
Execution/reuse/import/skip disposition is separate from lifecycle state.

Cancellation intent is recorded separately until termination is confirmed.
An interrupted/crashed executor with unconfirmed activity is marked
reconciliation_required in recovery metadata; do not declare it stopped or
dispatch a replacement. This is an operational hold, not a successful terminal
outcome. A committed cache result can survive an uncertain execution-journal response;
inspect/reconcile SQL history before further dispatch.

A Run succeeds only when every required selected task succeeds or is validly
reused, with inactive branches skipped. All attempt outputs/parameters must be
validated and their output set committed before success. The metadata projection
must be reconciled before returning a reusable successful result. Terminal
execution outcome and later artifact availability are separate.

Validation rejection occurs before accepted Run creation. After durable
acceptance, admission-time external resources can still disappear; record their
execution/materialization failure on that Run. Never convert it to an unrecorded
validation error.

## Failure and attempts

On failure stop dispatching new ordinary work and mark dependent tasks blocked.
Already completed independent results remain retained. No attempt is fabricated
for blocked, skipped or reused tasks. Record failing phase, exit status when
available, concise error, logs and partial-output disposition.

Retries default to zero. Honor supported compiled retry policy, bounded to at
most 3 additional attempts initially, with nonnegative backoff and maximum
backoff 300 seconds. Retry only eligible execution/transient-transfer failures.
Unchanged schema/type/output-contract validation failures are not retryable.
Publish-failure recovery first checks for a committed output set; it cannot
repeat an already committed computation.

Automatic retry of externally effectful work requires a declared idempotency/
recovery policy, in a definition-keyed local policy or the component's documented
contract. Without one reject a requested automatic retry rather than silently
assuming it is safe. Each retry preserves computational invocation and creates
a new attempt ID/workspace; no overlapping attempts or shared writable outputs.

## Interruption, cancellation and deadlines

Ctrl+C in a direct execution records interruption intent, stops dispatch and
requests termination of its active container. Allow 30 seconds by default for
graceful termination, then request forced termination. Preserve logs and staging
descriptors. After confirmed stop, an uncommitted attempt becomes interrupted
and is ineligible for reuse. A second signal may force owner exit but must leave
recovery evidence.

The owner serializes stop intent and output-set commitment. Stop intent recorded
first prevents a new output-set commit. An output set already committed before
stop intent remains a successful producing attempt after reconciliation; retain
its published artifacts. The Run may still end interrupted/cancelled with earlier
successful tasks. Recovery follows that same durable ordering, not signal timing
guesses.

Explicit cancellation of a queued Run removes it from the dispatchable queue
and marks cancelled. For an active Run mark cancelling, stop dispatch and request
termination. Only confirmed stopped execution becomes cancelled. Uncertain or
unreachable containers remain reconciliation_required and block replacement work
for that Run; SQLite retains its project-wide dispatch hold.

Stopping a waiting service client only stops waiting; accepted work continues.
Explicit cancellation uses its documented API. Graceful service shutdown stops
admission, preserves queued Runs, interrupts active execution through the same
termination policy, flushes records and releases ownership only after safe stop
or durable recording of uncertainty. Restart reconciles before dispatch.

Optional run timeout is zero/unlimited by default. A configured timeout starts
when execution begins, includes materialization, process, retry backoff and
publication, and excludes time queued. Record deadline_exceeded as reason;
confirm termination and mark failed. A wait timeout on a client is not an
execution timeout or cancellation request.

## Containers, resources and logs

Use unique container labels carrying project/run/task/attempt IDs and record
the daemon identity and container ID durably at creation before relying on
polling. The adapter must prevent a race in which unrecorded detached work
survives owner failure. Keep containers until exit status/logs are durably
captured; cleanup must not assume auto-removal implies success.

Respect admitted CPU/memory requirements using qualified Docker mappings.
No GPU, affinity or Kubernetes scheduling guarantees are admitted initially.
Never silently ignore unsupported resource fields. Defaults impose no additional
CPU/memory quota beyond host limits; validate positive configured limits and
record the actual applied settings.

Record task stdout/stderr separately with timestamps/sequence where available,
plus owner events and concise failure details. Preserve the original ordering
within each stream; do not invent total ordering across streams. Log chunks
persist in the SQL journal and are exposed through CLI/API.
Service application diagnostics also use container stdout/stderr.

Attach stdout/stderr before container start and persist chunks during execution,
without requiring a TTY or changing component commands. Use bounded transport
buffers; readers must not mutate state or use the worker RPC independently of
the execution thread. Split UTF-8 sequences must decode correctly across chunks.
Continue checking cancellation/deadlines during silent or noisy output. Complete
capture and confirm the numeric exit status before accepting task outputs.
Verify already streamed prefixes against retained container logs and append only
missing tails after exit or recovery; never silently duplicate saved output or
accept a changed/truncated retained prefix. Log timestamps are journal capture
times; chunk boundaries are not a stable line/message contract. Preserve emitted
ANSI colors in raw records, with display policy owned by CLI/browser clients.
Components must flush their own output for prompt visibility.

Do not pass Docker sockets or registry/control credentials to task containers.
Only explicitly declared task environment and data access is forwarded. Artifact
transfer by the owner is preferred so ordinary components need no storage SDK
or credentials. Component commands may perform declared network work; that is
part of their computation, not permission for Dockflow to build images.

## Cache connections and execution ownership

[Cache coordination](014_cache-coordination.md) governs producer connections to
the same database as execution state. Local staging roots may differ; SQLite ownership is project-wide, while
PostgreSQL execution authority is per Run. Waiting records a cache-wait disposition without a
container attempt. Cache leases never grant execution-journal ownership. Shared
cache retry budgets supersede Run-local retry multiplication for cacheable tasks;
uncacheable tasks retain their compiled bounded retry behavior.

## Supervision and accepted execution choices

The service supervises its complete scheduler lifetime. An escaping queue-read,
recovery or worker-start failure revokes readiness and Run admission, records a
non-secret diagnostic and preserves accepted work. Fail-stop with explicit service
restart is the initial recovery policy; do not silently replace an uncertain
owner. Readiness checks scheduler liveness when execution is enabled.

Admission records a versioned immutable execution-choice value: timeout, shutdown
grace, CPU/memory caps, image pull policy, resolved task policies and cache policy.
Execution uses these choices after restart and across PostgreSQL coordinators.
Database access, credentials, local work paths and provider connections remain
coordinator deployment settings. Remap explicit task mounts only by matching
logical target and access mode; never grant a mount absent from the current
coordinator's configuration. Refuse incompatible deployment constraints with a
recorded failure, without silently changing accepted computation settings.

Use common lifecycle transitions for normal completion, cancellation and crash
recovery. After confirmed reconciliation, Run, Task and Attempt outcomes agree.
Preserve committed successes; terminalize abandoned running Tasks and block
unstarted dependent work. Unresolved execution retains its recovery hold.
