# Specification packages

This package defines the specification package system. It describes how
specification packages are structured, versioned, read, composed, and reused
across projects.

## Macrostates

This package is part of [Macrostates](https://github.com/orgs/Macrostates), a
project for composing reusable specification packages into specs-driven
development projects.

## Scope

- Specification package concepts.
- Package structure and metadata.
- Package versioning and Git release tags.
- Project-level package selection and validation against package-owned dependencies.
- Project composition through root specification files, including an optional
  composition version whose policy is owned by the selected project rules.
- Repository-specific directory specifications and their scope and authority.
- Project kickoff and discovery of official specification packages.
- Generic tagged Git snapshots, optional legacy transports and package integrity.
- Independent package, project-baseline and application version identities.
- Optional CLI assistance and manual specification validation.
- Progressive disclosure for package documents.

Author dependencies with an explicit `at_least` constraint by default. Use
`compatible` or `exact` when a package needs a stricter boundary. New compositions
prefer the latest suitable published releases; numeric constraints supplement
reading and semantic review, and compositions still pin exact versions. See
[Concepts](001_concepts.md#package-paths) for dependency rules.

## Reading order

1. [Concepts](001_concepts.md)
2. [Project composition](002_project-composition.md)
3. [Progressive disclosure](003_progressive-disclosure.md)

## Conditional annexes

- [Project kickoff](annex_project-kick-off.md): read when preparing a new
  project's specification set, including intent and package selection when no
  composition manifest exists yet.
- [Official packages](annex_official-packages.md): read when discovering packages
  or explaining a proposed project composition.
- [Package integrity locks](annex_package-lock.md): read when importing or
  verifying archive packages, or inspecting their provenance baseline.
- [Macrostates CLI](annex_cli.md): read when preparing to use the CLI for setup,
  inspection or verification, or choosing equivalent manual checks.

## Resources

- [Project kickoff introduction](resources/project-kickoff.md): a short portable
  Macrostates introduction and Meta clone source to copy into a new project's
  `.macrostates/specs/` directory and activate through its `main.md`. The package's kickoff
  annex owns the procedure. This resource is not part of the core reading order.

## License

This specification package, including its documentation, metadata, and bundled
resources, is licensed under the [MIT License](LICENSE).

Copyright (c) 2026 Lucas Lopez.

## AI assistance

This project was developed with AI assistance.
