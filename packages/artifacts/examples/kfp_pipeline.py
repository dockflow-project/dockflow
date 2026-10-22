"""Compile with the kfp extra. Build an image containing this package before execution."""

from dockflow_artifacts.kfp import importer_component
from kfp import compiler, dsl


@dsl.component(
    base_image="example-artifact-components:prepared", install_kfp_package=False
)
def produce(version: str) -> str:
    import tempfile
    from pathlib import Path

    from dockflow_artifacts import Publisher, format_path

    with tempfile.TemporaryDirectory() as temporary:
        model = Path(temporary) / "model.json"
        model.write_text('{"coefficient": 2}\n')
        store = Publisher.from_config("/etc/dockflow-artifacts/config.json")
        return store.publish(
            model,
            format_path("models/{version}/model.json", version=version),
            artifact_type="system.Model",
        ).uri


@dsl.component(
    base_image="example-artifact-components:prepared", install_kfp_package=False
)
def consume(model: dsl.Input[dsl.Model]) -> float:
    import json

    with open(model.path) as stream:
        return float(json.load(stream)["coefficient"])


import_model = importer_component(dsl.Model)


@dsl.pipeline(name="custom-artifacts-example")
def pipeline(version: str = "v1"):
    output = produce(version=version)
    artifact = import_model(uri=output.output).set_display_name("Published model")
    consume(model=artifact.output)


if __name__ == "__main__":
    compiler.Compiler().compile(pipeline, "/tmp/custom-artifacts-example.yaml")
