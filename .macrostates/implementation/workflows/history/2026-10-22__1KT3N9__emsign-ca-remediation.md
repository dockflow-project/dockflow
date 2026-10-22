# eMudhra / emSign CA remediation

- Project phase: active
- Workflow type: Implementation update
- Status: completed
- Delivery state: accepted
- Change depth: moderate
- Branch: fix/emsign-ca-trust
- Requested by: Definer
- Implementer: Implementer
- Started at: 2026-10-22 15:05 UTC
- Last updated at: 2026-10-22 15:51 UTC

## Objective and authority

Remediate the eMudhra/emSign certificate trust incident in repository-owned
build tooling, Python environments, deployment images and installation guidance.
Follow the [Python security announcement](https://discuss.python.org/t/information-for-python-users-regarding-emudhra-emsign-ca-certificate-security-incident/109576)
and verify the actual embedded trust stores, including pip and gRPC.
The Definer explicitly authorized branch creation, implementation, workflow
closure after verification, push, PR submission and merge after required CI.
No further publication or replacement of immutable release artifacts is included.

Starting source: 55b7ec5da52c02648a1723d9e5cfade6c42e4c51.
Starting baselines: specs-0.1.0 / imp-0.1.0. Specification impact: none;
implementation impact: patch. Preserve finalized tags and published CLI files.
The previous release candidate is rejected for further publication.

## Acceptance criteria

- Patch the package/network tooling and rebuild owned images from reviewed pins.
- Remove affected trust from runtime and bundled bootstrap certificate stores.
- Add meaningful regression checks which reject the old candidate and validate
  the fixed artifact; retain TLS verification and unaffected trust.
- Document remediation for existing installs and third-party task images.
- Pass repository checks, clean packaging, service execution smoke and hosted CI.
- Close this workflow under the explicit instruction, then integrate through PR.

## Work and evidence

Updated uv, managed Python and gRPC; declared optional dependency security
floors. S3 clients use maintained certifi by default while retaining explicit
CA configuration. Rebuilt service, executor, registry, quickstart and publishing
runtimes remove the disclosed trust paths, including AAA cross-signing trust.
The publisher retains pinned PyPA upload/OIDC/attestation code and stages copies
without changing the approved candidate. Installation guidance covers existing
environments and consumer-owned task images.

The offline regression gate inspects parsed certificate subjects and embedded
pip/ensurepip stores. The original candidate fails; rebuilt images pass.
Full Python, frontend, real S3, clean package and service execution checks passed;
[verification and limits](../../validation/emsign-ca-remediation.md) records the
evidence. [The pending patch](../../changes/emsign-ca-remediation.yaml) preserves
starting baselines. No specification or release-version change is required.

## Closure and integration

Closed under the Definer's explicit instruction to complete, close, push and
merge this remediation. Local review and applicable verification are complete;
proposal-triggered hosted CI must pass before integration. No other workflows
remain open. This closure does not authorize package/image publication.
The withdrawn candidate, uploaded CLI and immutable tags remain unchanged.
