# Concurrent PostgreSQL execution validation

- Date: 2026-10-23
- Roles: Definer; Implementer
- Scope: Dockflow local SQLite ownership and distributed PostgreSQL Run coordination.
- Source: development branch `feat/distributed-artifact-cache`, origin commit
  `032444d3686f5951cb0b2457e64a023ded502387`, with uncommitted work.
- Delivery: awaiting acceptance; no commit, integration, tag or publication.

## Delivered contract

The Pipelines specification package advances to 8.0.0. Finalized repository
baselines and application versions remain unchanged. The existing state.backend
setting selects the coordination model: SQLite retains one local project owner,
Run and task attempt; PostgreSQL permits independent coordinators to execute
different Runs concurrently. Each coordinator dispatches one Run at a time and
tasks remain sequential within a Run. Both use the common database abstraction
and one physical database for state and cache. Artifact bytes remain external.

PostgreSQL sessions hold shared maintenance gates, while short project transactions
serialize durable counters, aliases, admission/idempotency, catalog mutations and
stop/publication ordering. Per-Run database-time leases renew independently;
owner/fence/deadline checks protect execution mutations and cache publication.
Uncertain commits never transparently reconnect an owner. Direct admission reserves
its Run atomically; service workers skip peer claims. Cancellation through a
separate coordinator preserves stop intent against stale worker snapshots.

Recovery claims abandoned Runs, preserves live peer Runs and verifies and retires
recorded handles on their original Docker daemon. Unreachable daemons leave that
Run unresolved, without globally stopping unrelated PostgreSQL execution. Restore,
rebuild and destructive maintenance exclude other coordinators and independent
cache transactions. Portable snapshots retain journal counters, cache observations
and project history; operational Run claims are excluded.

A consumer observing cache commitment before its producer's journal completion
retains an immutable cache observation instead of rewriting that live producer's
Attempt or Task lifecycle. The original owner can then complete normally.
Observation validation, idempotency, rebuild and portable restore are covered.
The fresh database schema is version 2; older schemas fail explicitly and are
not migrated by startup. No existing project history was deleted or ported.

This receipt supersedes PostgreSQL single-owner statements in the earlier dated
[state](database-execution-state.md), [cache](distributed-artifact-cache.md) and
[unified database](unified-database.md) receipts. Their measured results remain
historical evidence rather than claims about this source.

## Measured results

| Check | Result |
| --- | --- |
| Full Python 3.12.15 suite with real Docker/PostgreSQL/S3 | 684 passed, 14 skipped; 132.89 seconds. |
| Full Python 3.13.17 suite with the same provider profile | 684 passed, 14 skipped; 131.08 seconds. |
| Real isolated-service distributed scenarios | All five passed: concurrent success, remote cancellation, owner death/recovery beside a live Run, direct execution beside services, and same-key waiting with one computation. |
| Final protocol/concurrency tests | 12 PostgreSQL cases passed; corresponding SQLite parameters intentionally skip distributed-only behavior. |
| Ruff lint/format and Pyright | Passed; zero typing errors/warnings. |
| Generated API reference and frontend Node tests | Current; all five frontend test files passed. |
| Package verification | Three wheels/sdists built; clean CLI-only, Artifacts-only and combined-base installs passed; all sdists independently rebuilt. |
| Built service image smoke test | Passed non-root readiness/UI/OpenAPI, two-step execution, artifacts, reuse, retained logs and restart history. |
| PostgreSQL from two isolated final-image containers | Simultaneous distinct Run owners, same-Run exclusion, maintenance refusal and retained history/logs passed. |
| Composition/import integrity, documentation links and whitespace | Passed. |

The interpreters used SQLite 3.53.1; PostgreSQL was 18.6, Psycopg 3.3.6 and
Docker daemon 29.7.2. Real S3 tests used the disposable Dockflow MinIO image.
The final service image was
`sha256:264aacd2cd7fe24fc03261b211c77467b2a35109310ba065531b912ebcbb7a70`
on `linux/amd64`. Its runtime/system certificate audits passed.

Each full run emitted five upstream HTTP-client/KFP compatibility warnings.
Twelve skips are SQLite parameters for PostgreSQL-only distributed tests; one is
the existing PostgreSQL session test's SQLite parameter; one is the separately
configured Artifacts-library S3 publisher test. Pipelines' real S3 execution,
publication, backup and restore tests ran. The full suites include all new
runtime and protocol cases; additional image-container probing is separate.

## Coverage and reproduction

Run `pytest -q` with DOCKFLOW_TEST_DOCKER enabled and disposable providers selected
through DOCKFLOW_TEST_STATE_POSTGRES_DSN, DOCKFLOW_TEST_CACHE_POSTGRES_DSN,
DOCKFLOW_TEST_CACHE_S3_ENDPOINT and synthetic S3 credential variables. The two
PostgreSQL fixture variables may select the same database and do not represent
separate product databases. Both supported Python interpreters used the locked
all-package/all-extra environment.

`integration/test_concurrent_runs.py` covers shared coordinators, unique Run
claims, expiry/takeover, stale writes and renewal failure, remote cancellation,
transactional sequences/admission/idempotency, queue capacity, independent process
admission and crash recovery, direct reservation, cache publication rollback on
expiry/heartbeat failure, maintenance/cache contention, and live producer cache
observations through completion/rebuild/restore. Existing ownership tests retain
exclusive-maintenance and SQLite exclusion checks.

`test_distributed_runtime.py` launches actual independent service processes with
different state/work roots, common PostgreSQL/S3 and real Docker tasks. It starts
a second service while the first Run is live; checks simultaneous execution;
cancels a Run through its peer; kills an owner/worker process group and recovers
only that Run while another continues; executes a directly reserved Run beside
services; and verifies same-key waiting, one actual computation, subsequent reuse,
artifact identity and consistent history. Full suites retain official KFP client,
service restart, artifact, provider-fault and SQLite runtime regressions.

Package and standard image qualification use tools/verify_packages.py and
tools/verify_service_image.py. The additional disposable image protocol probe ran
two independent final-image containers against the same PostgreSQL project,
checked simultaneous authority/exclusion and persisted logs, then removed them.
Temporary providers and the extra interpreter environment were removed after
qualification. Retained receipts contain no private project, personal identity,
machine diagnostics or local absolute paths.

## Limits

Measured distributed execution uses isolated processes/containers on one host;
physical multi-host deployment, Docker Desktop and additional native platforms
remain unqualified. Isolated hosts require a durable PostgreSQL primary, common
artifact access, suitable session connections and reachable Docker daemons.
An abandoned Run whose original daemon is unavailable remains unresolved.
One Run per coordinator and sequential tasks per Run remain the initial bounds.
No schema migration, automatic rerun of abandoned computation or distributed task
fan-out is included.

## Source binding

SHA-256 values bind the runtime, tests and owning contracts used for this delivery.

| Repository-relative source | SHA-256 |
| --- | --- |
| `packages/pipelines/src/dockflow_pipelines/database.py` | `1f69714ec162930022f3659a09fbb869fbabec4294db2ff126e67f34225e6de6` |
| `packages/pipelines/src/dockflow_pipelines/database_schema.py` | `ba2a61299bbba31cbea57de2b0201f44c8c0baa4566667152512cba690fdedaf` |
| `packages/pipelines/src/dockflow_pipelines/run_ownership.py` | `8b124916c3512b23b55d0a7db109960f5ba13b9cbc72db820b4950bc4e5e3ca4` |
| `packages/pipelines/src/dockflow_pipelines/state_database.py` | `0003b1754c90ef963b9c319f94f2ec77a121a14450dc44efcb87ea1b9205d0b0` |
| `packages/pipelines/src/dockflow_pipelines/metadata.py` | `4be5e1aa7cc0944f981d50c575b3ef1263980b139d45bf5f5a065c997b218c99` |
| `packages/pipelines/src/dockflow_pipelines/cache_registry.py` | `56938f3cb31ca9494a9df343a026c74e2668d213d197a72cf0804e8138c43257` |
| `packages/pipelines/src/dockflow_pipelines/cache.py` | `768b877afd9479bfce1ea33bb7eecbe7412dedc0d89c5c159dcfa151183b5301` |
| `packages/pipelines/src/dockflow_pipelines/cache_storage.py` | `7af4d5bce2a4491865126a903c98f51e74b5e8e0c4274c8b7071d1776a57fae5` |
| `packages/pipelines/src/dockflow_pipelines/core.py` | `8e0a1c30138f9c00b13539932643140c95c3ec0b3b6b4aa8f5732231716789de` |
| `packages/pipelines/src/dockflow_pipelines/engine.py` | `091b7df90862e5e74bc5afc31dd9f4edb9bee64440d6d1b9b5bb7c40ff843aa6` |
| `packages/pipelines/src/dockflow_pipelines/service.py` | `2961aaedfad213f847093afd1c0916ce1e3de9c1a08690a2912eb1cb96881d69` |
| `packages/pipelines/src/dockflow_pipelines/cli.py` | `2debd6670e99320f20e6c2ff7accef73a396d5f5a0389a540b18c8bf67e3b473` |
| `packages/pipelines/src/dockflow_pipelines/config.py` | `735e95bb133acdc71f12eda847dfc2b0f6373958d5d3466e0d1c58e57b58a950` |
| `packages/pipelines/src/dockflow_pipelines/artifacts.py` | `519f0e3be6c9b1a2fc94c0bdf834b3afa034a388b7d942a18ba1ac7459373c8a` |
| `packages/pipelines/src/dockflow_pipelines/executor.py` | `555799c6cd75dc573a8a2cfed6d75e1e2a1868a7f65093bfc639e0c8ab1391fc` |
| `packages/pipelines/src/dockflow_pipelines/operations.py` | `f99e28781286ae8d0c9b006118a272329e46e30d81da3faad7fb6fc90ece8915` |
| `packages/pipelines/src/dockflow_pipelines/ownership.py` | `c9e7572be3d211522f5c50fb942450bedca076c3eb121664ca147dcf1377f30e` |
| `tools/backup.py` | `c006ac9c8c6ae61de744644aaf7c058860d1cd7666883a6f5ef357b3263d7d97` |
| `packages/pipelines/tests/integration/test_concurrent_runs.py` | `22652a4d5327a2e6d0f6ae835aa1fa4501500bc6fcd42e29196072966a18db3b` |
| `packages/pipelines/tests/integration/test_ownership.py` | `ea52a98db0a3c3e8ade262eca45796556e3463e6a13667a8760d85ec9d7b0b8c` |
| `packages/pipelines/tests/integration/test_database_state.py` | `0061278db47c36b6ad59d2920b03ef2b2f39ed185c639eeefa6d4d5b84a8a4bf` |
| `packages/pipelines/tests/integration/test_unified_database.py` | `a89a04a3023bd9d0b1ce96d3c6cfcb6f07635dc8f6b3f9573d68aa9e3cf4cee4` |
| `packages/pipelines/tests/integration/conftest.py` | `bf2e80c089d8f537414b2b5303061f855921a0430f1bce55884d74f223f8dae9` |
| `packages/pipelines/tests/test_distributed_runtime.py` | `52d6ffe1aa02d6d7d38bdf0330691e02b789b85b3fcfc19d607768f61cff8fb5` |
| `packages/pipelines/tests/test_service_runtime.py` | `1fcacb1b74d8b66c08503c411238853a34210b5a106c1d0e476a153859389a65` |
| `packages/pipelines/tests/unit/test_config.py` | `dbccfcd8c1fafe907ed1e228a8cda392661ce94092247359215f7246dbca2b8b` |
| `.macrostates/specs/053_dockflow-pipelines/001_pipelines.md` | `a9422dfb15a4b90acb0f83a3758256ff9dd3503c2474aed118a30e92e7ec51d3` |
| `.macrostates/specs/053_dockflow-pipelines/002_local-execution.md` | `f0fe40282fb6e4eaeff9e4d0d25d0e2eac0bd73a6a7104a81a4cc049b63a28e3` |
| `.macrostates/specs/053_dockflow-pipelines/003_configuration-and-backends.md` | `b2b42f0401ba637dc397c92dbd91a51032cf034fc0e66bf1df31895c509bb139` |
| `.macrostates/specs/053_dockflow-pipelines/005_execution-and-lifecycle.md` | `8e85c6cd803141dd7e86c0e8cf76ada2ae8e09e11767116633255089b7b1c983` |
| `.macrostates/specs/053_dockflow-pipelines/007_metadata-and-recovery.md` | `bdcd87d1d62f7571583705fa39ae831b67340694d2cde874d3137426fc4be072` |
| `.macrostates/specs/053_dockflow-pipelines/011_acceptance.md` | `0d6f5ed61f093b4faf90bcca9a135e397320c65146ebb556a741faf34d5f26b7` |
| `.macrostates/specs/053_dockflow-pipelines/014_cache-coordination.md` | `1c4ab97ef0b011229b9e1c2fd3f58ea19fa7dc0b95e736ac431368dabb927e62` |
| `.macrostates/specs/053_dockflow-pipelines/package.yaml` | `20befa6ce7a109a9a0e92da920933b0da4a15861bbd0e20f676ca63d17e936a4` |
