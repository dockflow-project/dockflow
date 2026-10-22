# Execution, ownership and lifecycle

## Admission, ownership and scheduling

Every mutating local operation acquires exclusive project-state ownership.
The service holds ownership for its lifetime and serializes state/MLMD writes.
Use a nonblocking OS-backed exclusive lock on the stable `state/owner.lock`
file, held until the coordinating operation or service has safely stopped.
Acquire that lock before initializing or mutating project records, SQLite,
catalogs or artifact state. Workers act through the existing coordinator; they
do not acquire independent writer ownership. Nested use by the same coordinator
retains its current lock and owner identity.

After each successful outer acquisition, write UTF-8 JSON diagnostic metadata
to the locked file with this schema:

| Field | Meaning |
| --- | --- |
| schema_version | Integer `1`. |
| owner_id | Fresh canonical lowercase UUIDv4 identifying this acquisition/coordinator instance. |
| hostname | Label reported by the execution environment; a container hostname may differ from its physical host. |
| pid | Coordinator process ID in that execution environment's PID namespace. |
| mode | `local` for a direct coordinating operation or `service` for the persistent API owner. |
| project_id | Configured stable project identity. |
| acquired_at | UTC RFC3339 acquisition time. |
| endpoint | Explicit service HTTP(S) base URL when available, otherwise `null`; never a credential-bearing URL. |

`owner_id` distinguishes owner instances even when their hostnames/PIDs repeat.
It is neither a globally unique physical-machine identity, authentication token,
nor a distributed fencing token. Hostname and PID describe where this owner
executes; neither alone identifies a physical host or proves liveness.

The OS lock is the sole authority. File existence, valid or stale metadata,
hostname, PID visibility, elapsed time and a previously recorded `owner_id`
never grant ownership, permit takeover or expire the lock. A live owner's PID
may be invisible or reused in another container namespace. Do not steal or
delete a lock on that basis. Normal exit or process death releases OS ownership;
retained metadata may remain and is replaced in place only after the next
successful acquisition. Empty, legacy, truncated or malformed metadata does not
prevent acquisition when the OS lock is free and never permits acquisition when
it is held.

Keep the lock file's inode stable: do not unlink, atomically replace, rename away
or recreate it while the state directory is operational. Update diagnostic
contents through the locked file itself and flush them; ordinary atomic-rename
rules for control projections do not apply to `owner.lock`. Different paths or
same-host bind-mount aliases for that file must contend on the same OS lock.
Failure to initialize diagnostic contents after acquiring the lock fails the
operation before project-state mutation and releases ownership safely.

A competing owner fails with `CONFLICT` (HTTP 409 where applicable). Its
operational diagnostic names the resolved state root and reports recognized,
validated owner metadata when readable, through the existing `field`/`reason`
error-details envelope and the structured owner-conflict extension in
[Service API](010_service-api.md). Accept diagnostic contents up to 8192 bytes;
a bounded read may consume one extra byte only to detect an oversized file.
Classify oversized, unsupported-schema or malformed contents without treating
them as authority. Include the recorded endpoint as an explicit connection option
when present; otherwise advise finishing/stopping the current owner before
retrying. Unreadable/legacy/malformed metadata reports unavailable diagnostic
fields without dumping arbitrary file contents. A lock-capability failure or
lock-file I/O failure is `UNAVAILABLE` (503), distinct from a busy owner, and
fails closed. Do not automatically switch modes, discover/start a service,
retry a mutation against an endpoint, or open a competing SQLite writer.

This contract is qualified only on local filesystems with working OS locking,
rename/fsync and SQLite semantics, including same-host bind mounts of the same
underlying state. It does not promise cross-machine or network-filesystem
coordination, a distributed lease, or safety after an operator replaces a live
lock inode. External SQL does not itself solve distributed execution ownership.

Reacquiring a free OS lock establishes only control-state ownership. Task
containers or workers may outlive a dead coordinator, and accepted queued work
may remain. Before accepting a new direct CLI Run, fail closed if retained Runs
are nonterminal (including queued), or a retained Run/attempt is marked
`reconciliation_required` or has unresolved activity. Explain that an explicitly
started service must reconcile prior execution and drain accepted queued work
before another direct Run. Do not infer task termination from coordinator death,
discard the old queue, create a replacement Run or implicitly rerun interrupted
work. This direct-admission guard does not change the service's durable queue:
its owner still reconciles before dispatch and accepts work under the existing
service admission rules.

Allow one active Run and one active task attempt. Direct execution is foreground;
a second direct submission is rejected as busy. The service accepts up to 100
waiting Runs by default, persists each before acknowledging it, and dispatches
FIFO by acceptance sequence. Reject overflow before acceptance. A queued Run has
its own immutable invocation and isolated paths. Client disconnect does not cancel
accepted service work.

Resolve the default Experiment named Default under ownership on the first
mutating submission that needs it. Creating it is part of durable admission;
help, validation and read-only listing must not create state.

The owner coordinates storage and state; a separate worker process hosts each
Run's process-global KFP local configuration. Workers report structured events
to the owner. All metadata mutations remain serialized through ownership.
Never concurrently reinitialize KFP from HTTP request threads. No extra queue
broker is required.

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
outcome. Publication committed but MLMD not reconciled similarly holds dispatch.

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
unreachable containers remain reconciliation_required and block further dispatch.

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
within each stream; do not invent total ordering across streams. File logs
persist under the attempt's logs directory and are exposed through CLI/API.
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
