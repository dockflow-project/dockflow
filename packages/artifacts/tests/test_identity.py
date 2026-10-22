"""Publication identity is stable, typed, portable and separate from execution caching."""

import json

import pytest
from dockflow_artifacts import ArtifactError, fingerprint, publication_id, step_path


def identity(parameters=None, **changes):
    options = dict(
        component_name="train",
        component_version="v1",
        parameters={} if parameters is None else parameters,
    )
    options.update(changes)
    return publication_id(**options)


def test_canonical_mapping_order_and_resolved_parameters():
    assert identity({"b": [1, {"z": None, "a": True}], "a": "é"}) == identity(
        {"a": "é", "b": [1, {"a": True, "z": None}]}
    )
    assert len(identity()) == 64
    assert identity({"seed": 42}) != identity()
    assert identity() != identity(component_name="evaluate")
    assert identity() != identity(component_version="v2")
    assert identity() != identity(inputs={"data": "sha256:new"})
    for field in ("pipeline_name", "exploration_id", "step_number", "step_digits"):
        assert identity({field: "one"}) != identity({field: "two"})


def test_types_and_order_are_preserved():
    values = [None, False, 0, 0.0, -0.0, True, 1, 1.0, "1", [], {}, [1, 2], [2, 1]]
    assert len({identity({"x": value}) for value in values}) == len(values)


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        2**53,
        -(2**53),
        {1: "x"},
        (1,),
        {1},
        b"x",
        "\ud800",
    ],
)
def test_nonportable_inputs_are_rejected(value):
    with pytest.raises(ArtifactError):
        identity({"value": value})


@pytest.mark.parametrize(
    "changes",
    [
        {"component_name": ""},
        {"component_version": ""},
        {"component_version": 1},
        {"parameters": []},
        {"inputs": []},
    ],
)
def test_invalid_identity_contract(changes):
    with pytest.raises(ArtifactError):
        identity(**changes)


def test_fingerprints_follow_contents_and_tree_names_not_staging_paths(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text("original")
    second.write_text("original")
    assert fingerprint(first) == fingerprint(second)
    second.write_text("changed")
    assert fingerprint(first) != fingerprint(second)
    tree = tmp_path / "tree"
    tree.mkdir()
    item = tree / "a.json"
    item.write_text("original")
    before = fingerprint(tree)
    assert before != fingerprint(first)
    item.rename(tree / "b.json")
    assert before != fingerprint(tree)
    alias = tmp_path / "alias"
    alias.symlink_to(first)
    with pytest.raises(ArtifactError):
        fingerprint(alias)


def test_golden_identity_is_stable():
    # Pin the public versioned encoding, including float bits and escaped Unicode.
    assert (
        identity({"seed": 42, "rate": 0.25, "label": "é"})
        == "2c8f34006f79e0849a0ccd30ff75aff51c65be9d00a4f3bddc2956181582ef05"
    )
    assert identity(json.loads('{"seed":42,"rate":0.25,"label":"é"}')) == identity(
        {"seed": 42, "rate": 0.25, "label": "é"}
    )


@pytest.mark.parametrize(
    "digits,number,expected",
    [(1, 3, "3"), (2, 3, "03"), (3, 100, "100"), (1, 100, "100")],
)
def test_pipeline_supplied_width(digits, number, expected):
    assert (
        step_path(
            "model.json",
            step_number=number,
            step_digits=digits,
            pipeline_name="training",
            component_name="train",
            publication_id="a" * 64,
        )
        == f"global/training/step_{expected}__train__{'a' * 64}/model.json"
    )


@pytest.mark.parametrize("digits", [0, -1, True, 1.5, "2", 13])
def test_invalid_width(digits):
    with pytest.raises(ArtifactError, match="Step digits"):
        step_path(
            "model.json",
            step_number=1,
            step_digits=digits,
            pipeline_name="training",
            component_name="train",
            publication_id="a" * 64,
        )


@pytest.mark.parametrize("key", ["a" * 63, "A" * 64, "g" * 64, "../x", 1, ""])
def test_invalid_publication_id(key):
    with pytest.raises(ArtifactError, match="Publication ID"):
        step_path(
            "model.json",
            step_number=1,
            step_digits=1,
            pipeline_name="training",
            component_name="train",
            publication_id=key,
        )
