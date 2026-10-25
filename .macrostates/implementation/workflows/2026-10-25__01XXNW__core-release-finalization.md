# Core release finalization preparation

- Project phase: active
- Workflow type: Release preparation
- Status: in_progress
- Delivery state: implementing
- Change depth: large
- Branch: release/0.2.0
- Requested by: Definer
- Closure authorized by: Definer; explicit acceptance, all-workflow closure, PR, merge and publication instruction
- Implementer: Implementer
- Started at: 2026-10-25 00:33 (UTC)
- Last updated at: 2026-10-25 00:33 (UTC)

## Objective and authorization

Prepare the accepted Core implementation and all pending feature changes as one
reviewable Dockflow 0.2.0 release candidate. The Definer accepts the qualified
implementation, explicitly closes all open workflows and authorizes pushing,
reviewed PR integration and PyPI publication. This bounded preparation covers
closure, current-target review, exact impact collection, coherent baseline
candidate declarations, release documentation and submission readiness. Hosted
CI, approved integration and immutable publication outcomes are subsequent
external release gates, recorded in Actions and the resulting release record.

## Scope and acceptance

Retain fresh-state compatibility limits and the final 813-test qualification on
each supported interpreter. Correct remaining editorial publication references to
Core and consumer-owned schemas without changing runtime behavior. Collect each
pending impact once against the finalized baseline and current fetched main.
Keep archived record bytes unchanged. All local workflows, including this
preparation, close under the existing authorization before PR submission.
Verify exact-source required CI before merge and build one preserved candidate
from successful main CI. Publish the exact verified artifacts and verify PyPI
hashes plus source/image/release identities. PyPI Core publisher configuration is
external and must match publish.yaml / pypi-core; the matching GitHub environment
now preserves the CLI publishing protections. No protection may be bypassed.
