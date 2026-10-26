# Dockflow Artifacts

A Python library for immutable artifact publication at caller-chosen paths,
content verification, and optional orchestration integration. Its first adapters
support filesystems, S3-compatible stores and KFP typed importers.

Python 3.12–3.13. MIT licensed. Developed with AI assistance.

Install with Python 3.12 or newer:

```bash
pip install dockflow-artifacts==0.3.0
# Optional S3 integration:
pip install 'dockflow-artifacts[s3]==0.3.0'
```

For the optional `kfp` extra, follow the installation guide's explicit urllib3
override. This library can be installed without the Dockflow CLI or service.

```python
from pathlib import Path
from dockflow_artifacts import Publisher, format_path

store = Publisher(Path("/absolute/path/to/artifacts"))
result = store.publish(
    "model.json",
    format_path("models/{experiment}/{version}/model.json", experiment="demo", version="v1"),
    artifact_type="system.Model",
    metadata={"algorithm": "example"},
)
print(result.uri)
store.verify("models/demo/v1/model.json")
```

Publication bookkeeping uses SQLite/PostgreSQL through the shared
`dockflow-core` package. Filesystem roots default to `.dockflow/state.sqlite`
under their parent; remote roots require explicit database configuration.
Pass Pipelines’ database and project ID to share its state. Install the
`postgresql` extra for an external PostgreSQL database.

The file lives at exactly the requested path. Different bytes or metadata cannot
replace an existing publication. Identical retries verify/reuse it. Importing
the library performs no configuration, network calls or filesystem writes;
publishing and verification perform explicit I/O.

Component scripts can remain independent. A wrapper runs a script and publishes
its files; the pipeline uses `dockflow_artifacts.kfp.importer_component` to register
the returned URI as a normal `Model` or `Dataset`. No Dockflow server is required.

[Documentation](https://github.com/dockflow-project/dockflow/blob/main/docs/artifact-library/README.md) covers configuration, publication semantics,
KFP integration and the public API. [Examples](https://github.com/dockflow-project/dockflow/blob/main/packages/artifacts/examples/) use synthetic data.
[Contributing](https://github.com/dockflow-project/dockflow/blob/main/CONTRIBUTING.md) describes development checks.

```bash
uv run pytest packages/artifacts/tests
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv build --package dockflow-artifacts --force-pep517
```

The repository-root `VERSION` governs the shared Dockflow application version;
package metadata is synchronized by the shared tooling.
The library is a member of the existing monorepo workspace, composition and
lifecycle. Macrostates baselines remain separate. The root `uv.lock` pins contributor tools,
not downstream users. Run development commands from the repository root.
