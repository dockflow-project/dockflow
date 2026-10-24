# Installation

[Documentation index](README.md) · Next: [quickstart](quickstart.md)

Install the coordinated Dockflow 0.2.0 packages below, or use the locked source
checkout. The qualified execution platform is Linux x86-64 with Python 3.12–3.13.
See the [compatibility guide](compatibility.md) for base client installation and
execution support. This version requires fresh state; earlier database and backup
formats are not migrated.

## Requirements

- Python 3.13.17 is the development default; package metadata requires Python 3.12
  or newer. Execution/provider dependencies retain their own platform qualification.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) 0.13.5 or newer manages the workspace.
- Use patched certificate stores and package tools; see [certificate maintenance](certificate-maintenance.md).
- Direct execution or an execution service needs a running Docker daemon for
  Linux containers. The reference runtime is Linux x86-64. Other runtime
  platforms require their own qualification; metadata alone is not that proof.
- A remote CLI only needs network access to an existing Dockflow service.
  It does not need Docker, KFP, MLMD or FastAPI locally.

If `uv` is missing, install it using its official installation guide before
running the commands below. If Docker is missing, install an engine suitable
for your OS using the [Docker installation guide](https://docs.docker.com/engine/install/).

## Install from PyPI

In a virtual environment, install the remote client:

```bash
pip install dockflow-pipelines==0.2.0
dockflow --version
dockflow pipelines --endpoint http://127.0.0.1:8080 runs list
```

The matching `dockflow-cli` is installed automatically. For the independent
artifact library, use `pip install dockflow-artifacts==0.2.0` (or
`'dockflow-artifacts[s3]==0.2.0'`).

Local execution and serving need the KFP dependency override explained below.
These commands work without a source checkout:

```bash
uv venv --python 3.13
uv pip install \
  --overrides https://raw.githubusercontent.com/dockflow-project/dockflow/v0.2.0/tools/runtime-overrides.txt \
  'dockflow-pipelines[runtime,service,s3]==0.2.0'
```

Add `'dockflow-artifacts[s3,kfp]==0.2.0'` to that same command when authoring
pipelines that use the artifact library. On Linux/macOS activate with
`source .venv/bin/activate`; on PowerShell use `.venv\Scripts\Activate.ps1`.
These commands install software; they do not start services or create storage.

## Full source environment

From the repository root:

```bash
uv sync --locked --all-packages --all-extras
uv run --all-packages --all-extras dockflow --version
uv run --all-packages --all-extras dockflow pipelines capabilities
```

For subsequent commands, activate the environment once:

```bash
source .venv/bin/activate
dockflow pipelines --help
```

On PowerShell use `.venv\Scripts\Activate.ps1`. If you prefer no activation,
prefix `dockflow` commands with `uv run --all-packages --all-extras` from the
repository root. The guides use the activated environment to keep commands short.

The install creates a Python environment. It does not start Docker, launch a
service, create a bucket, build component images or execute a pipeline.

### KFP dependency override

KFP 2.17.0 pins `urllib3==2.7.0`, a version with published security advisories.
Dockflow's workspace explicitly overrides that pin with `urllib3==2.8.0` and
qualifies the combination through its HTTP/KFP and DockerRunner tests. The locked
workspace and the service image apply this automatically. Keep using the locked
setup above when working from source.

For a separate environment that installs Pipelines' `runtime` extra or Artifacts'
`kfp` extra, apply the same override explicitly. For example, from this checkout:

```bash
uv venv .venv-runtime --python 3.13
uv pip install --python .venv-runtime/bin/python \
  --overrides tools/runtime-overrides.txt \
  ./packages/cli './packages/pipelines[runtime,service,s3]'
```

The override is an installation policy, not wheel metadata: plain `pip install`
still honors KFP's old pin, and dependency checkers may report that upstream
metadata conflict in the overridden environment. Do not remove the override just
to silence that warning. Reassess it when KFP publishes a compatible requirement;
no KFP source or package metadata is patched. Other dependency conflicts are not
covered by this exception.

## Select only the needed capabilities

Dockflow has four installable distributions: CLI, Pipelines, Artifacts and the
shared Database library. They share one application version;
a source checkout installs the local workspace members:

| Distribution / extra | Purpose |
| --- | --- |
| `dockflow-database` | Shared SQLite/PostgreSQL adapter and physical schema; optional `postgresql` driver. |
| `dockflow-artifacts` | Independent publication and integrity API; optional `postgresql`, `s3` and `kfp` extras. |
| `dockflow-cli` | Shared `dockflow` executable and installed command discovery. |
| `dockflow-pipelines` | Pipeline commands, remote client and definition validation. |
| `dockflow-pipelines[runtime]` | KFP DockerRunner and Docker SDK for execution. |
| `dockflow-pipelines[service]` | FastAPI/Uvicorn HTTP serving. Execution also needs `runtime`. |
| `dockflow-pipelines[s3]` | S3-compatible artifact storage; combine with the other extras as needed. |

For a client-only source environment use a separate virtual environment so you
do not remove dependencies from an existing development environment:

```bash
uv venv .venv-client --python 3.13
uv pip install --python .venv-client/bin/python ./packages/database ./packages/artifacts ./packages/cli ./packages/pipelines
.venv-client/bin/dockflow pipelines --endpoint http://127.0.0.1:8080 runs list
```

On Windows replace `bin/python` and `bin/dockflow` with `Scripts/python.exe` and
`Scripts/dockflow.exe`. To install into a prepared environment from built wheels,
install the matching CLI and Pipelines wheels together; Artifacts is independently installable; see [contributing](../CONTRIBUTING.md)
for build and clean-install checks.

## Select the Docker engine deliberately

Dockflow uses the Docker Python SDK's environment-based connection. It does not
promise to follow the Docker CLI's current context automatically. Set
`DOCKER_HOST` and any required Docker TLS variables when using a nondefault
daemon. Build/load the component image into that same daemon, or use a registry
it can reach. [Deployment](deployment.md) explains the dedicated Compose engine.

The [quickstart](quickstart.md) uses a small repository-owned example and requires
no sibling project, downloaded dataset or model framework.
