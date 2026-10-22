"""The public helper compiles to standard typed importer IR."""

import importlib.util
from pathlib import Path

import pytest
import yaml
from dockflow_artifacts.kfp import importer_component
from kfp import compiler, dsl


def test_example_compiles_with_typed_importer(tmp_path):
    source = Path(__file__).parents[1] / "examples/kfp_pipeline.py"
    spec = importlib.util.spec_from_file_location("artifact_example", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    destination = tmp_path / "pipeline.yaml"
    compiler.Compiler().compile(module.pipeline, str(destination))
    document = yaml.safe_load(destination.read_text())
    importers = [
        executor["importer"]
        for executor in document["deploymentSpec"]["executors"].values()
        if "importer" in executor
    ]
    assert len(importers) == 1
    assert importers[0]["typeSchema"]["schemaTitle"] == "system.Model"
    assert importers[0]["artifactUri"] == {"runtimeParameter": "uri"}
    tasks = document["root"]["dag"]["tasks"]
    registration = tasks["import-published-artifact"]
    assert registration["dependentTasks"] == ["produce"]
    assert registration["inputs"]["parameters"]["uri"]["taskOutputParameter"] == {
        "outputParameterKey": "Output",
        "producerTask": "produce",
    }
    nested = document["components"][registration["componentRef"]["name"]]["dag"]
    assert nested["tasks"]["importer"]["inputs"]["parameters"]["uri"] == {
        "componentInputParameter": "uri"
    }


def test_metadata_type_and_reimport_survive_compilation(tmp_path):
    import_model = importer_component(
        dsl.Model,
        metadata={"algorithm": "example", "rows": 50},
        reimport=True,
    )

    @dsl.pipeline
    def pipeline(uri: str) -> dsl.Model:
        return import_model(uri=uri).output

    destination = tmp_path / "pipeline.yaml"
    compiler.Compiler().compile(pipeline, str(destination))
    document = yaml.safe_load(destination.read_text())
    importer = next(
        executor["importer"]
        for executor in document["deploymentSpec"]["executors"].values()
        if "importer" in executor
    )
    assert importer["metadata"] == {"algorithm": "example", "rows": 50}
    assert importer["reimport"] is True
    assert importer["typeSchema"]["schemaTitle"] == "system.Model"


def test_dynamic_metadata_is_rejected_before_compilation():
    with pytest.raises(ValueError, match="static JSON"):
        importer_component(dsl.Model, metadata={"value": object()})
