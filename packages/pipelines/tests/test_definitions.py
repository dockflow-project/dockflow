"""Compiled input rejection must happen before any infrastructure or mutation."""

import copy
import json

import pytest
from dockflow_pipelines.definitions import (
    DefinitionError,
    UnsupportedCapability,
    evaluate_condition,
    load_definition,
    validate_parameters,
)


def primitive():
    return {
        "pipelineInfo": {"name": "fixture"},
        "schemaVersion": "2.1.0",
        "sdkVersion": "kfp-2.17.0",
        "root": {
            "executorLabel": "exec-test",
            "inputDefinitions": {
                "parameters": {
                    "count": {"parameterType": "NUMBER_INTEGER", "defaultValue": 2.0},
                    "ratio": {"parameterType": "NUMBER_DOUBLE", "defaultValue": 1.0},
                }
            },
        },
        "deploymentSpec": {
            "executors": {
                "exec-test": {
                    "container": {"image": "python:3.13-slim", "command": ["true"]}
                }
            }
        },
    }


def test_defaults_preserve_declared_type_and_reject_user_coercion():
    definition = load_definition(primitive())
    values = validate_parameters(definition)
    assert type(values["count"]) is int
    assert type(values["ratio"]) is float
    for bad in (True, "2", 2.5, 2**53):
        with pytest.raises((DefinitionError, ValueError)):
            validate_parameters(definition, {"count": bad})


@pytest.mark.parametrize(
    "suffix",
    [
        "\nschemaVersion: 2.1.0",
        "\nunknown: !!python/object:os.system {}",
        "\nextra: .nan",
    ],
)
def test_unsafe_or_ambiguous_definition_is_rejected(suffix):
    text = "schemaVersion: 2.1.0\n" + suffix
    with pytest.raises(DefinitionError):
        load_definition(text)


def test_unknown_executable_requirement_is_not_silently_ignored():
    document = primitive()
    document["deploymentSpec"]["executors"]["exec-test"]["container"]["resources"] = {
        "accelerator": {"type": "nvidia"}
    }
    with pytest.raises(UnsupportedCapability, match="accelerator"):
        load_definition(document)


def test_condition_parser_never_executes_python(tmp_path):
    target = tmp_path / "sentinel"
    with pytest.raises(UnsupportedCapability):
        evaluate_condition(f"__import__('pathlib').Path('{target}').touch()", {})
    assert not target.exists()
    assert evaluate_condition(
        "int(inputs.parameter_values['x']) >= 2 && !(inputs.parameter_values['name'] == 'skip')",
        {"x": 3, "name": "run"},
    )
    assert not evaluate_condition("!(int(inputs.parameter_values['x']) == 1)", {"x": 1})


def test_cycle_and_unknown_parameter_output_are_rejected():
    document = primitive()
    component = document.pop("root")
    component.pop("inputDefinitions")
    document["components"] = {"comp-test": component}
    document["root"] = {
        "dag": {
            "tasks": {
                "a": {"componentRef": {"name": "comp-test"}, "dependentTasks": ["b"]},
                "b": {"componentRef": {"name": "comp-test"}, "dependentTasks": ["a"]},
            }
        }
    }
    with pytest.raises(DefinitionError, match="cycle"):
        load_definition(document)


def test_source_bytes_are_retained_separately_from_normalized_document():
    text = "# a compiler comment\n" + json.dumps(primitive(), indent=2)
    definition = load_definition(text)
    same_content = load_definition(copy.deepcopy(primitive()))
    assert definition.document == same_content.document
    assert definition.sha256 != same_content.sha256
    assert definition.raw_bytes.decode() == text


def test_compiler_scientific_default_is_numeric_but_quoted_string_stays_string():
    text = json.dumps(primitive()).replace(
        '"defaultValue": 1.0', '"defaultValue": 1e-09'
    )
    definition = load_definition(text)
    assert validate_parameters(definition)["ratio"] == 1e-9
    text = text.replace('"defaultValue": 1e-09', '"defaultValue": "1e-09"')
    with pytest.raises(DefinitionError):
        load_definition(text)


@pytest.mark.parametrize("name", ["../escape", "/absolute", ".dockflow", "bad%2fname"])
def test_pipeline_storage_names_rejected_before_dispatch(name):
    document = primitive()
    document["pipelineInfo"]["name"] = name
    with pytest.raises(DefinitionError, match="safe storage"):
        load_definition(document)


@pytest.mark.parametrize("name", ["../model", "/model", "a\\b", "a/b", "%2e%2e"])
def test_artifact_binding_names_rejected_before_dispatch(name):
    document = primitive()
    document["root"]["outputDefinitions"] = {
        "artifacts": {
            name: {
                "artifactType": {
                    "schemaTitle": "system.Model",
                    "schemaVersion": "0.0.1",
                }
            }
        }
    }
    with pytest.raises(DefinitionError, match="artifact binding name"):
        load_definition(document)
