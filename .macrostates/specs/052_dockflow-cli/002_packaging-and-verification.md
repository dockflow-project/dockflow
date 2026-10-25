# CLI packaging and verification

## Selected identities and dependencies

| Item | Selection |
| --- | --- |
| Distribution | `dockflow-cli` |
| Import package | `dockflow_cli` |
| Member directory | `packages/cli/`, with `src/dockflow_cli/` |
| Installed executable | `dockflow` |
| Console-script target | `dockflow_cli.main:main` |
| Feature entry-point group | `dockflow_cli.modules` |
| Feature object contract | An exported `typer.Typer` application. |
| Direct runtime framework | `typer>=0.27.3,<0.28.0` |

The relevant console-script metadata is:

```toml
[project.scripts]
dockflow = "dockflow_cli.main:main"
```

Choose no additional direct runtime library for discovery, version lookup,
configuration, or plugin management: the standard library and Typer supply the
initial requirements. Dependencies of Typer remain transitive unless host code
directly imports one, in which case follow the shared dependency policy.

Typer 0.27.3 is the initial qualification candidate/minimum, selected from its
published release metadata and checked with temporary framework probes on
CPython 3.12 and 3.13. The next-minor upper bound follows the shared 0.x policy.
These framework checks do not establish completed Dockflow application or
platform qualification. The actual application, built artifact, and full
platform tests remain implementation obligations. Review a newer dependency
line deliberately; builds must not select an unreviewed line automatically.

Use the general package's Python 3.12 minimum/3.13 default, uv workspace,
`uv_build`, lock, metadata, artifact, and shared release policies. Application
versions come from that policy, not this specification package's version.
Importing `dockflow_cli` must not discover/load plugins, run commands, perform
network I/O, or configure unrelated global state. Construct/discover the CLI
only through explicit invocation, preserving the root version path.

## Required implementation verification

Before qualifying the CLI, verify observable behavior from installed artifacts:

- CLI-only installation, no-feature help, bare-root help/exit 0, and installed
  distribution version reporting, including unavailable metadata failure.
- Metadata-based group discovery, deterministic help order/descriptions,
  registered module help/dispatch, and adding/removing a test-only second
  distribution without editing or rebuilding the host.
- Invalid/reserved module names, duplicate providers, wrong object types,
  import failures, and command-construction failures, including module/provider
  identification and failure before silently running a partial installation.
- Root `--version` with a broken plugin or import-side-effect sentinel: provider
  discovery/loading must not run. Root/module help must not contact Docker,
  object storage, a database, or a server, and must not execute a task.
- Output streams and exit codes 0/1/2; an operational failure remains a failure,
  usage errors are distinct, and unexpected exceptions have no default raw
  traceback. Verify that module options stay inside the module's command tree.
- Package-root import side effects, shell-completion option suppression, clean
  wheel installation, standalone source-distribution rebuilds, and registration
  metadata surviving packaging. Installation must not deploy Compose, start a
  Docker daemon, or create service volumes.
- The shared Python/platform matrix and a real Pipelines registration test when
  that distribution exists; generic fixture checks do not qualify its runtime.

No CLI policy decision remains open in this initial specification. The work
above is implementation and qualification, not permission to invent feature
semantics. In particular, Pipelines owns `dockflow pipelines run` arguments,
submission/waiting behavior, results, and runtime failure semantics.

## References

- [Python plugin discovery](https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/)
- [Python entry points](https://packaging.python.org/en/latest/specifications/entry-points/)
- [Typer command groups](https://typer.tiangolo.com/tutorial/subcommands/add-typer/)
- [Typer version option](https://typer.tiangolo.com/tutorial/options/version/)
- [Typer 0.27.3 metadata](https://pypi.org/project/typer/0.27.3/)

Use the exact shared application version of dockflow-core for common primitives.
The [Core boundary](../051_dockflow/007_core.md) governs dependency direction;
CLI registration and discovery remain CLI-owned.
