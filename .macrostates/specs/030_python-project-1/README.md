# Python project specification package

This package describes reusable conventions for a Python repository. It is
intended for Python projects that want the same baseline layout, tooling,
packaging, and testing expectations.

## Macrostates

This package is part of [Macrostates](https://github.com/orgs/Macrostates), a
project for composing reusable specification packages into specs-driven
development projects.

## Summary

This package defines a reusable Python project baseline built on the generic
`python-1` package: `src` layout, `pyproject.toml` project configuration, `uv` for
virtual environments, dependency management, workspaces, and packaging, Ruff for
formatting, linting, and import sorting, Pyright for checking declared types,
`pytest` for unit and integration tests, `pytest-cov` for coverage measurement,
API contract tests for APIs, and `pre-commit` for Git hooks. It also includes a
conditional Docker annex for Python projects that use Docker.

It also defines conventions for exceptional vendored internal Python libraries:
vendored libraries live under `./vendor/`, are normally maintained with Git
subtree, are recorded in `./vendor/subtrees.toml`, integrate through `uv`
workspaces when practical, and may behave as subprojects with their own local
specifications or lifecycle.

## Scope

- `src` project layout conventions.
- uv-based virtual environment and dependency management conventions.
- Vendored internal Python library conventions.
- Ruff-based formatting conventions.
- Ruff-based linting conventions.
- Pyright-based type checking conventions.
- Unit, integration, and API contract testing conventions.
- pre-commit-based Git hook conventions.
- uv-based packaging conventions.
- Distribution version defaults, explicit independent policies, and release provenance.

Domain-specific behavior, repository integration policy, and general workflow
ownership are out of scope for this package. Distribution-specific build
integration follows the selected Process and application policies.

## Process compatibility

This release requires Process 5.0.0 or later and uses its separate `specs-*` and
`imp-*` baselines, change records, and reviewed release-preparation policy.
The dependency declaration records all required minima. An `at_least` constraint permits
selection across majors, but does not prove semantic compatibility with future
requirements. Earlier Python-project releases retain their original rules.

Python distributions default to the numeric part of their selected finalized
implementation baseline unless another effective specification declares an
independent application policy. Process owns repository baseline versions;
application specifications own distribution versions and publication strategy.

## Macrostates artifacts

Follow the selected Meta package's project layout: numbered specification
packages and the project entrypoint are tracked under `.macrostates/specs/`.
Implementation documentation, decisions, workflows and release declarations,
when required by project rules, live under `.macrostates/implementation/`.
Application source, tests, build configuration and runtime configuration retain
their language/tool locations outside `.macrostates/`. This package does not
make the Macrostates CLI mandatory or change the scope of a subproject.

## Reading order

1. [Project layout](001_project-layout.md)
2. [Dependency management](002_dependency-management.md)
3. [Vendored libraries](003_vendored-libraries.md)
4. [Formatting](004_formatting.md)
5. [Linting](005_linting.md)
6. [Type checking](006_type-checking.md)
7. [Testing](007_testing.md)
8. [Hooks](008_hooks.md)
9. [Packaging](009_packaging.md)
10. [Distribution Versioning And Releases](010_versioning.md)

Conditional annexes:

- [Docker](annex_docker.md): read when Docker support is being specified,
  implemented, reviewed, or maintained for a Python project.

## License

This specification package, including its documentation, metadata, and bundled
resources, is licensed under the [MIT License](LICENSE).

Copyright (c) 2026 Lucas Lopez.

## AI assistance

This project was developed with AI assistance.
