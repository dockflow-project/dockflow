# Images

Docker images should be reproducible, minimal enough for their purpose, and
safe to run in normal development and production contexts.

## Development and production images

Development and production images have different responsibilities.

Development images may include development tools, test tooling, debuggers,
watchers, editable installs, and other conveniences needed for local work.

Production images should include only what is needed to run the intended
application behavior. They should avoid unnecessary build tools, caches,
development dependencies, source-control metadata, test-only files, and local
developer conveniences.

The project may use separate Dockerfiles, separate build targets, or separate
compose/service definitions for development and production. The chosen approach
should make the difference explicit.

## Multi-stage builds

Production images should normally use multi-stage builds.

Build stages may install compilers, package managers, dependency caches, and
build tools. Runtime stages should copy only the runtime artifacts and files
needed by the application.

Multi-stage builds should make it clear which stage is used for development,
testing, building, and production runtime when those concerns differ.

## Runtime user

Production containers should run as a non-root user unless the project has a
clear, documented reason to require root.

Files copied into the runtime image should have ownership and permissions that
allow the runtime user to execute the application without broad write access to
the image filesystem.

## Build context

Docker build context should be kept intentionally small.

Use `.dockerignore` or an equivalent mechanism to exclude files that are not
needed in image builds, such as local virtual environments, caches, temporary
files, build outputs, secrets, editor files, and source-control internals.

Do not rely on accidental files from a developer machine being present in the
build context.

Include the authoritative application metadata and captured provenance required
by [Naming and publishing](003_naming-and-publishing.md). Obtain identity without
copying the full Git repository into the runtime image or requiring a network
lookup during a release build.

## Dependency caching

Dockerfiles should be structured to make dependency installation cacheable when
practical.

Copy dependency metadata before copying frequently changing source files when
that helps reuse build layers. Avoid cache tricks that make dependency state
hard to understand or reproduce.

## Credentials

Never bake credentials into Docker images.

Do not copy secrets, private keys, access tokens, `.env` files, credential
stores, or local machine authentication state into an image.

If private package indexes or registries are needed during a build, use a build
secret mechanism or another project-approved secure mechanism. Credentials used
during the build must not remain in final image layers.
