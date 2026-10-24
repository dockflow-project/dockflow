# Conformance corrections qualification

Roles: Definer and Implementer. Qualification date: 2026-10-24 UTC.
Target: the dirty `feat/distributed-artifact-cache` checkout above commit
`032444d3686f5951cb0b2457e64a023ded502387`. This record covers all eight findings
and every design recommendation in the specification conformance review.
Earlier review and cleanup receipts retain their historical observations.

## Contract and implementation

| Finding | Correction and evidence |
| --- | --- |
| F1: dead scheduler readiness | Complete scheduler supervision revokes readiness and native/KFP admission on queue, periodic-recovery or process-start failure. Accepted work remains queued for explicit restart. |
| F2: named source rollback | Remote name resolution refreshes the catalog and follows its current definition pointer. A/B/A retains history while direct resolution and remote CLI admission select A. |
| F3: accepted execution settings | Frozen versioned `ExecutionChoices` retains timeout, grace, resource caps, image pull, reuse/task/cache policies and logical mounts. Execution binds current provider/database access and work paths; incompatible caps/mounts fail explicitly. SQLite and PostgreSQL tests read the accepted value through another Core instance. |
| F4: recovery lifecycle | Shared lifecycle functions merge stop intent and finish normal/recovered Runs. Recovery terminalizes running Tasks, blocks pending work and preserves committed successful Attempts/Tasks and parameters. Unconfirmed handles retain recovery holds. |
| F5: scalar admission | Definition owners enforce exact boolean/integer values, retry factors and one resource conversion. Zero, underflow, nonfinite and unrepresentable Docker limits fail before acceptance. Retry delay calculation remains bounded even with a large finite factor. |
| F6: complete projections | Pure projection definitions derive expected rows for every domain table. Checks detect changed/missing/orphaned resources, sources, output sets, cache observations, log snapshots, input relations and log entries, plus journal-counter disagreement. Replay repairs derived data without resetting authoritative counters. |
| F7: compiled capture | One bounded regular-file reader rejects links/FIFOs/oversize sources and compares open/path identities and observed mutation. Configuration preserves lexical source paths for repeated validation. |
| F8: filesystem durability | File publication and identity creation flush all required ancestor entries, including new roots and identical retries. Injected leaf/ancestor failures cannot record SQL completion; an identical retry repairs the durable boundary. |

The shared database/bytes foundation remains: one physical schema and backend
abstraction, separate journal/cache transaction boundaries, local SQLite ownership
and PostgreSQL fenced Run claims. New `queries.py`, `execution_choices.py`,
`lifecycle.py`, `compiled_source.py` and `projections.py` keep these invariants with
their owners. Filtering, keyset pages, queue/recovery eligibility, catalog,
idempotency/signature lookups and Run/sequence log ranges use selective SQL.
Normalized input/log projections support indexed lookup. PostgreSQL queries cast
canonical JSON text without changing signed-zero or numeric representations.

Pipelines 004/005/007/009/010/A38 and Artifacts 002/005 own the changed contracts.
Local package metadata/composition select Pipelines 11.0.0 and Artifacts 3.1.0.
The major impact is the fresh database/Run format. Physical schema is 5 and
portable backup state format is `dockflow-sql-v4`. No data migration is provided.
Application version and project baseline declarations remain unfinalized by this
work; no commit, upload, publication or workflow closure occurred.

## Verification

The focused correction suite passed **59 tests**, including both database
backends. Standalone filesystem fault injection passed **5 tests**. Full provider
matrices pass on the final runtime source.

| Interpreter/provider matrix | Result |
| --- | --- |
| CPython 3.13.17, SQLite/PostgreSQL/S3/Docker | 790 passed, 14 skipped, 5 upstream warnings; 143.83 seconds. |
| CPython 3.12.15, same providers | 790 passed, 14 skipped, 5 upstream warnings; 146.16 seconds. | Retained test sources:

- `packages/pipelines/tests/integration/test_conformance_corrections.py`
- `packages/pipelines/tests/integration/test_cache_execution.py`
- `packages/artifacts/tests/test_directory_durability.py`
- Existing direct/service runtime, fencing, cancellation, publication, rebuild
  and portable backup/restore suites.

Ruff lint/format, Pyright, generated OpenAPI/API drift, synchronized application
version declarations, composition/imported integrity and whitespace checks pass.
The matrix skips are SQLite parameters of PostgreSQL-only concurrency,
ownership and maintenance cases. Warnings originate in the upstream Starlette
test client and KFP compatibility notice. Live S3 cases run with both SQL backends.
JavaScript checks pass **30 tests across 5 files**. Anonymous-document and local
link checks pass for affected documents. Service image checks pass non-root
readiness, packaged UI/OpenAPI, two-step execution, artifact publication, reuse,
retained logs and restart with persistent history in an isolated Docker engine.

All four distributions pass wheel/source inspection, independent source rebuilds
and clean installs for database-only, CLI-only, Artifacts-only and combined base.
Runtime/provider extras remain absent from base installations. Local sanitized
receipts are `dist/verification.json` and
`dist/corrections-service-verification.json`.

## Artifacts and source binding

Service image `dockflow-corrections:verification`:
`sha256:5cb007e6c22ff3862f3aedcf6c287c036a8f5d6ef9c85fe523795e594c904f04` (`linux/amd64`), isolated Docker server `29.7.2`.

| Distribution | SHA-256 |
| --- | --- |
| `dockflow_cli-0.1.1-py3-none-any.whl` | `d431dd3eaec13c91a08abf6c22d94188a639f889f067e9c8c0588f1f6bb1a0f3` |
| `dockflow_pipelines-0.1.1-py3-none-any.whl` | `8d172b50adf6d5870d9654a7fdaac462190be0cc96e681918470e9a7158cc17f` |
| `dockflow_artifacts-0.1.1-py3-none-any.whl` | `7ca5784c0986a1e60f13e423a0d9ababa4a8b7e77608cc3646eaceb7d1a8d500` |
| `dockflow_database-0.1.1-py3-none-any.whl` | `405922781a7336f89371a8f5be88e806b3eb9a045c32e8e2fc71f68157376143` |
| `dockflow_cli-0.1.1.tar.gz` | `91da0d563df0f0379c923b2c26b9b376cb96f2f9b5a7fbccdfe1d4ee6622f39f` |
| `dockflow_pipelines-0.1.1.tar.gz` | `0bed5ce3275f22a3b1e220129aaffc1374acb2ebb8cf13f9aec99a0cca17fd24` |
| `dockflow_artifacts-0.1.1.tar.gz` | `972055f4fcf3db9c9b633ff0fce10c0ce94c9f5a71dfb7a8cf209c08244cf1db` |
| `dockflow_database-0.1.1.tar.gz` | `9283492d0726580584ede002858c54df2c569c63468475276c47285840da10bd` |

The aggregate binding covers 264 Git-visible regular files under `packages/`,
`tools/`, `tests/`, `deploy/`, `docs/`, `.macrostates/specs/` and `.github/`, plus
`VERSION`, `pyproject.toml`, `uv.lock` and `CHANGELOG.md`. SHA-256 is computed from
UTF-8 lines `<file-sha256>  <repository-relative-path>\n`, sorted by path.
Implementation records are excluded to avoid self-reference. Aggregate:
`9d9ca30b1d514dd105c6921af4f48796db9afafd743f5caeabc25b5d492ded4b`.
The complete portable inventory is retained at
`tmp/reviews/conformance-corrections/source.json`.

## Scope and limits

Environment: Linux x86-64, CPython 3.12.15/3.13.17, SQLite 3.53.1,
PostgreSQL 18.6, Psycopg 3.3.6, KFP 2.17.0, Docker 29.7.2, uv 0.13.5 and
uv_build 0.11.33. Providers run in isolated processes/containers on one host.

Qualification covers Linux x86-64, SQLite, disposable PostgreSQL 18, conditional
S3-compatible storage and actual Docker direct/service execution. Directory
fault injection verifies acknowledgement boundaries; it does not simulate physical
power loss. Indexed plans and bounded row fetching are checked; no throughput or
large-scale latency benchmark is claimed. No new physical multi-host, native
platform, real-browser journey or particular serverless-provider qualification
is inferred. Automatic Run resumption, original-daemon reconciliation and worker
lifetime requirements retain their documented meaning.

Disposable PostgreSQL and S3 containers were stopped and automatically removed.
The task-created Python 3.12 environment was removed; pre-existing interpreters
remain. Image verification removed its isolated deployment resources. The local
service image, distributions and sanitized receipts remain available for review.
Existing project data, unrelated edits and earlier workflows remain preserved.

Final delivery state is `awaiting_acceptance`; workflows remain open and the
project remains active. No baseline finalization or publication is implied.
