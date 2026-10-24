"""Strict compiled KFP 2.17 input boundary and a derived execution plan.

No consumer Python is imported. The plan retains compiled component/task keys;
KFP itself constructs executor inputs and resolves execution placeholders.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .canonical import MAX_INTEGER, validate_json
from .compiled_source import read_compiled_source

PROFILE = "dockflow-kfp-2.17-v1"
MAX_DEFINITION_BYTES = 16_777_216
PARAMETER_TYPES = {
    "STRING",
    "BOOLEAN",
    "NUMBER_INTEGER",
    "NUMBER_DOUBLE",
    "STRUCT",
    "LIST",
}


class DefinitionError(ValueError):
    """Invalid compiled definition or invocation."""


class UnsupportedCapability(DefinitionError):
    """An executable requirement is outside the admitted profile."""


class _Loader(yaml.SafeLoader):
    pass


def _mapping(
    loader: _Loader, node: yaml.MappingNode, deep: bool = False
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise DefinitionError("Definition mapping keys must be strings")
        if key in result:
            raise DefinitionError(f"Duplicate definition key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)
# The IR has JSON semantics: timestamps and YAML's yes/no/on/off are strings.
_Loader.yaml_implicit_resolvers = {
    key: [
        (tag, pattern)
        for tag, pattern in values
        if tag not in {"tag:yaml.org,2002:timestamp", "tag:yaml.org,2002:bool"}
    ]
    for key, values in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$", re.I), list("tTfF")
)

# JSON-compatible scientific notation accepted by the KFP compiler, including
# exponent-only mantissas and an exponent without a mandatory explicit sign.
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?[eE][+-]?\d+$"),
    list("-0123456789"),
)


@dataclass(frozen=True)
class TaskSpec:
    name: str
    component_key: str
    component: dict[str, Any]
    task: dict[str, Any]
    parents: tuple[str, ...]
    conditional: bool = False

    @property
    def executor_label(self) -> str | None:
        return self.component.get("executorLabel")


@dataclass(frozen=True)
class Definition:
    raw_bytes: bytes
    document: dict[str, Any]
    sha256: str
    kind: str
    name: str
    tasks: dict[str, TaskSpec]

    @property
    def root(self) -> dict[str, Any]:
        return self.document["root"]

    def to_record(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "sha256": self.sha256,
            "pipeline_spec": self.document,
            "source_text": self.raw_bytes.decode("utf-8"),
            "profile": PROFILE,
            "compatibility_diagnostics": [],
            "available": True,
        }


def _fields(value: Any, allowed: set[str], location: str) -> None:
    if not isinstance(value, dict):
        raise DefinitionError(f"{location} must be an object")
    unknown = set(value) - allowed
    if unknown:
        raise UnsupportedCapability(
            f"{location}: unsupported fields {', '.join(sorted(unknown))}"
        )


def _booleans(value: dict, names: tuple[str, ...], location: str) -> None:
    for name in names:
        if name in value and type(value[name]) is not bool:
            raise DefinitionError(f"{location}.{name}: expected a boolean")


def resource_value(field: str, value: Any) -> float:
    """Validate and normalize the admitted CPU/core and memory/byte units."""
    cpu = field in {"cpuLimit", "resourceCpuLimit"}
    if isinstance(value, str):
        pattern = (
            r"(\d+(?:\.\d+)?)(m)?" if cpu else r"(\d+(?:\.\d+)?)([EPTGMK]i?|[eptgmk])?"
        )
        match = re.fullmatch(pattern, value)
        if not match:
            raise UnsupportedCapability(
                f"resources.{field}: unsupported resource expression"
            )
        number, unit = match.groups()
        result = float(number)
        if cpu:
            result /= 1000 if unit else 1
        else:
            power = (
                "KMGTPE".find((unit or "").upper().replace("I", "")) + 1 if unit else 0
            )
            result *= (1024 if unit and "i" in unit else 1000) ** power
    elif type(value) in {int, float}:
        result = float(value) * (1 if cpu else 1_000_000_000)
    else:
        raise DefinitionError(f"resources.{field}: positive numeric value required")
    quantity = result * 1_000_000_000 if cpu else result
    if not math.isfinite(quantity) or quantity < 1 or quantity >= 2**63:
        raise DefinitionError(
            f"resources.{field}: finite positive representable value required"
        )
    return result


def validate_parameter(
    value: Any, contract: dict[str, Any], location: str, *, compiled: bool = False
) -> Any:
    kind = contract.get("parameterType")
    validate_json(value)
    if kind == "NUMBER_INTEGER":
        if compiled and type(value) is float and value.is_integer():
            value = int(value)
        if type(value) is not int or abs(value) > MAX_INTEGER:
            raise DefinitionError(f"{location} requires a portable integer")
    elif kind == "NUMBER_DOUBLE":
        if type(value) not in {int, float} or not math.isfinite(value):
            raise DefinitionError(f"{location} requires a finite number")
        value = float(value)
    elif kind == "STRING" and not isinstance(value, str):
        raise DefinitionError(f"{location} requires a string")
    elif kind == "BOOLEAN" and type(value) is not bool:
        raise DefinitionError(f"{location} requires a boolean")
    elif kind == "STRUCT" and not isinstance(value, dict):
        raise DefinitionError(f"{location} requires a JSON object")
    elif kind == "LIST" and not isinstance(value, list):
        raise DefinitionError(f"{location} requires a JSON array")
    elif kind not in PARAMETER_TYPES:
        raise UnsupportedCapability(f"{location}: unsupported parameter type {kind!r}")
    return value


def _contracts(component: dict[str, Any], location: str) -> None:
    for direction in ("inputDefinitions", "outputDefinitions"):
        interface = component.get(direction, {})
        _fields(interface, {"parameters", "artifacts"}, f"{location}.{direction}")
        for name, contract in interface.get("parameters", {}).items():
            _fields(
                contract,
                {"parameterType", "defaultValue", "isOptional", "description"},
                f"{location}.{name}",
            )
            if contract.get("parameterType") not in PARAMETER_TYPES:
                raise UnsupportedCapability(
                    f"{location}.{name}: unsupported parameter type"
                )
            _booleans(contract, ("isOptional",), f"{location}.{name}")
            if "defaultValue" in contract:
                validate_parameter(
                    contract["defaultValue"],
                    contract,
                    f"{location}.{name}.default",
                    compiled=True,
                )
        for name, contract in interface.get("artifacts", {}).items():
            if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", name):
                raise DefinitionError(f"Invalid artifact binding name {name!r}")
            _fields(
                contract,
                {"artifactType", "isArtifactList", "isOptional", "description"},
                f"{location}.{name}",
            )
            _booleans(contract, ("isOptional", "isArtifactList"), f"{location}.{name}")
            if contract.get("isArtifactList"):
                raise UnsupportedCapability(
                    f"{location}.{name}: artifact lists are not supported"
                )
            _fields(
                contract.get("artifactType", {}),
                {"schemaTitle", "schemaVersion"},
                f"{location}.{name}.artifactType",
            )
            if any(
                not isinstance(value, str) or not value
                for value in contract["artifactType"].values()
            ) or not contract["artifactType"].get("schemaTitle"):
                raise DefinitionError(
                    f"{location}.{name}: artifact schemaTitle is required"
                )


def _validate_executor(executor: dict[str, Any], location: str) -> None:
    _fields(executor, {"container", "importer"}, location)
    if len(executor) != 1:
        raise DefinitionError(f"{location}: exactly one executor is required")
    if "importer" in executor:
        importer = executor["importer"]
        _fields(
            importer,
            {"artifactUri", "typeSchema", "metadata", "reimport"},
            location + ".importer",
        )
        _booleans(importer, ("reimport",), location + ".importer")
        _fields(
            importer.get("artifactUri", {}),
            {"constant", "runtimeParameter"},
            location + ".artifactUri",
        )
        if len(importer.get("artifactUri", {})) != 1:
            raise DefinitionError(f"{location}: importer requires an artifactUri")
        _fields(
            importer.get("typeSchema", {}),
            {"schemaTitle", "schemaVersion"},
            location + ".typeSchema",
        )
        return
    container = executor["container"]
    _fields(
        container,
        {"image", "command", "args", "env", "resources"},
        location + ".container",
    )
    if not isinstance(container.get("image"), str) or not container["image"]:
        raise DefinitionError(f"{location}: container image is required")
    for name in ("command", "args"):
        if not isinstance(container.get(name, []), list) or any(
            not isinstance(s, str) for s in container.get(name, [])
        ):
            raise DefinitionError(f"{location}.{name}: expected string array")
    for env in container.get("env", []):
        _fields(env, {"name", "value"}, location + ".env")
        if not isinstance(env.get("name"), str) or not isinstance(
            env.get("value"), str
        ):
            raise DefinitionError(f"{location}.env: name and value must be strings")
    resources = container.get("resources", {})
    _fields(
        resources,
        {
            "cpuLimit",
            "memoryLimit",
            "cpuRequest",
            "memoryRequest",
            "resourceCpuLimit",
            "resourceMemoryLimit",
        },
        location + ".resources",
    )
    if {"cpuLimit", "resourceCpuLimit"} <= resources.keys() or {
        "memoryLimit",
        "resourceMemoryLimit",
    } <= resources.keys():
        raise DefinitionError(f"{location}: conflicting resource aliases")
    for field, value in resources.items():
        if field in {"cpuRequest", "memoryRequest"}:
            raise UnsupportedCapability(
                f"{location}.resources.{field}: Docker has no qualified request mapping"
            )
        resource_value(field, value)


def load_definition(source: str | bytes | Path | dict[str, Any]) -> Definition:
    if isinstance(source, Path):
        try:
            raw = read_compiled_source(source, MAX_DEFINITION_BYTES)
        except (OSError, ValueError) as exc:
            raise DefinitionError(str(exc)) from exc
    elif isinstance(source, dict):
        validate_json(source)
        raw = json.dumps(
            source, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode()
    elif isinstance(source, str):
        raw = source.encode("utf-8")
    else:
        raw = source
    if not isinstance(raw, bytes) or len(raw) > MAX_DEFINITION_BYTES:
        raise DefinitionError("Definition must be UTF-8 and at most 16777216 bytes")
    try:
        document = yaml.load(raw.decode("utf-8"), Loader=_Loader)
        validate_json(document)
    except (ValueError, UnicodeError, yaml.YAMLError, RecursionError) as exc:
        raise DefinitionError(f"Invalid compiled definition: {exc}") from exc
    if not isinstance(document, dict):
        raise DefinitionError("Compiled definition must be an object")
    if "pipelineSpec" in document:
        _fields(document, {"pipelineSpec", "platformSpec"}, "document")
        if document.get("platformSpec"):
            raise UnsupportedCapability(
                "platformSpec: Kubernetes/platform plugins are unsupported"
            )
        document = document["pipelineSpec"]
    _fields(
        document,
        {
            "pipelineInfo",
            "root",
            "components",
            "deploymentSpec",
            "schemaVersion",
            "sdkVersion",
            "defaultPipelineRoot",
        },
        "pipelineSpec",
    )
    if document.get("schemaVersion") != "2.1.0":
        raise UnsupportedCapability(
            "Only KFP PipelineSpec schemaVersion 2.1.0 is admitted"
        )
    if not re.fullmatch(r"kfp-2\.17\.\d+", document.get("sdkVersion", "")):
        raise UnsupportedCapability(
            "Only definitions compiled by KFP SDK 2.17 are admitted"
        )
    _fields(
        document.get("pipelineInfo", {}),
        {"name", "description", "displayName"},
        "pipelineInfo",
    )
    name = document.get("pipelineInfo", {}).get("name")
    if not isinstance(name, str) or not name:
        raise DefinitionError("pipelineInfo.name is required")
    if not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*", name) or name.endswith("."):
        raise DefinitionError("pipelineInfo.name must be a safe storage path segment")
    _fields(document.get("deploymentSpec", {}), {"executors"}, "deploymentSpec")
    executors = document.get("deploymentSpec", {}).get("executors", {})
    for label, executor in executors.items():
        _validate_executor(executor, f"executors.{label}")
    components = document.get("components", {})
    root = document.get("root")
    if not isinstance(root, dict):
        raise DefinitionError("root must be a compiled component")
    tasks: dict[str, TaskSpec] = {}

    def visit(
        component: dict[str, Any],
        path: str,
        stack: tuple[str, ...],
        conditional: bool = False,
    ) -> None:
        _fields(
            component,
            {"dag", "executorLabel", "inputDefinitions", "outputDefinitions"},
            path or "root",
        )
        _contracts(component, path or "root")
        if ("dag" in component) == ("executorLabel" in component):
            raise DefinitionError(
                f"{path or 'root'} requires exactly one dag or executorLabel"
            )
        if "executorLabel" in component:
            if component["executorLabel"] not in executors:
                raise DefinitionError(
                    f"{path}: missing executor {component['executorLabel']}"
                )
            return
        dag = component["dag"]
        _fields(dag, {"tasks", "outputs"}, f"{path or 'root'}.dag")
        local = dag.get("tasks", {})
        if not isinstance(local, dict):
            raise DefinitionError(f"{path}: tasks must be an object")
        dependencies: dict[str, set[str]] = {}
        for key, task in local.items():
            location = f"{path}/{key}".strip("/")
            if not isinstance(key, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", key):
                raise DefinitionError(f"Invalid compiled task key {key!r}")
            _fields(
                task,
                {
                    "taskInfo",
                    "componentRef",
                    "inputs",
                    "dependentTasks",
                    "cachingOptions",
                    "triggerPolicy",
                    "retryPolicy",
                },
                location,
            )
            _fields(task.get("taskInfo", {}), {"name"}, location + ".taskInfo")
            _fields(task.get("componentRef", {}), {"name"}, location + ".componentRef")
            ref = task.get("componentRef", {}).get("name")
            if ref not in components:
                raise DefinitionError(f"{location}: unknown component {ref!r}")
            if ref in stack:
                raise DefinitionError(f"{location}: recursive component cycle")
            trigger = task.get("triggerPolicy", {})
            _fields(trigger, {"condition", "strategy"}, location + ".triggerPolicy")
            if trigger.get("strategy", "ALL_UPSTREAM_TASKS_SUCCEEDED") not in {
                "ALL_UPSTREAM_TASKS_SUCCEEDED",
                0,
            }:
                raise UnsupportedCapability(
                    f"{location}: exit handlers/alternate trigger strategies are unsupported"
                )
            if trigger.get("condition"):
                evaluate_condition(trigger["condition"], {}, validate_only=True)
            _fields(
                task.get("cachingOptions", {}),
                {"enableCache", "cacheKey"},
                location + ".cachingOptions",
            )
            _booleans(
                task.get("cachingOptions", {}),
                ("enableCache",),
                location + ".cachingOptions",
            )
            if task.get("cachingOptions", {}).get("cacheKey"):
                raise UnsupportedCapability(
                    f"{location}: explicit upstream cache keys are unsupported"
                )
            retry = task.get("retryPolicy", {})
            _fields(
                retry,
                {
                    "maxRetryCount",
                    "backoffDuration",
                    "backoffFactor",
                    "backoffMaxDuration",
                },
                location + ".retryPolicy",
            )
            count = retry.get("maxRetryCount", 0)
            if type(count) is not int or not 0 <= count <= 3:
                raise UnsupportedCapability(
                    f"{location}: at most 3 retries are supported"
                )
            factor = retry.get("backoffFactor", 2)
            if (
                type(factor) not in {int, float}
                or not math.isfinite(factor)
                or factor < 1
            ):
                raise DefinitionError(
                    f"{location}.backoffFactor: finite value at least 1 required"
                )
            for duration in ("backoffDuration", "backoffMaxDuration"):
                value = retry.get(duration, "0s")
                if (
                    not re.fullmatch(r"\d+(?:\.\d+)?s", str(value))
                    or float(str(value)[:-1]) > 300
                ):
                    raise UnsupportedCapability(
                        f"{location}.{duration}: duration must be 0..300 seconds"
                    )
            inputs = task.get("inputs", {})
            _fields(inputs, {"parameters", "artifacts"}, location + ".inputs")
            deps = set(task.get("dependentTasks", []))
            child = components[ref]
            for input_kind in ("parameters", "artifacts"):
                contracts = child.get("inputDefinitions", {}).get(input_kind, {})
                for input_name, binding in inputs.get(input_kind, {}).items():
                    # KFP injects parameter channels used by f-string bindings.
                    if input_name not in contracts and not (
                        input_kind == "parameters"
                        and input_name.startswith("pipelinechannel--")
                    ):
                        raise DefinitionError(
                            f"{location}: unknown {input_kind} input {input_name}"
                        )
                    allowed = (
                        {
                            "componentInputParameter",
                            "taskOutputParameter",
                            "runtimeValue",
                        }
                        if input_kind == "parameters"
                        else {"componentInputArtifact", "taskOutputArtifact"}
                    )
                    _fields(binding, allowed, f"{location}.inputs.{input_name}")
                    if len(binding) != 1:
                        raise DefinitionError(
                            f"{location}.{input_name}: exactly one input source required"
                        )
                    source_key = next(iter(binding))
                    source = binding[source_key]
                    if source_key.startswith("taskOutput"):
                        _fields(
                            source,
                            {"producerTask", "outputParameterKey", "outputArtifactKey"},
                            location + ".source",
                        )
                        producer = source.get("producerTask")
                        if producer not in local:
                            raise DefinitionError(
                                f"{location}: unknown producer {producer!r}"
                            )
                        producer_component = components.get(
                            local[producer].get("componentRef", {}).get("name"), {}
                        )
                        output_name = source.get(
                            "outputParameterKey", source.get("outputArtifactKey")
                        )
                        if output_name not in producer_component.get(
                            "outputDefinitions", {}
                        ).get(input_kind, {}):
                            raise DefinitionError(
                                f"{location}: unknown output {producer}.{output_name}"
                            )
                        if input_name in contracts:
                            _compatible_contract(
                                producer_component["outputDefinitions"][input_kind][
                                    output_name
                                ],
                                contracts[input_name],
                                input_kind,
                                f"{location}.{input_name}",
                            )
                        deps.add(producer)
                    elif source_key.startswith("componentInput"):
                        if source not in component.get("inputDefinitions", {}).get(
                            input_kind, {}
                        ):
                            raise DefinitionError(
                                f"{location}: unknown parent input {source}"
                            )
                        if input_name in contracts:
                            _compatible_contract(
                                component["inputDefinitions"][input_kind][source],
                                contracts[input_name],
                                input_kind,
                                f"{location}.{input_name}",
                            )
                    elif source_key == "runtimeValue":
                        _fields(source, {"constant"}, location + ".runtimeValue")
                        if input_name in contracts:
                            validate_parameter(
                                source.get("constant"),
                                contracts[input_name],
                                f"{location}.{input_name}",
                                compiled=True,
                            )
                for input_name, contract in contracts.items():
                    if (
                        input_name not in inputs.get(input_kind, {})
                        and "defaultValue" not in contract
                        and not contract.get("isOptional")
                    ):
                        raise DefinitionError(
                            f"{location}: missing required input {input_name}"
                        )
            if not deps <= local.keys():
                raise DefinitionError(f"{location}: unknown dependency")
            dependencies[key] = deps
            is_conditional = conditional or bool(trigger.get("condition"))
            tasks[location] = TaskSpec(
                location,
                ref,
                child,
                task,
                tuple(path.split("/")) if path else (),
                is_conditional,
            )
            visit(child, location, (*stack, ref), is_conditional)
        pending = dict(dependencies)
        while pending:
            ready = [key for key, deps in pending.items() if not deps & pending.keys()]
            if not ready:
                raise DefinitionError(f"{path or 'root'}: task dependency cycle")
            for key in ready:
                del pending[key]
        _validate_dag_outputs(
            dag.get("outputs", {}),
            local,
            components,
            path or "root",
            component.get("outputDefinitions", {}),
        )

    visit(root, "", ())
    if "executorLabel" in root:
        tasks["root"] = TaskSpec("root", "root", root, {}, ())
    definition = Definition(
        raw,
        document,
        hashlib.sha256(raw).hexdigest(),
        "pipeline" if "dag" in root else "component",
        name,
        tasks,
    )
    _validate_placeholders(definition)
    return definition


def _compatible_contract(
    producer: dict[str, Any], consumer: dict[str, Any], kind: str, location: str
) -> None:
    if kind == "parameters":
        compatible = producer.get("parameterType") == consumer.get("parameterType")
    else:
        required = consumer.get("artifactType", {})
        compatible = (
            required.get("schemaTitle") == "system.Artifact"
            or producer.get("artifactType") == required
        )
    if not compatible:
        raise DefinitionError(
            f"{location}: incompatible producer/consumer {kind} contracts"
        )


def _validate_dag_outputs(
    outputs: dict[str, Any],
    tasks: dict[str, Any],
    components: dict[str, Any],
    location: str,
    contracts: dict[str, Any],
) -> None:
    _fields(outputs, {"parameters", "artifacts"}, location + ".outputs")
    for kind in ("parameters", "artifacts"):
        if set(outputs.get(kind, {})) != set(contracts.get(kind, {})):
            raise DefinitionError(
                f"{location}: DAG {kind} outputs differ from the declared contract"
            )
    for kind, values in outputs.items():
        for name, output in values.items():
            allowed = (
                {"valueFromParameter", "valueFromOneof"}
                if kind == "parameters"
                else {"artifactSelectors"}
            )
            _fields(output, allowed, f"{location}.outputs.{name}")
            if kind == "artifacts":
                selectors = output.get("artifactSelectors", [])
            elif "valueFromOneof" in output:
                selectors = output["valueFromOneof"].get("parameterSelectors", [])
            else:
                selectors = [output.get("valueFromParameter", {})]
            for selector in selectors:
                _fields(
                    selector,
                    {
                        "producerSubtask",
                        "outputArtifactKey",
                        "outputParameterKey",
                        "condition",
                    },
                    f"{location}.selector",
                )
                producer = selector.get("producerSubtask")
                if producer not in tasks:
                    raise DefinitionError(
                        f"{location}: output selector names unknown producer {producer}"
                    )
                child = components[tasks[producer]["componentRef"]["name"]]
                output_key = selector.get(
                    "outputArtifactKey", selector.get("outputParameterKey")
                )
                if output_key not in child.get("outputDefinitions", {}).get(kind, {}):
                    raise DefinitionError(
                        f"{location}: output selector names unknown output {output_key}"
                    )
                _compatible_contract(
                    child["outputDefinitions"][kind][output_key],
                    contracts[kind][name],
                    kind,
                    f"{location}.{name}",
                )
                if selector.get("condition"):
                    evaluate_condition(selector["condition"], {}, validate_only=True)


def _validate_placeholders(definition: Definition) -> None:
    fixed = {
        "{{$}}",
        "{{$.outputs.output_file}}",
        "{{$.outputMetadataUri}}",
        "{{$.pipeline_job_name}}",
        "{{$.pipeline_job_uuid}}",
        "{{$.pipeline_task_name}}",
        "{{$.pipeline_task_uuid}}",
        "{{$.pipeline_root}}",
    }
    for task in definition.tasks.values():
        if not task.executor_label:
            continue
        executor = definition.document["deploymentSpec"]["executors"][
            task.executor_label
        ]
        container = executor.get("container", {})
        for text in [*container.get("command", []), *container.get("args", [])]:
            for placeholder in re.findall(r"\{\{.*?\}\}", text):
                if placeholder in fixed:
                    continue
                match = re.fullmatch(
                    r"\{\{\$\.(inputs|outputs)\.(parameters|artifacts)\['([^']+)'\](?:\.(path|uri|metadata|output_file))?(?:\['([^']+)'\])?\}\}",
                    placeholder,
                )
                if not match:
                    raise UnsupportedCapability(
                        f"{task.name}: unsupported placeholder {placeholder}"
                    )
                direction, kind, name, suffix, metadata_key = match.groups()
                if metadata_key and suffix != "metadata":
                    raise UnsupportedCapability(
                        f"{task.name}: only artifact metadata keys are supported"
                    )
                contracts = task.component.get(
                    "inputDefinitions"
                    if direction == "inputs"
                    else "outputDefinitions",
                    {},
                ).get(kind, {})
                if name not in contracts and not (
                    kind == "parameters" and name.startswith("pipelinechannel--")
                ):
                    raise DefinitionError(
                        f"{task.name}: placeholder refers to undeclared {name}"
                    )
                if kind == "artifacts" and suffix not in {"path", "uri", "metadata"}:
                    raise DefinitionError(
                        f"{task.name}: artifact placeholder requires path, uri or metadata"
                    )


def validate_parameters(
    definition: Definition, values: dict[str, Any] | None = None
) -> dict[str, Any]:
    values = values or {}
    if not isinstance(values, dict):
        raise DefinitionError("parameters must be an object")
    contracts = definition.root.get("inputDefinitions", {}).get("parameters", {})
    if unknown := set(values) - contracts.keys():
        raise DefinitionError(
            f"Unknown pipeline parameters: {', '.join(sorted(unknown))}"
        )
    result: dict[str, Any] = {}
    for name, contract in contracts.items():
        if name in values:
            result[name] = validate_parameter(values[name], contract, name)
        elif "defaultValue" in contract:
            result[name] = validate_parameter(
                contract["defaultValue"], contract, name, compiled=True
            )
        elif not contract.get("isOptional"):
            raise DefinitionError(f"Missing required pipeline parameter: {name}")
    return result


def validate_selection(
    definition: Definition, selection: dict[str, Any] | None = None
) -> set[str]:
    selection = selection or {"mode": "full"}
    mode = selection.get("mode", "full")
    if mode == "full":
        _fields(selection, {"mode"}, "selection")
        return set(definition.tasks)
    if any(t.conditional for t in definition.tasks.values()):
        raise UnsupportedCapability(
            "Partial selections crossing conditional graph boundaries are unsupported"
        )
    _fields(
        selection,
        {"mode", "task"} if mode == "from" else {"mode", "tasks"},
        "selection",
    )
    selected = [selection.get("task")] if mode == "from" else selection.get("tasks", [])
    if (
        mode not in {"from", "tasks"}
        or not isinstance(selected, list)
        or not selected
        or len(set(selected)) != len(selected)
    ):
        raise DefinitionError("Invalid task selection")
    selected_names: list[str] = []
    for item in selected:
        if not isinstance(item, str):
            raise DefinitionError("Task selectors must be strings")
        selected_names.append(item)
    if set(selected_names) - definition.tasks.keys():
        raise DefinitionError("Selection names an unknown qualified task path")
    result = set(selected_names)
    # Selecting a DAG invokes its descendants, preserving native nested semantics.
    for name in selected_names:
        result.update(path for path in definition.tasks if path.startswith(name + "/"))
    if mode == "from":
        changed = True
        while changed:
            changed = False
            for name, task in definition.tasks.items():
                prefix = name.rsplit("/", 1)[0] + "/" if "/" in name else ""
                deps = set(task.task.get("dependentTasks", []))
                for mapping in task.task.get("inputs", {}).values():
                    for binding in mapping.values():
                        for source in binding.values():
                            if isinstance(source, dict) and source.get("producerTask"):
                                deps.add(source["producerTask"])
                if name not in result and any(prefix + dep in result for dep in deps):
                    result.add(name)
                    result.update(
                        path for path in definition.tasks if path.startswith(name + "/")
                    )
                    changed = True
    return result


# A small parsed CEL subset: input scalar references, scalar literals, conversions,
# comparison, parentheses, !, && and ||. No expression is evaluated as Python.
_TOKEN = re.compile(
    r"\s*(inputs\.parameter_values\[(?:'[^'\\]*'|\"[^\"\\]*\")\]|(?:int|double|string|bool)\b|true\b|false\b|null\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|==|!=|<=|>=|&&|\|\||[!<>()])"
)


def evaluate_condition(
    expression: str, parameters: dict[str, Any], *, validate_only: bool = False
) -> bool:
    if not isinstance(expression, str) or len(expression) > 65536:
        raise UnsupportedCapability("Unsupported scalar condition")
    tokens: list[str] = []
    offset = 0
    while offset < len(expression):
        match = _TOKEN.match(expression, offset)
        if not match:
            if expression[offset:].strip():
                raise UnsupportedCapability(
                    f"Unsupported condition expression at {expression[offset : offset + 40]!r}"
                )
            break
        tokens.append(match.group(1))
        offset = match.end()
    index = 0

    def take() -> str:
        nonlocal index
        if index >= len(tokens):
            raise DefinitionError("Incomplete condition expression")
        value = tokens[index]
        index += 1
        return value

    def atom() -> Any:
        token = take()
        if token == "!":
            return not atom()
        if token == "(":
            value = logical_or()
            if take() != ")":
                raise DefinitionError("Unbalanced condition parentheses")
            return value
        if token in {"int", "double", "string", "bool"}:
            if take() != "(":
                raise DefinitionError("Invalid scalar conversion")
            value = atom()
            if take() != ")":
                raise DefinitionError("Invalid scalar conversion")
            if validate_only:
                return 0
            # Compiler-generated casts describe the declared scalar type only.
            return {"int": int, "double": float, "string": str, "bool": bool}[token](
                value
            )
        if token.startswith("inputs."):
            key = token[token.index("[") + 2 : -2]
            if not validate_only and key not in parameters:
                raise DefinitionError(f"Condition refers to missing parameter {key}")
            return parameters.get(key, 0)
        if token in {"true", "false", "null"}:
            return {"true": True, "false": False, "null": None}[token]
        if token.startswith(('"', "'")):
            # YAML's safe scalar parser provides string escaping without eval.
            value = yaml.safe_load(token)
            if not isinstance(value, str):
                raise DefinitionError("Invalid scalar string")
            return value
        try:
            return float(token) if any(c in token for c in ".eE") else int(token)
        except ValueError as exc:
            raise DefinitionError("Invalid condition scalar") from exc

    def comparison() -> Any:
        nonlocal index
        left = atom()
        if index < len(tokens) and tokens[index] in {"==", "!=", "<", "<=", ">", ">="}:
            operator = take()
            right = atom()
            if validate_only:
                return False
            if type(left) is bool or type(right) is bool:
                if type(left) is not type(right):
                    raise DefinitionError("Condition scalar types do not match")
            try:
                if operator == "==":
                    return left == right
                if operator == "!=":
                    return left != right
                if operator == "<":
                    return left < right
                if operator == "<=":
                    return left <= right
                if operator == ">":
                    return left > right
                return left >= right
            except TypeError as exc:
                raise DefinitionError("Incompatible condition operands") from exc
        return left

    def logical_and() -> Any:
        value = comparison()
        while index < len(tokens) and tokens[index] == "&&":
            take()
            right = comparison()
            value = bool(value) and bool(right)
        return value

    def logical_or() -> Any:
        value = logical_and()
        while index < len(tokens) and tokens[index] == "||":
            take()
            right = logical_and()
            value = bool(value) or bool(right)
        return value

    result = logical_or()
    if index != len(tokens):
        raise UnsupportedCapability("Unsupported trailing condition expression")
    if not validate_only and type(result) is not bool:
        raise DefinitionError("A condition must produce a boolean")
    return bool(result)
