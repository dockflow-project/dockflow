# Artifact library and consuming example

- Project phase: `bootstrapping`
- Workflow type: `Project bootstrapping`
- Status: completed
- Delivery state: `accepted`
- Change depth: `large`
- Branch: `feat/initial-implementation` in the existing Dockflow monorepo.
- Requested by: Definer
- Implementer: AI-assisted implementation
- Started at: 2026-10-20 16:38 UTC
- Last updated at: 2026-10-21 19:54 (UTC)

## Objective and acceptance criteria

Provide independent artifact publication inside the monorepo, including custom paths and
KFP integration.

## Delivered behavior and decisions

Delivered packages/artifacts with filesystem/S3 file and directory publication,
immutable claims, manifests, checksums, retry and conflict handling. Typed KFP
importers register URIs; nested graphs accommodate KFP 2.17 parent-input resolution.
Owner-configured mounts supply roots or secret files; compiled definitions cannot
request host mounts. Setup/reset prerequisites and missing-mount diagnostics were
corrected and qualified.

Bookkeeping lives below the artifact root in .dockflow/dockflow-pipelines and
.dockflow/dockflow-artifacts. Old managed descriptors remain readable; legacy
publisher roots require a fresh root or explicit reset.

Paths use exploration/pipeline/step_number__component__publication-id/filename.
Exploration defaults to global. Pipeline wrappers supply their name, position and
width computed from computational step count; component wrappers select names,
versions and filenames. Identity hashes typed canonical parameters and explicit
input fingerprints. Backend caches own computation reuse: identical invocations
retain URIs; changed parameters, inputs or context select separate directories.

Final qualification records 440 Dockflow regressions, 265 integration-fixture
regressions and one live SeaweedFS test. Eight payloads match across local Docker,
Compose and native KFP. MLMD records six COMPLETE then six CACHED executions with
typed model references and stable URIs. Local/API repeats and changed context were
exercised. Filesystem runtime qualification is Linux; automatic retention is out
of scope. General/Pipelines/Artifacts specifications are 0.3.0/4.0.0/2.0.0;
application identity remains 0.1.0.dev0.

## Verification

Historical outcomes and qualification limits: [validation receipt](../../validation/deterministic-publication-paths.json).
These are recorded observations, not tests rerun during anonymization.

Earlier receipts: [initial publication](../../validation/artifact-library.json),
[reset prerequisites](../../validation/artifact-reset-mounts.json), and
[bookkeeping layout](../../validation/exploration-artifact-layout.json).

## Record scope

This is an anonymized historical summary. Integration fixture identities and
locations are omitted. Obsolete scratch inputs and raw fixtures were discarded
during publication cleanup. Historical hashes do not attest to this edited text.

## Closure

On 2026-10-21, the Definer explicitly authorized closure of the complete existing
open-workflow set. Review confirmed that this workflow's recorded scope was
delivered; it is accepted and closed as `completed` under that authorization.
The recorded evidence and qualification limits remain unchanged. Closure does
not claim fresh runtime validation, accept or finalize project baselines, or
authorize PR preparation, commits, pushes, tags or external publication.
