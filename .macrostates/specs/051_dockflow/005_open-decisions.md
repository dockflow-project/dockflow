# Publication scope and qualification gates

The preceding documents define the shared licensing, compatibility, dependency,
workspace/build and release policies. These are selected requirements, not open
implementation choices. Tool-specific contracts belong to the CLI, Pipelines and
Artifacts packages.

## Selected first-publication scope

The first publication is the source development preview defined in the
[release policy](004_releases.md#public-source-and-application-releases).
Installation uses the repository checkout and lock; the shared application stays
a development version until a separately approved application release. The
published scope is the implemented, documented profile with explicit evidence
limits. It does not advertise unqualified platforms or depend on PyPI/GHCR
accounts being provisioned.

No product or publication-policy decision remains open in this package. The
selected destinations, support targets and release procedure are requirements.
Checks against an actual candidate or hosting account are execution gates,
not unspecified design choices. Keep their measured status in implementation
records rather than assigning speculative outcomes here.

## Gates for each application release candidate

Apply the existing [compatibility](002_compatibility.md),
[build](003_dependencies-and-build.md) and [release](004_releases.md) policies to
the actual candidate:

1. **Qualified scope.** Identify the exact dependency resolution, service images
   and Python/platform combinations covered by evidence for that candidate.
   Resolve qualification gaps before advertising support. A configured CI matrix
   or a successful image build alone does not establish runtime qualification.
2. **Publication configuration.** Verify the selected PyPI/GHCR namespaces,
   ownership, permissions and Trusted Publisher configuration. Candidate-building
   automation and version checks do not establish an operational publishing
   workflow or authorize uploads.
3. **Release acceptance.** Assign the reviewed application version and exact
   source/baseline references, qualify the artifacts to be distributed, and obtain
   the approvals required by the release policy. A development build or completed
   qualification run does not finalize a baseline or publish a release.

## Implementation status and evidence

The [implementation overview](../../implementation/main.md) and its linked
[qualification records](../../implementation/validation/README.md) describe
implemented tooling, tested combinations and remaining limits. Keep dated
completion claims there; this specification defines the standing requirements
for assessing a candidate. Existing implementation must be reviewed against
those requirements rather than assumed absent or complete from this checklist.
