# Docker specification package

This package describes reusable Docker conventions for projects that build and
run container images.

## Macrostates

This package is part of [Macrostates](https://github.com/orgs/Macrostates), a
project for composing reusable specification packages into specs-driven
development projects.

## Summary

This package defines a reusable Docker baseline: separate development and
production image concerns, multi-stage builds, non-root runtime users, health
checks, image naming and tagging, safe environment variable and secret handling,
volume boundaries, container logging, restart policy expectations, dependency
caching, and a strict rule that credentials must never be baked into images.

Language-specific Docker rules belong in language or project-structure packages.
Project-specific image names, exposed ports, services, dependencies, and
deployment topology belong in project-specific specifications.

## Scope

- Docker image structure and build conventions.
- Development and production image expectations.
- Runtime container behavior.
- Configuration, secrets, volumes, and logging.
- Image naming, tagging, and metadata.
- Application-version policy and conditional Macrostates release provenance.
- Dependency caching and build hygiene.

Programming-language-specific packaging, application architecture, orchestration
platforms, and deployment infrastructure are out of scope for this package.

Process-specific baseline, preparation, and provenance rules apply when a
project selects Process 5.0.0 or later, as the optional dependency declares.
Docker conventions remain usable without it. An
explicit application policy may version images independently; otherwise a
Process-governed stable release uses the numeric selected implementation version.
Image publication is a separate authorized operation from baseline finalization.

Required and optional minima use explicit `at_least` constraints. Numeric
eligibility across future majors does not establish semantic compatibility;
review those selected requirements before adopting them.

## Macrostates artifacts

Follow the selected Meta package's project layout: numbered specification
packages and the project entrypoint are tracked under `.macrostates/specs/`.
Implementation documentation, decisions, workflows and release declarations,
when required by project rules, live under `.macrostates/implementation/`.
Application source, tests, build configuration and runtime configuration retain
their language/tool locations outside `.macrostates/`. This package does not
make the Macrostates CLI mandatory or change the scope of a subproject.

## Reading order

1. [Images](001_images.md)
2. [Runtime](002_runtime.md)
3. [Naming and publishing](003_naming-and-publishing.md)

## License

This specification package, including its documentation, metadata, and bundled
resources, is licensed under the [MIT License](LICENSE).

Copyright (c) 2026 Lucas Lopez.

## AI assistance

This project was developed with AI assistance.
