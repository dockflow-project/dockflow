# Source publication readiness

- Reviewed on: 2026-10-21
- Scope: public source development preview; no package/image publication
- Application version: `0.1.0.dev0`
- Source: unborn development branch `feat/initial-implementation`; no commit/tag
- Roles: Definer and Implementer; no personal or machine attribution retained

## Outcome and decisions

The local source tree is prepared for a public development preview. Shared
licensing, dependency, platform, storage, interface and release policies have no
remaining unspecified product choices. The first publication makes source,
specifications, tests, examples and checkout installation available under MIT.
It does not advertise stable packages, full KFP parity, untested platforms or
operational package registries. Candidate/account checks are execution gates,
not unresolved design decisions.

The selected working specification is adopted for continued bootstrapping;
accepting reviewed work and closing workflows do not finalize the provisional
`specs-0.1.0` seed or create an implementation baseline. No source commit, PR,
merge, push, tag or external publication was performed. Imported specification
snapshots remain unchanged.

Local package changes: shared Dockflow `0.5.0` adds the source-preview publication
scope; Pipelines `4.1.1` and Artifacts `2.1.1` remove stale draft-status prose.
CLI stays `0.2.1`. These specification versions do not change application VERSION.

## Corrections

- Shared policy and public guides separate source availability from versioned
  application release qualification, without weakening existing runtime contracts.
- Current implementation documentation removes stale package versions and live
  acceptance claims, and links to dated evidence rather than repeating historical
  counts as proof for later source.
- CI now checks specification composition and locked external package integrity
  using the pinned Macrostates tool.
- Package-verification receipts report observable clean, dirty, unborn or
  unavailable Git state. Unknown status is nullable; detached commits remain
  attributable; an archive inside an unrelated checkout is not attributed to it.
  The verifier does not infer baseline acceptance or publication.
- Security policy selects GitHub private vulnerability reporting. Hosting
  activation and verification are explicitly separate from source changes.
- All 32 earlier delivered workflows and this readiness workflow are completed
  under the explicit closure authorization. Their limitations and historical
  evidence remain in the 33 archived records. No open workflow remains.

## Current verification

Checks used the local Linux x86-64 environment with Python 3.13.16 and uv 0.12.24.
No external CI job is represented as having run.

| Check | Result |
| --- | --- |
| `pytest -q -m 'not docker and not s3'` | 504 passed; 16 infrastructure tests deselected. Includes 13 new package-provenance tests. |
| Dependency-free frontend tests | Five test files passed. |
| Ruff lint and formatting | Passed for packages, tests, tools and quickstart. |
| Pyright | Zero errors or warnings. |
| Generated API documentation | Current; no drift. |
| Version synchronization and offline lock check | Passed; shared application remains `0.1.0.dev0`. |
| Macrostates composition/import check | Passed; immutable inventories unchanged. |
| Package verification | Three wheels and three sdists built; CLI-only, Artifacts-only and combined base installs passed; each sdist rebuilt independently. |
| Publication hygiene | 253 authored text files and 118 archive text members reviewed; no private path, consumer identifier or credential pattern remains. Imported notices/provenance remain intact. |
| Documentation and closure | 368 relative links and 18 anchors across 99 authored Markdown files pass; 33 completed/accepted workflows, zero open. |
| Source provenance receipt | Correctly reports unborn/dirty checkout, null commit and no inferred release. |

The regression run retains three upstream warnings (Starlette TestClient
compatibility and the KFP client version advisory); there are no test failures.
Build receipts and the six qualified archives are local generated outputs under
`dist/`, excluded from source control. The packaging backend is uv 0.11.33 under
the declared backend range. Tests create only disposable Git fixtures; the
project's Git history was not changed.

The dependency lock did not change in this task. The earlier dated
[security verification](http-security-fixes.json) retains its audit and Docker
scope; no new live dependency audit or container-image vulnerability scan is
claimed here. Docker, live S3, native KFP, browser journeys and non-Linux/native
ARM64 qualification were not repeated for these documentation/build-tool changes.
Their earlier evidence remains bounded by its source/time/platform scope.

## During public-hosting setup

Enable GitHub private vulnerability reporting when the repository is public and
verify the confidential reporting entrypoint before announcing the preview, as required by
[SECURITY.md](../../../SECURITY.md). The intended hosting namespace is policy,
not evidence of account ownership or enabled settings. No hosting operation was
part of this work.

PyPI/GHCR ownership and Trusted Publisher setup, source/baseline finalization,
release artifact approval and additional platform qualification belong to a
separately authorized application release. They do not block inspection or
checkout installation of the explicitly bounded development preview.
