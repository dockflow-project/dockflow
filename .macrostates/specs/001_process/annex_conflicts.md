# Annex: conflicts

This annex applies when an ambiguity or conflict is found during a workflow.
Normal execution should continue without this annex unless a conflict or
material ambiguity is actually encountered.

## Ambiguity

When an ambiguity materially affects intended behavior, compatibility, safety,
operations, persisted data, or future implementation cost, ask the definer for
direction before encoding a choice that would be hard to reverse.

When an ambiguity is small, local, and reversible, the implementer may choose a
reasonable implementation path if the applicable specifications allow it. The
choice should be documented when it may matter later.

## Authority conflicts

When authority rules resolve a conflict, tell the definer what conflict was
found, which authority rule resolved it, and how the work proceeded.

When authority rules do not resolve a conflict, ask the definer how to proceed
before touching any affected file.

## Workflow conflicts

When planned work conflicts with an open workflow, ask the definer whether to
continue, pause, close, abandon, supersede, or open a parallel workflow before
touching affected files.

Warn more strongly when the open workflow has `large` or `systemic` change
depth, or when multiple open workflows could make the resulting state hard to
review.
