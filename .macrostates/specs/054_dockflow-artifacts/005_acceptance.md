# Packaging and acceptance

MIT license, src layout, py.typed, pytest, Ruff and Pyright. The library lives
at packages/artifacts in the Dockflow monorepo, with shared composition, workflow
tracking, tooling, lock and environment. Root VERSION is the shared application
version authority; package metadata is synchronized by the shared release tools.
Application versioning is independent of Macrostates baselines. Preserve
public API compatibility once stable; establish stability through the shared
release policy rather than specification selection alone.
Build wheel/sdist without Git and rebuild/install the sdist independently.
Use the root development uv.lock for repeatable checks, not downstream constraints.

Provide README, contributor instructions, installation/usage/storage/KFP/API
documentation, a synthetic runnable example and documented configuration.
Public documentation must not depend on a sibling consuming repository,
private paths, credentials or unregistered public repository URLs. Examples
must import the installed public API. Record AI assistance and MIT authorship.

Test files and directory trees, empty files, unsafe paths and symlinks, metadata
identity, source mutation, concurrent/conflicting/retried publication, partial
uploads, checksum failures and completed-object deletion. Test S3 conditional
publication against a real compatible service as well as focused test doubles.
Test optional-import isolation, construction without network/credential discovery,
first-use client initialization, missing-extra diagnostics and compile/importer
metadata preservation.
Exercise the consuming example through local Docker, Compose/SeaweedFS and native
KFP; retain exact evidence and report any environmental qualification gaps.

No separate Git initialization, tags, remote publication or package upload is authorized
by ordinary build/test commands. Acceptance and workflow closure follow the selected Process and explicit
repository instructions. Current-state docs and dated validation have separate roles.

Verify typed deterministic identity with golden vectors, order independence,
parameter/version/context changes, input content changes, invalid inputs and
path-independent staging. Verify pipeline-computed widths at 9/10 and 99/100
boundaries. Qualify identical native cache reuse, different parameter paths,
and distinct pipeline/exploration contexts without overwriting earlier outputs.

Verify publication with real SQLite and PostgreSQL, independent processes,
conflicting/overlapping destinations, lost completion responses, interrupted
payload transfer and database failures. Inspect filesystem and S3 roots to prove
claims/manifests/recovery descriptors are SQL-only. Verify shared database use
with Pipelines, project isolation, maintenance exclusion, consistent backup and
restore, read-only verification and secret-safe failure diagnostics.

Verify ancestor-directory durability for new roots and nested destinations,
including identity creation, concurrent creation and identical retries. Inject
file/directory flush failures and verify no SQL completion is acknowledged until
durability succeeds. Keep measured power-loss/platform qualification separate
from syscall-order assertions.

Verify the [Core boundary](../051_dockflow/007_core.md) and prove standalone
publication creates only Artifacts-owned tables and Core's generic version
registry. Adding Pipelines later must preserve those publications. Schema version
mismatch, incomplete objects and initialization failure must fail closed without
repairing state during verification. Preserve publication identity golden bytes
when sharing deterministic encoding and filesystem primitives through Core.
