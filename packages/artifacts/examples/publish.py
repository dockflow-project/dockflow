"""Run with: uv run python packages/artifacts/examples/publish.py (uses only temporary files)."""

from pathlib import Path
from tempfile import TemporaryDirectory

from dockflow_artifacts import Publisher

with TemporaryDirectory() as directory:
    root = Path(directory)
    model = root / "model.json"
    model.write_text('{"coefficient": 2}\n')
    store = Publisher(root / "published")
    receipt = store.publish(
        model, "models/demo/v1/model.json", artifact_type="system.Model"
    )
    assert store.verify("models/demo/v1/model.json") == receipt
    print(receipt.uri)
