# Naming and publishing

Image names and tags should make image identity, version, and intended use clear.

## Image names

Image names should be stable and should identify the project, service, or tool
the image runs.

Project-specific specifications should define concrete image names when images
are part of the supported project interface or deployment model.

Avoid image names that depend on a single developer machine, temporary branch,
or local experiment.

## Application Versions And Macrostates Baselines

The application or image release policy defines its public version scheme,
authoritative version source, assignment mechanism, release conditions, and
registry promotion strategy. A project-specific specification may override a
package-provided policy according to composition authority. Different images or
services in a monorepo can retain independent application versions.

When Process's baseline/versioning policy is selected and no explicit
application versioning policy applies, the stable application or image version
is the numeric part of its selected finalized `imp-*` baseline. For example,
`imp-4.12.3` supplies `4.12.3`. An explicit independent application version
takes precedence. Macrostates `specs-*` and `imp-*` identities are provenance;
they must not silently replace a distribution's independently declared version.

Finalizing a new repository baseline does not automatically rebuild, release, or
publish every image. Unchanged published images retain their existing identity
and baseline provenance. Shared source or dependency changes must still be
reviewed for their effect on images that depend on them.

These Process-specific rules apply when Process is selected. This Docker package
remains usable without Process; in that case the project's declared image and
application policy supplies its release identity and provenance without requiring
Macrostates implementation artifacts or inventing a baseline.

## Tags

Use immutable tags for builds that may be deployed, released, audited, or
compared later.

Useful immutable tags may include a release version, Git commit, build number,
or another stable build identifier defined by the project.

Mutable tags such as `latest`, `dev`, or branch names may be used for
convenience, but they should not be the only way to identify an important image.

Production deployment should not depend on an ambiguous mutable tag unless a
project-specific specification explicitly accepts that tradeoff.

Keep immutable image identity separate from convenient version aliases. A digest,
source commit, or immutable build identifier may distinguish variants and rebuilds
of a version. When several deliverables release independently, use image names
and tag namespaces that cannot collide. Development images must expose honest
development/source identity rather than claim an unchanged stable release.

## Labels

Images should include useful metadata labels when practical.

Labels may identify source repository, revision, version, license, build time,
or image purpose. Do not put secrets or sensitive environment details in image
labels.

When Process is selected, release records and inspectable image metadata must
preserve the released deliverable identity and version, exact specification and
implementation baseline references, and source revision. Define label names or
the equivalent inspectable metadata mapping in the project policy. A release
record can bind the resulting image digest without trying to commit a source
commit hash into the same commit it identifies.

Populate metadata deterministically from the authoritative tracked declarations
or explicitly captured build provenance. A release source archive must not need
Git or a network lookup to rediscover its application version. Ordinary image
builds must not mutate version declarations, change records, counters, commits,
or tags. Do not copy source-control internals or credentials into runtime images
to obtain identity metadata. If source identity is unavailable, report that state
rather than fabricate finalization or provenance.

## Publishing

Pushing images to registries should be an explicit project operation.

Registry names, credentials, publishing permissions, and promotion rules belong
in project-specific specifications or deployment documentation.

Do not publish images from local experiments unless the active workflow and
project-specific rules allow it.

Where Process is selected, follow its reviewed integration and baseline release
preparation procedures. Preparing or finalizing a baseline is distinct from
application release preparation and registry publication. Neither a branch
merge nor a normal build automatically authorizes an image upload. No hosting
platform or external changeset product is required by these rules.

Before authorized publication, verify the exact image candidate's application
version, source and baseline provenance where applicable, immutable identity,
required checks, and target registry/promotion policy. Preserve published
identities. Report prepared, built, pushed, and promoted states accurately; a
partial upload or promotion does not imply the entire release succeeded.
