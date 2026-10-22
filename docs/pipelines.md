# Components and pipelines

[Documentation index](README.md) · Example: [quickstart source](../examples/quickstart/README.md)

## Keep computation independent

A component can be an ordinary Python program, shell program or compiled binary.
It receives parameter values and local input/output paths through arguments. It
does not need to import Dockflow or KFP. The quickstart follows this layout:

```text
examples/quickstart/
├── components/
│   ├── generate/main.py
│   └── summarize/main.py
├── Dockerfile
├── .dockflow-pipelines.toml
└── orchestration/kfp/
    ├── definitions/pipeline.py
    ├── compile.py
    └── compiled/statistics.yaml
```

The two scripts use only the Python standard library. For example, `generate`
accepts `--count` and `--output-directory`; the KFP wrapper maps its `Dataset`
output to that directory. `summarize` accepts the dataset directory, a report
directory and an output file for its numeric mean.

Use exit status zero only after all declared outputs have been written. Send
diagnostic text to stdout/stderr. Write outputs only at the supplied paths and
avoid side effects outside the declared computation if you want safe reuse or
retries. Do not assume a particular absolute staging path or a shared working
directory between tasks.

## Wrap and compile with KFP

The wrapper declares types, the prepared image and its command:

```python
from kfp import dsl

@dsl.container_component
def generate(count: int, dataset: dsl.Output[dsl.Dataset]):
    return dsl.ContainerSpec(
        image="dockflow-quickstart-components:v1",
        command=["python", "/components/generate/main.py"],
        args=["--count", count, "--output-directory", dataset.path],
    )
```

Compose those components with `@dsl.pipeline`, then compile using the selected
KFP 2.17 toolchain. The example's reproducible command is:

```bash
python examples/quickstart/orchestration/kfp/compile.py
```

Keep the compiled YAML/JSON as a reviewable deployment artifact. Dockflow reads
it as data and never imports the consumer's Python definitions. A compiled
primitive component can also be submitted directly as a single-task Run.

## Prepare images separately

Build component images before running the pipeline. A component image contains
its own code and dependencies, not the Dockflow orchestrator. Pin dependencies
and use immutable image digests for repeatable deployments. The quickstart's
local tag is convenient during development; change it when changing its code.

Make the image available to the Docker engine used by the execution owner:

- Build/load it into that engine for a local project.
- Publish it to a registry the engine can reach for a remote deployment.
- Explicitly load it into a dedicated Compose engine for local testing.

A registry and an engine's image cache are different stores. A host build is
not automatically available inside Docker-in-Docker. See [deployment](deployment.md).

## Register or submit a definition

For files checked into your project, add a name-to-path map:

```toml
[definitions.pipelines]
statistics = "orchestration/kfp/compiled/statistics.yaml"
```

Run that name or submit a compiled file directly:

```bash
dockflow pipelines --config PROJECT_CONFIG run statistics
dockflow pipelines --config PROJECT_CONFIG run ./statistics.yaml
```

`PROJECT_CONFIG` stands for your actual TOML file. In remote mode a file operand
is read by the client and sent as compiled content. It is not interpreted as a
path on the service. Direct file submission snapshots the definition for that
Run; use a configured registration or the upload API for a named catalog entry.

For a service populated through HTTP, use the official KFP client:

```python
import kfp

client = kfp.Client(host="http://127.0.0.1:8080")
pipeline = client.upload_pipeline(
    "examples/quickstart/orchestration/kfp/compiled/statistics.yaml",
    pipeline_name="statistics-uploaded",
)
client.run_pipeline(
    experiment_id=client.create_experiment("Tutorial").experiment_id,
    job_name="First uploaded run",
    pipeline_id=pipeline.pipeline_id,
    params={"count": 10},
)
```

The example uses a different name from the configuration-owned `statistics`
registration. Pipeline names are unique within a project; uploading over an
existing configured name is a conflict. See the [API guide](api.md) for version
upload, exact-version execution and adapter limits.

Uploading registers the compiled definition and its embedded component
contracts. It does not build/push images, upload datasets or execute tasks.
The browser's upload action uses this same API.

## Version and refresh behavior

Configured files are validated when used. Changed valid bytes create a new
immutable definition snapshot; old Runs retain their original snapshot. Run
`definitions refresh` to reconcile all configured mappings. Missing/removed
configured sources become unavailable by name, but retained IDs remain
inspectable and explicitly selectable.

API uploads create immutable named versions. Their latest committed version is
the pipeline's default. Uploading an existing pipeline or version name conflicts;
there is no replacement/delete operation. A configuration refresh does not erase
API-owned pipelines or choose different defaults for them.

Use `definitions validate` before execution and inspect `capabilities` for the
actual profile. [Compatibility](compatibility.md) lists unsupported KFP constructs
that are rejected before execution.
