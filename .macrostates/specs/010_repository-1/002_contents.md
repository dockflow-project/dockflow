# Repository contents

The repository root should stay small, intentional, and easy to scan.

## Root files

The repository root contains project entrypoint files and repository control
files. Expected root files include:

- `.gitignore`: excludes generated, local, secret, cache, and temporary files.
- `README.md`: practical entrypoint for repository users when needed.
- `CONTRIBUTING.md`: contribution guidance when needed.
- `CHANGELOG.md`: release or notable-change history when needed.
- `LICENSE`: repository license when needed.

Additional root files should have a clear repository-level purpose.

## Macrostates artifacts

Track `.macrostates/specs/` and, when selected, `.macrostates/implementation/`,
including imported packages and composition locks. Do not blanket-ignore
`.macrostates/` or all dot directories. Ignore only disposable caches or local
operation workspaces; preserve recovery data until an interrupted operation is
resolved. Root `AGENTS.md` points to `.macrostates/specs/main.md`.

## Temporary files

Do not create garbage, scratch, dataset, or temporary test files directly in the
repository root.

If temporary files are needed inside the repository, they must be placed under
`./tmp/`. Do not create files directly under `./tmp/`; create a dedicated
subdirectory for each temporary activity, such as
`./tmp/testing-comms-1/`.

Temporary directories should be named clearly enough to identify their purpose.
They should be safe to delete unless another specification or explicit definer
instruction says otherwise.

## Temporary directory tracking

The repository should contain `./tmp/.gitkeep` so the temporary workspace exists
in a clean checkout.

The root `.gitignore` should exclude the full `./tmp/` directory except for
`./tmp/.gitkeep`.
