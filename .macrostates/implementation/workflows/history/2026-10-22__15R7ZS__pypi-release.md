# Initial package release

- Project phase: active (started during bootstrapping)
- Workflow type: Release preparation
- Status: completed
- Delivery state: accepted
- Change depth: large
- Branch: release/0.1.0
- Requested by: Definer
- Implementer: Implementer
- Started at: 2026-10-22 10:59 UTC
- Last updated at: 2026-10-22 12:47 UTC
- Closed at: 2026-10-22 12:47 UTC

## Objective and scope

Prepare the first coordinated PyPI release of dockflow-cli, dockflow-pipelines
and dockflow-artifacts at the explicitly selected stable application version
0.1.0. Implement the existing release policy's reviewed candidate and Trusted
Publishing flow, package metadata, installation guidance and exact provenance.
Account for the matching service image and release record under that policy.
Product behavior and the private consuming example are outside this scope.

## Origin and acceptance

The release branch starts from the verified public main commit
fc00ff0325483e62505edf694540abbc798576a6. The selected specs-0.1.0 is an
unfinalized seed and no implementation baseline exists. Establishing a first
baseline requires an explicit reviewed scope and acceptance; version assignment
and previous source publication do not establish conformance or finalization.
The compatibility policy review is not overdue.

Acceptance requires aligned versions/lock, independently usable distributions,
verified candidate hashes, deployment smoke evidence, accurate limitations,
protected manual publication using the same artifacts, and exact source/baseline
binding. Explicit workflow closure, baseline acceptance, integration and candidate
publication remain distinct recorded gates.

## Work done

- Inspected release policy, current metadata, baseline records and hosted CI.
- Verified that all three intended names have no public PyPI projects; this is
  not a reservation or a guarantee of availability.
- Established release/0.1.0 from clean main before project changes.
- Selected publish.yaml with distinct pending publisher environments: pypi-cli,
  pypi-pipelines and pypi-artifacts. PyPI requires each pending publisher
  configuration to be unique. The Definer confirmed account-side setup; each
  corresponding GitHub environment requires maintainer review and permits main
  only. No publishing token is stored.
- Confirmed upstream KFP 2.17 still pins urllib3 below the tested override;
  published installation guidance must preserve the explicit exception.
- Synchronized VERSION, all package metadata, the image and lockfile to 0.1.0
  without third-party dependency upgrades. Added public package links, accurate
  installation/compatibility guidance, release notes and generated API version.
- Implemented nonpublishing candidate preparation and protected CLI-first
  Trusted Publishing. Candidates bind all six distributions, the tested image,
  receipts and release notes to their exact source and SHA-256 manifest.
  Publication verifies approved bytes and annotated tags and never rebuilds.
- Added immutable collision checks and partial-publication recovery for PyPI,
  GHCR and GitHub release assets. Documented operations and initial tooling's
  same-source baseline-tag constraint.
- Added exact-wheel image builds alongside the existing source build and a
  disposable isolated-engine deployment qualification harness.
- Prepared the manual first-baseline review, candidate declarations and consumed
  change record without rewriting its original contents. Imported packages are
  unchanged. See [initial release review](../../validation/initial-release.md) for
  requirement coverage, platform limits and Macrostates CLI limitations.

## Verification

- Full Python/Docker suite: 543 passed, one externally configured S3 test
  deselected. Five frontend test files, Ruff, Pyright, version/lock checks,
  generated API drift and Macrostates composition/import integrity passed.
- All three wheels clean-install and all three source distributions rebuild
  independently. Existing-artifact verification preserves their hashes.
- Exact-wheel service image smoke passed two-step execution, managed artifact
  publication, repeated-run reuse, component logs, packaged UI/OpenAPI and
  persisted history after restart. The default source image build also passed.
- Capability-description follow-up passed 36 focused interface/release tests;
  final release-tool checks passed all 22 provenance/integrity tests.
- Reviewed 272 authored text files and 361 relative Markdown links: no broken
  links or private identifying data. All 36 earlier workflows are closed with
  retained closure evidence. All workflow actions are pinned by full commit.
- Local preliminary artifacts remain unapproved qualification outputs. Exact
  integrated-source CI and the hosted candidate are still required; no registry
  upload, release tag or finalized baseline is claimed.

## Definer-confirmed closure

The Definer explicitly confirmed closure on 2026-10-22, accepted the documented
bounded 0.1.0 implementation as the first baseline and authorized the transition
from bootstrapping to active. Submission and integration are authorized once
hosted CI passes. This closes local release preparation, not publication.
All 37 workflows are closed; no imported specification contract was changed.

The proposal and exact integrated-source CI must still pass in the hosting
system. Reviewed integration finalizes the accepted candidate declarations.
Then build and review the hosted candidate and obtain its publication/tag
approval. Publish the preserved artifacts and verify public identities,
installation and image access. Record later CI, integration and publication
outcomes in the hosting system/release assets rather than reopening this record.
