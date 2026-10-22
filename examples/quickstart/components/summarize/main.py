"""Read a dataset directory and write a JSON report and numeric output file."""

import argparse
import json
from pathlib import Path
from statistics import mean


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-directory", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--mean-output", type=Path, required=True)
    args = parser.parse_args()
    numbers = json.loads(
        (args.input_directory / "numbers.json").read_text(encoding="utf-8")
    )
    report = {"count": len(numbers), "sum": sum(numbers), "mean": mean(numbers)}
    args.output_directory.mkdir(parents=True, exist_ok=True)
    (args.output_directory / "summary.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    args.mean_output.parent.mkdir(parents=True, exist_ok=True)
    args.mean_output.write_text(str(report["mean"]), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
