# Initial application release review

- Application candidate: `0.1.0`, all three distributions and the service image.
- Proposed specification baseline: `specs-0.1.0` (first finalization of the seed).
- Proposed implementation baseline: `imp-0.1.0` (first accepted implementation).
- Original source/primary target: `fc00ff0325483e62505edf694540abbc798576a6`.
- Original tree: `98e086a889b28d305347461150e2266d7a1e5eb3`.
- Review date: 2026-10-22; branch: `release/0.1.0`.
- State: local preparation accepted by the Definer on 2026-10-22; release
  preparation explicitly closed and first-baseline/active-phase acceptance
  recorded. Submission and integration are authorized after passing hosted CI.
  Exact integrated-source candidate build and publication remain separate gates.

## Contract and first-baseline scope

This is the bounded initial milestone permitted by Pipelines Acceptance's
incremental-delivery rule. It does not claim the full intended platform matrix
or exhaustive qualification of every initial-profile scenario. The
[capabilities manifest](0.1.0-capabilities.json), public compatibility guide and
changelog identify the delivered semantics and explicit limits. Unsupported IR
constructs fail admission rather than being silently ignored.

The review covers the complete implementation inherited from the source preview,
the closed CI/Windows corrections, and the release preparation changes. It is
not a claim that one metadata patch constitutes the first implementation. The
existing specification contract is retained. Release preparation adds the
previously required automation and accurate version/provenance metadata;
existing working requirements are not weakened to make a release pass.

Process permits manual first-baseline establishment when the installed CLI only
plans releases against an existing implementation. The candidate plan explicitly
records null prior implementation and the unfinalized specification seed.
No provisional baseline is fabricated solely to satisfy automated planning.
Reviewed integration finalizes the candidate only after explicit first-baseline
acceptance and workflow closure. Annotated tags and registry uploads are separate.

## Requirement coverage

| Surface | Implementation and evidence |
| --- | --- |
| CLI registration and standalone packaging; A01/A17 | CLI package tests, installed-module integration, clean CLI/Artifacts/combined installs, independent sdist rebuilds; hosted base matrix on Python 3.12/3.13. |
| Compiled IR, types, DAGs, importers, conditions; A02–A04/A16 | Definition and runtime tests, strict rejection tests, quickstart components, historical native KFP parity receipts. No full KFP parity claim. |
| Artifact publication, identity, integrity and reuse; A05–A12/A20 | Artifact library/provider fixtures, managed artifact/reuse/maintenance tests, deterministic-path and real-provider historical receipts. New image smoke exercises filesystem publication and reuse. |
| Ownership, queue, worker isolation and recovery; A13–A15/A28 | Owner-lock and bind-mount tests, runtime cancellation/retry tests, real service worker/restart tests, journal/index failure injection. Exhaustive crash injection and distributed filesystem locking remain unqualified/outside the profile respectively. |
| Native/KFP APIs and upload catalog; A18–A19/A25–A27 | Actual pinned KFP SDK HTTP tests, native schema/contracts, upload recovery and invalid-input tests. Unsupported backend methods reject. |
| Deployment and images; A21–A23 | Linux Docker runtime CI, built non-root service with the exact package wheels, disposable isolated-engine deployment, artifact/log/reuse/restart checks. ARM64 execution and Docker Desktop are not advertised. |
| Configuration, browser and logs; A24/A29–A31 | API/configuration provenance tests, five frontend test files, retained real-browser receipts, HTTP security tests, real Docker incremental-log tests. Browser evidence limits remain in dated records. |
| Artifact library contract | Independent import/install, typed identity vectors, immutable file/directory publishing, conflict/retry/corruption tests, KFP importer compilation; historical filesystem/SeaweedFS/native-KFP path and cache comparison. |
| Release policy | Aligned VERSION/lock/metadata; distinct protected pending publishers; manual candidate workflow; exact bundle hashes and source/tag binding; CLI-first uploads; preserved image publication; immutable collision checks and resume procedure. |

The baseline does not add loops, accelerators, parallel task execution,
distributed owners, network-filesystem fencing, external SQL metadata, recurring
jobs, full KFP API parity or artifact payload previews/downloads. Native runtime
support outside Linux x86-64 needs additional evidence before advertisement.

## Local verification

These checks used the release working tree, not an already integrated/tagged
source. Final publication must use the successful hosted candidate for the exact
integrated main commit; these preliminary artifacts are not approved uploads.

- Python 3.13.16, uv 0.12.24, uv_build 0.11.33; Linux x86-64, glibc 2.44.
- Full Python/Docker suite: 543 passed, one externally configured S3 provider
  test deselected. Four upstream dependency warnings; no test failures.
- Release-bundle checks include 22 tests for altered bytes/inventories,
  provenance/tag mismatch, unexpected files/symlinks, and conflicting or partial
  immutable PyPI uploads.
- Three wheels clean-install independently/as a base group; all three sdists
  rebuild independently. The existing-artifact verification mode leaves the
  candidate package hashes unchanged.
- Image smoke: Ubuntu 24.04, Python 3.13.16, Linux/amd64, Docker host 29.7.2,
  isolated pinned Docker 29.1.3. Passed non-root readiness, packaged UI/OpenAPI,
  two-step execution, dataset/report publication, reuse, logs and persistent
  history after restart. Preliminary image ID:
  `sha256:aec97ebf7138d874d2692d683d6e9af00e80cfecec31ced3b74269bdfd8e3964`.
  This precedes the descriptive capability-metadata update; it is not the final
  release image. Candidate automation repeats qualification on the final image.
- New smoke-harness corrections: grant its non-root service access to the
  disposable engine socket; rediscover Docker's ephemeral host port after
  restart. Initial failures were harness configuration, not hidden passes.
- Five frontend test files, Ruff lint/format, Pyright, version/lock checks,
  generated API drift and Macrostates composition/import integrity pass.
- The later capability-description change passes 36 focused API/release tests;
  the default source-image build also passes. The first restricted API test
  invocation was stopped because its socket fixtures need host permissions;
  the correctly permissioned invocation passed.
- Public source CI at the original commit passed all nine jobs. CI must run
  again for the release proposal and exact integrated main source.

Package/OS targets inherit exact source-preview CI evidence where unchanged:
Ubuntu 24.04 x86-64, macOS 14 ARM64 and Windows Server 2022 x86-64, each with
Python 3.12/3.13, for base packages only; Linux runtime on both interpreters.
No native Windows 11 execution, macOS execution or ARM64 image is inferred.

Macrostates 0.5.0's generic release check is not a passing first-baseline check:
it reports the expected dirty/open-workflow gates at preparation time, cannot
derive a first implementation from the prior null declaration, and expects an
already-finalized tag for the provisional specification seed. Its workflow
parser also rejects the backtick-formatted statuses in the 36 existing closed
records. Manual review verifies their actual completed/accepted statuses and
closure evidence without rewriting history. Composition/import checks pass;
manual first-baseline verification preserves the Process requirements rather
than treating these tool limitations as permission to skip acceptance or tags.

## External configuration and remaining gates

The Definer confirmed all pending PyPI publishers are configured. GitHub
environments `pypi-cli`, `pypi-pipelines`, `pypi-artifacts` require maintainer
review and allow only `main`. All entries bind `publish.yaml` in the canonical
repository. No PyPI token is stored. Successful OIDC publication is not claimed
until it actually occurs.

The Definer explicitly accepted the first baseline, the active phase and closure
of release preparation, and authorized submission/integration after CI passes on
2026-10-22. Remaining gates: reviewed proposal and successful hosted CI;
authorized integration; exact candidate build/review; annotated tags and
publication approval; upload hash verification, public GHCR visibility and
anonymous pull, and public PyPI installation. Later outcomes belong to the
hosting system/release receipts. Source-version assignment and local checks
alone do not satisfy those gates.
