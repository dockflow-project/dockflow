# Coordinated 0.1.1 release review

Application candidate: 0.1.1, all three distributions and the matching service
image. Baselines: unchanged specs-0.1.0 and proposed imp-0.1.1. Original target:
7491beded1b08a3f08f93c2fcfd2bd9deadea601. Branch: release/0.1.1.
Release-plan source: 1050844f1f246518482ba44e7c8cd8631b9c8c9a.
State: the Definer accepted the proposed baseline and confirmed preparation
closure and submission/integration after hosted CI on 2026-10-22.
No publication or candidate approval claimed.

## Scope and provenance

Includes accepted eMudhra/emSign maintenance, version synchronization and normal
upstream publication. No product contract changes or unrelated dependency
upgrades. The release plan binds consumed change bytes and original declarations;
previous planning evidence is retained in history/release-plans/0.1.0.yaml.
The accepted initial profile and runtime qualification limits remain unchanged.

The application and implementation tags must identify the exact release commit.
The unchanged specification tag remains at its original commit: its full
.macrostates/specs tree is identical and ancestral. Real Git tests reject changed
specification bytes, unrelated ancestry, lightweight tags and older implementation
source. The original 0.1.0 tags and uploaded CLI remain immutable; candidate
39787991471 is withdrawn and will not be resumed.

Publication restores the official PyPA v1.14.3 action pinned at
7245906fb61fa33a13554f9d5fb856fe61758086. The custom Dockerfile, wrapper and related
tests are removed. Trusted Publishing environments and PEP 740 attestations are
retained; no fallback token or alternate upload process is introduced.
The [upstream advisory](https://github.com/pypa/gh-action-pypi-publish/security/advisories/GHSA-5xjx-3w67-w9x9)
identifies v1.14.3 as patched. Offline inspection of the upstream image confirms
certifi 2026.10.19, sigstore 4.5.1 and 120 effective certificate authorities with
none of the disclosed roots. This checks the publisher's active network trust;
it does not claim every unused bootstrap bundle in that third-party image was
rebuilt. It does not issue OIDC credentials or upload packages.

## Verification

- All three 0.1.1 wheels clean-install; all three sdists rebuild independently.
- 27 release integrity/provenance tests pass, including five real Git scenarios.
- Ruff, formatting, Pyright, generated API/version checks, frontend tests and
  Macrostates composition/import integrity pass.
- Full Docker-backed regression suite: 568 passed, one opt-in S3 test deselected;
  four upstream warnings, no failures.
- Workspace lock changes only the four first-party versions; third-party
  resolution remains unchanged from accepted CA maintenance.

## Remaining release gates

Workflow closure is confirmed; reviewed integration requires hosted CI. Run the
nonpublishing candidate workflow on that exact main source; inspect its package,
image and smoke receipts, then obtain approval for the exact manifest before
creating the new annotated tags and starting protected publication.
Source preparation and local artifacts do not establish a published 0.1.1.
