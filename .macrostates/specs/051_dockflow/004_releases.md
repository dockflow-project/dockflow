# Shared application releases

## Public source and application releases

The first public repository publication is a **source development preview**.
It makes the MIT-licensed source, specifications, tests, examples and development
instructions available for inspection and installation from a checkout. Retain
the development application identity from `VERSION`; source publication does
not allocate a stable version or require uploading distributions or service
images.

The public entrypoints must identify this preview, describe the implemented
compatibility profile and link to its tested scope and remaining qualification
limits. Provide a reproducible locked installation and self-contained example.
Source availability does not establish full initial-profile conformance, native
platform qualification or an operational package registry. Reject unsupported
runtime requests under the existing product contracts.

Source publication preserves Process's reviewed integration, baseline provenance
and workflow rules. Closing workflows does not finalize baselines, create tags,
merge source or authorize publication. Repository publication and versioned
application releases are separate authorized operations; neither implies the
other. The candidate procedure below governs versioned package/image releases.

## Versions and authority

All first-party distributions share one Dockflow `X.Y.Z` application version
and release history. Stable application tags are `vX.Y.Z`. This explicitly
overrides Python Project's implementation-derived distribution default while
preserving Process's separate `specs-*` / `imp-*` baselines, workflow closure,
reviewed integration, and release-finalization requirements.

Classify the application version against all supported Python, CLI, REST, and
persisted-data compatibility surfaces. Stable releases use semantic versioning;
pre-1.0 breaking changes still require explicit review and release notes. Release
candidates use Python-compatible versions such as `0.1.0rc1`, with a matching
application tag `v0.1.0rc1`. Examples do not allocate an actual release.

A tracked repository-root `VERSION` file is the single editable authority for
the application version. It contains the normalized Python distribution version
without a `v` prefix. Release preparation assigns that version and synchronizes
each member's static `project.version` and inter-package dependency metadata.
Those generated/synchronized fields are not separately edited authorities.
CI and release checks reject disagreement. Runtime version reporting reads
installed distribution metadata.

Each source distribution includes its synchronized version metadata so it can
rebuild independently of the repository-root file, Git, or a network lookup.
Ordinary builds do not edit `VERSION` or synchronize metadata. Development builds
identify their unreleased/source state and must not present changed source as an
unchanged published stable artifact; development-version encoding must satisfy
Python packaging rules. Create the version file and release tooling during
implementation, not merely to fill this initial specification.

## Publication destinations

| Deliverable | Selected destination and identity |
| --- | --- |
| Shared CLI | PyPI distribution `dockflow-cli`. |
| Pipelines | PyPI distribution `dockflow-pipelines`. |
| Artifacts | PyPI distribution `dockflow-artifacts`. |
| Dockflow Pipelines service image | `ghcr.io/dockflow-project/dockflow-pipelines`, tagged with the same application version and bound to an immutable digest. |
| Versioned application source and release notes | `dockflow-project/dockflow`, with one shared `v<version>` tag and release record. |

These destinations express the intended publication policy, not reserved names,
existing uploads, or configured permissions. Verify availability, ownership,
publisher permissions, and visibility before publication. Third-party Compose
service images and user task images retain their own independently pinned
identities; they do not inherit Dockflow's version.

## Qualification and publication procedure

Use GitHub Actions for release automation, with manual release initiation and
explicit approval before external publication. Configure PyPI Trusted Publishing
separately for each distribution; use short-lived workflow credentials and
scoped registry permissions rather than stored personal publishing tokens.
Acceptance of this specification authorizes future tooling design, not an upload
or tag operation in the current session.

Before publishing versioned distributions or service images:

1. Follow Process's current-target integration and baseline procedures. Complete
   the required reviews, close workflows only with definer confirmation, and
   resolve any overdue compatibility review with the definer.
2. Prepare and review the shared application version, dependency metadata,
   release notes, migration information, and exact source/baseline references.
3. Pass the declared Python/platform tests, unit/integration/contract checks,
   clean wheel installs, standalone source-distribution rebuilds, version and
   dependency consistency checks, and the Pipelines deployment smoke tests.
   Keep explicit gaps from being mistaken for qualified platforms or features.
4. Build candidate artifacts once, record their hashes/digests and build
   toolchain, and verify those exact artifacts. Obtain publication approval for
   that candidate; changed source or rebuilt artifacts require reassessment.
5. Publish the already verified CLI wheel/sdist before Pipelines, publish the
   Pipelines and Artifacts wheels/sdists, then the matching service image and
   shared release record. Account for all three distributions and the image when
   recording outcomes or recovering a partial publication. Verify the resulting
   identities; do not rebuild different artifacts after approval.

Every versioned application-release deliverable records its version, exact source commit, exact
`specs-*` and `imp-*` baseline references, and artifact identity. Macrostates
baseline numbers need not equal the public application version. Annotated source
and baseline tags are created and verified only through their authorized
procedures. A tracked candidate declaration must not embed its own eventual
commit hash; use an immutable source tag resolved at publication or a post-commit
release receipt.

Publish the current first-party distributions together for the shared version.
If publication partly fails, preserve successful immutable identities and report
the incomplete release. Resume with the same verified artifacts where allowed;
never replace a published version with different bytes. A later independent
release cadence or changed version policy requires a deliberate specification
update. Builds and baseline finalization alone do not publish applications.

Reference: [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/).
