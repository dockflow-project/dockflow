# Packaging

Python projects using this package should use `uv` for package build and
packaging workflows.

Packaging turns the project source and declared metadata into distributable
artifacts. It should be reproducible from a clean checkout after installing the
documented development tooling.

## Project metadata

Package metadata should be declared in `pyproject.toml`.

The metadata should include the package name, version, supported Python version,
runtime dependencies, and any entry points required by the project.

The exact metadata fields depend on whether the project is an application,
library, service, tool, or mixed repository. Project-specific specifications may
define stricter metadata requirements.

Follow [Distribution Versioning And Releases](010_versioning.md) for the
implementation-derived default, explicit independent policies, development
identities, authoritative metadata, and release provenance. A repository baseline
does not automatically assign or publish every distribution's application version.

## Build tool

Use `uv` as the normal interface for building package artifacts.

The project may use a build backend supported by Python packaging standards, but
normal build commands should be expressed through `uv` when practical so they
use the same dependency and environment conventions as the rest of this package.

During bootstrapping, the Implementer should formalize the build backend,
package discovery, project metadata, and build commands.

## Build output

Built package files should be written to `./dist/`.

`./dist/` is generated output. It should not be committed and should be ignored
by the repository `.gitignore`.

Build artifacts should be regenerated from source and metadata rather than
edited manually.

## Source layout

Packaging configuration should support the `src` layout defined by this package.

Only intended package source, metadata, license files, readme files, typed
package markers, and explicitly included project resources should be included in
the build.

Generated files, tests, temporary files, local configuration, virtual
environments, caches, and implementation workflow records should not be bundled
unless a project-specific specification explicitly requires them.

## Vendored libraries

Vendored Python libraries required by the project must be included in the build
in a way that preserves the intended runtime behavior.

When vendored libraries are integrated through a `uv` workspace, the build
configuration should ensure the resulting package artifacts can resolve or
bundle those libraries according to the project's distribution model.

The Implementer should not silently drop vendored libraries from package
artifacts. If the appropriate packaging strategy is ambiguous, the Implementer
should ask the Definer before producing or publishing distributable artifacts.

## Verification

When packaging behavior changes, the Implementer should run the relevant build
command when practical and verify that artifacts are created under `./dist/`.

When practical, the Implementer should also perform a basic install or import
check from the built artifact, especially for libraries, command-line tools, and
projects with vendored libraries.

If packaging checks are skipped, the final response should say why.
