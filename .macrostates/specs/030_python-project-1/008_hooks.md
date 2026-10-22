# Hooks

Python projects using this package use `pre-commit` for Git hooks.

## Purpose

Git hooks should catch common local issues before changes enter the repository
history.

Hooks are a convenience and safety net. They do not replace explicit workflow
verification, CI checks, or the Implementer's responsibility to report what was
and was not checked.

## Tooling

Use `pre-commit` to define and run Git hooks.

`pre-commit` should be available through the project dependency management
mechanism. For this package, that means it should normally be declared as a
development dependency managed by `uv`.

Hook configuration should be formalized during bootstrapping or implementation
work, normally in `.pre-commit-config.yaml`.

Do not create hook configuration during specification-only work unless the
Definer explicitly asks for repository configuration files to be changed.

## Hook contents

The hook set should stay focused and fast enough for normal local use.

When applicable, hooks should run checks already defined by this package,
including:

- Ruff formatting checks or fixes.
- Ruff linting checks or fixes.
- Ruff import sorting.
- Pyright type checks when the project size and speed make that practical.
- Lightweight pytest selections when they are fast and deterministic.

The project may provide a separate integration-preparation hook or command for
Process's change-record and closed-workflow checks. Do not require all workflows
to be closed on every development commit: an active implementation workflow is
expected while work is in progress. The complete readiness gate runs when
preparing the integration proposal and again before integration. Macrostates CLI
checks are recommended when available; equivalent manual verification remains
supported under Process.

Long-running integration tests, provider-backed tests, load tests, or other
expensive checks should not be mandatory local pre-commit hooks unless a
project-specific specification requires them.

## Execution

Project documentation should make the intended hook installation and execution
commands clear once the repository is bootstrapped.

When practical, hook commands should run through the project environment, for
example with `uv run`.

The Implementer may run hooks manually before completing a workflow when that is
the most efficient way to run the relevant checks.

## Failures and bypassing

Hook failures should usually be fixed before the workflow is considered
complete.

Bypassing hooks should be exceptional. If hooks are bypassed for a meaningful
change, the Implementer should report that in the final response and explain
which checks were still run.
