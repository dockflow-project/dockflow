# Dockflow CLI requirements

This local specification package owns the `dockflow-cli` distribution,
its `dockflow_cli` import package, the `dockflow` executable, and the interface
through which installed feature modules register command groups. Its source
scope is `packages/cli/`, together with the corresponding CLI integration tests.

It depends on the [general Dockflow requirements](../051_dockflow/README.md).
Repository-wide licensing, package boundaries, and shared release policy remain
there. Tool-specific runtime behavior belongs to the package for that tool.
These are specification packages within one root project, not separate project
compositions or independent application release lifecycles.

## Reading order

1. [Shared CLI contract](001_cli.md)
2. [Packaging and verification](002_packaging-and-verification.md)

These documents define the CLI contract. Implementation status, dated
qualification and acceptance belong to the
[implementation records](../../implementation/main.md); package version metadata
does not establish any of those states.
