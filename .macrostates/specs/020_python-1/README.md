# Python-1 specification package

This package describes one reusable convention set for Python code. It is
intended for projects that want these language-level expectations without
necessarily using the same repository layout, tooling, packaging, or test
structure.

## Macrostates

This package is part of [Macrostates](https://github.com/orgs/Macrostates), a
project for composing reusable specification packages into specs-driven
development projects.

## Summary

This package defines a reusable Python baseline: modern supported Python, clear
and maintainable code, practical type annotations at stable boundaries,
`pathlib` filesystem paths, timezone-aware UTC timestamps for real moments,
meaningful exception handling, standard Python logging, and testable I/O
boundaries.

Project-shaped Python repository conventions belong in a project package such
as `python-project-1`.

## Scope

- Python runtime posture.
- Code clarity and module responsibility.
- Type annotation expectations at stable boundaries.
- Filesystem path handling.
- Time and timestamp conventions.
- Error handling.
- Logging.
- I/O boundary testability.

Project layout, dependency management, formatting tools, linting tools, static
type checking tools, test layout, hooks, packaging, and Docker integration are
out of scope for this package.

Under Process 5, project `specs-*` and `imp-*` baseline versioning belongs to
Process. Python
distribution versions, release policies, and any application-specific overrides
belong to the selected project/library or local application specifications. This
language baseline neither couples distribution versions to repository baselines
nor requires a particular integration or publication tool.

## Macrostates artifacts

Follow the selected Meta package's project layout: numbered specification
packages and the project entrypoint are tracked under `.macrostates/specs/`.
Implementation documentation, decisions, workflows and release declarations,
when required by project rules, live under `.macrostates/implementation/`.
Application source, tests, build configuration and runtime configuration retain
their language/tool locations outside `.macrostates/`. This package does not
make the Macrostates CLI mandatory or change the scope of a subproject.

## Reading order

1. [Python](001_python.md)

## License

This specification package, including its documentation, metadata, and bundled
resources, is licensed under the [MIT License](LICENSE).

Copyright (c) 2026 Lucas Lopez.

## AI assistance

This project was developed with AI assistance.
