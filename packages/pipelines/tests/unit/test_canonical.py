import json
from pathlib import Path

import pytest
from dockflow_pipelines.canonical import canonical_bytes, digest, loads


def test_normative_digest_vectors():
    root = Path(__file__).resolve().parents[4]
    fixture = (
        root
        / ".macrostates/specs/053_dockflow-pipelines/resources/canonical-digests.json"
    )
    for vector in json.loads(fixture.read_text())["vectors"]:
        assert canonical_bytes(vector["value"]).decode() == vector["canonical_utf8"]
        assert digest(vector["value"]) == vector["sha256"]


@pytest.mark.parametrize(
    "value", [2**53, -(2**53), float("nan"), float("inf"), "\ud800", {1: "x"}]
)
def test_reject_nonportable_json(value):
    with pytest.raises(ValueError):
        canonical_bytes(value)


def test_strict_json_boundary_and_numeric_distinction():
    with pytest.raises(ValueError, match="Duplicate"):
        loads('{"x":1,"x":2}')
    with pytest.raises(ValueError):
        loads('{"x":NaN}')
    assert digest(1) != digest(1.0)
    assert digest(0.0) != digest(-0.0)
