# Docker

This annex describes how the Docker conventions from the `docker-1` package
apply to Python projects using this package.

Read this annex only when a Python project uses Docker or when Docker support is
being specified, implemented, reviewed, or maintained.

## Relationship to Docker package

The `docker-1` package defines general Docker behavior. This annex specializes
those rules for Python projects using `src` layout, `uv`, `pyproject.toml`, and
the tooling conventions in this package.

When this annex conflicts with `docker-1`, this annex should govern
Python-specific Docker behavior. The general Docker package still governs Docker
concerns not specialized here.

## Project layout

Docker build configuration should work with the Python `src` layout.

The build should install or package the Python project from its declared project
metadata instead of relying on imports from the repository root.

Dockerfiles should copy dependency and package metadata before source code when
that improves dependency layer caching.

## uv

Docker builds for Python projects should use `uv` for dependency installation,
environment preparation, and packaging workflows when practical.

The Dockerfile should make the relationship between `uv`, `pyproject.toml`, the
lockfile, and the runtime environment clear.

Production images should install from locked dependency metadata when a lockfile
is committed and applicable.

## Development images

Development images may use editable installs and include development
dependencies when they are needed for local workflows.

A development image may include tools for testing, linting, formatting, type
checking, hooks, debugging, or live reload when those tools are part of the
supported developer experience.

Development images should still avoid baking credentials into image layers.

## Production images

Production images should normally build a wheel or another explicit Python
artifact and install that artifact into the runtime image.

Production images should not rely on editable installs, repository-root imports,
or development-only dependency groups.

The runtime image should include only the files and dependencies needed to run
the supported production behavior.

Image tags and labels identify the distribution or service being released.
Use its independent application version when an effective policy declares one;
otherwise use the numeric implementation-derived default. Record exact
Macrostates specification/implementation baselines and source provenance under
the selected Docker and Process rules. Do not overwrite a wheel's distribution
version with a repository baseline or release unchanged workspace members merely
because the repository has a newer implementation version.

## Workspace members

When the Python project uses `uv` workspaces, Docker builds should include the
workspace members needed by the image being built.

Workspace members should be copied and installed in a way that preserves their
declared package metadata and dependency relationships.

Do not replace workspace dependency resolution with manual `PYTHONPATH` or
`sys.path` manipulation.

## Vendored libraries

Vendored Python libraries required by the project must be available in Docker
builds and runtime images according to the project's packaging and distribution
model.

When vendored libraries are `uv` workspace members, Docker builds should include
the relevant `./vendor/` projects and workspace metadata needed to resolve them.

The Docker build should not silently omit vendored libraries that are required
by the application.

## Testing and checks

Docker support should not create a separate, contradictory testing path.

When practical, Docker-based checks should run the same project commands used
outside Docker, such as `uv run pytest`, Ruff, and Pyright commands defined by
the project.

Project-specific specifications should decide whether Docker images are tested
only by build success, by smoke tests, by integration tests, or by deployment
checks.
