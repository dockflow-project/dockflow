# Distributed artifact-cache qualification

- Date: 2026-10-23
- Definer: Definer
- Implementer: Implementer
- Source origin: `032444d3686f5951cb0b2457e64a023ded502387`
- Development branch: `feat/distributed-artifact-cache`; dirty working tree.
- Starting baselines: `specs-0.1.0`, `imp-0.1.1`.
- Contract: [cache coordination](../../specs/053_dockflow-pipelines/014_cache-coordination.md), including A32.
- Status: local qualification complete; acceptance and physical multi-host qualification remain separate.

## Delivered boundaries

The registry coordinates independent Dockflow execution histories sharing a stable
project/namespace and managed store. Each history retains exclusive OS ownership,
one active Run and its own MLMD index. SQLite and PostgreSQL use one transition
implementation with backend-specific serialization and authoritative clocks.
Scope registration binds the configured label to a persistent actual store identity.

Cacheable tasks claim before computation, heartbeat independently, validate and
seal complete output sets, then publish under fresh ownership. The journal owner
orders publication against stop intent. Consumers verify complete portable
manifests and retain original producer/artifact identities without a new local
attempt. Registry success can repair producer facts after later journal failure.
Legacy automatic results are misses; explicit historical selection remains checked.

Filesystem reservations and conditional S3 objects prevent replacement. Bounded
finalization retries recover matching bytes/descriptors after lost acknowledgments.
Confirmed corruption uses artifact-specific invalidation. Transient read failures
leave validity and producer selection intact. Retry counts, cooldowns and terminal
reasons survive requester restarts. Administrative operations require expected
identities and never delete committed bytes or reset fencing history implicitly.

## Environment and providers

Local native Linux x86-64, glibc 2.44; CPython 3.13.17 and refreshed managed
CPython 3.12.15. Locked KFP 2.17.0, Docker SDK 7.2.0, MLMD 1.21.0,
Psycopg/binary 3.3.6, boto3 1.43.114. Python 3.13 SQLite is 3.53.1.
Docker daemon 29.7.2; disposable PostgreSQL 18.6 and MinIO
RELEASE.2025-10-15T17-29-55Z with Go 1.26.10. Providers were reached over local
network sockets; each process had independent connections and private state
locations, with a common artifact store. No private project fixture was used.

The original system-selected Python 3.12 interpreter failed two existing CA
checks. A freshly installed managed build under the disposable test workspace
passed those checks and the full suite. The machine's installed interpreter and
trust stores were not modified. Sandbox-only attempts could not reach local
providers or download the build backend; required provider/build commands then
ran with authorized access. No raw logs or unsanitized backups are retained here.

## Checks and evidence

| Check | Result |
| --- | --- |
| Python 3.13 full suite, real Docker/PostgreSQL/S3 | 631 passed, 1 skipped; four upstream deprecation warnings. |
| Python 3.12 full suite, refreshed interpreter | 624 passed, 1 skipped; four upstream deprecation warnings. |
| Final Python 3.12 cache execution/import isolation | 19 passed, including the subsequently added transfer-failure classification test. |
| Final process transition races, both backends | 6 passed on each interpreter. |
| Frontend regressions | 5 Node test files passed; pre-existing graph work preserved. |
| Ruff lint / format | All affected source/tests/tools pass. |
| Pyright | Zero errors and warnings. |
| Composition/imported integrity | Macrostates 0.5.0 `check` passes; external snapshots unchanged. |
| Lock / application declarations | Locked resolution and synchronized application identity checks pass; no release identities advanced. |
| Generated API contract | `tools/generate_api_docs.py --check` passes, including cache mutation models. |
| Distribution verification | All three wheels/sdists build; clean CLI-only, Artifacts-only and combined base installs pass; all sdists independently rebuild without the checkout. Optional runtime/server/storage/PostgreSQL imports remain absent from base installs. |

The skipped test is the separate artifact-library S3 publication test requiring
its own publisher configuration. Dockflow Pipelines' new real S3 cache test ran
against the disposable provider, including conditional conflicts, empty directory
round trips, corruption, and ambiguous payload/descriptor PUT responses.

The final artifact receipt under ignored `dist/verification.json` contains only
portable software/source identities, filenames and hashes. It is a development
verification receipt, not release acceptance or publication evidence.

## Requirement coverage

The proposed feature's numbered test requirements are owned by section 17 of
its adopted contract; the following map groups their evidence without replacing
those obligations.

| Requirements | Automated evidence |
| --- | --- |
| 1–6: identity, restart, eligibility, complete sets | Canonical signature tests; `test_cache_execution.py` covers cross-state reuse, changed inputs/namespace, uncacheable execution, missing multi-output validation and whole-set verification. |
| 7–12: contention and backend conformance | `test_cache_registry.py` repeats 20-process barriers twice for healthy empty keys and once after shared failure, on each backend. Exactly one producer wins each wave; all consumers verify the same directory manifest. Separate keys claim concurrently; real SQLite writer and PostgreSQL row-lock timeouts retry without extra production budget. |
| 13–19: crashes, stale owners, leases and ambiguous commits | Spawned producers are terminated after claim, validation, immutable finalization and publication. Lazy expiry/takeover, every stale owner mutation, healthy renewal past the original deadline, lost renewals, database clock jumps and committed-then-lost claim/publication responses preserve invariants. Rollback before claim commitment allocates no ownership. Independent processes race renewal/failure/publication and expiry/takeover. |
| 20–27: validity and storage | Finalized orphan bytes remain unselected; corruption triggers conditional invalidation; late failures and delayed invalidation cannot revoke newer results. Permission/access errors preserve valid selection. Multi-output failure, traversal/symlink regressions, filesystem sealing, complete directory inventories and freshness snapshot retention are checked. Real S3 publication recovers lost object and descriptor acknowledgments without overwriting conflicting bytes. |
| 28–35: retry, cancellation and administrative races | Persisted budgets/cooldowns, retry exhaustion, nonretryable failures, scope conflicts, revision-checked reset, bounded waiter timeout/cancellation and polling-only progress are exercised. Replacement and stale cancellation/failure callbacks are fenced. Process races cover delayed invalidation and historical publication acknowledgments against a new publication. |
| 36–38: retention, migration and unsupported storage | Cache eviction/orphan deletion is disabled. Existing cleanup remains confined to owned terminal work. New versioned keys/locations isolate old writers; imports/reopen/recovery retain original IDs. Shared SQLite, known network mounts, unsafe registry placement, and different stores using one scope are rejected. |

After fault tests, invariant assertions inspect unique entry identity, ordered
nonreused fences, at most one active authorized attempt, terminal timestamps,
valid cross-row references and validated selected manifests. PostgreSQL runs
against a real database; thread-only test doubles are not used as evidence of
process coordination. CI now provisions the pinned PostgreSQL service on both
Linux Python targets; this local receipt does not claim hosted CI execution.

## Compatibility and operating limits

- The local Pipelines specification package advances to 5.0.0 because registry
  authority, the default coordinated payload namespace and legacy cache behavior
  change an existing contract. Pending specification and implementation impact
  are Major; finalized baselines and root application VERSION remain unchanged.
- One state root remains serial and owner-exclusive. PostgreSQL enables cache
  coordination, not distributed execution-journal writes or multi-node scheduling.
- SQLite requires a qualified local filesystem. Mount detection is conservative
  and cannot prove all filesystem semantics.
- Physical multi-host, non-Linux and additional architecture qualification were
  not performed. Independent local workers demonstrate shared-registry/store
  behavior; they do not establish physical multi-host deployment qualification.
- Coordinated S3 files are limited to 5 GiB; larger outputs must disable caching.
  Conditional writes and provider consistency are required. Component code and
  explicitly granted mounts/credentials remain within the trusted workload profile.
- Published bytes and fencing history are retained; no automatic cache eviction
  or orphan deletion is enabled. Shared-cache backup must quiesce all participating
  owners and preserve registry, store identity and all versioned bytes. Restoring
  older registry history requires a fresh namespace. A local history backup alone
  cannot establish cache-wide recovery.
- This working tree also contains a separate graph-view amendment awaiting
  acceptance. Its files and workflow were preserved. No commit, integration,
  tagging, service publication or package upload was performed.

## Final source file digests

These hashes bind the implementation files checked here, without embedding a
future commit's own identity. Workflow/document-only edits do not alter them.

| Repository-relative file | SHA-256 |
| --- | --- |
| `packages/pipelines/src/dockflow_pipelines/cache_registry.py` | `0ed0f532bad14607b0af14bbc3f5b2d44cf00f24c59276e69846a9bcf4868c68` |
| `packages/pipelines/src/dockflow_pipelines/cache.py` | `768b877afd9479bfce1ea33bb7eecbe7412dedc0d89c5c159dcfa151183b5301` |
| `packages/pipelines/src/dockflow_pipelines/cache_storage.py` | `3b9570d7068029d780ff9d4fa71f690c0f4f93166e4dceac294ac9d3baea56c7` |
| `packages/pipelines/src/dockflow_pipelines/engine.py` | `37d49fc6f11202cc18f628f76a02f80cf6edcd21391f52832ca5627b3102e59a` |
| `packages/pipelines/src/dockflow_pipelines/artifacts.py` | `91a7701fe3045f6af4118a0d068ff2a65be929b25665b9f2a679a6c562456f48` |
| `packages/pipelines/src/dockflow_pipelines/metadata.py` | `0d3297e775643a1df00435f60f729c285ffd61dabe47862f587ea3630cfe94c7` |
| `packages/pipelines/src/dockflow_pipelines/config.py` | `75d176b5cc873d405d04b421267b4bac3a0c7b4f544db869d538dcaec9aacedf` |
| `packages/pipelines/src/dockflow_pipelines/core.py` | `57adf59beb0972a87c8b5bdc4765845b350082aad34dc78a341d1cdbb388bcd5` |
| `packages/pipelines/src/dockflow_pipelines/reuse.py` | `db5188237d29a093c9881ede92e952fd5f3ffa7783fe4045928e3437bd47feb2` |
| `packages/pipelines/src/dockflow_pipelines/operations.py` | `f99e28781286ae8d0c9b006118a272329e46e30d81da3faad7fb6fc90ece8915` |
| `packages/pipelines/src/dockflow_pipelines/cli.py` | `04b09e0d7d215e13d09ed887b8b0d223c7faf2e62dfdee0b37298b0e2de1ec88` |
| `packages/pipelines/src/dockflow_pipelines/client.py` | `d7c0fd006ee1569f76f2a4769d3bc0dd3190388eddaf582a9f5e52e438565c04` |
| `packages/pipelines/src/dockflow_pipelines/service.py` | `eda5314583150f23d726c7c54e1bf4f45ba52b5706e4eb9d9e72b2c00e301f66` |
| `packages/pipelines/src/dockflow_pipelines/openapi.py` | `1676053267817e2dc5bea7defe4aec44c393263b0e5cda87d3c3a266992e78b0` |
