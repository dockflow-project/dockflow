# Installation

[Documentation index](README.md) · Next: [quickstart](quickstart.md)

This development preview is installed from source. Use a checkout of this
repository and the checked-in dependency lock. The commands below do not depend
on published Dockflow packages or service images.

## Requirements

- Python 3.13 is the development default; package metadata requires Python 3.12
  or newer. The runtime depends on MLMD wheels, so Python/platform availability
  is narrower than the CLI's pure Python requirements.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) manages the workspace.
- Direct execution or an execution service needs a running Docker daemon for
  Linux containers. The reference runtime is Linux x86-64. Other runtime
  platforms require their own qualification; metadata alone is not that proof.
- A remote CLI only needs network access to an existing Dockflow service.
  It does not need Docker, KFP, MLMD or FastAPI locally.

If `uv` is missing, install it using its official installation guide before
running the commands below. If Docker is missing, install an engine suitable
for your OS using the [Docker installation guide](https://docs.docker.com/engine/install/).

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

Dockflow has three installable distributions. They share one application version;
the source preview installs the local workspace members:

| Distribution / extra | Purpose |
| --- | --- |
| `dockflow-artifacts` | Independent filesystem publication and integrity API; optional `s3` and `kfp` extras. |
| `dockflow-cli` | Shared `dockflow` executable and installed command discovery. |
| `dockflow-pipelines` | Pipeline commands, remote client and definition validation. |
| `dockflow-pipelines[runtime]` | KFP DockerRunner, Docker SDK and MLMD for execution. |
| `dockflow-pipelines[service]` | FastAPI/Uvicorn HTTP serving. Execution also needs `runtime`. |
| `dockflow-pipelines[s3]` | S3-compatible artifact storage; combine with the other extras as needed. |

For a client-only source environment use a separate virtual environment so you
do not remove dependencies from an existing development environment:

```bash
uv venv .venv-client --python 3.13
uv pip install --python .venv-client/bin/python ./packages/cli ./packages/pipelines
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
