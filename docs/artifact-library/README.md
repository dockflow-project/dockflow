# Using Dockflow Artifacts

Dockflow Artifacts is an independently installable library in this monorepo.
It publishes immutable files or directories at paths you choose, then verifies
and records their contents. KFP integration is optional; no Dockflow server is
required. All Dockflow distributions share the root VERSION and release process.

From the monorepo checkout, with an activated Python 3.12 or 3.13 environment:

```bash
uv pip install ./packages/artifacts
# Add object storage and KFP authoring support when needed:
uv pip install --overrides tools/runtime-overrides.txt './packages/artifacts[s3,kfp]'
```

Install the standalone library with `pip install dockflow-artifacts==0.2.0`.
Filesystem publication
requires POSIX filesystem primitives; runtime qualification is on Linux.

```python
from pathlib import Path
from dockflow_artifacts import Publisher, format_path

publisher = Publisher(Path("data/artifacts").resolve())
receipt = publisher.publish(
    "model.json",
    format_path("models/{version}/model.json", version="v1"),
    artifact_type="system.Model",
    metadata={"algorithm": "example"},
)
print(receipt.uri)
assert publisher.verify("models/v1/model.json") == receipt
```

`model.json` must already exist. Publication preserves its bytes; a conflicting
write fails instead of replacing a previously published artifact.

1. [Publishing and storage configuration](storage.md)
2. [KFP and Dockflow integration](kfp.md)
3. [Public API reference](api.md)

[Contributing](../../CONTRIBUTING.md) describes the shared development environment,
tests and package verification. The library follows the repository's MIT license.

Publication claims and manifests use the shared SQLite/PostgreSQL database.
Storage contains payloads and an identity marker; see [storage](storage.md) for
defaults, explicit remote configuration and coordinated backups.
