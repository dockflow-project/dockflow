# Publication CI correction

- Project phase: `bootstrapping`
- Workflow type: `Integration preparation`
- Status: completed
- Delivery state: `accepted`
- Change depth: `bounded`
- Branch: `feat/initial-implementation`
- Requested by: Definer
- Implementer: AI-assisted implementation
- Started at: 2026-10-22 10:18 (UTC)
- Last updated at: 2026-10-22 10:23 (UTC)

## Objective and origin

Correct failures discovered by the first hosted CI run before completing the
approved initial source publication. The previous preparation workflow is closed;
this separate correction preserves its acceptance and evidence.

Original commit: `565a50481a5be0bbc507b3949737237dc3809e87`. Hosted CI run:
[39761725781](https://github.com/dockflow-project/dockflow/actions/runs/39761725781).
The repository remains private and has no `main` branch. The initial source is
uploaded only to its topic branch. No application or baseline release is allocated.

## Finding and plan

Hosted base-package jobs enable Rich terminal formatting. The nested CLI help
probe exits successfully and its import guard passes, but raw ANSI sequences
interrupt the expected option spelling. The test must compare rendered text while
retaining its check that help avoids optional execution imports. Reproduce the
hosted color environment and validate with and without forced formatting.
Inspect the remaining CI jobs before closing the correction; do not hide a product
failure or weaken required checks. Record any additional failure and its remedy.

## Completion criteria

The corrected test passes locally under the hosted color conditions and in a
minimal base installation. Run relevant static checks and review all original
hosted failures. Obtain explicit closure before publishing the correction. Hosted
CI for the resulting commit must pass before initial primary integration and
public visibility. No runtime or specification change is expected.


## Delivered correction and evidence

All eight failed hosted jobs were reviewed. Both Linux runtime jobs also lacked
`python:3.13-slim`, required by fixture configurations with `pull_policy=never`.
Their fifteen Docker failures share that missing prerequisite. The other two
runtime failures were help-text comparisons; the six base jobs failed the nested
help comparison. No runtime failure was suppressed or skipped.

Both help assertions now compare Rich's rendered text. The optional-import probe
runs in explicit plain and forced-color subprocess environments. CI pulls the
quickstart Dockerfile's existing immutable Python base and tags it with the
fixture name before running Docker tests. Contributor instructions document the
same preparation. The local image was verified to have that exact digest.

A local reproduction with `GITHUB_ACTIONS=true`, `FORCE_COLOR=1`, and no inherited
`TERM`/`NO_COLOR` failed before correction and passed afterward. The complete
Python/Docker suite passed **520 tests**, with one external S3-provider test
deselected. A fresh base-only installation passed **81 tests** under the same
hosted color conditions. Ruff, formatting, specification integrity and whitespace
checks passed. Application code, versions and specification contracts are unchanged.

The pending `source-publication-ci` change record retains the actual original
commit with no specification or implementation version impact. Hosted checks on
the corrected commit remain required after submission; the earlier failed run is
retained as evidence, not claimed as successful qualification.

## Definer-confirmed closure

The Definer explicitly approved closure and submission of this completed correction
on 2026-10-22, with the previously approved public publication continuing afterward.
All 35 workflow records are now closed. Hosted CI must still verify the submitted
commit before primary integration; its outcome remains in GitHub rather than
being inferred from this accepted local correction. No new product contract,
application version or finalized baseline is allocated.
