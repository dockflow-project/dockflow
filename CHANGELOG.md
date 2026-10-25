# Changelog

## Unreleased

## 0.2.0

This pre-1.0 release introduces incompatible persisted-state and backup formats.
Use fresh state; no migration from earlier formats is provided. All four packages
share this version, including the new `dockflow-core` library. Artifacts use
separate filesystem/S3 payload storage and one database for durable bookkeeping.

- Establish domain-independent `dockflow-core`; consumers own and version their
  schemas and persistence logic. Preserve one database for Pipelines and Artifacts.
- Supervise scheduler failures and revoke readiness/admission; resolve named
  definitions through the catalog's current pointer, including source rollback.
- Preserve immutable execution choices across coordinators and share terminal
  lifecycle transitions so crash recovery completes Task and Attempt records.
- Reject malformed IR scalars and resource limits before admission; capture
  compiled files with bounded stable reads and reject symlinks/nonregular files.
- Use indexed selective SQL queries for resource pages, queue dispatch, lookup
  and log ranges; validate every derived projection and journal counter.
- Flush filesystem publication ancestors and identity entries, including retries.
  The new database format and required Run choices need fresh state.

- Replace file-shaped SQL state with domain repositories, numeric journal events
  and one resource projection. Remove the optional index wrapper, database import
  facades and historical artifact-layout inference.
- Rebuild definition sources, output sets, cache observations and log snapshots
  from accepted events, detect orphaned projections, and retain stable KFP aliases.
  Integrity reports now use `projections_checked`. The new schema needs fresh state.

- Store artifact publication claims, completion manifests and recovery descriptors
  in the same SQLite/PostgreSQL database as state and cache. Artifact storage
  retains payloads and `.dockflow/storage.json`; no bookkeeping sidecars remain.
- Share generic database adapters and schema coordination through `dockflow-core`;
  each consumer owns its schema and persistence logic.
  Standalone Artifacts accepts explicit database/project configuration; remote
  roots require it. Publication JSON configuration uses schema 2, and receipt
  manifest addresses now identify SQL records. Existing state needs a fresh start.
- Include publication records and the full managed payload root in offline backup,
  validate completed publication checksums, and reject omitted additional roots.

- Preserve SQLite single ownership and add PostgreSQL synchronization across
  isolated coordinators with fenced Run leases, atomic admission and queue claims,
  remote cancellation and Run-scoped recovery. Add exclusive maintenance gates
  and durable journal sequence counters; retain sequential tasks within each Run.

- Use one configured database for execution history and cache coordination on
  both SQLite and PostgreSQL, through a shared backend abstraction and schema.
  Remove separate cache connection settings. Portable project backups include
  all cache namespaces, fencing history, published bytes and store identity.

- Store complete execution history, compiled definitions, logs and query data in
  local SQLite or external PostgreSQL. Disposable environments can share durable
  history through the same project/database. File-history migration is intentionally omitted.
- Add portable SQL state backup/restore, transactional projection rebuild and
  stable database-backed KFP references; remove the native MLMD dependency.

- Coordinate cacheable task production across Dockflow connections
  using local SQLite or shared PostgreSQL, renewable fenced claims, immutable
  complete output sets and durable shared retry budgets.
- Add cache inspection, conditional invalidation and retry reset to CLI/API.
- Isolate new cache keys and storage from legacy writers. Legacy automatic
  results without registry publication are misses; manual historical inputs
  remain available. Coordinated S3 files are limited to 5 GiB. See
  [cache configuration](docs/configuration.md#coordinated-artifact-cache).

## 0.1.1

- Address the eMudhra/emSign CA incident in Python, uv, gRPC, S3 trust defaults,
  and the reference container stack.
- Check actual certificate bundles, including embedded pip/ensurepip and
  cross-signing roots, during CI and service image qualification.
- Preserve explicit custom S3 CA settings and existing registry storage format.
- Publish through the official PyPA v1.14.3 Trusted Publishing action; remove
  the custom publisher wrapper. Keep unchanged specification baseline provenance
  without moving existing tags.

The 0.1.0 publication stopped after the CLI upload. Its vulnerable service
candidate is withdrawn. Version 0.1.1 is the coordinated replacement; publication
remains subject to exact-candidate approval.

## 0.1.0

Initial coordinated release of `dockflow-cli`, `dockflow-pipelines` and
`dockflow-artifacts`. All packages require Python 3.12 or newer; the tested
interpreter matrix is 3.12 and 3.13.

- Execute the supported compiled KFP 2.17 pipeline profile locally with Docker
  or through a persistent REST/browser service without Kubernetes.
- Inspect durable runs, logs, artifacts, lineage and reuse; upload immutable
  pipeline versions through the supported KFP client API subset.
- Publish immutable files and directories to caller-selected filesystem or S3
  paths, and register them through typed KFP importers with the artifact library.
- Install the remote CLI without Docker, KFP or MLMD dependencies.

The qualified execution/service target is Linux x86-64 with Linux containers.
Base-package installation is separately checked on Linux, macOS and Windows.
Native ARM64 execution and Docker Desktop deployments are not qualified by this
release. This is a bounded initial milestone, not full KFP backend parity;
unsupported constructs are rejected. See [compatibility](docs/compatibility.md)
and the runtime `dockflow pipelines capabilities` response.

KFP extras require the documented urllib3 override; ordinary pip resolution
retains upstream KFP's older exact pin. Follow [installation](docs/installation.md).

There is no earlier published Dockflow package release to migrate from.
Experimental source-checkout state is not promised an automatic migration;
back up retained state before switching an existing deployment.
