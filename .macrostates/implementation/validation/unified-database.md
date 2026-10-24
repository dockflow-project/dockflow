# Unified database validation

- Date: 2026-10-23
- Roles: Definer; Implementer
- Scope: Dockflow shared database abstraction, schema, configuration and recovery.
- Source: development branch `feat/distributed-artifact-cache`, origin commit
  `032444d3686f5951cb0b2457e64a023ded502387`, with uncommitted work.
- Delivery: awaiting acceptance; no commit, integration, tag or publication.

## Delivered contract

The Pipelines specification package advances to 7.0.0 for removal of independent
cache connection configuration. Finalized repository baselines and application
versions remain unchanged. `[state]` selects the only physical database:
`.dockflow/state.sqlite` by default, or PostgreSQL through one DSN environment
reference. `[cache]` contains policy only; former connection fields and their
environment overrides are rejected. Existing split databases are deliberately
not migrated.

`database.py` provides the common backend abstraction for connection setup,
dialect, durability, schema, transactions, clocks, row locks, ownership primitives
and driver failure classification. `database_schema.py` defines one atomic
versioned schema. State and cache repositories use the same adapter classes and
connection options, while retaining their respective transaction policies. State
ownership remains pinned and fails closed on uncertain commits. Cache operations
use independent short connections and retain idempotency, leases and fencing.
One active coordinator/Run per project remains the execution contract.

Project export uses a consistent SQL snapshot covering history and every cache
namespace, including attempts, fences, retry state and manifests. It excludes
other projects and owner diagnostics. Portable SQLite exports restore into both
backends. Artifact backups include cache-only published bytes and store identity;
restore verifies both. Artifact bytes remain outside SQL. Stop workers and use a
fresh cache namespace when restoring older history; ownership alone does not prove
surviving workers or containers have stopped.

This receipt supersedes split connection and backup behavior described in the
earlier dated [state](database-execution-state.md) and
[cache](distributed-artifact-cache.md) receipts. Their earlier measurements remain
historical evidence rather than claims about the current source.

## Measured results

| Check | Result |
| --- | --- |
| Full Python 3.12.15 suite with real Docker, PostgreSQL and S3 | 660 passed, 2 skipped; 77.54 seconds. |
| Full Python 3.13.17 suite with the same providers | 660 passed, 2 skipped; 76.39 seconds. |
| Focused shared snapshot and real S3 backup/restore tests | 16 passed before the final full matrix. |
| Ruff lint/format and Pyright | Passed; zero typing errors/warnings. |
| Generated API reference | Current. |
| Frontend Node tests | All 5 test files passed. |
| Package verification | Three wheels and sdists built; clean CLI-only, Artifacts-only and combined-base installs passed; all sdists independently rebuilt. |
| Service image smoke test | Passed readiness/UI/OpenAPI, two-step Docker execution, artifacts, reuse, logs and restart history. |
| PostgreSQL from the built service image | Shared schema, cache progress under pinned state ownership and fresh-environment retention passed. |
| Composition/import integrity, local documentation links and Git whitespace | Passed. |

SQLite was 3.53.1 on both interpreters, PostgreSQL 18.6 and Psycopg 3.3.6.
The Docker daemon was 29.7.2; real S3 tests used the disposable Dockflow MinIO
image. The service image was
`sha256:1ab43f476303f551189812953c367236dd38b1e73dc8d59417dba4e93c87e2ec`
on `linux/amd64`. Its runtime and system certificate audits passed.

Each full run emitted five upstream HTTP-client/KFP compatibility warnings.
Skips are the PostgreSQL-specific session test's SQLite parameter and a separately
configured Artifacts-library publisher S3 test. Pipelines' actual S3 publication
and backup/restore tests ran on both state backends.

## Reproduction and coverage

Run the full `pytest -q` suite with disposable providers selected through
DOCKFLOW_TEST_DOCKER, DOCKFLOW_TEST_STATE_POSTGRES_DSN,
DOCKFLOW_TEST_CACHE_POSTGRES_DSN and DOCKFLOW_TEST_CACHE_S3_ENDPOINT plus synthetic
S3 credentials. The two PostgreSQL test variables can select the same disposable
database; they only select fixture providers, not separate product connections.

`integration/test_unified_database.py` exercises both initialization orders,
cache progress while state ownership is held, fresh staging roots, every cache
namespace, project isolation, nonempty-target protection, split-schema rejection,
concurrent cache commits during snapshot export and portable restore into each
backend. `integration/test_cache_s3.py` tests backup and restore of bytes published
without a journal artifact record and preservation of the actual store identity.
Existing ownership, cache concurrency/fault, database-state, service-worker and
runtime suites remain enabled. Build/image checks use `tools/verify_packages.py`
and `tools/verify_service_image.py`; the service verifier cleans its own stack.
Temporary providers and the task's extra Python environment were removed after
validation. No external project, personal identity or local absolute path is
retained in this receipt.

## Limits

Physical multi-host deployment, Docker Desktop variants and additional native
platforms remain unqualified. PostgreSQL still needs a durable primary and common
artifact access. SQLite remains local-filesystem/one-host only. No legacy schema
migration or distributed execution scheduler is included. Cache publication and
journal commits remain separate recovery boundaries inside the same database.

## Source binding

SHA-256 values bind the runtime, tests and owning contracts used for this delivery.

| Repository-relative source | SHA-256 |
| --- | --- |
| `packages/pipelines/src/dockflow_pipelines/database.py` | `77a07182eeae5ee96903b158561a6bdd6259d0b6c0cc19a52c9b1c68089d4a5f` |
| `packages/pipelines/src/dockflow_pipelines/database_schema.py` | `7c7006372e0f05823bd1328735b8266e511eeb78b5f1642854bf71e4cac3a8ec` |
| `packages/pipelines/src/dockflow_pipelines/state_database.py` | `4f749b1105f228eb72ff00cfb091294d0a046eace2ff77375124709e18bc0df3` |
| `packages/pipelines/src/dockflow_pipelines/cache_registry.py` | `fbecd820fae03cfa287d86f5d264c85dff77cd7247ec0c96bbbbff3dc8417462` |
| `packages/pipelines/src/dockflow_pipelines/cache.py` | `768b877afd9479bfce1ea33bb7eecbe7412dedc0d89c5c159dcfa151183b5301` |
| `packages/pipelines/src/dockflow_pipelines/cache_storage.py` | `7af4d5bce2a4491865126a903c98f51e74b5e8e0c4274c8b7071d1776a57fae5` |
| `packages/pipelines/src/dockflow_pipelines/config.py` | `249e7aecb0434dd5357ad4a5e2c8bb197ea0c3529e68670b1e3cb7dbfa000a05` |
| `packages/pipelines/src/dockflow_pipelines/core.py` | `076e7f45382a91bfe3b4c22f82a1149e57fcf0a82ddf34331f2e7e2019f68095` |
| `packages/pipelines/src/dockflow_pipelines/engine.py` | `869673e3ef037174c3671d28cc5b6c43eb2aa278c0b852df1a0c00cb0e25836d` |
| `packages/pipelines/src/dockflow_pipelines/metadata.py` | `af60f44871d9d8c2a0d1e934d307db51371bae5c65f7ae81d1ca27d4189af899` |
| `packages/pipelines/src/dockflow_pipelines/artifacts.py` | `519f0e3be6c9b1a2fc94c0bdf834b3afa034a388b7d942a18ba1ac7459373c8a` |
| `packages/pipelines/src/dockflow_pipelines/ownership.py` | `c9e7572be3d211522f5c50fb942450bedca076c3eb121664ca147dcf1377f30e` |
| `packages/pipelines/src/dockflow_pipelines/operations.py` | `f99e28781286ae8d0c9b006118a272329e46e30d81da3faad7fb6fc90ece8915` |
| `tools/backup.py` | `29b5bc520dd9fe88901d13e70575f6938319c14520c7baee622d772229cc65f2` |
| `packages/pipelines/tests/integration/conftest.py` | `9aed907c9057b8c87ba75b48167bf5ec00c138364c3c4b8bd270c236010d925e` |
| `packages/pipelines/tests/integration/test_cache_registry.py` | `c5f39e1a923793ccd223f3a1f64020064825a89284001296d3ee4d1ed93c0597` |
| `packages/pipelines/tests/integration/test_cache_execution.py` | `f16777ef638ebde3f337cf7d1653f19c8a8e7a20cd313a83304e49e5992d880b` |
| `packages/pipelines/tests/integration/test_cache_s3.py` | `70f05f0aadba747d38298f3ba74bcb45b659f96b9386f667e2b5e02eb029c9a2` |
| `packages/pipelines/tests/integration/test_database_state.py` | `b8cc8f901c1fbf6546142542577defeed0a12bfffbb6e9a6c3bfc2d5df4de0f6` |
| `packages/pipelines/tests/integration/test_unified_database.py` | `1100036d6f823d8028e1e2d79f7773163cab42ec3ff87d4ba03ac74696ae646c` |
| `.macrostates/specs/053_dockflow-pipelines/003_configuration-and-backends.md` | `2c1da395f252c20aad0c38845a757d7c35275a55efbfc3bb3b3f6f9fc6c19906` |
| `.macrostates/specs/053_dockflow-pipelines/005_execution-and-lifecycle.md` | `d672da6c984f7c33affe2a9dd2011c531c3ba46ea7b075f4150d049af23dd3d0` |
| `.macrostates/specs/053_dockflow-pipelines/006_artifacts.md` | `8d81341235fc56510dcde93a3c13a335bf0a27c4f0285133b1cdd8e72fcfc0b9` |
| `.macrostates/specs/053_dockflow-pipelines/007_metadata-and-recovery.md` | `a3145ee6b9ee904165e3fe701f688a87edaab39e8fb72166948e7d23f9cbcf7e` |
| `.macrostates/specs/053_dockflow-pipelines/011_acceptance.md` | `8a997e8fb71ab3f90febb9662dc0b1c2330525cb2084f29fa770d13a58b222a2` |
| `.macrostates/specs/053_dockflow-pipelines/014_cache-coordination.md` | `1007c9210dec283126fe65e9a599ff9be14bcd367e7f78fbf772505e9e7630ed` |
| `.macrostates/specs/053_dockflow-pipelines/package.yaml` | `87c3d157fd643b69454198e62d4f6bc18c34d884664e4c27be2c019740c4f8f1` |
