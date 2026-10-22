# Annex: package integrity locks

Read when importing archive packages, verifying external packages or inspecting
a provenance baseline. The CLI is recommended but optional; manual imports and
verification must preserve the same evidence.

## Location and ownership

Track `.macrostates/specs/composition.lock.yaml` alongside the composition and
package contents. The composition selects release tags; the lock records what
was resolved and verified. It does not define authority, select another version
or permit `source.commit` in the composition. Local packages remain editable and
are excluded from external integrity inventories.

## Format 1

Top-level `schema_version` is the integer `1`. `packages` is a mapping keyed by
each imported external package name. Each record contains:

- `selection`: selected `name`, `version`, normalized relative `path` (without
  trailing slash), `entrypoint` and complete credential-free `source`.
- `commit`: the tag's resolved full lowercase Git commit ID (40 or 64 hex digits).
- `files`: every package-relative file path mapped to its lowercase SHA-256
  `sha256` and boolean `executable` flag.
- `content_sha256`: SHA-256 of UTF-8 canonical JSON serialization of `files`,
  recursively sorted keys, separators `,` and `:`, no whitespace, and non-ASCII
  characters retained (`ensure_ascii=False`).

Inventory ordinary files, including dot files; exclude only the archive's
outer directory and Git checkout metadata. Empty directories have no record.
Any execute bit makes `executable` true. Compare extracted bytes, not compressed
archive bytes. Reject absolute paths, traversal, links, special files, unsafe
Git metadata paths, overlapping destinations and case collisions.

Generic Git archives and supported provider archives use the same inventory
format. Record the actual source type in `selection.source`; never reinterpret
a legacy source silently. An archive obtained through local Git access must
resolve the selected tag and compare canonical bytes just as a remote import does.

## Establishing and checking a baseline

Resolve the selected tag at its canonical repository, verify tagged metadata,
entrypoints and dependencies, and calculate inventory before importing. A manual
lock must match the canonical release; never bless unexplained local changes.
Record the verification method in workflow evidence.

Offline verification checks selection binding and the full inventory, including
missing, added, modified and mode-changed files. A clean Git working tree is
insufficient. Locks are reviewed evidence, not signatures or independent proof
of upstream trust; review lock changes as carefully as package changes.

For unchanged selections, later source access must refuse moved tags or changed
content at a recorded commit. Stop and investigate. Deliberate updates change
version/tag together, verify the new release, require installed files to match
the old baseline, and replace content and lock coherently. Preserve unexplained
local modifications. Interrupted operations must leave recoverable evidence;
never discard it merely to rerun an installer.

Subtree projects may record locks after canonical comparison; locks never
establish or replace subtree history. Unknown formats require an explicit reader
or equivalent documented verification; never guess.
