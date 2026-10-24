# Specification conformance and design review

- Project phase: `active`
- Workflow type: `Review or gap assessment`
- Status: `completed`
- Delivery state: `accepted`
- Change depth: `large`
- Branch: `feat/distributed-artifact-cache`
- Requested by: Definer
- Implementer: Implementer
- Started at: 2026-10-24 23:06 (UTC)
- Last updated at: 2026-10-24 23:48 (UTC)

## Objective and scope

Compare the effective Dockflow specifications with the current implementation
on its own design merits. Inspect CLI, definitions/planning, execution/recovery,
state/coordination, artifact publication, API/browser and qualification boundaries.
Distinguish confirmed contract defects, design recommendations and evidence gaps.
Use bounded synthetic probes where useful. Preserve existing source, contracts,
project state and unrelated changes; this request does not authorize implementation
or specification amendments, commits, publication or workflow closure.

## Acceptance criteria

Report prioritized findings with the concrete trigger, consequence, applicable
contract and repository-relative code references. Separate observed results from
inference and avoid classifying explicitly supported product limits as defects.
Keep the task-specific assessment under ignored `tmp/reviews/` according to the
documentation policy. Use anonymous role attribution and portable examples.

## Progress

Completed the contract/source review and bounded reproductions. Findings:

1. P1: a scheduler queue-read failure can leave readiness healthy and admission open.
2. P1: remote named resolution selects a newer historical definition after source rollback.
3. P2: queued execution can use changed coordinator settings rather than accepted limits.
4. P2: abandoned-Run recovery leaves running Task resources nonterminal.
5. P2: strict IR validation accepts malformed booleans and nonpositive resource strings.
6. P2: integrity checks miss corrupt cache observations and orphaned domain rows.
7. P2: compiled-file capture follows symlinks and lacks bounded stable-file reads.
8. P2: standalone filesystem publication does not explicitly sync new ancestor entries.

The eighth finding confirms missing flush operations; power-loss consequences are
inferred, not experimentally established. Architecture recommendations distinguish
accepted execution choices, coordinator deployment access, supervised lifecycle
transitions and selective SQL queries. Shared database/artifact boundaries remain
appropriate. Explicit product/platform limits were not treated as defects.

## Delivery and verification

The task-specific [assessment](../../../../tmp/reviews/specification-conformance/report.md),
[portable probes](../../../../tmp/reviews/specification-conformance/probes.py) and
[sanitized evidence](../../../../tmp/reviews/specification-conformance/evidence.json)
are under ignored `tmp/reviews/` as required by the documentation policy. The
workflow retains the summary; those ignored artifacts are local review products.

Focused existing regressions: 230 passed, 5 PostgreSQL-dependent cases skipped,
3 upstream warnings, 6.88 seconds on Python 3.13. Browser JavaScript: 5 files passed.
Specification integrity, review probe lint/format, local links, anonymization and
source/evidence bindings passed. The source binding matches the preceding cleanup
receipt. No implementation, effective specification, package or generated API
bytes changed. No baseline/version impact is assigned to this assessment.

The review did not repeat real-provider/image matrices, physical multi-host,
actual-browser or power-loss qualification. Proposed fixes remain unimplemented
and require subsequent authorized implementation scope. Existing project state,
unrelated changes and earlier workflows remain preserved. Review delivery is
ready for acceptance; this workflow remains open. No commit, publication or
workflow closure was performed.


## Acceptance and closure

The Definer explicitly accepted the completed delivery and authorized closure of
all open workflows on 2026-10-24 23:48 UTC, together with reviewed integration and
package publication. This scope is completed; earlier pending-state statements
are historical. Later conformance corrections retain their own evidence.
