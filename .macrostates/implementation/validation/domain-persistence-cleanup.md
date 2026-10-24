# Domain persistence cleanup: validation

Delivery state: **awaiting_acceptance**. Roles: Definer and Implementer.
Recorded at 2026-10-24 23:04 UTC.
Qualification uses the dirty development branch `feat/distributed-artifact-cache`
above commit `032444d3686f5951cb0b2457e64a023ded502387`. Source bindings below
identify the delivered files. No commit, publication, baseline finalization or
workflow closure is included.

## Delivered behavior

The implementation uses domain repositories in the shared SQLite/PostgreSQL
schema. Numeric journal sequences replace synthetic event filenames. Resource
projections have one SQL representation; definition sources use definition IDs,
output sets and cache observations use attempt IDs, and retained log snapshots
use attempt ID plus stream. Project metadata uses explicit names. Journal facts
remain immutable audit history alongside the single current resource projection.

Definition/log events include explicit identities and integrity digests. Mutations
commit their journal sequence, event and projections atomically. Integrity checks
validate domain snapshots and detect orphaned resources. Rebuild clears and
replays domain projections while preserving KFP numeric aliases, publication
records and cache fencing history. Read-only inspection needs no index attachment.

Pipelines consumes `dockflow-database` directly. Both backends retain the existing
ownership model: one local SQLite coordinator and PostgreSQL per-Run fenced
owners with shared maintenance exclusion. The metadata and database layers now
share one reentrant transaction lock. A bounded subprocess reproduces the earlier
opposite lock acquisition order; the current regression permits concurrent log
and resource mutations to finish on both backends.

The audit covered all four installable packages, direct/service/worker adapters,
configuration, cache coordination, artifact publication, recovery, maintenance,
backup/restore, packaging tools and their tests. CLI and standalone Artifacts
retain their supported public contracts; their use of the common database was
checked with clean package installs and the full regression suite.

## Removal and retention manifest

Removed:

- The `dockflow_state_objects` virtual file table, generic state path/read/write
  operations, duplicate resource copy and optional `SQLIndex` layer.
- Pipelines `database.py`, `database_schema.py` and `errors.py` import facades.
  The earlier removed `mlmd_index.py` also stays absent from built wheels.
- File-snapshot events, path-derived Run authority and file-shaped recovery,
  definition, output-set and retained-log identities.
- Optional index initialization/attachment and related read-only setup.
- Alternate runtime settings/definition shapes and implicit cache-side database
  selection outside validated configuration.
- Historical artifact-layout guessing, relocation, redundant content/key tuples
  and obsolete ownership diagnostic fields.
- Metadata identity-helper re-exports, unused version constants, `record` and
  `new_id` method aliases, duplicated terminal states and the unused exclusive
  backup-file write mode. Callers import record helpers from their owning module.

Retained intentionally:

- Actual payload paths, supported `artifacts.root` configuration, explicit current
  `kfp-v2`/`cache-v1` layouts, administrative import/cache payload namespaces and
  `.dockflow/storage.json` store identity.
- Disposable executor/staging files, local SQLite/WAL/SHM/operational lock files,
  bootstrap configuration, filesystem durability helpers and portable backups.
- Explicit refusal of unsupported historical state/layouts. Negative tests name
  old formats to prove rejection; no migration or compatibility reader is added.
- Accepted invocation policies, explicit historical artifact selections, bounded
  KFP compatibility and unsupported-route errors. These remain product behavior.

Physical database schema 4 and backup state format `dockflow-sql-v3` require fresh
state. No existing project data was migrated or deleted. The integrity response
field is now `projections_checked`. The Pipelines specification package receives
a Major change; application `VERSION` and finalized project baselines are unchanged.

## Verification

| Check | Result |
| --- | --- |
| Final full Python 3.13.17 regression, real PostgreSQL/S3/Docker | 725 passed, 14 skipped, 5 upstream warnings; 135.00 s. |
| Final full Python 3.12.15 regression, same providers | 725 passed, 14 skipped, 5 upstream warnings; 140.56 s. |
| Domain persistence suite, both SQL backends | 10 passed. |
| Bounded previous lock-order reproduction | Reproduced; current regression passes. |
| Ruff lint/format | Passed; 97 Python files formatted. |
| Pyright | 0 errors, warnings or information messages. |
| Generated API reference and application version checks | Passed. |
| Browser JavaScript tests | 5 passed. |
| Specification composition/imported integrity | Passed. |
| Changed/new Markdown local files and heading links | 64 documents checked; no broken local links. |
| Authored document/distribution receipt privacy scan | Passed. |
| Git whitespace check | Passed. |
| Four wheels/sdists | Clean Database-only, CLI-only, Artifacts-only and combined-base installs; independent sdist rebuilds passed. |
| Final service image | Non-root readiness, UI/OpenAPI, two-step execution, artifacts, reuse, retained logs and persistent restart passed. |

The full-matrix skips are SQLite parameters for PostgreSQL-only ownership,
concurrency and maintenance checks. Warnings originate from the upstream
Starlette test client and KFP client compatibility notice. Live S3 publication
cases run with both SQL backends. The new domain persistence suite adds rollback,
numeric journal, single projection, snapshot repair, orphan removal, alias
retention and deterministic transaction-lock coverage on both backends.

Environment: Linux x86-64; CPython 3.12.15/3.13.17; SQLite 3.53.4;
PostgreSQL 18.6; Psycopg 3.3.6; Docker 29.7.2; uv 0.13.5 and qualified build
backend uv_build 0.11.33. Providers and services use isolated processes and
containers on one physical host. Physical multi-host, Docker Desktop, native
ARM64 and a particular serverless platform are not qualified.

## Final artifact identities

Service image `dockflow-cleanup:verification` (`linux/amd64`):
`sha256:051a1f136967dd35070c47e7f0ee673b4a3a284c49993d83cb32ef2ccbe97229`.
The sanitized deployment receipt is `dist/cleanup-service-verification.json`;
package identities are also recorded in `dist/verification.json`. These remain
local qualification products; they are not published or approved release candidates.

| Package artifact | SHA-256 |
| --- | --- |
| `dockflow_cli-0.1.1-py3-none-any.whl` | `d431dd3eaec13c91a08abf6c22d94188a639f889f067e9c8c0588f1f6bb1a0f3` |
| `dockflow_pipelines-0.1.1-py3-none-any.whl` | `1db8fe64553d1cb11559fda3244f3c86d40f66c11f4a0e62f9bced34ab9e3b6f` |
| `dockflow_artifacts-0.1.1-py3-none-any.whl` | `3939acc7ed4dd9b6ec5ff834d1b6344fd545f012885488b732742df21189ff6c` |
| `dockflow_database-0.1.1-py3-none-any.whl` | `d5c2f1b391106b9ef225dbceef3a1d17d47dc12437b9cc67805e327f68a7c598` |
| `dockflow_cli-0.1.1.tar.gz` | `91da0d563df0f0379c923b2c26b9b376cb96f2f9b5a7fbccdfe1d4ee6622f39f` |
| `dockflow_pipelines-0.1.1.tar.gz` | `df4ca6b6d0c77c156eecbcc192f3c8905d96267f4fe007049acdc34ccbbd4541` |
| `dockflow_artifacts-0.1.1.tar.gz` | `844417e5a6ca46a942708c14fb872e97a9def1bbfdb3c9bf3724aaef658d248c` |
| `dockflow_database-0.1.1.tar.gz` | `a7f7c63838b0a40487ee31260a3693c3d3a4b69a6de318c7876f99d54290c2d9` |

## Source bindings

The aggregate source binding covers 257 Git-visible regular files under
`packages/`, `tools/`, `tests/`, `deploy/`, `docs/`, `.macrostates/specs/` and
`.github/`, plus `VERSION`, `pyproject.toml`, `uv.lock` and `CHANGELOG.md`.
It is SHA-256 of UTF-8 lines `<file-sha256>  <repository-relative-path>\n`,
sorted by path. Implementation records are excluded to avoid self-reference.
Aggregate SHA-256: `55579487aab3621bc6580e55ad041c86a086009d0211b46ae8c9c051095b7545`.

Key files are also bound individually:

| Repository-relative source | SHA-256 |
| --- | --- |
| `packages/database/src/dockflow_database/database.py` | `e0d3bdb3089dc43ee93342e14453a2d7ff00e050af4fc92660b2efed81894aca` |
| `packages/database/src/dockflow_database/database_schema.py` | `65c9970fad081b107cf3ccb7dd2a6f846e812a9194a3fd71280ce8f34b366a99` |
| `packages/pipelines/src/dockflow_pipelines/state_database.py` | `88ba1ecc3ffee0398d94750d99b4cbf590dd572fcb4a213fce92f57a9839db5f` |
| `packages/pipelines/src/dockflow_pipelines/metadata.py` | `1b794d251281f8d5f8ce71ccab45f995fb8cdf8d477ae5aaef66b437d770a9c5` |
| `packages/pipelines/src/dockflow_pipelines/records.py` | `fe5b99b619663f22c8a50c7a351639abd35f2a216ba1fe2b6f8ff4da235fdf7a` |
| `packages/pipelines/src/dockflow_pipelines/ownership.py` | `abe8b536374e69134fe41aaab58a9592000740a7b04691b9caac878fed9ac2f1` |
| `packages/pipelines/src/dockflow_pipelines/artifacts.py` | `1d851adb4cec34cc0a834393a06b79d7a878c97fad867b8abfb6f0ecdfd05b4f` |
| `packages/pipelines/src/dockflow_pipelines/cache_registry.py` | `b9ebac713fe25881b7797d1729890ede29fc6f145528dfe3efd901957701c389` |
| `packages/pipelines/src/dockflow_pipelines/engine.py` | `f89db64e23126a67943cf6849e27615e518e883a810a32b628305f8e4c80d864` |
| `packages/pipelines/src/dockflow_pipelines/config.py` | `dbd898c0999a4816a8a061a99a89e962016e4bed936deaceb20b3cc5cf2329a1` |
| `packages/pipelines/src/dockflow_pipelines/core.py` | `66f41284249222806cbfce732f32af391a45381a73d9f4b1789c2663de75ba28` |
| `packages/pipelines/src/dockflow_pipelines/service.py` | `a2b6cf3f9d90ab73949d94c7e2fe1633443f35b063a384d58b9c4b657898e9b6` |
| `packages/pipelines/tests/integration/test_domain_persistence.py` | `39979a9a50e35929d67702b3b7d2638129089451126a4dc34a34110c1aa417ef` |
| `packages/pipelines/tests/integration/test_database_state.py` | `971f91b72d961f2ce436de48aa71d4a66c35611a32a2085fd8daaffc0853759a` |
| `packages/pipelines/tests/integration/test_artifact_layout.py` | `bf3163e91250191ae8e3326e44f7f5824d70beb7c51803b4acae67a4bb542cf4` |
| `packages/pipelines/tests/integration/conftest.py` | `a87b170568391b07d0d7b1d2ee0811ee87c26d812bc5d9b84498d953355fd839` |
| `packages/pipelines/tests/test_runtime.py` | `9484bda32bbb45b032462e53c1d7acee8a42ad85238d3d13d7df28c213d8d7b4` |
| `packages/pipelines/tests/test_web.py` | `6618795ccda238dd6317bbf2259a7d7741f84d7b6b6bce82c5ef3ce135ff11a9` |
| `tools/backup.py` | `a423ac575adbab05ab1260e9116f5526afe98f6b3aefaf02b3cdd1b53745f497` |
| `.macrostates/specs/053_dockflow-pipelines/006_artifacts.md` | `b0da78c32c7689a7fa0270daafd5d8cd58f08cf997b94349c73b2b3c7f8e068e` |
| `.macrostates/specs/053_dockflow-pipelines/007_metadata-and-recovery.md` | `2e33b46faf20dcea76169bd5a2291e8106e97a2cec41df9f8383c877345fb079` |
| `.macrostates/specs/053_dockflow-pipelines/010_service-api.md` | `0d16656acf62e8596886e7899299c96d912d32cdcdbbcd957a9689ac0cbe801b` |
| `.macrostates/specs/053_dockflow-pipelines/011_acceptance.md` | `5a43269a2bccc1242890e6243d8a5f67d4f38fd912c6a97d5fe3254fb7ecd9f3` |
| `docs/architecture.md` | `5cdcb884bdb9bc3e59f6d3f76b7ff795df5a7bee2e432a7b4b6ac671fa4e0b3b` |
| `docs/persistence.md` | `e58028622fc773a0faa49b9d2ad498578fa4795d3d54217a536ef24897c19d4f` |

## Cleanup and limits

Disposable PostgreSQL and S3 containers were stopped and automatically removed.
The task-created Python 3.12 environment and temporary source snapshot were
removed; pre-existing interpreters/environments remain. Service-image verification
removed its isolated deployment resources. The local verified service image,
distributions and sanitized receipts remain available for review.
Existing project state, unrelated edits and earlier workflows remain preserved.

This record supersedes current-implementation claims in earlier dated state,
unified-database and artifact-record receipts; those receipts retain historical
observations. PostgreSQL and shared artifacts preserve history across disposable
hosts, but Docker/staging access, worker lifetime, reconciliation after preemption
and launch/scaling requirements remain unchanged. This cleanup adds neither
automatic Run resumption nor a new distributed task scheduler.
