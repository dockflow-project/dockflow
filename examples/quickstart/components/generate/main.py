"""Write a small deterministic dataset using only the Python standard library."""

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.count <= 10_000:
        parser.error("--count must be between 1 and 10000")
    args.output_directory.mkdir(parents=True, exist_ok=True)
    (args.output_directory / "numbers.json").write_text(
        json.dumps(list(range(1, args.count + 1))) + "\n", encoding="utf-8"
    )
    print(f"Generated integers 1 through {args.count}")


if __name__ == "__main__":
    main()
