# Configurable managed artifact directory

- Project phase: `bootstrapping`
- Workflow type: `Project bootstrapping`
- Status: `completed`
- Delivery state: `accepted`
- Change depth: `medium`
- Branch: `feat/initial-implementation` (unborn)
- Requested by: Definer
- Implementer: AI-assisted implementation
- Started at: 2026-10-20 11:23 (UTC)
- Last updated at: 2026-10-21 19:54 (UTC)

## Objective and acceptance criteria

Configure the filesystem managed directory directly without an implicit managed child.

## Delivered behavior and decisions

Added artifacts.managed_root and its environment mapping while retaining root/legacy
defaults. Conflicting roots, S3 filesystem settings and protected overlaps fail before
mutation. Admission, publication, materialization and backup share the resolved
directory; restore accepts old manifests and preserves URIs. Per-request storage
overrides remain rejected. Pipelines specification 1.6.0 records the addition.

## Verification

Historical outcomes and qualification limits: [validation receipt](../../validation/managed-artifact-directory.json).
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
