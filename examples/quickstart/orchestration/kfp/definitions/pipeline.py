"""KFP contracts for the independent scripts in components/."""

from kfp import dsl

IMAGE = "dockflow-quickstart-components:v1"


@dsl.container_component
def generate(count: int, dataset: dsl.Output[dsl.Dataset]):
    return dsl.ContainerSpec(
        image=IMAGE,
        command=["python", "/components/generate/main.py"],
        args=["--count", count, "--output-directory", dataset.path],
    )


@dsl.container_component
def summarize(
    dataset: dsl.Input[dsl.Dataset],
    report: dsl.Output[dsl.Artifact],
    mean: dsl.OutputPath(float),
):
    return dsl.ContainerSpec(
        image=IMAGE,
        command=["python", "/components/summarize/main.py"],
        args=[
            "--input-directory",
            dataset.path,
            "--output-directory",
            report.path,
            "--mean-output",
            mean,
        ],
    )


@dsl.pipeline(name="statistics", description="Generate numbers and summarize them.")
def statistics(count: int = 10):
    generated = generate(count=count)
    summarize(dataset=generated.outputs["dataset"])
