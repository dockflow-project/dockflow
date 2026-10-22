# Progressive disclosure

Specification packages should be organized so implementers can read the normal
path first and consult rare branches only when those branches become relevant.

This keeps packages usable across sessions and projects. A package should make
mandatory information easy to find, while avoiding the need to read unusual
case handling before every ordinary task.

## Core documents

Core documents contain information an implementer should read when beginning a
session or working with the package in the ordinary case.

Core documents should define scope, authority, common concepts, required
artifacts, normal workflows, and any rules that must be known before changing
files.

## Annex documents

Annex documents contain conditional guidance. They should be read only when the
core documents identify that the relevant situation has occurred.

Use annex documents for rare branches, recovery procedures, extended examples,
special cases, and detailed handling that would distract from the normal path.

Annex filenames should use `annex_<hyphenated-name>.md`: an underscore
after `annex`, then lowercase descriptive words separated by hyphens. For
example, use `annex_project-kick-off.md`. Existing annexes should be renamed
with their references when a package adopts this convention.

Core filenames should expose their normal reading order. Use a three-digit
prefix and underscore for core documents after the package entrypoint, such as
`001_concepts.md` or `002_artifacts.md`. Keep `README.md` unnumbered as the
normal package entrypoint.

## References

Core documents should reference the right annex at the point where it becomes
relevant. The reference should explain when to stop and read the annex.
