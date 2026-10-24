# Database execution-state validation

- Date: 2026-10-23
- Roles: Definer; Implementer
- Scope: Dockflow database-authoritative state and existing combined-tree regressions.
- Source: development branch `feat/distributed-artifact-cache`, origin commit
  `032444d3686f5951cb0b2457e64a023ded502387`, with uncommitted work.
- Delivery: awaiting acceptance; no commit, integration, tag or publication.

## Delivered contract

The Pipelines local specification package advances to 6.0.0 for the breaking
persistence-authority/configuration change. Finalized repository baselines and
application versions are unchanged. SQL owns journal, resource queries, exact
compiled sources, logs, queue/idempotency, pagination and artifact provenance.
SQLite defaults to `.dockflow/state.sqlite`; PostgreSQL holds shared complete
history without durable local history mounts. Native MLMD is removed. Existing
file history is explicitly rejected and intentionally not migrated.

One project/database still admits one active coordinator/Run. SQLite uses local
OS exclusion on its database inode; PostgreSQL uses a pinned advisory-lock session.
Mutations and projections share SQL transactions. Uncertain COMMIT responses
poison mutation authority/readiness until fresh acquisition and reconciliation.
Docker recovery verifies the original daemon and retires stopped handles.
Artifact contents remain filesystem/S3 data. An omitted PostgreSQL cache backend
and DSN reference derive from state; explicit cache settings retain precedence.

## Measured results

| Check | Result |
| --- | --- |
| Full Python 3.12.15 suite, real Docker/PostgreSQL/S3 enabled | 641 passed, 2 skipped; 69.85 seconds. |
| Full Python 3.13.17 suite, same provider profile | 641 passed, 2 skipped; 72.02 seconds. |
| Final schema-completeness/persistence/restore regressions on both interpreters | 90 passed, 1 PostgreSQL-only SQLite-parameter skip. |
| Frontend Node tests | 5 test files passed; existing graph amendment preserved. |
| Ruff lint/format and Pyright | Passed; zero typing errors/warnings. |
| Generated API reference | Current. |
| Macrostates CLI 0.5.0 | Composition/imported integrity checks passed. |
| Package verification | Three wheels/sdists built; clean CLI-only, Artifacts-only and combined-base installs passed; all sdists independently rebuilt. |
| Service image build and smoke test | Passed; non-root readiness, packaged UI/OpenAPI, two-step Docker execution, publication/reuse, retained logs and persistent-history restart. |
| Cleaned Python 3.13 environment after removing MLMD/gRPC | 25 certificate/optional-import boundary tests passed. |
| Local documentation links and Git whitespace checks | Passed. |

SQLite was 3.53.1 on both interpreters, PostgreSQL 18.6, Psycopg 3.3.6,
KFP 2.17.0, Docker SDK 7.2.0 and Docker daemon 29.7.2. Real S3-compatible tests
used the Dockflow MinIO development image; Boto3 was 1.43.114.
The full-suite counts precede the final schema-completeness guard; the additional
affected-suite runs cover that guard and affected persistence/restore behavior on both
interpreters. The PostgreSQL missing-table observation was additionally rerun
after its non-destructive failure injection was finalized. Package and service
image verification bind the final source.

Five warnings on each full run originate in the upstream HTTP test client and
KFP SDK compatibility notice. Skips are the PostgreSQL-specific session test's
SQLite parameter and a separately configured Artifacts-library publisher S3 test.
Pipelines' real S3 cache tests ran.

The rebuilt service image was
`sha256:f95227f5ea9634ee7e489cce6e5aec2fc4eb4435ebf06bb2d75e97fb3c091f9a`
for `linux/amd64`. Its certifi, provider fallback, interpreter bootstrap and
system trust bundles passed the certificate audit. gRPC is no longer mandatory;
its version floor and bundle audit remain active whenever it is installed.
Both absent-optional and installed-distrusted-bundle regressions pass.

## Coverage and reproducibility

Run `pytest -q` with the following explicit disposable-provider profile (supply
local test endpoints and synthetic credentials through the environment):

- `DOCKFLOW_TEST_DOCKER=1`
- `DOCKFLOW_TEST_STATE_POSTGRES_DSN` for a disposable PostgreSQL database.
- `DOCKFLOW_TEST_CACHE_POSTGRES_DSN` for a disposable registry database.
- `DOCKFLOW_TEST_CACHE_S3_ENDPOINT` and standard synthetic S3 credential variables.

`integration/test_database_state.py` covers fresh-environment catalog/history,
source/log retention, queue/idempotency, pagination, artifact availability,
portable export/import across backends, unknown/foreign schemas, legacy-history
rejection, orphan/empty-target protection, lazy configuration and secret omission.
`integration/test_ownership.py` covers actual independent-process contention,
normal/crash release, rollback, project isolation, nested threads, PostgreSQL
session termination/takeover, unsafe file types, diagnostic filtering,
consistent read snapshots and lost COMMIT responses. Persistence/registration
regressions test atomic complete-set/catalog commits, source recovery, corruption,
backup/restore and rebuild. Real service-worker tests use the official KFP client
against both SQLite and PostgreSQL. Existing cache contention/fencing/provider
fault suites remain enabled.

Build verification uses `tools/verify_packages.py`. Image qualification uses
`deploy/Dockerfile` and `tools/verify_service_image.py`; the latter cleans its own
disposable stack. No external project, personal identity, machine diagnostic or
absolute local path is retained here.

## Limits

- Physical multi-host deployment, Docker Desktop variants and additional native
  execution platforms remain unqualified. Separate local processes/containers
  and real provider services are not advertised as physical multi-host evidence.
- This feature preserves serial project ownership; it adds no distributed task
  scheduler or exactly-once component side-effect guarantee.
- SQLite requires supported local filesystem semantics. PostgreSQL execution
  ownership uses a pinned session and must not pass through transaction pooling.
- Unfinished execution requires access to its original Docker daemon. A new daemon
  cannot declare old containers stopped. Terminal history remains portable.
- Filesystem artifact URIs require stable shared mount locations; PostgreSQL does
  not move bytes. S3-compatible storage is available for shared durable contents.
- Project backup does not quiesce/back up the entire shared cache. Cache-wide
  backup/restore retains its independent contract. No file-history migration,
  automatic schema upgrade, MySQL backend or physical database corruption repair
  is claimed.
- Collection filtering/log selection still materialize retained records before
  paging; no large-scale SQL query-performance qualification is claimed.

## Source inventory

These hashes identify the delivered persistence/provider boundary and locked
runtime inputs independently of uncommitted Git status.

| Repository-relative source | SHA-256 |
| --- | --- |
| `packages/pipelines/pyproject.toml` | `9d4ef96c2b18dc67bf9ed91df7697d3a5895119032b19eb1f70f560a0973fdac` |
| `packages/pipelines/src/dockflow_pipelines/__init__.py` | `64a580d8c415e8b1f75f349d3b545f8808910674a5c601a4ebb8f3437e5522a2` |
| `packages/pipelines/src/dockflow_pipelines/artifacts.py` | `519f0e3be6c9b1a2fc94c0bdf834b3afa034a388b7d942a18ba1ac7459373c8a` |
| `packages/pipelines/src/dockflow_pipelines/cache.py` | `768b877afd9479bfce1ea33bb7eecbe7412dedc0d89c5c159dcfa151183b5301` |
| `packages/pipelines/src/dockflow_pipelines/cache_registry.py` | `0ed0f532bad14607b0af14bbc3f5b2d44cf00f24c59276e69846a9bcf4868c68` |
| `packages/pipelines/src/dockflow_pipelines/cache_storage.py` | `3b9570d7068029d780ff9d4fa71f690c0f4f93166e4dceac294ac9d3baea56c7` |
| `packages/pipelines/src/dockflow_pipelines/canonical.py` | `d4633592fb3e5cc37b8060583617dd6f6af162239fef76988bb2cd3dece081f5` |
| `packages/pipelines/src/dockflow_pipelines/cli.py` | `3f5f7081a45d6a26a344b7bc71b4c10b4c099da6d845ea87b10dd8cdd670e2ae` |
| `packages/pipelines/src/dockflow_pipelines/client.py` | `d7c0fd006ee1569f76f2a4769d3bc0dd3190388eddaf582a9f5e52e438565c04` |
| `packages/pipelines/src/dockflow_pipelines/config.py` | `f043d7c3543295bdf1d3d1b6f156e50d96aa2474741957c94b1dc6d81c0cd1a0` |
| `packages/pipelines/src/dockflow_pipelines/console.py` | `5f808972ca5dfaa3618488ed13e12e02961505a7c30b01863eeff81b2c8f4157` |
| `packages/pipelines/src/dockflow_pipelines/container_logs.py` | `1f5f2ca8e296c68fde512dcbc7b228b6231ef11c8523d245750f9e70fc45207f` |
| `packages/pipelines/src/dockflow_pipelines/core.py` | `749604f89b5349828ecc2055378383904bf29d80c5d9c76298eb2652eea90724` |
| `packages/pipelines/src/dockflow_pipelines/definitions.py` | `555e59e5b7dc93accdd8a756165cd7e570161d1f6ef307968f2c1724fb7e6b46` |
| `packages/pipelines/src/dockflow_pipelines/engine.py` | `623307b083e05dd0e23fa3ea3ae7bbb04a5543fd28f8be1f0983c8abb6ea0677` |
| `packages/pipelines/src/dockflow_pipelines/errors.py` | `e417a406c4428a14c4b6dc66396a4f044d5bfdbd21aa9a3a194e6ff5b6368743` |
| `packages/pipelines/src/dockflow_pipelines/executor.py` | `555799c6cd75dc573a8a2cfed6d75e1e2a1868a7f65093bfc639e0c8ab1391fc` |
| `packages/pipelines/src/dockflow_pipelines/kfp_api.py` | `9afd5840cab4dcddd92a780ca77a305f08fa075a09134d5542ced635d9fe3090` |
| `packages/pipelines/src/dockflow_pipelines/metadata.py` | `1dcc8dce9e5a2fd3190e8efd643f9167f41d6b41deb13dcc8178f70058224bbc` |
| `packages/pipelines/src/dockflow_pipelines/openapi.py` | `1676053267817e2dc5bea7defe4aec44c393263b0e5cda87d3c3a266992e78b0` |
| `packages/pipelines/src/dockflow_pipelines/operations.py` | `f99e28781286ae8d0c9b006118a272329e46e30d81da3faad7fb6fc90ece8915` |
| `packages/pipelines/src/dockflow_pipelines/ownership.py` | `c9e7572be3d211522f5c50fb942450bedca076c3eb121664ca147dcf1377f30e` |
| `packages/pipelines/src/dockflow_pipelines/records.py` | `ae4aa92ef35ec14547d24752d059fdf068fe07d95e5c65f6954e1b50e13f6cc5` |
| `packages/pipelines/src/dockflow_pipelines/reuse.py` | `db5188237d29a093c9881ede92e952fd5f3ffa7783fe4045928e3437bd47feb2` |
| `packages/pipelines/src/dockflow_pipelines/service.py` | `1f3f30298337dcc7479788082d7aa377d93c74bc9c8736bc664fc4ea6bde8e1d` |
| `packages/pipelines/src/dockflow_pipelines/state_database.py` | `b6a936c6126e88c6a0f71556b9d1e3614dbd94b4aa7e5512e3e7dc0251673cb0` |
| `packages/pipelines/src/dockflow_pipelines/web.py` | `79e6a4d04cf153abf76de9f53889610af8d148fcd98ba0ee7ab7d889b245b742` |
| `tools/backup.py` | `f5829ae4d096f0c4e7747bf3ca1288d8fab5c7feeaffd1092a34d77d40a5e6a0` |
| `tools/check_ca_trust.py` | `ccfb676338a1a577e1a3e4249c13b4081fb0993553db50e9c2b3407467492dcf` |
| `uv.lock` | `218eca087a3a8f973a6939577bcb2627b4ce153de72a8a1352ae5a96fdcb3045` |
