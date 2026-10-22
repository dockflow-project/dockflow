# Project layout

Python projects using this package should use the `src` layout.

## Directory structure

Project source code should live under `./src/`.

A typical repository should use this shape:

```text
.macrostates/
  specs/
    main.md
    composition.yaml
    composition.lock.yaml
    000_meta/
    001_process/
  implementation/
    main.md
    release.yaml
    decisions/
    workflows/
      history/
src/
  <package_name>/
tests/
  unit/
  integration/
  contract/
```

The concrete package name is project-specific. It should be a valid Python
package name, should be stable once bootstrapped, and should normally match the
project identity closely enough that imports are easy to recognize.

## Source package

Importable project code should live inside the package under `./src/`.

Python modules should be organized by responsibility. Keep core domain behavior
separate from interface code, provider adapters, persistence details, and other
I/O-heavy edges when practical.

The top-level package should not become a dumping ground for unrelated modules.
When a project grows, prefer clear subpackages over large modules that mix
domain logic, I/O, configuration, and interface behavior.

## Tests

Tests should live outside `./src/` under `./tests/`.

Test directory layout is defined by the testing document in this package. Tests
should import the installed package or the package as resolved by the project
tooling, rather than relying on accidental imports from the repository root.

## Entry points

Executable entry points should be declared through Python project metadata when
practical, instead of relying on ad hoc scripts at the repository root.

Small local helper scripts may exist when a project-specific specification or
repository convention allows them, but they should not become the primary way to
run supported project behavior unless they are documented and maintained as part
of the project interface.

## Configuration files

Python tooling configuration should normally live in `pyproject.toml` when the
tool supports it and when doing so keeps the repository easier to understand.

Dedicated configuration files may be used when a tool requires them or when a
separate file is clearer for that tool.

## Generated and temporary files

Generated, build, cache, virtual environment, and temporary files should not be
placed inside `./src/` unless the generator or project-specific specs explicitly
require it.

Build outputs, caches, and temporary files should follow the repository package
rules for generated and temporary content.

## Bootstrapping expectations

During bootstrapping, the Implementer should create the concrete package layout,
package metadata, and import configuration needed for the `src` layout to work
from a clean checkout.

The Implementer should avoid creating empty architectural directories just
because they might be needed later. Add subpackages when there is real behavior
or a clear project-specific reason for them.
