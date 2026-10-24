# HTTP security and dependency fixes

- Project phase: `bootstrapping`
- Workflow type: `Implementation amendment` (security corrections)
- Status: completed
- Delivery state: `accepted`
- Change depth: `medium`
- Branch: `feat/initial-implementation` (unborn)
- Requested by: Definer
- Implementer: AI-assisted implementation
- Started at: 2026-10-21 14:39 (UTC)
- Last updated at: 2026-10-21 19:54 (UTC)

## Objective and scope

Correct service authentication decisions for malformed Host headers and mounted
paths, prevent the remote client's credentials from following redirects, and
update the vulnerable Python dependencies identified in the publication review.
Add meaningful regression coverage, verify the refreshed environment and update
operating documentation/current-state evidence. Preserve optional-auth
and local execution defaults. Scope is Dockflow HTTP boundaries and dependency maintenance. Release
identities, Git integration and publication are outside this workflow.

## Context and acceptance

At original delivery, the previous open-source review and other implementation
workflows remained open awaiting their own acceptance. This correction was
separately tracked and did not then close or supersede them. The development
branch contained the uncommitted initial implementation.

Acceptance: malformed hosts cannot exempt protected API reads, mutations or
uploads from authentication; valid health/UI, root-path and token usage remains
functional; remote redirects cannot disclose tokens or replay requests to an
unexpected endpoint; dependency metadata and lock agree and the previously
reported advisories are removed from the qualified environment. Run HTTP, KFP
upload, packaging, Docker runtime and normal quality checks as applicable, and
record actual coverage and limits.

## Implementation and decisions

Service admission validates Host before inspecting reconstructed URLs and uses
ASGI routing paths with segment-aware root-path handling for authentication and
native/KFP error envelopes. Invalid/duplicate/missing hosts return 400. The
standard-library remote client rejects redirects for all API methods/origins,
including HTTPS downgrades, and keeps the configured TLS context. Public health
and UI routes, valid bearer access and unauthenticated local defaults remain.

Updated FastAPI to the qualified 0.136 line and declared the already-imported
Starlette dependency at >=1.9,<2; the former FastAPI bound prevented security
fixes. FastAPI 0.136.3 supports the patched Starlette without introducing the
unrelated mandatory telemetry dependencies observed in newer FastAPI metadata.
The lock now uses Starlette 1.9.0, certifi 2026.10.19 and pytest 9.1.1. KFP 2.17.0
is still the latest available KFP release and exactly pins urllib3 2.7.0. A scoped
uv override selects urllib3 2.8.0, qualified against KFP/DockerRunner on both
supported Python versions. This does not modify or fork KFP. The standalone
install override file is checked against the workspace setting and documented;
ordinary pip resolution still follows upstream metadata. Dependency checkers
therefore report one expected KFP/urllib3 metadata conflict. Other conflicts are
not waived. Reassess/remove the exception when upstream allows a fixed release.

No specification package change was needed: these corrections enforce the
existing secret-file bearer, endpoint and dependency-maintenance contracts.
Updated operating docs, current implementation overview, package install examples
and generated API references. FastAPI's generated validation-error schema gains
optional input/ctx properties. CI audits the exported third-party lock using
pinned pip-audit; first-party workspace packages are excluded from the public
advisory lookup. No vulnerability advisories are suppressed.

## Validation

- Python 3.13.16: 499 tests passed, one S3 integration test deselected.
- Python 3.12.15: 499 tests passed, one S3 integration test deselected.
- Both runs include actual Docker execution, owner locks, service recovery and
  the official KFP SDK upload/client contract.
- New tests cover malformed/duplicate/missing Host, token-protected reads/writes/
  uploads, proxy roots, valid IPv4/IPv6/DNS hosts, same/cross-origin redirects for
  GET/POST and 301/302/303/307/308, normal credentials and HTTPS downgrade refusal.
- Five browser logic tests, Ruff lint/format, Pyright, version validation,
  generated API drift check and Macrostates check passed.
- pip-audit 2.10.1: 81 applicable locked third-party dependencies, zero known
  vulnerabilities; earlier reviewed findings are absent from that environment.
- All wheels/sdists built and base clean installs/independent sdist rebuilds
  passed. Clean Python 3.12 installation of built wheels with runtime/service/S3
  and Artifacts KFP extras succeeded with the documented standalone override.
- Built isolated image tag dockflow-pipelines:security-review. A real Uvicorn
  probe in that non-root, network-isolated image returned 401 without a token,
  400 for the malformed-host write, and 200 for valid authentication/public health.
  No user workloads or existing services were touched.

Portable evidence: ../../validation/http-security-fixes.json. Detailed remediation,
raw audit output and image probe are retained under ignored tmp/reviews/. No
private local paths or real credentials were added to the public evidence.

## Qualification limits

The KFP metadata
exception is documented installation policy until upstream updates its pin;
plain pip runtime installs do not inherit uv's override. Full S3/Compose provider
and OS-image vulnerability scans are outside this correction. No source was
merged, published or tagged; unrelated readiness findings remain separate.

## Definer-confirmed closure

On 2026-10-21, the Definer explicitly authorized closure of the complete existing
open-workflow set. Review confirmed that this workflow's recorded scope was
delivered; it is accepted and closed as `completed` under that authorization.
The recorded evidence and qualification limits remain unchanged. Closure does
not claim fresh runtime validation, accept or finalize project baselines, or
authorize PR preparation, commits, pushes, tags or external publication.
