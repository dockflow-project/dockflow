# Dockflow CLI

`dockflow-cli` supplies the shared `dockflow` executable. Installed feature
packages register Typer applications through the `dockflow_cli.modules` Python
entry-point group; `dockflow-pipelines` supplies the `pipelines` commands.

```text
dockflow --help
dockflow --version
dockflow pipelines --help
```

Help/version requests are offline. Installing this package alone does not start
services, install feature modules or contact a registry. The command host reports
invalid or conflicting plugin registrations rather than silently omitting them.

This package is an unpublished MIT-licensed development implementation.
In the source repository, see [installation](../../docs/installation.md),
[CLI usage](../../docs/cli.md) and the [contribution guide](../../CONTRIBUTING.md).
There is no published-package installation claim in this README.
