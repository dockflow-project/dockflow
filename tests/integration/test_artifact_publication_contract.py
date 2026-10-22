"""The independent publisher's standard importer IR is accepted by Pipelines."""

import importlib.util
from pathlib import Path

from dockflow_pipelines.definitions import load_definition
from kfp import compiler


def test_custom_publication_example_is_admitted_without_ir_extensions(tmp_path):
    source = (
        Path(__file__).resolve().parents[2]
        / "packages/artifacts/examples/kfp_pipeline.py"
    )
    spec = importlib.util.spec_from_file_location("publication_example", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    compiled = tmp_path / "pipeline.yaml"
    compiler.Compiler().compile(module.pipeline, str(compiled))
    definition = load_definition(compiled)
    assert definition.name == "custom-artifacts-example"
    assert set(definition.tasks) == {
        "produce",
        "import-published-artifact",
        "import-published-artifact/importer",
        "consume",
    }
