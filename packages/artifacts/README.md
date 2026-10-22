# Dockflow Artifacts

A Python library for immutable artifact publication at caller-chosen paths,
content verification, and optional orchestration integration. Its first adapters
support filesystems, S3-compatible stores and KFP typed importers.

Python 3.12–3.13. MIT licensed. Developed with AI assistance.

This is an unpublished development project. Install from a checkout:

```bash
uv sync --all-packages --all-extras
uv pip install ./packages/artifacts
# Optional integrations (KFP's urllib3 security override is required):
uv pip install --overrides tools/runtime-overrides.txt './packages/artifacts[s3,kfp]'
```

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

The file lives at exactly the requested path. Different bytes or metadata cannot
replace an existing publication. Identical retries verify/reuse it. Importing
the library performs no configuration, network calls or filesystem writes;
publishing and verification perform explicit I/O.

Component scripts can remain independent. A wrapper runs a script and publishes
its files; the pipeline uses `dockflow_artifacts.kfp.importer_component` to register
the returned URI as a normal `Model` or `Dataset`. No Dockflow server is required.

[Documentation](../../docs/artifact-library/README.md) covers configuration, publication semantics,
KFP integration and the public API. [Examples](examples/) use synthetic data.
[Contributing](../../CONTRIBUTING.md) describes development checks.

```bash
uv run pytest packages/artifacts/tests
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv build --package dockflow-artifacts --force-pep517
```

The repository-root `VERSION` governs the shared Dockflow application version,
currently `0.1.0.dev0`; package metadata is synchronized by the shared tooling.
The library is a member of the existing monorepo workspace, composition and
lifecycle. Macrostates baselines remain separate. There is no finalized release
provenance or published artifact yet. The root `uv.lock` pins contributor tools,
not downstream users. Run development commands from the repository root.
