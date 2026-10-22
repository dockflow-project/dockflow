# Dockflow Pipelines

`dockflow-pipelines` executes supported compiled KFP definitions through
DockerRunner with durable history, typed artifacts, lineage, reuse, a CLI and a
REST/browser service. Kubernetes is not required. Component images and compiled
definitions are prepared by the consuming project.

The base package supports remote CLI operations. Install the `runtime` extra for
local execution, add `service` for HTTP/browser serving, and add `s3` when using
S3-compatible artifacts. Installation instructions are in the
[installation guide](https://github.com/dockflow-project/dockflow/blob/main/docs/installation.md).

The generic service accepts compiled pipeline/version uploads through the
documented KFP 2.17 client subset. Those uploads contain component contracts and
executor metadata; images remain separate and must be available to the execution
engine. The service does not need the consuming project's Python source.

Start with the [tutorial](https://github.com/dockflow-project/dockflow/blob/main/docs/quickstart.md), then consult the
[CLI](https://github.com/dockflow-project/dockflow/blob/main/docs/cli.md), [API](https://github.com/dockflow-project/dockflow/blob/main/docs/api.md),
[browser](https://github.com/dockflow-project/dockflow/blob/main/docs/ui.md), [configuration](https://github.com/dockflow-project/dockflow/blob/main/docs/configuration.md)
and [compatibility](https://github.com/dockflow-project/dockflow/blob/main/docs/compatibility.md) guides in the source repository.

Install the remote client with Python 3.12 or newer:

```bash
pip install dockflow-pipelines==0.1.1
```

This also installs the matching `dockflow-cli`. For local execution and serving,
use the installation guide's **uv override command**; plain pip installation of
KFP extras retains upstream KFP's older urllib3 pin.

This MIT-licensed initial release implements a bounded KFP profile. One
project has one execution owner, one active Run and serial task execution.
Qualification gaps are recorded in the implementation overview; the full KFP
server API and all runtime platforms are not claimed as supported.

Runtime installations use the qualified urllib3 security override described in
the [installation guide](https://github.com/dockflow-project/dockflow/blob/main/docs/installation.md#kfp-dependency-override).
It applies automatically in the locked workspace/service image. Standalone
installs must apply it explicitly while KFP 2.17 retains its older exact pin.
