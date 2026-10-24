# Windows publication correction

- Project phase: `bootstrapping`
- Workflow type: `Integration preparation`
- Status: completed
- Delivery state: `accepted`
- Change depth: `bounded`
- Branch: `feat/initial-implementation`
- Requested by: Definer
- Implementer: AI-assisted implementation
- Started at: 2026-10-22 10:28 (UTC)
- Last updated at: 2026-10-22 10:34 (UTC)

## Objective and provenance

Resolve Windows base-package failures exposed by hosted CI before completing the
approved source publication. Original commit:
`40f53fca9904ebb6f0e943b9210a0356d6816030`. CI run:
[39762697899](https://github.com/dockflow-project/dockflow/actions/runs/39762697899).
The prior correction's review incorrectly generalized the Linux base result to
all base jobs; inspect each platform's concrete failures for this correction.

## Findings and intended correction

The canonical UTF-8 vector test reads its JSON using the Windows default encoding;
read the normative UTF-8 fixture explicitly. The missing-mount-source assertion
treats Windows backslashes as regex syntax; escape the literal expected path.
The configuration parser validates explicit Linux container destinations using
host-native Path rules, rejecting a valid POSIX destination on Windows. Validate
explicit destinations with PurePosixPath while retaining native source resolution
and the documented default target equal to that source. Preserve root, traversal,
duplicate and execution overlap checks. This fixes the existing mount contract;
it does not establish native Windows execution qualification or infer host-to-VM
path mapping.

## Plan and completion criteria

Add a cross-platform assertion preserving explicit POSIX target spelling. Run
unit/base and complete Python/Docker checks, static validation and packaging as
needed. Classify implementation patch impact with unchanged specifications and
application development identity. Obtain explicit closure before submission and
require all hosted jobs to pass before primary integration and public visibility.


## Delivered correction and verification

Explicit mount destinations now use PurePosixPath on every host; omitted targets
retain the resolved native source exactly. Traversal, root and duplicate checks
remain, and explicit drive-letter destinations are rejected for Linux containers.
Unit tests assert the preserved POSIX spelling and cover drive-letter rejection.
The normative digest fixture is read as UTF-8, and the missing-source assertion
escapes its literal platform path. Configuration documentation explains explicit
container path syntax without claiming native Windows runtime qualification.

With hosted color settings, the full local Python/Docker suite passed **521 tests**
with one external S3-provider test deselected. The base-only selection passed
**82 tests**. Ruff, formatting, Pyright, generated API drift and specification
integrity checks passed. All three distributions built, clean installations passed
and every source distribution rebuilt independently. Actual Windows verification
remains required from hosted CI on the submitted correction.

The preceding hosted run passed both Linux runtime jobs, all Linux/macOS base
jobs and specification integrity. Both Windows logs were inspected separately:
they reported the same three issues addressed here. Product contract and application
identity remain unchanged. The path parser is an implementation bug fix; no
finalized implementation baseline exists against which to declare a patch. The
manual review below records its scope without inventing a baseline or declaring
a false no-impact implementation change.

## Closure

The Definer explicitly approved closure and submission on 2026-10-22, followed by
the already approved publication after hosted checks pass. All 36 workflows are
closed. The local correction is accepted; actual Windows CI, initial primary
integration and public visibility must still be verified in the hosting system.
No finalized baseline, package/image upload or application release is implied.


## Manual bootstrapping change review

The immutable work-origin record captures the original source commit and explicit
absence of an implementation baseline. The Macrostates checker rejects a schema-1
implementation-impact record in this state (`change.implementation_missing`).
Retain this manual record for the source development preview rather than
fabricating `imp-*` or misclassifying a product correction as no impact.

Specification impact: none. Implementation scope: patch-like correction to an
existing requirement during unfinalized bootstrapping. Affected deliverable:
`dockflow-pipelines`. Exact source origin and hosted failures are identified above;
local check evidence and qualification limits are explicit. No baseline/application
version is allocated by source publication. A future first implementation baseline
must assess the complete initial implementation and this correction together.

Coverage: the explicit-task-storage-mount contract requires absolute targets and
the resolved-source default. The parser now separates explicit container syntax
from native source syntax and preserves rejection guards. Unit assertions cover
both destination forms and invalid Linux destinations. The digest fixture and
literal-path test corrections preserve normative values without changing runtime
canonicalization. There is no unresolved known gap in this corrected scope;
hosted Windows checks must confirm it after submission.
