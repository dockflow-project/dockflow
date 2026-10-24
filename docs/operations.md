# Operations

[Documentation index](README.md) · [Persistence and recovery](persistence.md)

Use the service endpoint for ordinary mutations while the service owns the
project. Use the original project configuration for offline maintenance.
`PROJECT_CONFIG`, `RUN_ID` and similar uppercase operands below are placeholders.

## Start, inspect and stop

For a Python service:

```bash
dockflow pipelines --config PROJECT_CONFIG serve --host 127.0.0.1 --port 8080
```

For the prepared reference Compose stack, from the repository root:

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d --wait
docker compose --env-file deploy/.env -f deploy/compose.yaml ps
docker compose --env-file deploy/.env -f deploy/compose.yaml logs -f dockflow
```

Preparation/build instructions are in [deploy/README.md](../deploy/README.md).
Open `http://127.0.0.1:8080/ui/` for the browser or use the CLI:

```bash
curl --fail http://127.0.0.1:8080/health/ready
dockflow pipelines --endpoint http://127.0.0.1:8080 runs list --state running
dockflow pipelines --endpoint http://127.0.0.1:8080 runs list --state queued
dockflow pipelines --endpoint http://127.0.0.1:8080 logs RUN_ID --follow
```

Readiness can fail while the process is alive if recovery cannot confirm prior
execution has stopped or metadata reconciliation is required. Inspect its JSON
checks and service logs before submitting new work. Readiness also fails when
the scheduler thread stops after a queue, recovery or worker-start error. Resolve
the reported cause and restart the service. Accepted queued Runs remain in SQL;
readiness and new Run admission resume after successful startup reconciliation.

Finish or cancel active work before planned shutdown:

```bash
dockflow pipelines --endpoint http://127.0.0.1:8080 runs cancel RUN_ID
dockflow pipelines --endpoint http://127.0.0.1:8080 runs show RUN_ID
```

Wait for a terminal result. Stop a foreground service with Ctrl+C in its service
terminal; stop the reference stack with:

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml down
```

The normal Compose stop preserves volumes. Do not add `--volumes` unless you
intend to delete their history, artifacts and image state. Killing the coordinator
or Docker engine is not proof that a task stopped successfully.

## Check integrity

```bash
dockflow pipelines --config PROJECT_CONFIG metadata check
dockflow pipelines --config PROJECT_CONFIG metadata check --verify-contents
```

The first inspects records, indexes and availability without promising a complete
rehash. The second verifies artifact bytes against recorded fingerprints. The
same read-only check is available through the service endpoint. Missing/corrupt
outputs remain part of historical lineage but cannot be reused.

## Reclaim scratch work

```bash
dockflow pipelines --config PROJECT_CONFIG clean
dockflow pipelines --config PROJECT_CONFIG clean --apply
```

The first returns a plan; the second revalidates it under idle ownership and
removes only eligible disposable work. You can use the endpoint for this operation
when the service is idle. It preserves committed artifacts, definitions, logs,
history, pins and external sources. There is no automatic published-artifact
expiry in this profile.

## Backup, restore and rebuild

Stop admission and make the owner idle/stopped before backup. Back up the full
SQL project state and managed artifact payloads together. The repository includes `tools/backup.py` with
inventory verification and explicit, empty-target restore. Follow the complete
[backup/restore procedure](persistence.md#backup-and-restore).

An index rebuild can recover the derived SQL resource projections from accepted
records, but cannot recreate lost authoritative records or bytes:

```bash
dockflow pipelines --config PROJECT_CONFIG metadata rebuild
# After stopping the service and resolving uncertain execution:
dockflow pipelines --config PROJECT_CONFIG metadata rebuild --apply
```

The service only offers the rebuild plan; it refuses live index replacement.
Rebuild is not a migration to a new project ID, filesystem layout or backend.

## Recover after an unexpected exit

Retained SQL owner diagnostics may outlive a process; database ownership is
authoritative. Never replace a live SQLite database to clear a lock. A free
ownership lock also does not prove prior task
containers stopped. Start the service with the same project configuration to
reconcile retained execution, and let it drain or explicitly cancel queued Runs.

The service confirms ownership of recorded containers before stopping them.
If the daemon cannot be reached or stop confirmation fails, readiness remains
held. Restore the original daemon connection/access, inspect logs and retry
recovery. Successful reconciliation preserves terminal outcomes and clears
execution uncertainty; it does not automatically rerun interrupted computation.

See [troubleshooting](troubleshooting.md) for common diagnostics and
[persistence](persistence.md#ownership-and-isolated-environments) for the locking model.

## Update a deployment

Preserve the current configuration, project ID, image identities and a verified
backup. Review changes before replacing an unreleased development image. Stop
the owner cleanly, build/load the intended service image and restart with the
same data mounts. Check readiness, history and artifact integrity before new
execution. This development repository does not promise an automatic migration
for every future state-format change.

## Inspect and recover cache coordination

A cache waiter has disposition `cache_wait` and no container attempt. A producer
has an attempt ID, fence and renewable lease. Task inspection includes its cache
key and scope; structured `cache.*` events distinguish verified hits, claims,
waits, takeover, rejected stale mutations, validation, publication and retry
exhaustion. Cache waiting times out independently of the producing Run and never
cancels another Run's producer. Producer cancellation can release its claim for
another requester under the shared retry budget.

```bash
dockflow pipelines --config PROJECT_CONFIG cache show CACHE_KEY
dockflow pipelines --config PROJECT_CONFIG cache invalidate CACHE_KEY \
  --artifact-id SELECTED_ARTIFACT_ID --reason CONFIGURATION_REVISION_CHANGED
dockflow pipelines --config PROJECT_CONFIG cache reset CACHE_KEY \
  --revision EXPECTED_ENTRY_REVISION --reason RETRY_APPROVED
```

Use the group `--json` option for structured output or `--endpoint` for the
same operations through a service. Inspection returns the selected artifact,
freshness deadline, current producer/lease, complete attempt history, retry
count/cooldown and terminal reason. Invalidation and reset reject stale expected
identities. Reasons must be nonsecret, nonblank and at most 256 characters.
Reset requires no live producer and no reusable selected artifact. Neither
operation deletes bytes or historical fencing records.

After a crash, a later requester observes lease expiry and may claim after the
shared cooldown. A healthy producer renews through validation and finalization.
A paused stale process may still consume resources, but cannot publish or alter
replacement output. Side effects inside component code are not exactly once.
Do not delete registry rows or storage identity records to unlock work.

Legacy results without a registry publication are automatic cache misses. New
coordinated outputs use `.dockflow/dockflow-pipelines/cache-v1/` inside the managed
store, preserving their KFP relative hierarchy and original producer identity.
Explicit manual historical inputs retain normal complete-output verification.
Old clients must not write this new namespace. Published bytes and fencing
history are retained; automatic eviction and orphan deletion are disabled.
Finalization retries a temporary transfer error up to three times within the same
producer attempt, recovering identical filesystem/object writes after a lost
acknowledgment. It never replaces conflicting bytes.
S3 cache publication requires conditional object writes and limits each file to
5 GiB; disable caching for larger outputs. Permission/timeouts fail as storage
access errors. Confirmed missing/corrupt bytes invalidate only the selected output
set and open one new retry episode. Validated cache publication remains reusable
if a later producing-journal projection fails; reconcile execution history before
admitting another Run to that state root.
