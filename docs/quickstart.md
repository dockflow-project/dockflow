# Run your first pipeline

[Documentation index](README.md) · Prerequisite: [installation](installation.md)

The [quickstart project](../examples/quickstart/README.md) runs two independent
Python programs. `generate` writes integers 1 through 10 into a dataset directory;
`summarize` reads it and writes a JSON report plus a numeric mean. The expected
result is count **10**, sum **55**, mean **5.5**.

Run the commands from the repository root with its Python environment activated
and a local Docker daemon available. The compiled definition is checked in, so
you do not need to author or compile a pipeline first.

## 1. Prepare the component image

```bash
docker build -t dockflow-quickstart-components:v1 examples/quickstart
```

This creates a component image in the selected Docker engine. The first build
may download its pinned Python base image. The image contains only the example's
two programs and the Python standard library. Dockflow itself runs in your
Python environment.

## 2. Validate and execute

```bash
dockflow pipelines --config examples/quickstart/.dockflow-pipelines.toml definitions validate statistics
dockflow pipelines --config examples/quickstart/.dockflow-pipelines.toml run statistics --parameter count=10
```

Direct execution waits until completion. It prints a Run ID such as `run_…` and
the final state. The example keeps state in `examples/quickstart/.dockflow/`,
published data in `examples/quickstart/artifacts/`, and staging under
`examples/quickstart/work/`. These directories are ignored by Git.

## 3. Inspect the result

```bash
dockflow pipelines --config examples/quickstart/.dockflow-pipelines.toml runs list
dockflow pipelines --config examples/quickstart/.dockflow-pipelines.toml artifacts list
```

Use the full IDs from those results in place of the example operands:

```bash
dockflow pipelines --config examples/quickstart/.dockflow-pipelines.toml runs show RUN_ID
dockflow pipelines --config examples/quickstart/.dockflow-pipelines.toml logs RUN_ID
dockflow pipelines --config examples/quickstart/.dockflow-pipelines.toml tasks show TASK_ID
dockflow pipelines --config examples/quickstart/.dockflow-pipelines.toml artifacts show ARTIFACT_ID
```

The `summarize` log includes `{"count": 10, "sum": 55, "mean": 5.5}`. Its task
record exposes output IDs; the report artifact record gives its durable URI.
On this filesystem-backed project, open `summary.json` inside that artifact's
directory. The separate mean output is a typed parameter tracked by Dockflow.

Add the group option `--json` before the command when scripting:

```bash
dockflow pipelines --config examples/quickstart/.dockflow-pipelines.toml --json runs list
```

## 4. See reuse

Repeat the same `run statistics --parameter count=10` command. It creates a new
Run; eligible tasks can reuse verified outputs from the first Run. Task records
show the reuse decision and original producing attempt. Change the count to 20
to change the computation, or request fresh execution explicitly:

```bash
dockflow pipelines --config examples/quickstart/.dockflow-pipelines.toml run statistics --parameter count=10 --scope none
```

See [artifacts and reuse](artifacts.md) for what makes an output reusable.

## 5. Serve the same project

After the direct Run finishes, start one persistent owner in this terminal:

```bash
dockflow pipelines --config examples/quickstart/.dockflow-pipelines.toml serve --port 8080
```

Open [the browser interface](http://127.0.0.1:8080/ui/) to inspect pipeline
versions, run graphs and results. The service uses the same configuration,
history, artifacts and local engine as the earlier direct commands.

In another activated terminal:

```bash
dockflow pipelines --endpoint http://127.0.0.1:8080 runs list
dockflow pipelines --endpoint http://127.0.0.1:8080 run statistics --parameter count=20
```

The remote CLI needs no local project configuration for these commands. Service
submission waits by default; add `--no-wait` to return after acceptance. While
the service owns this project's state, use its endpoint for mutations. A direct
mutation against the same state is refused with owner details.

Stop the service with Ctrl+C in its terminal. Ctrl+C in a separate waiting client
only detaches that client; use `runs cancel RUN_ID` to cancel accepted work.
Use an unused port if another service already occupies 8080.

## Continue

- [Write your own components and pipelines](pipelines.md).
- [Use external data and preserve artifacts](artifacts.md).
- [Serve with Docker Compose](deployment.md).
- [Maintain or back up a project](operations.md).

`clean --apply` only removes eligible execution scratch data; it is not a full
history reset. To start a separate experiment from scratch, copy the example to
a new directory without its generated `.dockflow`, `artifacts` and `work`
directories and give it a new stable `project.id`. Preserve the original project
until you have finished inspecting it.
