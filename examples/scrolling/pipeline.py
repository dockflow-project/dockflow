"""Compile a static, executable KFP example for exploring graph scrolling."""

import argparse
from pathlib import Path

from kfp import compiler, dsl

STEP = """import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--value', type=int, required=True)
parser.add_argument('--label', required=True)
parser.add_argument('--result', required=True)
args = parser.parse_args()
result = args.value + 1
destination = Path(args.result)
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(str(result))
print(f'{args.label}: {args.value} -> {result}', flush=True)
"""


@dsl.container_component
def step(value: int, label: str, result: dsl.OutputPath(int)):
    return dsl.ContainerSpec(
        image="python:3.13-slim",
        command=["python", "-c", STEP],
        args=["--value", value, "--label", label, "--result", result],
    )


@dsl.pipeline(
    name="scrolling-example",
    description="98 small steps: eight parallel branches of twelve steps, plus start and finish.",
)
def scrolling_example(seed: int = 0):
    start = step(value=seed, label="Start").set_display_name("Start")
    tails = []
    for branch in range(1, 9):
        previous = start
        for stage in range(1, 13):
            label = f"Branch {branch} / Step {stage:02d}"
            previous = step(
                value=previous.outputs["result"], label=label
            ).set_display_name(label)
        tails.append(previous)
    step(value=tails[-1].outputs["result"], label="Finish").set_display_name(
        "Finish"
    ).after(*tails)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path(__file__).with_name("pipeline.yaml")
    )
    arguments = parser.parse_args()
    compiler.Compiler().compile(scrolling_example, str(arguments.output))


if __name__ == "__main__":
    main()
