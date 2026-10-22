# Type checking

Python projects using this package use Pyright for static type checking.

## Type checking posture

Type checking should verify the types that are declared in the code.

When a function, method, variable, class attribute, or interface declares types,
Pyright should be expected to check those declarations and report meaningful
incompatibilities.

Code that does not declare types should not be forced into strict type checking
by default. Unannotated implementation details may remain lightly checked, and
the type checker should be configured to avoid turning every missing annotation
into an error unless another specs package explicitly requires that stricter
posture.

This package encourages useful typing without requiring every local helper or
internal implementation detail to be fully annotated.

## Required annotations

Public functions, module boundaries, domain models, adapter contracts, and other
stable interfaces should declare types when practical.

The more code is shared across modules, exposed to callers, or used as a
compatibility surface, the more important its declared types become.

Small private helpers may omit annotations when their behavior is clear and the
project-specific specs do not require them.

## Configuration

Pyright configuration should be formalized during bootstrapping or
implementation work. The configuration may live in `pyproject.toml` or another
Pyright-supported configuration file, depending on the project structure.

The configuration should encode:

- the supported Python version;
- the source paths to check;
- the project virtual environment behavior, when needed;
- a type checking mode that checks declared types without requiring every
  unannotated symbol to become an error;
- project-specific exclusions for generated files, build artifacts, temporary
  files, or vendored code.

The Implementer should not create type checker configuration during
specification-only work unless the Definer explicitly asks for repository
configuration files to be changed.

## Dependency and environment

Pyright should be available through the project dependency management mechanism.
For this package, that means it should normally be declared as a development
dependency managed by `uv`.

Type checking commands should run through the project environment when
practical, for example with `uv run`.

## Suppressions

Type checker suppressions should be narrow and local.

Suppressions should not be used to hide broad design uncertainty. If a typing
problem reveals an unclear interface or an unstable compatibility surface, the
Implementer should either fix the type design or record the unresolved decision
according to the process specs package.

## Completion expectations

When a workflow touches typed Python code, public interfaces, domain models, or
adapter contracts, the Implementer should run the relevant Pyright check when
practical.

If type checking is skipped, the final response should say why.
