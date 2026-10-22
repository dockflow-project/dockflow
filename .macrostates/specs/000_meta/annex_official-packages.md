# Annex: official Macrostates specification packages

Read this catalog when discovering packages for project kickoff or discussing a
composition with the definer. It is selection guidance, not an import instruction,
package selection or normative dependency on any listed package.

The following existing repositories were verified against the canonical
[Macrostates organization](https://github.com/Macrostates) and each repository's
`package.yaml` and `README.md` on 2026-10-08. Use the repository links or HTTPS
clone URLs below to inspect instructions. Install verified published releases
rather than using an inspection checkout as the installed package.

| Package | When to suggest it | Typical local directory | Official HTTPS repository |
| --- | --- | --- | --- |
| [meta](https://github.com/Macrostates/macrostates-meta) | Specification packages, composition, authority and discovery; common foundation. | `000_meta/` | `https://github.com/Macrostates/macrostates-meta.git` |
| [process](https://github.com/Macrostates/macrostates-process) | Specification-driven development, workflows and lifecycle; common foundation. | `001_process/` | `https://github.com/Macrostates/macrostates-process.git` |
| [repository-1](https://github.com/Macrostates/macrostates-repository-1) | General source repository conventions, documentation and Git hygiene. | `010_repository-1/` | `https://github.com/Macrostates/macrostates-repository-1.git` |
| [docker-1](https://github.com/Macrostates/macrostates-docker-1) | Docker images, container runtime and publishing when containers are wanted. | `011_docker-1/` | `https://github.com/Macrostates/macrostates-docker-1.git` |
| [python-1](https://github.com/Macrostates/macrostates-python-1) | Language-level conventions when Python is selected. | `020_python-1/` | `https://github.com/Macrostates/macrostates-python-1.git` |
| [python-project-1](https://github.com/Macrostates/macrostates-python-project-1) | Python project layout, tooling, testing and packaging, including applications. | `030_python-project-1/` | `https://github.com/Macrostates/macrostates-python-project-1.git` |
| [python-library-1](https://github.com/Macrostates/macrostates-python-library-1) | Reusable Python libraries, public API, compatibility and library documentation. | `031_python-library-1/` | `https://github.com/Macrostates/macrostates-python-library-1.git` |
| [android-app-1](https://github.com/Macrostates/macrostates-android-app-1) | Android applications using the package's Kotlin/Gradle, build and quality conventions. | `040_android-app-1/` | `https://github.com/Macrostates/macrostates-android-app-1.git` |

## Explain a compatible selection

Start with the definer's goals and technology choices, using Meta and Process as
the usual foundation. Add relevant repository, runtime, language and project-shape
packages and explain the benefit of each. A library and an application can require
different project-shape packages even when they share a language. Typical paths
do not define authority or make optional technologies mandatory.

Read every proposed release's entrypoint and `package.yaml` before selecting it.
For a new composition, start with the latest published releases appropriate to
the project's intent and validate the whole selection. `at_least` is the
dependency authoring default; explicit `compatible` or `exact` declarations
remain binding. Passing a numeric minimum does not prove semantic compatibility
with a later Major. Existing deliberate selections require an authorized update.
Find a published `v<version>` tag in its canonical repository, verify its identity,
and resolve required dependencies against the complete proposed composition.
Check optional constraints only for selected optional packages. The catalog does
not pin versions, guarantee compatibility between arbitrary releases or replace
package-owned metadata. Older releases may impose different Process or technology
constraints; do not infer compatibility from another package's requirements.
Report incompatible choices and discuss compatible
releases or explicitly requested specification changes with the definer.

This is a checked inventory, not a guarantee that no additional official packages
exist. Refresh discovery from the organization or canonical repositories when
needed, and distinguish a real source from an unpublished local draft. A package
must have real source metadata and a verified release before an import is claimed.
Domain and project-local packages outside this catalog can be selected deliberately
under the normal composition rules; they are not official Macrostates packages
merely because a consuming project contains them.

Return to [Project kickoff](annex_project-kick-off.md) to prepare the manifest and
perform verified release imports after the definer's choices are established.
