# Distribution Versioning And Releases

## Ownership

Process owns project-wide `specs-MAJOR.MINOR.PATCH` and
`imp-MAJOR.MINOR.PATCH` baselines, computed development identities, change
records, integration preparation, and release preparation. Meta owns each
reusable specification package's independent version. Neither identity is
automatically the public version of every Python distribution in a repository.

This package supplies a Python distribution default. Project-specific
specifications or another selected package may define an explicit independent
versioning and release policy according to composition authority. That policy
can select a changeset tool, CI automation, or a documented manual procedure.
This package requires no particular external changeset product or hosting
platform. Repository integration and application publication remain separate.

## Default And Overrides

Without an explicit distribution policy, use the numeric part of the finalized
implementation baseline selected for the release: `imp-4.12.3` gives `4.12.3`.
Do not include the `imp-` prefix or a Macrostates development suffix in a stable
distribution version. Do not derive the distribution version from a reusable
specification package's version.

A declared independent policy defines its version scheme, public compatibility
surface, authoritative source, assignment mechanism, checks, release conditions,
and tagging/publication procedure. It may retain a version such as `7.3.25`
while the repository has `imp-4.12.3`. Applications, libraries, services, and
workspace members may have separate release policies and schedules; each
independently released distribution has a stable deliverable identity.

A new Macrostates baseline does not automatically publish or change the recorded
release identity of every distribution. Unchanged published distributions retain
their previous versions and exact baseline provenance. Shared changes must still
be reviewed for their effect on dependent deliverables.

## Authoritative Build Metadata

`pyproject.toml` declares the distribution metadata and either its authoritative
version or the configured source from which the build backend obtains it. There
must be one editable authority for each version, rather than competing constants
in the build configuration, Python source, documentation, and CI.

The optional Process `.macrostates/implementation/deliverables.yaml` document
can declare identities, strategies, versions, and exact baseline references. A
project may use another explicit authoritative application declaration and a
deterministic metadata mapping. A build must validate that the selected policy
and distribution metadata agree. Independent versions are assigned under that
policy; Macrostates release preparation must not silently choose them.

Version strings must satisfy Python distribution version rules. The build may
represent development status using an appropriate Python development or local
version under its policy, or capture development provenance separately where
appropriate. Raw Macrostates strings such as
`imp-4.12.3-branch.feature-x.gabc123` are not Python distribution versions and
must not be copied into package metadata verbatim.

Development builds must not claim that changed source is the unchanged stable
release. Record the applicable development/candidate status and source identity
under the declared build policy. Do not guess a future official version from a
branch name, reserve a Macrostates version on a feature branch, or rely on a
moving tag for package identity.

A clean release checkout and source distribution must build the declared version
without consulting Git, the network, a user's current directory, or untracked
machine-local version settings. Include any authoritative version resource
needed by the build in the source distribution. A source archive without Git may
use explicitly captured build provenance or report unavailable source identity;
it must not invent finalization or commit data.

Ordinary builds do not mutate versions, change records, release dates, Git state,
or tags. Keep version assignment in the explicit release-preparation procedure.
If runtime version reporting is exposed, it must agree with the installed
distribution metadata.

## Preparation And Release Provenance

During feature work, declare specification and implementation impacts through
Process change records. Keep their original starting baselines when refreshing a
development branch from its target; review inherited changes and rerun affected
checks. A package build does not finalize those pending baselines.

Complete and close the relevant work and integration-preparation workflows
before submitting the integration proposal. Apply Process's local preparation
and final integration gates; external review and checks may begin after the
proposal exists, but required reviews and checks still block integration. The
proposal mechanism is defined by the repository policy, not this package.

Repository release preparation aggregates pending records and proposes official
Macrostates baselines. Distribution release preparation follows the selected
default or independent application policy. Neither ordinary integration nor
baseline finalization automatically authorizes distribution publication.

Each finalized distribution release records its stable deliverable identity,
distribution version, exact `specs-*` and `imp-*` baselines, and source commit.
Its own version need not share their Major.Minor. References for an unchanged
previously published distribution remain historical rather than being rewritten
to the latest repository baseline. In a monorepo, use unambiguous release/tag
namespaces where distributions have separate identities.

Before authorized publication, verify the exact candidate's metadata, baseline
references, version uniqueness under the distribution policy, and required
validation. Preserve published identities. Distinguish a prepared candidate,
tagged source, and uploaded distribution when reporting completion or recovering
from partial publication.

## Verification

For packaging or version-source changes, verify:

- The selected default or explicit override is clear and metadata agrees with it.
- Wheels and source distributions contain the same intended distribution version.
- A source-distribution build succeeds without its original Git checkout.
- Clean artifact installation and runtime version reporting agree where exposed.
- Build commands do not edit declarations, counters, records, or Git state.
- Release provenance identifies the exact source and Macrostates baselines.
- Unchanged workspace members retain their own published identities.

Use the package's normal build and project environment commands. Report checks
that could not run and why; matching numeric version fields is not proof that
requirements are implemented.
