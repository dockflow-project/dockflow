"""Rebuild the checked-in compiled definition; Dockflow does not run this script."""

from pathlib import Path

from definitions.pipeline import statistics
from kfp import compiler

destination = Path(__file__).parent / "compiled" / "statistics.yaml"
destination.parent.mkdir(parents=True, exist_ok=True)
compiler.Compiler().compile(statistics, str(destination))
