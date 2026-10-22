# Annex: exceptions

This annex applies when an `Exception` workflow is needed.

An exception workflow records work that must proceed even though the request or
project state does not fit the normal process cleanly.

## When to use

Use an exception workflow when:

- The definer explicitly asks for something that skips, ignores, or contradicts
  the process and no ordinary workflow type can honestly contain the work.
- The project is in or must enter the `conflicting` phase.
- Recovery work is needed before ordinary specification or implementation work
  can continue.

## Minimum safeguards

The implementer must still follow the process as much as possible. At minimum,
the implementer must create an open exception workflow record before changing
files.

An exception workflow does not suspend specification authority, file ownership,
conflict handling, secret handling, or safety rules.

## Record contents

The exception workflow record should explain:

- What process rule was difficult or impossible to follow normally.
- Why the request could not fit an ordinary workflow type.
- What minimum process safeguards were preserved.
- What risk, cleanup, or follow-up remains.
- What condition will make the project coherent enough to leave the exception.
