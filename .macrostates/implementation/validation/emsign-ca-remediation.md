# eMudhra / emSign remediation verification

Scope: repository-owned source, package metadata, build tooling, reference images
and publishing runtime. No host OS, consumer repository or unrelated environment
was modified. Specification impact is none; implementation impact is patch.

## Sources and scope

- [Python incident guidance](https://discuss.python.org/t/information-for-python-users-regarding-emudhra-emsign-ca-certificate-security-incident/109576).
- [uv incident advisory](https://github.com/astral-sh/uv/security/advisories/GHSA-hq85-5cpj-mr62).
- [gRPC root update](https://github.com/grpc/grpc/pull/43700).
- [Root and cross-sign disclosure](https://www.openwall.com/lists/oss-security/2026/10/20/1).

The trust check parses certificate subjects and rejects all three disclosed
root trust paths, including AAA Certificate Services. It is a targeted offline
regression check, not a comprehensive revocation service or TLS implementation.

## Verification

- uv 0.13.5, Python 3.13.17, certifi 2026.10.19, gRPC 1.84.1;
  Linux x86-64. Refreshed managed Python 3.12.15 also contains pip/ensurepip 26.2.2.
- Full Python suite: 565 passed, one opt-in S3 case deselected; real Docker and
  loopback HTTP checks included. The S3 case separately passed against rebuilt
  MinIO, including concurrent conditional publication, interruption and corruption.
- Final S3 default review also covers explicit `verify=None`; all 23 CA/publisher
  regression tests passed after that correction.
- 25 frontend assertions passed; Ruff, format, Pyright, generated API drift,
  composition/import integrity and whitespace checks passed.
- Clean wheel installations and independent sdist rebuilds passed for all three
  packages. The exact exported third-party lock has no known audit findings.
- The service image completed non-root readiness, UI/OpenAPI, two-step execution,
  artifact reuse, logs and persistent restart in a disposable isolated engine.
- Registry push/pull preserved exact image identity in a disposable loopback test.
- Service, publisher, executor, registry, MinIO and quickstart base trust bundles
  passed. The previous candidate fails the new check (gRPC 1.84.0).
- PyPA metadata validation passed offline on preserved candidate distributions.
  Unit tests cover protected workflow guards, OIDC credential forwarding by name,
  and separate writable attestation staging. Actual upload/OIDC issuance remains
  a future publication operation; no replacement release is claimed.

The first restricted local test invocation stalled in socket-dependent cases and
was stopped; the full run above used the required local socket/Docker access.
A package-verification permission review timed out; the authorized retry passed.
Neither event is recorded as a product regression.

## Qualified local image identities

- Service: `sha256:7bbd64d348d34f88b69aa1cf33cd01b14342eaf34721479ae857fcc1d8280cdc`.
- Isolated engine: `sha256:5c55c09e530910b39bbc51fe8e9f5a1cbf1d07aa93967d37de4cac681a56ae06`.
- Publisher: `sha256:d98c08c1b4438f8ff9f3358c2ab4e2874bb9a7be9a5e27818314730803a56a6c`.

Hosted CI will independently rebuild and verify the submitted source before merge.

## Release boundary

Candidate 39787991471 is withdrawn from further publication. Its preserved image
is sha256:be5b34f7d7708942853b9f6aad6c6201382782f84eb2eecc212f069517893b7e.
Existing 0.1.0 tags and the uploaded CLI remain immutable. Fixed package builds
are local verification outputs, not replacements for that public version.
Baseline declarations remain specs-0.1.0/imp-0.1.0 with a pending patch record;
future release preparation must select a new coordinated application version.

Host certificate stores, custom CA bundles, other virtual environments and user
task images need their own updates. The maintenance guide explains the boundary
and commands. Runtime qualification remains Linux x86-64; hosted base-package
checks cover the existing Python/platform matrix before integration.
