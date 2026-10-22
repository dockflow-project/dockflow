# Dockflow documentation

Dockflow runs a supported subset of compiled Kubeflow Pipelines (KFP) definitions
through Docker. A CLI, a REST service and a browser interface share the same
execution, artifact and history model. Kubernetes is not required for Dockflow.

These pages document the **unpublished development implementation**. They do not
claim a stable release or full KFP compatibility. Start with the tutorial, then
choose direct execution or a persistent service for your project.

## Start here

1. [Install Dockflow](installation.md): source checkout, package extras and requirements.
2. [Run your first pipeline](quickstart.md): a complete two-component example,
   inspection, reuse, and the same project through the service.
3. [Understand the model](concepts.md): definitions, components, Runs, attempts,
   artifacts, experiments and ownership.
4. [Write components and pipelines](pipelines.md): independent component programs,
   KFP wrappers, compilation, image preparation and registration.

## Use and configure

| Guide | What it covers |
| --- | --- |
| [CLI](cli.md) | Execution, inspection, selection, structured output and exit codes. |
| [Browser interface](ui.md) | Pipeline versions, run graphs, task results, logs and artifacts. |
| [HTTP API](api.md) | Requests, authentication, pagination, errors and the KFP client adapter. |
| [Generated API reference](reference/api.md) | Routes and schemas from the implementation's OpenAPI contract. |
| [Configuration](configuration.md) | TOML fields, environment overrides, paths and service/client boundaries. |
| [Artifacts and reuse](artifacts.md) | External inputs, managed data, lineage, integrity and historical selection. |
| [Artifact library](artifact-library/README.md) | Independently installable publication at custom paths, verification and typed KFP registration. |
| [KFP compatibility](compatibility.md) | Admitted features and explicit limits. |

## Operate and contribute

| Guide | What it covers |
| --- | --- |
| [Deployment](deployment.md) | A Python service, container topology, image stores and mounts. |
| [Operations](operations.md) | Start, stop, inspect, cancel and maintain a project. |
| [Persistence and recovery](persistence.md) | Ownership, data layout, backup, restore and crash recovery. |
| [Troubleshooting](troubleshooting.md) | Common failures and targeted diagnostics. |
| [Contributing](../CONTRIBUTING.md) | Development environment, checks, review and specification workflow. |
| [Architecture](architecture.md) | Internal boundaries and design. |
| [Certificate maintenance](certificate-maintenance.md) | Update Python tools, trust stores and existing container deployments. |
| [Security](../SECURITY.md) | Trust model, deployment boundaries and reporting. |

The [specifications](../.macrostates/specs/main.md) define requirements and their
authority. The [implementation overview](../.macrostates/implementation/main.md)
records qualification evidence and gaps. Ordinary users can follow these guides
without installing the specification tooling.
