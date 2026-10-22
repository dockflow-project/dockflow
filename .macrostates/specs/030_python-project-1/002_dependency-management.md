# Dependency management

Python projects using this package use `uv` for virtual environment and
dependency management.

## Virtual environment

The project virtual environment should be managed with `uv` and should normally
live at `./.venv/`.

The virtual environment is local generated state. It must not be committed, and
project commands should not depend on a globally activated Python environment.
When practical, commands should be run through `uv run` so they use the project
environment consistently.

## Dependency declaration

Python dependencies should be declared in `pyproject.toml`.

Runtime dependencies, development dependencies, test dependencies, linting
dependencies, and formatting dependencies should be separated using the project
dependency structure supported by `uv` and `pyproject.toml`. The exact grouping
may be chosen during bootstrapping, but it should make clear which dependencies
are needed to run the project and which are only needed to develop, test, lint,
or format it.

Dependencies should not be installed ad hoc with global `pip` commands as part
of normal project work. If a dependency is required by the project, it should be
declared in the project dependency metadata.

## Locking

Application and service repositories should normally commit the `uv` lockfile so
the project environment can be reproduced consistently.

Reusable library repositories may choose a different lockfile policy if their
project-specific specs require it. When no project-specific rule exists, prefer
committing the lockfile for repeatable development and CI behavior.

The lockfile should be updated together with dependency metadata changes.

## Python version

The supported Python version range should be declared in `pyproject.toml` and
should be consistent with the Python runtime rules in this package.

During bootstrapping, the Implementer should formalize the Python version,
virtual environment behavior, dependency groups, and lockfile policy in the
project configuration.

## Dependency changes

Dependency changes should be intentional and scoped to the workflow being
performed.

Before adding a new dependency, the Implementer must confirm the dependency with
the Definer. This confirmation should happen before changing dependency
metadata, lockfiles, or project code that relies on the dependency.

When dependencies are added, removed, or upgraded, the Implementer should update
the dependency metadata and lockfile together, then run the relevant tests and
checks when practical. If checks are skipped, the final response should say why.

Private indexes, credentials, tokens, or provider-specific authentication
details must not be written into committed dependency files unless another specs
package explicitly defines a safe mechanism for doing so.
