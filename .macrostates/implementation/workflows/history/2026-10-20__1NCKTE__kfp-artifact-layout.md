# KFP-compatible managed artifact layout

- Project phase: `bootstrapping`
- Workflow type: `Project bootstrapping`
- Status: `completed`
- Delivery state: `accepted`
- Change depth: `medium`
- Branch: `feat/initial-implementation` (unborn)
- Requested by: Definer
- Implementer: AI-assisted implementation
- Started at: 2026-10-20 15:33 (UTC)
- Last updated at: 2026-10-21 19:54 (UTC)

## Objective and acceptance criteria

Store generated artifacts in a KFP-equivalent pipeline/run/task/attempt/output
hierarchy.

## Delivered behavior and decisions

Filesystem/S3 publication uses compiled pipeline name, run ID, leaf task, attempt UUID
and output name. Files occupy the output itself; parameters remain metadata. Descriptors
and imports are separate from payloads. Descriptor-driven reads/reuse/restore support
old layouts; unsafe paths, symlinks and overwrites are rejected. Pipelines specification
3.0.0 records the change; package-specific hidden bookkeeping follows in the
artifact-library workflow.

## Verification

Historical outcomes and qualification limits: [validation receipt](../../validation/kfp-artifact-layout.json).
These are recorded observations, not tests rerun during anonymization.

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
