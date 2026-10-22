# Documentation boundaries and maintenance

## Ownership

Each normative requirement has one topic owner. Package entrypoints identify
those owners and the reading order; summaries link to the owning section instead
of maintaining another list of defaults, limits or protocol details. Public API
reference material is generated from the implementation schema and checked for
drift. Usage guides explain the supported contract without becoming another
specification authority.

Keep documentation according to its purpose:

| Purpose | Location and authority |
| --- | --- |
| Product contracts and acceptance criteria | Selected specification packages, under the composition's authority rules. |
| Installation, usage, operation and API reference | Root user-facing entrypoints and `docs/`. |
| Current architecture, implementation status and limitations | `.macrostates/implementation/main.md` and linked topic records. |
| Dated validation, changes and decisions | Process-owned validation, workflow and decision records. |
| Task-specific assessments, publication-readiness reviews and roadmap proposals | Purpose-specific directories under ignored `tmp/`; these are not product documentation. |

Package metadata owns reusable specification versions; the composition pins its
selection. Avoid copying exact package versions into narrative summaries.
Root `VERSION` owns the application version under the release contract.
Implementation existence, test coverage, acceptance and publication are separate
facts. Specifications define obligations; current completion claims and measured
results belong in implementation records. Link to that evidence when useful.

## Anonymous authoring

The explicit repository instruction in `AGENTS.md` governs anonymous authoring,
including its precedence over imported Process attribution defaults. Use role
attribution and neutral descriptions of requirements/outcomes. Keep personal
identities, conversation quotations, private project references and actual local
absolute paths out of authored documents, exported evidence and scratch reports.
Use portable placeholders or repository-relative paths. These rules do not alter
runtime path semantics, local operational logs or ownership diagnostics.

Necessary public dependency/standard links, canonical package provenance and
copyright/license notices remain intact. Treat exported raw output as source
material to sanitize before retention, rather than copying it into a public
record. Do not store an unsanitized backup beside a sanitized document.

## Updating contracts

When behavior changes, update the owning section, affected references and
acceptance criteria together. Record implementation gaps explicitly. Preserve
existing requirement identifiers and useful document routes when reorganizing;
map moved or consolidated requirements in the workflow. Removing duplicate
prose must not remove its substantive requirements or qualification obligations.

Validate package/composition alignment, local links, affected implementation
contracts and imported integrity. Preserve immutable external packages; changes
to their canonical rules require a verified upstream release selection. Existing
explicit repository instructions continue to govern until such adoption.
