# Example data layout

- Project phase: `bootstrapping`
- Workflow type: `Project bootstrapping`
- Status: `completed`
- Delivery state: `accepted`
- Change depth: `medium`
- Branch: `feat/initial-implementation` (unborn)
- Requested by: Definer
- Implementer: AI-assisted implementation
- Started at: 2026-10-20 11:11 (UTC)
- Last updated at: 2026-10-21 19:54 (UTC)

## Objective and acceptance criteria

Qualify data/artifacts and data/external/dataset locations independent of SQLite control
metadata.

## Delivered behavior and decisions

Updated disposable integration configuration, dataset preparation, read-only mounts and
reset targets. Source bytes retain their checksum; generated history can be recreated.
Reference artifacts need no separate payload directory. Docker training/inference and
integrity checks qualified the paths. This consumes existing configuration without a
generic migration API.

## Verification

Historical outcomes and qualification limits: [validation receipt](../../validation/example-data-layout.json).
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
