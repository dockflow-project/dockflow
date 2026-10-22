# Annex: project state

This annex applies when normal project phase checks find inconsistent or
unclear project artifacts. The core project phase model is defined in
`001_concepts.md`; normal execution checks are defined in `003_execution.md`.

## Conflicting state

Use the `conflicting` phase when project artifacts disagree about the current
phase, history, or implementation state.

`conflicting` is a temporary recovery state. It is not a normal development
destination and should not be used to continue ordinary specification or
implementation work.

## Recovery flow

When a project appears conflicting, the implementer should:

1. Tell the definer which signals conflict.
2. Set or propose setting the project phase to `conflicting`.
3. Ask the definer what the intended state is before touching affected files,
   unless the only file change needed first is the required `Exception`
   workflow record.
4. Open an `Exception` workflow record for the recovery work.
5. Inspect or repair only the files needed to bring the project back to a valid
   phase.
6. Close the `Exception` workflow only after the definer and implementer agree
   that the project state is coherent again.

## Examples

If `.macrostates/implementation/main.md` is missing but workflow records exist,
treat the project as `conflicting`. The implementation documentation may have
been lost, never created, or intentionally removed. Open an `Exception` workflow
and ask the definer which explanation is correct.

If `.macrostates/implementation/main.md` is missing but source code, tests,
generated artifacts, release artifacts, or other implementation files exist,
treat the project as `conflicting`. Ask whether the visible implementation
should be accepted as a starting point, reconstructed from, removed, or ignored.

If no workflow records exist but implementation appears to exist, do not assume
the implementation is invalid. Tell the definer that the implementation is not
represented by workflow history and ask whether it should be accepted as the
starting point. If accepted, open an `Exception` workflow as the first workflow
record, inspect the implementation, create or repair implementation
documentation, and close the exception when the project has a coherent phase
and baseline.

If implementation documentation was lost but source code remains, suggest
reconstructing `.macrostates/implementation/main.md` and any necessary
implementation documentation from the current code and specifications.

If workflow records were intentionally cleaned up, record that explanation in
the exception workflow before starting a new workflow history.

If the project appears copied or migrated but workflow records, package
composition, or implementation documentation describe another project, ask the
definer whether the copied artifacts should be adapted, archived, or removed.
