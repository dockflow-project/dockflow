# Repository specification package

This package describes reusable conventions for a source code repository. It is
intended for projects that want the same baseline hygiene, configuration,
compatibility, and version control expectations.

## Macrostates

This package is part of [Macrostates](https://github.com/orgs/Macrostates), a
project for composing reusable specification packages into specs-driven
development projects.

## Scope

- Repository self-containment.
- Configuration and secret hygiene.
- Generated and local file boundaries.
- Root repository contents.
- Repository documentation.
- Git feature/release branches and platform-independent reviewed integration.
- Fork and topic-branch synchronization, stale validation and merge gates.
- Compatibility surfaces.
- Commit hygiene.

Language-specific rules, process rules, and domain-specific behavior are out of
scope for this package.

All authored changes are developed on topic branches and enter the primary
branch through the defined review procedure: pull/merge requests when available
or an explicit native Git equivalent. Implementers must not author file changes
while checked out on the primary branch. See [Technology](004_technology.md) for Git behavior and authorization.

## Macrostates artifacts

Follow the selected Meta package's project layout: numbered specification
packages and the project entrypoint are tracked under `.macrostates/specs/`.
Implementation documentation, decisions, workflows and release declarations,
when required by project rules, live under `.macrostates/implementation/`.
Application source, tests, build configuration and runtime configuration retain
their language/tool locations outside `.macrostates/`. This package does not
make the Macrostates CLI mandatory or change the scope of a subproject.

## Reading order

1. [Conventions](001_conventions.md)
2. [Contents](002_contents.md)
3. [Documentation](003_documentation.md)
4. [Technology](004_technology.md)

## License

This specification package, including its documentation, metadata, and bundled
resources, is licensed under the [MIT License](LICENSE).

Copyright (c) 2026 Lucas Lopez.

## AI assistance

This project was developed with AI assistance.
