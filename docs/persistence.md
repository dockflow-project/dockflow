# Persistence and offline recovery

[Documentation index](README.md) · [Routine operations](operations.md)

This guide explains what must be preserved, how one owner protects a shared
project, and how to recover without changing accepted history. For ordinary
start/stop, log inspection and cancellation, use the operations guide.

## What is durable

Dockflow keeps accepted immutable mutations in `STATE/records/`, exact compiled
source snapshots in `STATE/definitions/`, and retained logs in each Run/attempt.
Current resource JSON files and the MLMD SQLite database are projections of that
history. Public UUIDs and original producing attempts survive index rebuilding.
Copying SQLite alone does not back up a project.

An attempt's complete `output-set.json` marker commits its outputs. Staged
descriptors or uploads without that marker cannot be consumed or reused. Startup
replays a committed marker after a crash, without executing the computation again.
The service also reconciles recorded Docker containers before dispatching work.
An unreachable daemon leaves the operation unresolved until it can be inspected.

## Shared state and its owner

A direct local operation and an API service can use the same configured project
state on a supported local filesystem. Each mutating local operation acquires an
exclusive OS lock on `STATE/owner.lock`; the service holds that lock for its
lifetime. A competing writer fails before initializing or changing project
records or the MLMD index. Use the explicit service endpoint for mutations while
that service is running, or stop it and reconcile any uncertain execution before
using direct local operations.

The lock file records a versioned diagnostic owner object: a random `owner_id`
for that ownership acquisition, `project_id`, `hostname`, `pid`, `mode` (`local`
or `service`), `acquired_at` and the service `endpoint` when supplied. The hostname
labels the owner's execution environment, which may be a container; it is not a
globally unique physical-machine identity. The owner ID distinguishes instances
even when hostnames or PIDs repeat. Contention errors include the state path and
available owner details so a user can identify the owner and its explicit API
endpoint. The CLI never automatically connects using lock-file contents.

The OS lock establishes exclusivity. File contents are diagnostic, not a lease:
old metadata can remain after exit or a crash, and acquisition succeeds when
the OS has released the lock. Never remove or replace `owner.lock` to clear a
busy condition: that can create a second lock inode while the first remains
owned. PID checks, hostname comparisons and timestamps cannot authorize takeover.
Malformed or older diagnostic contents do not defeat a live lock. Locking or
filesystem failures stop the operation rather than allowing an unlocked writer.

Releasing the coordinator's lock does not establish that its Docker tasks have
stopped. Before admitting a new direct Run, Dockflow rejects retained queued or
active Runs and unresolved execution records. Start the service to reconcile
lost execution and drain or explicitly cancel accepted queued work before
switching back to direct execution. A free lock never bypasses these recovery
checks or reruns lost computation automatically.
Successful service reconciliation clears execution uncertainty after confirming
the recorded tasks have stopped, while preserving existing terminal Run outcomes.
Failed confirmation leaves the recovery hold in place.

Same-host bind mounts of the same underlying state directory share the same
lock. All cooperating writers must use that directory, compatible project IDs,
paths and permissions. Copying the directory creates a different state store and
lock. Arbitrary network-filesystem SQLite sharing and cross-machine distributed
ownership remain outside the supported profile; owner identifiers alone do not
provide distributed fencing or locking guarantees.

## Check and rebuild

Run these commands from an environment with the `runtime` extra installed.
Select the consuming project's configuration explicitly:

```bash
dockflow pipelines --config /path/to/.dockflow-pipelines.toml metadata check
dockflow pipelines --config /path/to/.dockflow-pipelines.toml metadata check --verify-contents
dockflow pipelines --config /path/to/.dockflow-pipelines.toml metadata rebuild
```

The default check distinguishes unverified bytes from verified contents. A
historically successful attempt remains successful when its payload is later
missing or corrupt; its unavailable outputs cannot be reused.

For an index rebuild, stop the API first and resolve any uncertain task
containers. Then run:

```bash
dockflow pipelines --config /path/to/.dockflow-pipelines.toml metadata rebuild --apply
```

This command acquires exclusive ownership, uses SQLite's backup API, validates
accepted history, builds another MLMD index, and switches only after successful
projection. A live HTTP service rejects applying its own index replacement.
Rebuilding cannot recreate lost authoritative records, deleted payloads or missing
logs from their filenames.

## Backup and restore

Stop the API and leave the configured artifact provider available. From the
Dockflow checkout, activate an environment with the `runtime` extra (and `s3`
for S3 storage), using the same project environment and provider credentials:

```bash
python tools/backup.py backup \
  --config /path/to/.dockflow-pipelines.toml /path/outside/project/backup-name
python tools/backup.py verify \
  /path/outside/project/backup-name
```

The backup captures a consistent accepted-sequence boundary, control records,
compiled snapshots, logs, an SQLite online-backup snapshot while the owner is
idle, and managed artifact bytes. S3-compatible managed contents are downloaded
into the backup. It records a canonical inventory and content hashes. External
reference payloads remain their owners' responsibility and are excluded.

Keep the original configuration, provider endpoint settings and credential
references separately. Restore supports the original project ID and configured
state, metadata and artifact locations; changing durable URIs is a migration.
The restore target state, metadata and managed artifact locations must be empty.
For filesystem stores, backup and restore use the resolved `artifacts.managed_root`
directory, including pipeline/run/task output directories and hidden `.dockflow/`
recovery metadata. S3 backup bundles are restored to each descriptor's original
object keys; both current and historical layouts retain their URIs.
The backup's internal `managed/` section does not add a child to the
live store. Older backups that recorded only `artifacts.root` remain supported.
Preserve any existing data separately first. Preview and apply with:

```bash
python tools/backup.py restore \
  --config /path/to/.dockflow-pipelines.toml /path/outside/project/backup-name
python tools/backup.py restore \
  --config /path/to/.dockflow-pipelines.toml --apply /path/outside/project/backup-name
```

Restore verifies the backup, takes ownership, restores records/index/managed
contents, reconciles MLMD and hashes artifact contents. Inspect the reported
availability of external references before restarting the API. If copying is
interrupted, preserve the partial target for diagnosis, prepare empty targets
again and repeat from the verified backup. No existing contents are overwritten
by restore.

For a Compose deployment, run the backup tool with the service's configuration,
state and execution volume mounts and the same provider network/credentials.
Alternatively snapshot the stopped `dockflow-state` volume and the stopped
`artifacts` provider volume together, plus any configured external inputs and
deployment configuration. Registry/engine volumes preserve prepared images and
container-reconciliation evidence; retain them when unresolved execution exists.
The `artifacts` volume includes managed imports and generated outputs (such as
models and evaluation reports), as well as SeaweedFS/MinIO's provider metadata.
`dockflow-execution` holds staged/workspace files; `docker-state` and
`docker-containerd` hold the inner engine's persistent state. Registry image data
remains in `registry-data`, and the shared Unix socket remains in `docker-socket`.
Compose normally prefixes these labels with its project name. When migrating
older volume labels, copy only while the owner/provider/engine are stopped,
preserve permissions/content, and retain original volumes until verification.
Do not copy a live SQLite main file without its WAL/journal state. After restoring
volumes, run `metadata check --verify-contents` before admitting new work.

## Cleanup

`dockflow pipelines ... clean` previews disposable work for terminal Runs;
`clean --apply` rechecks idle ownership before removing it. Neither command
expires committed artifacts, control history, definitions, logs or external
references. Artifact pins survive restart and index rebuilding. Retention expiry
and migrations to an external SQL backend are outside this development profile.
