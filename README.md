# Dockflow

Dockflow runs compiled Kubeflow Pipelines definitions through Docker, without
Kubernetes. It adds persistent run history, typed artifacts and lineage,
verified task reuse, a CLI, a REST API and a browser interface.

**Release candidate: 0.1.1.** It supports a bounded
KFP 2.17 profile, one active Run per project and serial task execution. It is
intended for trusted components. See [compatibility](docs/compatibility.md) for
features, limits and qualification boundaries.

## Get started

After 0.1.1 publication, install `dockflow-pipelines==0.1.1` from PyPI; it includes
the shared CLI. For local execution, use the [installation guide](docs/installation.md)
to apply the required KFP dependency override, or follow the locked source setup
below. Release changes and limits are in the [changelog](CHANGELOG.md).

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and a running
Docker engine for Linux containers. From this checkout:

```bash
uv sync --locked --all-packages --all-extras
source .venv/bin/activate
docker build -t dockflow-quickstart-components:v1 examples/quickstart
dockflow pipelines --config examples/quickstart/.dockflow-pipelines.toml run statistics
```

The repository-owned example generates a dataset and summarizes it in two
independent components. It requires no sibling checkout or external dataset.
The [installation guide](docs/installation.md) covers environments and platforms;
the [tutorial](docs/quickstart.md) explains results, reuse and inspection.

Serve that same project and open `http://127.0.0.1:8080/ui/`:

```bash
dockflow pipelines --config examples/quickstart/.dockflow-pipelines.toml serve
```

Use another terminal to talk to the service:

```bash
dockflow pipelines --endpoint http://127.0.0.1:8080 runs list
```

Components and image building belong to your project. Dockflow accepts compiled
definitions, including uploads through a bounded official KFP client-compatible
API. The generic service image needs configuration and access to those images;
it needs no project-specific application code.

## Artifact publication library

`packages/artifacts` provides the independently installable `dockflow-artifacts`
Python library. It publishes immutable files and directories at custom paths in
a filesystem or S3-compatible store, verifies their integrity, and registers
those URIs as typed KFP artifacts. It requires no Dockflow service. See the
[artifact library guide](docs/artifact-library/README.md).

## Documentation

Start at the [documentation index](docs/README.md).

- [Components and pipelines](docs/pipelines.md), [artifacts and reuse](docs/artifacts.md).
- [CLI](docs/cli.md), [browser interface](docs/ui.md), [API guide](docs/api.md)
  and [generated API reference](docs/reference/api.md).
- [Configuration](docs/configuration.md), [deployment](docs/deployment.md)
  and [reference Docker Compose](deploy/README.md).
- [Operations](docs/operations.md), [persistence/recovery](docs/persistence.md)
  and [troubleshooting](docs/troubleshooting.md).

The live OpenAPI document is at `/dockflow/v1/openapi.json`; its packaged explorer
is at `/dockflow/v1/docs`. Browser assets are served by Dockflow itself.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development and review, and
[SECURITY.md](SECURITY.md) for the trust model and reporting. The
[specification entrypoint](.macrostates/specs/main.md) defines requirements;
the [implementation overview](.macrostates/implementation/main.md) records
qualification evidence. Neither is needed to follow the user tutorial.

Dockflow uses the [MIT License](LICENSE). Imported specification packages retain
their own license files and attribution. The source quickstart remains usable
without published packages or service images. All four distributions share
one release version; the artifact library is independently installable.
