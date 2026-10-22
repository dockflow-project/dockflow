# Formatting

Python projects should use Ruff for automated code formatting.

Formatting should make the codebase consistent, readable, and easy to review.
Humans and implementers should not spend time debating purely stylistic details
that can be handled by the formatter.

## Desired style

Python code should use:

- Four spaces for indentation.
- A maximum line length of 88 characters unless a project-specific
  specification chooses another limit.
- Double quotes for strings when the formatter can choose safely.
- Trailing commas where they improve multi-line diffs and the formatter applies
  them.
- One clear import section per module, with imports ordered consistently by the
  Ruff import-sorting lint rules.
- Blank lines and wrapping chosen by the formatter rather than manual alignment.

Avoid hand-formatting that fights the configured formatter.

## Ruff configuration

The desired format must be made formal in Ruff configuration during project
bootstrapping.

Prefer declaring Ruff configuration in `pyproject.toml` with the rest of the
Python project tooling. A separate Ruff configuration file may be used when the
project has a clear reason.

The Ruff configuration should encode at least:

- The selected Python target version.
- The line length.
- Formatter settings needed to produce the desired style.

Import sorting is owned by Ruff linting rules rather than the formatter itself.
When practical, formatting and Ruff import sorting should be run together so the
resulting file shape is consistent.

Do not create Ruff configuration during specification work merely because this
document mentions it. Create it during bootstrapping or implementation work
when project tooling is actually being established.

## Generated files

Generated files should not be manually reformatted unless the generator,
repository rules, or project-specific specifications say they should be.

Prefer formatting the source that generates a file over editing generated
output directly.
