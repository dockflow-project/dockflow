# Repository documentation

Repository documentation is the small set of root-level documents intended for
anyone encountering the repository.

This documentation helps a reader understand what the repository is, how to use
it, how to contribute to it, and what legal or release information applies. It
must not become the home for project specifications, implementation notes,
developer reference material, generated API documentation, or internal design
records.

## Root documents

Use these root-level files when they are needed:

- `README.md`: practical entrypoint for the repository, including purpose,
  setup, common commands, and links to deeper documentation.
- `CONTRIBUTING.md`: contribution expectations, topic-branch synchronization,
  integration preparation, review facilities or native equivalents, and project
  participation guidance. Link to authoritative policies rather than duplicating
  mutable version or workflow status.
- `CHANGELOG.md`: notable user-facing or operator-facing changes by release or
  version.
- `LICENSE`: legal license text for the repository.

Other conventional root documents may be added when they have a clear
repository-facing purpose.

## Style

Repository documentation should be concise, accurate, and workable-with. Prefer
clear links to the authoritative detailed documents over repeating large amounts
of content.

Keep repository usage documentation in the root files when practical. Do not
create extra repository-usage files by default.

If an implementer believes a repository-related topic deserves its own file, it
must ask the definer before creating or splitting that file.
