# Database artifact records: validation

Delivery state: **awaiting_acceptance**. Roles: Definer and Implementer.
Recorded at 2026-10-24 22:30 UTC. Qualification uses the dirty development
branch `feat/distributed-artifact-cache` above source commit
`032444d3686f5951cb0b2457e64a023ded502387`; source bindings below identify the
reviewed files. No commit, publication, baseline finalization or workflow closure
was performed.

## Delivered behavior

One `dockflow-database` library supplies SQLite/PostgreSQL connections, schema,
durability, driver classification, ownership/maintenance primitives and immutable
artifact records. Pipelines retains domain execution/cache behavior and its
existing import facades. Standalone Artifacts imports neither Pipelines nor CLI.

Physical schema 3 includes publication claims, completion manifests, storage
reservations and recovery descriptors. Publication reserves ancestor/leaf paths
atomically, transfers/verifies bytes outside SQL transactions, then commits
completion. Identical retries recover uncertain completion; conflicts fail.
Pipelines record mutations retain the pinned owner and Run fence checks. Independent
publisher transactions respect PostgreSQL exclusive maintenance.

Artifact storage retains payloads, disposable staging and `.dockflow/storage.json`.
Publication JSON configuration uses schema 2; `manifest_uri` is a logical SQL
record address. Filesystem publishers default to SQLite beside their root; remote
stores require explicit database settings. Shared roots require the same project
ID/database. No existing state was migrated or deleted.

Project export includes all publication records in its consistent SQL snapshot.
Filesystem/S3 backups preserve the complete managed hierarchy and verify standalone
publication checksums. Restore uses original relative object keys without descriptor
sidecars. The single-root tool refuses records for additional roots; those projects
require an offline coordinated provider snapshot of the database and every root.

General, Pipelines and Artifacts specification packages receive Major changes
for shared packaging, persisted schema, publication configuration/receipt addresses
and backup compatibility. Finalized project baselines and the application version
are not allocated by these package-version changes.

## Verification

| Check | Result |
| --- | --- |
| Full Python 3.13.17 regression, real PostgreSQL/S3/Docker | 714 passed, 14 skipped, 5 upstream warnings; 137.40 s. |
| Full Python 3.12.15 regression, same providers | 714 passed, 14 skipped, 5 upstream warnings; 139.86 s. |
| Final shared configuration/publication suite, Python 3.13 | 26 passed, 1 backend-specific skip; 2.29 s. |
| Final shared configuration/publication suite, Python 3.12 | 26 passed, 1 backend-specific skip; 2.39 s. |
| Ruff lint/format | Passed; 99 Python files formatted. |
| Pyright | 0 errors, warnings or information messages. |
| Generated API reference | Current. |
| Browser JavaScript tests | 5 passed. |
| Specification composition/imported integrity | Passed. |
| Changed/new Markdown local files and heading links | 61 documents checked; no broken local links. |
| Git whitespace check | Passed. |
| Four wheels/sdists | Clean Database-only, CLI-only, Artifacts-only and combined-base installs; independent sdist rebuilds passed. |
| Final service image | Non-root readiness, UI/OpenAPI, two-step execution, artifacts, reuse, logs and persistent restart passed. |

The full-matrix skips are SQLite parameters for PostgreSQL-only ownership,
concurrency and maintenance checks. Both live standalone S3 publication backend
cases ran. Warnings originate from the upstream Starlette test client and KFP
client compatibility notice. A final guard rejecting malformed backend values
was added after the full matrix; the final shared configuration/publication suites
above cover that code on both interpreters. The package artifacts and service image
were rebuilt and reverified afterward.

Publication cases cover publisher-first schema initialization, shared adapter
identity, read-only snapshots, six independent competing processes, identical and
conflicting producers, immutable namespace claims, interrupted and ambiguously
committed completion, database failure without payload upload, secret-safe errors,
SQL-only bookkeeping, portable project snapshots, corrupt-publication refusal,
additional-root refusal and maintenance contention. Existing full-suite checks
cover execution/cache lease fencing, isolated services, owner crashes, remote
cancellation, cache-only bytes and filesystem/S3 backup/restore. Conditional S3
publication also ran against a real compatible provider with both SQL backends.

Environment: Linux x86-64; CPython 3.12.15/3.13.17; SQLite 3.53.4;
PostgreSQL 18.6; Psycopg 3.3.6; Docker 29.7.2. Package frontend uv 0.13.5;
qualified PEP 517 backend uv_build 0.11.33. Measurements use isolated processes and
containers on one physical host. Physical multi-host, Docker Desktop, native ARM64
and a specific serverless platform are not qualified here.

## Final artifact identities

Service image `dockflow-records:verification` (`linux/amd64`):
`sha256:f646793be7e61625306070aed4214cce7ee0afcbfdaf49e5173a4c2e7a8d9925`.
The sanitized deployment receipt is `dist/records-service-verification.json`;
package identities are also recorded in `dist/verification.json`. These are local
qualification products, not published or approved release candidates.

| Package artifact | SHA-256 |
| --- | --- |
| `dockflow_cli-0.1.1-py3-none-any.whl` | `d431dd3eaec13c91a08abf6c22d94188a639f889f067e9c8c0588f1f6bb1a0f3` |
| `dockflow_pipelines-0.1.1-py3-none-any.whl` | `fae5a140454d15791748e468d733bf887d3709bb0f6528ae79b0724ef70646a0` |
| `dockflow_artifacts-0.1.1-py3-none-any.whl` | `3939acc7ed4dd9b6ec5ff834d1b6344fd545f012885488b732742df21189ff6c` |
| `dockflow_database-0.1.1-py3-none-any.whl` | `7932afe2f814ac23593afde0045858313b64b267aae32e1962783d7cfe5cbd3c` |
| `dockflow_cli-0.1.1.tar.gz` | `91da0d563df0f0379c923b2c26b9b376cb96f2f9b5a7fbccdfe1d4ee6622f39f` |
| `dockflow_pipelines-0.1.1.tar.gz` | `4de5ba65d6a7811e42ee0d0252923f5d8332f61a7bc54ba81dab329111b20663` |
| `dockflow_artifacts-0.1.1.tar.gz` | `844417e5a6ca46a942708c14fb872e97a9def1bbfdb3c9bf3724aaef658d248c` |
| `dockflow_database-0.1.1.tar.gz` | `cab711133996891fa537a197d7f17774277dfc4376a4a1b55c82c01dda279671` |

## Source bindings

| Repository-relative source | SHA-256 |
| --- | --- |
| `packages/database/pyproject.toml` | `d691aa5152195bb920b96b155d6d2c42f157714b81fcf383ac288234a5d68c77` |
| `packages/database/README.md` | `e71f88595d12ca2feadede588bfd4d388c147b1e67890e63d6222ddf2f701466` |
| `packages/database/src/dockflow_database/__init__.py` | `32c15667421405e28f446aea8c981c27b6e326a3f5df067d5d2579cc6f58b890` |
| `packages/database/src/dockflow_database/database.py` | `80298239dcb63e62d73e0106ad80643577ea45ac4f7b6326796035e709ab23ca` |
| `packages/database/src/dockflow_database/database_schema.py` | `44aab2f7efa0542b6699e1a7421879eb34a791d1d04516d3d2c525f0573980d6` |
| `packages/database/src/dockflow_database/errors.py` | `e417a406c4428a14c4b6dc66396a4f044d5bfdbd21aa9a3a194e6ff5b6368743` |
| `packages/database/src/dockflow_database/locking.py` | `714993831cac7916b033a91764af77b038229d6dcee82231fda0b7f0dcec7cbf` |
| `packages/database/src/dockflow_database/records.py` | `cc9c819bc648f45d4a270d1567cc4fbdbdc5fddb029c633806378d9a648bc48f` |
| `packages/database/tests/test_database.py` | `665655ffb367f5da6ee5afc20bc057e554690fd1d06a2e00edd10d1875c5387a` |
| `packages/artifacts/pyproject.toml` | `614ea63d63061cdeef5511aae9ab4d2fb56eeab7d5f0f0a55a9ef1af26e8174d` |
| `packages/artifacts/src/dockflow_artifacts/publication.py` | `23ad3762ecde6c9f4f5784eef4cf0b56ba821d56816f359dadce378fffceed4c` |
| `packages/artifacts/src/dockflow_artifacts/_storage.py` | `84bef24398896490bb4b7efe37fbb9b5b02c1459be7a563aaffac675f2938c74` |
| `packages/artifacts/src/dockflow_artifacts/_paths.py` | `cccdfb0820b77f68cde739fa7f639e4bb576aece0b3abc35e252226788766450` |
| `packages/artifacts/tests/test_publication.py` | `544bfd6f754ecda8d705a93e9b1a945330dc70e8837fe6b737b324120ce878d1` |
| `packages/artifacts/tests/test_s3_integration.py` | `2f96d3784ea9d78cb724179a6046e8ab01c7dfd1bd8a71206794328ab640b376` |
| `packages/pipelines/pyproject.toml` | `d81e5358729d387aec535ea3c065c9158f542294e573056ffdc183f0169fb4ac` |
| `packages/pipelines/src/dockflow_pipelines/database.py` | `58508ff31cfbc33a9e4a3a9ed174afbd6d5d1a0ecd7abe2f43cf507496c6dd97` |
| `packages/pipelines/src/dockflow_pipelines/database_schema.py` | `cd4d642301d426801e20ac61aa90e7babad8885d95222824476a7e4185429a92` |
| `packages/pipelines/src/dockflow_pipelines/errors.py` | `6388c273391b441497f327ce308b4a8d2808048cbad2269deb6f9674d18ed195` |
| `packages/pipelines/src/dockflow_pipelines/ownership.py` | `1a6b9d5a4656283ed4b021294e3f1cff6ccc2de74bfc5e54bdb1e35d0c9193c5` |
| `packages/pipelines/src/dockflow_pipelines/artifacts.py` | `6f47b0449921ee00056eb181a68c934b317351c5490b89f447e407c4a6a49e8c` |
| `packages/pipelines/src/dockflow_pipelines/state_database.py` | `bbd6519e65dc8b6245c3cbbfc8539ac86e192902102aa1d676a6fa02ae040ba3` |
| `packages/pipelines/src/dockflow_pipelines/metadata.py` | `1cb31dd78013f182c2bbabefe9d3a17ebe7e436db4d3cbbe8fb94b1823433539` |
| `packages/pipelines/tests/integration/test_publication_database.py` | `cebef2d0e5fde8f52b210197b6d7db93b7e9d5e4b7534fe8efbb6ccdeb216c18` |
| `packages/pipelines/tests/integration/conftest.py` | `196a570e72b3cdae684a8a31b9bd0ebaeaa6798e352011b8c93db3aa27a84abe` |
| `packages/pipelines/tests/integration/test_artifact_layout.py` | `26879d8186357032ae670e8acef31b7f978a57fcdefd814d98ceb59414a58c07` |
| `packages/pipelines/tests/integration/test_cache_s3.py` | `00d903ba9f65deb5b659fb3c5ecee9ee619b4845f58550109aed533bab07da35` |
| `packages/pipelines/tests/integration/test_s3_artifacts.py` | `ffc74a4086346895c282ee976a98eb1e34a95deb047fee9e720eb341ae18d718` |
| `packages/pipelines/tests/test_owner_bind_mount.py` | `c5db2e71a469b3da07e7af8bfd587efd3ed4bb3a5899b4f831469ac7eb03323d` |
| `pyproject.toml` | `b172ca322864edda86fc9bfafff855a7bb0ab9ddf3c558e971441a7d5ee33d33` |
| `uv.lock` | `3867823189e1be18180dff23cb7d40249ba3517b8f1e593c82d32173df4d48ff` |
| `tools/backup.py` | `60d050f8fa600351e6c9eadd06c0043c8b72e31bad8e103ae9c2675959ca871d` |
| `tools/version.py` | `1018b454e67c230712e9f7a6aa466b141093c785afd91d79dc3dd2cc1fbeb980` |
| `tools/verify_packages.py` | `95957c904a043dd7b1c8ff301ad2c6c7c24bd34783d0eb4f192e3d15baf73d36` |
| `tools/release.py` | `4b509fca68e006630ff47295b601a7d675e059fe5ede96e3f37283829c33cdfe` |
| `deploy/Dockerfile` | `cd47e372502dcc9d4a4f5c0e83acd5111707a4913db461b28bea2e6e8c34bc3d` |
| `.github/workflows/ci.yaml` | `5a8049cc01308e7ade5a162a9da7b1a65056a2a69e4c18cb7e2415111c3ad4e8` |
| `.github/workflows/publish.yaml` | `d3cacd1ada4116b216137a42d58c37af9582c3985874d1a7e8aad1462cee4bbd` |
| `.macrostates/specs/051_dockflow/001_project.md` | `2a8d5ecc4eb46e39b77ca08ef2c9f44d5dc4cf314d1ed9a153c594f66df1ca51` |
| `.macrostates/specs/051_dockflow/003_dependencies-and-build.md` | `d61750982d53f0d5e3835ca71767a675fddec147cd2c104e890c8b30e42c01c5` |
| `.macrostates/specs/051_dockflow/004_releases.md` | `db685940b4e055cdeb4318e1b7c06716882ad053c8c6b66ae6f78e91b6f181ef` |
| `.macrostates/specs/053_dockflow-pipelines/006_artifacts.md` | `ef39976e3d76bf7947cb779717ba0a1ec850c89e835ec2335ddc3d3d069a8ce8` |
| `.macrostates/specs/053_dockflow-pipelines/007_metadata-and-recovery.md` | `f4df9d42ebe7a9334a0ed865d4633e3ee560d88e808a52f65a9d6249f41f28cf` |
| `.macrostates/specs/053_dockflow-pipelines/011_acceptance.md` | `b783b77dffca8ee954abad455cd483be56ff186d3293cbed3dde564d52ed549e` |
| `.macrostates/specs/054_dockflow-artifacts/001_product.md` | `8fd067c2861fb63e943a573896f2be4b7c09accee93f05bd4fd2aebe068d97ca` |
| `.macrostates/specs/054_dockflow-artifacts/002_publication.md` | `d46113693d87c3c492d25a4d57c6644e730c385cbf52aaa766232e7ef97bfcf9` |
| `.macrostates/specs/054_dockflow-artifacts/003_storage.md` | `da9bff1d5a0d03a5ee852d54e17ce4886d9b06ab64a028b3c8ba781f38d2c9fa` |
| `.macrostates/specs/054_dockflow-artifacts/005_acceptance.md` | `f04f2a3186039d5235597fd6edfa545260ea0765fb0a0797a64d83bc7d844aca` |

## Cleanup and limits

Disposable PostgreSQL and S3 test containers were stopped and automatically
removed. The additional Python 3.12 environment and task-specific cache were
removed; pre-existing interpreters and environments remain intact. Service-image
qualification removed its isolated deployment resources. Local verified image
and sanitized distribution receipts remain available for review. Existing project
state, unrelated changes and earlier workflows remain preserved.

The new schema deliberately omits migration. Independent publishers must share
both database and project identity. SQLite stays local; PostgreSQL supplies shared
coordination across isolated hosts. Docker/staging access, worker lifetime,
preemption reconciliation and platform launch/scaling requirements remain as
specified before this change. Moving bookkeeping into SQL does not add automatic
Run resumption or qualify a particular serverless platform.
