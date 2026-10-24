# Macrostates setup

- Project phase: `specification`
- Workflow type: `Project scaffolding`
- Status: completed
- Delivery state: `accepted`
- Change depth: `systemic`
- Branch: `chore/macrostates-setup` (unborn repository; no starting commit)
- Requested by: Definer
- Implementer: AI-assisted implementation
- Started at: 2026-10-15 11:10 (UTC)
- Last updated at: 2026-10-21 19:54 (UTC)

## Objective and acceptance criteria

Establish specification composition, repository entrypoints, licensing and verification
tooling.

## Delivered behavior and decisions

Installed tagged specification snapshots with an integrity lock and explicit
reading/authority orders. Adopted Python Project conventions and separate local general,
CLI and Pipelines packages under one lifecycle. Added MIT licensing and repository
hygiene. The provisional specification seed is not an accepted implementation baseline.

## Verification

Macrostates CLI 0.5.0 on Python 3.14.7 passed the initial composition checks.
Independent release-archive comparisons verified 65 imported files, including
executable flags and content inventories. The tooling environment passed its
package dependency check. Later composition refinements removed the evaluated
Python Library package and its obsolete whitespace exception. Application runtime
checks were outside this scaffolding workflow.

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
