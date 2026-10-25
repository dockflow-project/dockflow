# Persistence and offline recovery

[Documentation index](README.md) · [Routine operations](operations.md)

## What is durable

Dockflow stores accepted mutations, Runs/Tasks/Attempts, exact compiled sources,
logs, catalog, queue, idempotency data, pagination key and artifact provenance in
a SQL database. SQLite is the default at `.dockflow/state.sqlite`; PostgreSQL is
the external backend. Current resources have one mandatory SQL query projection, committed with each
accepted mutation and can be rebuilt from the database journal. There is no
required JSON history tree or MLMD index. Publication claims, completion manifests
and artifact recovery descriptors also live in that same database. Artifact contents live separately in
filesystem or S3-compatible managed storage, alongside `.dockflow/storage.json`
which identifies the store. No publication bookkeeping sidecars are required.

Preserve the single database and managed artifacts to retain history and cache
coordination across days, restarts and disposable execution environments. Workspaces are disposable; published data,
definitions, logs and history have no automatic expiry. External reference
contents remain their source owner's responsibility.

This is a fresh database format. Old file-authoritative state is rejected; no
migration/import of that history is provided. Select fresh state locations.

## Schema ownership
`dockflow-core` provides the generic database adapters and schema registry.
Artifacts and Pipelines supply their own definitions, versions and persistence
logic. Standalone Artifacts creates only its publication schema; Pipelines adds
its execution/cache schema and explicitly consumes the Artifacts schema. Either
initialization order uses the same physical database. Verification checks the
required consumer versions and objects without creating or repairing anything.
This fresh format replaces the previous combined schema; existing state may be
discarded, and no migration or compatibility package is supplied.

## Ownership and isolated environments

SQLite has one coordinator, active Run and task attempt per project database.
A competing writer is refused; use the existing service endpoint or stop it first.
PostgreSQL permits multiple coordinators sharing a project, with one fenced owner
per Run. Each coordinator executes one Run at a time; different coordinators may
execute different Runs concurrently. Readers inspect committed snapshots.

SQLite requires a local filesystem with working locks and durability, including
same-host bind-mounted volumes. Its stable database inode is also the POSIX
ownership lock; Windows uses a small operational lock companion. Never replace
an operational database to clear ownership. SQLite WAL/SHM files are normal
operational companions. Sharing SQLite across hosts/network filesystems is
unsupported.

PostgreSQL coordinators hold shared maintenance gates and use short project
transactions for journal sequences, admission/idempotency, catalog updates and
cancellation. Run leases use the database clock and renew independently of task
execution. Every execution mutation checks the current owner, fence and deadline;
an expired worker cannot write after another process takes over. State sessions
never reconnect transparently after an uncertain commit.

A fresh environment sees the same history and cache through its stable project
ID, PostgreSQL database and managed artifact store. Local staging directories may
differ. Direct submissions reserve their Run atomically; services claim different
queued Runs. Cancellation submitted to any coordinator reaches the owning worker
through persisted stop intent.

Recovery acts only on abandoned Runs, leaving live remote Runs alone. A free lock
or expired lease does not prove Docker tasks stopped. Reconcile recorded handles
against the original daemon and retire them before declaring the Run stopped;
unknown or unreachable daemons leave that Run unresolved. Unrelated PostgreSQL
Runs can continue. SQLite retains its project-wide recovery/admission guard.

Offline restore, projection rebuild and destructive cleanup require exclusive
maintenance access; stop other coordinators first. Cache transactions respect that
same gate. Run claims are operational and excluded from portable backups; the
journal sequence counter is retained. Older database schemas fail explicitly;
no schema migration is included in this fresh-state implementation.

## Accepted execution choices

Every accepted Run carries a versioned `execution_choices` value. Timeouts,
shutdown grace, CPU/memory caps, image pull policy, reuse defaults, task policies
and cache policy remain fixed after acceptance. Editing a configuration or policy
file affects future submissions. A different coordinator uses the accepted
choices and its own database/provider access, credentials and local work paths.

Task mounts record logical targets and access modes. Another coordinator must
provide matching targets/modes from its own configured sources. Extra local
mounts are not granted to an older Run. A stricter current resource cap or missing
mount fails the Run explicitly rather than silently changing its accepted choices.

Resource lists, queue eligibility, name/idempotency lookups and log ranges use
selective SQL queries and indexes. Public pages fetch bounded rows. Input-artifact
relationships and log entries are derived projections; full integrity checks and
offline replay/export intentionally inspect complete accepted history.

## Check and rebuild

```bash
dockflow pipelines --config PROJECT_CONFIG metadata check
dockflow pipelines --config PROJECT_CONFIG metadata check --verify-contents
dockflow pipelines --config PROJECT_CONFIG metadata rebuild
# Stop the service and resolve uncertain execution before applying:
dockflow pipelines --config PROJECT_CONFIG metadata rebuild --apply
```

Checks report journal/projection consistency and artifact availability through
`projections_checked`. They compare all derived rows, including missing, changed
and orphaned cache observations, sources, output sets, log snapshots, input
relationships and log entries. A sequence counter ahead of accepted history is
an authoritative inconsistency; rebuild refuses to hide that loss. Inspection needs no index attachment or state initialization. Content
hashing is explicit. Rebuild validates the journal, then replaces projections in
one SQL transaction while preserving public IDs and KFP numeric aliases. A live
service refuses apply with OFFLINE_REQUIRED. Rebuild cannot recover a lost or
physically corrupt authoritative database, deleted payloads or missing logs.
Restore a verified backup for those losses.

## Backup and restore

Stop admission and make the project idle before backup. From the checkout:

```bash
python tools/backup.py backup --config PROJECT_CONFIG backups/dockflow-snapshot
python tools/backup.py verify backups/dockflow-snapshot
python tools/backup.py restore --config PROJECT_CONFIG backups/dockflow-snapshot
python tools/backup.py restore --config PROJECT_CONFIG --apply backups/dockflow-snapshot
```

Use a new backup directory outside state, database and managed artifact roots.
The tool exports one project's journal, source bytes, logs, projections,
numeric aliases and publication records into portable `state.sqlite`, and copies all managed-root
contents with a hashed inventory. Filesystem and S3 snapshots preserve the same
storage-relative layout. Standalone completed publications are checked against
their SQL manifests before a backup succeeds. It supports SQLite and PostgreSQL;
no DSN/credential values or owner diagnostics are added to backup configuration.
Keep provider settings and credential references separately. Keep publishers idle
during backup. Projects with additional publication roots require a coordinated
offline provider snapshot covering every root; this tool refuses to omit them.

Restore requires an empty target project and empty managed artifact locations.
Local state/work locations may differ; durable artifact locations must match.
The database import is atomic and preserves original IDs and the pagination key.
Inspect verification and external-reference availability before restarting work.
An interrupted artifact copy can leave partial storage; preserve/clear that
partial restore explicitly before retrying. The tool never overwrites an
existing project or populated managed store.

Use the SQLite backup API or the database provider's snapshot tooling for native
backups. Do not copy a live SQLite main file without accounting for its WAL.
Persistent Compose state/provider volumes can also be snapshotted together while
stopped. Do not delete those volumes when replacing disposable compute.

## Cleanup

`dockflow pipelines ... clean` previews terminal Run workspaces;
`clean --apply` rechecks idle ownership and removes only disposable execution
work. Neither operation expires the database journal, definitions, logs, pins or
published artifacts. Database migration/schema upgrade is a separate operation;
unknown schema versions fail closed.

## Cache registry authority and backup

Cache registry tables share the configured state database and one schema version.
The execution journal and cache remain distinct commit boundaries, with different
ownership and retry rules, but there is no second database to configure or back up.
The `dockflow-core` library supplies the shared SQLite/PostgreSQL adapter
for history, cache and publication records.

The project backup includes every cache namespace, its entries, attempts, retry
budgets, fences and published manifests in the same consistent SQL snapshot as
history, logs and definitions. It also collects cache-only published bytes and
the artifact store identity. Other projects and operational owner diagnostics
are excluded. Native provider backups may instead preserve the whole database
and matching artifact store.

Stop all workers before restoring an older snapshot. Use a fresh cache namespace
before resuming dispatch so pre-restore producer tokens cannot regain authority.
A project owner does not prove old workers or containers have terminated. Restore
requires an empty project and artifact target, validates cache contents and store
identity, and can target either database backend. Journal replay alone cannot
reconstruct lost fences, retry budgets or bytes.


During concurrent reuse, a committed cache result may become visible before its
producer finishes journal recording. Consumers retain a separate immutable cache
observation and leave the live producer's lifecycle records to its owner. Those
observations are included in project history, rebuild and backup.

## Domain identities

Journal events use numeric sequence keys. Resources use collection/public IDs;
definition source bytes use definition IDs; output sets and cache observations
use attempt IDs; retained log snapshots use attempt ID and stream. These are SQL
domain records with no synthetic filenames or directory hierarchy. Project
identity, pagination and reconciliation metadata use named SQL settings.

This format replaces the earlier file-shaped SQL records. Use fresh state;
no data migration is included. Backup snapshots use the current SQL format and
retain all domain records. Supported bootstrap configuration and artifact payload
locations keep their existing meaning.
