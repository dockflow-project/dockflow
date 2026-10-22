# Linting

Python projects should use Ruff for linting.

Linting should catch likely bugs, unsafe patterns, unused code, import issues,
and maintainability problems without turning subjective style preferences into
manual review burden.

## Ruff configuration

The desired linting rules must be made formal in Ruff configuration during
project bootstrapping.

Prefer declaring Ruff configuration in `pyproject.toml` with the rest of the
Python project tooling. A separate Ruff configuration file may be used when the
project has a clear reason.

The Ruff configuration should encode at least:

- The selected Python target version.
- The selected lint rule sets.
- Any intentionally ignored rules.
- Per-file ignores when a rule should not apply to a narrow file category.
- Import linting and ordering behavior when managed by Ruff.

Do not create Ruff configuration during specification work merely because this
document mentions it. Create it during bootstrapping or implementation work
when project tooling is actually being established.

## Desired linting posture

Linting should prioritize:

- Correctness and likely bug detection.
- Import hygiene.
- Unused code detection.
- Clear exception handling.
- Safe logging and string formatting.
- Modern Python idioms for the supported runtime.
- Consistent, maintainable module structure.

Avoid broad rule suppressions. Prefer fixing the underlying code when the rule
protects correctness, compatibility, security, or maintainability.

When a lint rule conflicts with a project-specific requirement, document the
reason for the ignore in the Ruff configuration or in implementation
documentation when the reason is not obvious.

## Import sorting

Import sorting should be handled by Ruff.

Ruff should be configured to check and fix import ordering, normally through its
import-sorting lint rule set. Import sorting should keep imports deterministic
and easy to review without requiring manual rearrangement during code review.

When practical, the Implementer should run Ruff import sorting together with the
formatter so formatting and import organization settle in a single pass.

Project-specific import grouping rules may be added when needed, but broad
manual import-order conventions should be avoided unless they are formalized in
the Ruff configuration.

## Running lint checks

Lint checks should be runnable from a clean checkout after installing documented
development dependencies.

When changing Python code, the implementer should run the relevant Ruff lint
check when practical.

If lint checks cannot be run, or if a relevant lint failure is intentionally
left unresolved, the implementer should say what was not checked or fixed and
why.

## Generated files

Generated files should not be linted or manually edited unless the generator,
repository rules, or project-specific specifications say they should be.

Prefer linting and fixing the source that generates a file over editing
generated output directly.
