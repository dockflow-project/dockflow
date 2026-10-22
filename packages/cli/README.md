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

Install the command host with Python 3.12 or newer:

```bash
pip install dockflow-cli==0.1.0
```

Installing `dockflow-pipelines==0.1.0` also installs this matching host.
MIT licensed. See [installation](https://github.com/dockflow-project/dockflow/blob/main/docs/installation.md),
[CLI usage](https://github.com/dockflow-project/dockflow/blob/main/docs/cli.md) and the [contribution guide](https://github.com/dockflow-project/dockflow/blob/main/CONTRIBUTING.md).
