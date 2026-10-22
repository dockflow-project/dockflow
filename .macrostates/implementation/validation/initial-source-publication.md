# Initial source publication checks

Date: 2026-10-22. Scope: the initial `0.1.0.dev0` source development preview,
reviewed on `feat/initial-implementation` before its first commit. The remote
repository was verified empty and private, with administrator access available.
There is no existing source/target commit or finalized implementation baseline.
These checks do not allocate or finalize release identities.

## Verification

- Python 3.13.16 on Linux x86-64: `DOCKFLOW_TEST_DOCKER=1 python -m pytest -m
  'not s3'` passed **519 tests**, including real Docker execution. The one external
  S3-provider test was deselected. Four upstream deprecation/future warnings were
  reported; they did not fail the checks.
- Five dependency-free frontend test files passed under Node.
- Ruff lint and formatting, Pyright, generated OpenAPI documentation, shared
  version metadata and the locked dependency resolution passed.
- Macrostates composition and immutable imported inventory checks passed.
- All three wheels and source distributions built. CLI-only, Artifacts-only and
  combined-base clean installs passed; all source distributions rebuilt outside
  the checkout. Runtime extras were absent from the base installations.
- A current pip-audit 2.10.1 check of all **81 locked third-party dependencies**
  reported no known vulnerabilities. This is advisory evidence as of this date,
  not a guarantee against undiscovered vulnerabilities.
- Candidate file review found no machine-specific source paths, private consumer
  references, private keys or supported credential patterns. The container's
  `/home/dockflow` work directory and a deliberately synthetic credential URL in
  a security regression test were reviewed as expected matches.
- The publication inventory contains 307 text files and no symlinks. All 367
  checked relative documentation links resolve inside the exported tree. Ignored
  environments, runtime state, credentials, build outputs and temporary reports
  are excluded. Required license notices and immutable imported provenance remain.

## Publication preparation corrections

The setup-uv v6 reference was an annotated tag object's SHA. Resolve the official
tag to its immutable commit `d0cc045d04ccac9d8b7881df0226f9e82c39688e` in both
GitHub workflows, retaining the same action source. The other action pins resolve
to existing upstream commits. Remove two clickable links to ignored review
reports, retaining their historical location and explicit unavailability in the
public tree. Replace the current-state claim of having no source commit with a
description that remains accurate after the initial commit.

## Remaining gates and limits

The Definer approved closure of the completed integration-preparation workflow
and the initial public source integration on 2026-10-22. The empty remote has no pull-request base; the initial snapshot is prepared for
native review against the empty tree, followed by an explicitly approved initial
primary ref. Staging identifies the exact proposed tree without embedding its own
hash in a tracked file. Subsequent remote commit/check evidence belongs to GitHub
and the publication receipt, not a guessed self-referential source hash.

GitHub Actions is enabled, but its cross-platform jobs have not run for this
source. Native macOS/Windows and other unqualified targets remain outside this
local validation. Check required hosted results before integrating. Public
visibility and private vulnerability reporting must be verified before announcing
publication. No package, service image, baseline tag or application release is
created by these checks.
