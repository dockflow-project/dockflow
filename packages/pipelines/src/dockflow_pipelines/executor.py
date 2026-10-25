"""The version-specific KFP DockerRunner adapter.

KFP owns compiled loading, native executor input, placeholder and output mechanics.
The narrow Docker transport hook retains exited containers and records their ID
before start, instead of upstream's auto-remove/assume-success implementation.
This module is imported only for execution and imports runtime extras lazily.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from .container_logs import ContainerLogs
from .definitions import (
    DefinitionError,
    UnsupportedCapability,
    resource_value,
    validate_parameter,
)


class ExecutionStopped(RuntimeError):
    def __init__(self, reason: str, *, confirmed: bool = True):
        super().__init__(reason)
        self.reason = reason
        self.confirmed = confirmed


class ContainerFailed(RuntimeError):
    def __init__(self, exit_code: int):
        super().__init__(f"Container exited with status {exit_code}")
        self.exit_code = exit_code


class KFPAdapter:
    """One process-local adapter. Owners must isolate concurrent Runs by process."""

    def __init__(
        self,
        pipeline_root: Path,
        workspace_root: Path,
        *,
        pull_policy: str = "if-missing",
        initialize: bool = True,
    ):
        try:
            import docker
            import kfp
            from docker.errors import APIError, ImageNotFound
            from kfp import local
        except ImportError as exc:
            raise RuntimeError(
                "Install dockflow-pipelines[runtime] for local Docker execution"
            ) from exc
        if not kfp.__version__.startswith("2.17."):
            raise UnsupportedCapability(
                "This adapter requires the qualified KFP 2.17 minor line"
            )
        self.docker = docker
        self.api_error = APIError
        self.image_not_found = ImageNotFound
        self.local = local
        self.pipeline_root = pipeline_root.resolve()
        self.workspace_root = workspace_root.resolve()
        self.pull_policy = pull_policy
        self.client = docker.from_env()
        try:
            self.daemon = self.client.info()
        except Exception:
            self.client.close()
            raise
        if initialize:
            self.pipeline_root.mkdir(parents=True, exist_ok=True)
            self.workspace_root.mkdir(parents=True, exist_ok=True)
            self.local.init(
                runner=local.DockerRunner(),
                pipeline_root=str(self.pipeline_root),
                workspace_root=str(self.workspace_root),
                raise_on_error=True,
            )
        self.images: dict[str, dict[str, Any]] = {}
        self.active_container = None

    def close(self) -> None:
        self.client.close()

    def stop(self, grace: int = 30) -> bool:
        container = self.active_container
        if container is None:
            return True
        try:
            container.reload()
            if container.attrs.get("State", {}).get("Running"):
                try:
                    container.stop(timeout=grace)
                except self.api_error:
                    container.kill()
            container.reload()
            return not container.attrs.get("State", {}).get("Running", False)
        except Exception:
            return False

    def load(self, document: dict[str, Any]) -> None:
        from kfp.components import load_component_from_text

        # The upstream compiled-component path handles both root graphs and
        # primitive compiled components without importing their authoring code.
        loader_view = dict(document)
        # Protobuf's absent map is empty. The 2.17 loader indexes this optional
        # map directly even for a root primitive, so supply its schema default.
        loader_view.setdefault("components", {})
        self.loaded_component = load_component_from_text(json.dumps(loader_view))

    def resolve_image(self, reference: str) -> dict[str, Any]:
        if reference in self.images:
            return self.images[reference]
        if self.pull_policy == "always":
            image = self.client.images.pull(reference)
        else:
            try:
                image = self.client.images.get(reference)
            except self.image_not_found:
                if self.pull_policy == "never":
                    raise DefinitionError(
                        f"Image {reference!r} is unavailable with pull_policy=never"
                    ) from None
                image = self.client.images.pull(reference)
        attrs = image.attrs
        resolved = {
            "reference": reference,
            "image_id": image.id,
            "repo_digests": sorted(attrs.get("RepoDigests") or []),
            "os": attrs.get("Os", "linux"),
            "architecture": attrs.get("Architecture"),
            "variant": attrs.get("Variant"),
        }
        self.images[reference] = resolved
        return resolved

    def artifact(self, descriptor: dict[str, Any], path: Path) -> Any:
        from kfp.dsl import executor

        return executor.create_artifact_instance(
            {
                "name": descriptor["artifact_id"],
                "uri": str(path),
                "type": {
                    "schemaTitle": descriptor["type"]["schema_title"],
                    "schemaVersion": descriptor["type"].get("schema_version", "0.0.1"),
                },
                "metadata": descriptor.get("metadata", {}),
            }
        )

    def run_task(
        self,
        *,
        component: dict[str, Any],
        executor: dict[str, Any],
        arguments: dict[str, Any],
        attempt_id: str,
        task_name: str,
        image: dict[str, Any],
        labels: dict[str, str],
        resources: dict[str, Any],
        on_created: Callable[[dict[str, Any]], None],
        on_log: Callable[[str, str], None],
        should_stop: Callable[[], str | None],
        on_interrupt: Callable[[], None],
        shutdown_grace: int = 30,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        from google.protobuf import json_format
        from kfp.local import (
            docker_task_handler,
            executor_input_utils,
            placeholder_utils,
            task_dispatcher,
        )
        from kfp.pipeline_spec import pipeline_spec_pb2

        generated_schema: Any = pipeline_spec_pb2
        component_pb = json_format.ParseDict(
            component, generated_schema.ComponentSpec()
        )
        executor_pb = json_format.ParseDict(
            executor,
            generated_schema.PipelineDeploymentConfig.ExecutorSpec(),
        )
        executor_pb.container.image = image["image_id"]
        arguments = dict(arguments)
        task_resource = task_name.replace("/", "--")
        task_root = self.pipeline_root / attempt_id / task_resource
        task_root.mkdir(parents=True, exist_ok=True)
        preview = executor_input_utils.construct_executor_input(
            component_pb, arguments, str(task_root), False
        )
        preview_dict = executor_input_utils.executor_input_to_dict(
            preview, component_pb
        )
        for env in executor_pb.container.env:
            values = placeholder_utils.replace_placeholders(
                [env.value],
                preview_dict,
                attempt_id,
                task_resource,
                str(self.pipeline_root),
                attempt_id,
            )
            if len(values) != 1:
                raise UnsupportedCapability(
                    "Environment binding must resolve to one scalar string"
                )
            env.value = values[0]
        run_args: dict[str, Any] = {
            "labels": labels,
            "name": f"dockflow-{attempt_id}",
            "use_config_proxy": False,
        }
        run_args.update(
            {key: value for key, value in resources.items() if key != "dockflow_mounts"}
        )
        if "user" in resources and not any(
            env.name == "HOME" for env in executor_pb.container.env
        ):
            home = task_root / ".home"
            home.mkdir(parents=True, exist_ok=True)
            run_args["environment"] = {
                "HOME": str(home),
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            }
        runner = self.local.DockerRunner(**run_args)
        observation: dict[str, Any] = {
            "daemon_id": self.daemon.get("ID"),
            "image": image,
        }

        def transport(
            client: Any,
            image: str,
            command: list[str],
            volumes: dict[str, Any],
            **kwargs: Any,
        ) -> int:
            volumes = task_volumes(volumes, resources.get("dockflow_mounts", []))
            # create is deliberately separate from start: durable ownership and
            # recovery identity precede execution, even if the worker dies here.
            container = client.containers.create(
                image=image,
                command=command,
                volumes=volumes,
                auto_remove=False,
                **kwargs,
            )
            self.active_container = container
            observation["container_id"] = container.id
            observation["applied_resources"] = resources
            on_created(dict(observation))
            reason = should_stop()
            if reason:
                raise ExecutionStopped(reason)
            stopped_reason = None
            with ContainerLogs(container, on_log) as logs:
                container.start()
                try:
                    while True:
                        logs.pump(0.1)
                        container.reload()
                        state = container.attrs.get("State", {})
                        if state.get("Status") in {"exited", "dead"}:
                            break
                        reason = should_stop()
                        if reason:
                            stopped_reason = reason
                            try:
                                container.stop(timeout=shutdown_grace)
                            except self.api_error:
                                container.kill()
                            container.reload()
                            if container.attrs.get("State", {}).get("Running"):
                                raise ExecutionStopped(reason, confirmed=False)
                            break
                except KeyboardInterrupt:
                    # Drain the final diagnostics before propagating the signal
                    # to the engine's interruption/state transition boundary.
                    on_interrupt()
                    if self.stop(shutdown_grace):
                        logs.finish()
                    raise
                result = container.wait(timeout=max(shutdown_grace, 5))
                exit_code = result.get("StatusCode")
                if type(exit_code) is not int:
                    raise RuntimeError(
                        "Docker did not confirm a numeric container exit status"
                    )
                observation["exit_status"] = exit_code
                on_created(dict(observation))
                logs.finish()
            if stopped_reason:
                raise ExecutionStopped(stopped_reason)
            return exit_code

        # This patch is confined to the isolated worker process. KFP continues
        # dispatching through DockerTaskHandler and DockerRunner unchanged.
        with patch.object(docker_task_handler, "run_docker_container", transport):
            outputs, task_status = task_dispatcher.run_single_task_implementation(
                pipeline_resource_name=attempt_id,
                component_name="comp-" + task_name.replace("/", "--"),
                component_spec=component_pb,
                executor_spec=executor_pb,
                arguments=arguments,
                pipeline_root=str(self.pipeline_root),
                runner=cast(Any, runner),
                raise_on_error=False,
                block_input_artifact=False,
                unique_pipeline_id=attempt_id,
            )
        if observation.get("exit_status") != 0:
            raise ContainerFailed(observation.get("exit_status", -1))
        task_root = self.pipeline_root / attempt_id / task_name.replace("/", "--")
        output_contracts = component.get("outputDefinitions", {})
        output_file = task_root / "executor_output.json"
        from dockflow_core.canonical import loads

        wire = loads(output_file.read_text()) if output_file.exists() else {}
        wire_parameters = wire.get("parameterValues", {})
        declared_parameters = output_contracts.get("parameters", {})
        if set(wire_parameters) - declared_parameters.keys():
            raise DefinitionError("Executor returned undeclared output parameters")
        for name, contract in declared_parameters.items():
            parameter_file = task_root / name
            if parameter_file.exists():
                text = parameter_file.read_text()
                value = (
                    text
                    if contract["parameterType"] == "STRING"
                    else loads(
                        text.lower() if contract["parameterType"] == "BOOLEAN" else text
                    )
                )
            elif name in wire_parameters:
                value = wire_parameters[name]
            elif name in outputs:
                value = outputs[name]
            else:
                raise DefinitionError(f"Missing required output parameter {name}")
            outputs[name] = validate_parameter(
                value, contract, f"output.{name}", compiled=True
            )
        for name, contract in output_contracts.get("artifacts", {}).items():
            expected = task_root / name
            if name not in outputs:
                # Plain container components may write supplied OutputPath only.
                # KFP declares the artifact in ExecutorInput; it is still native
                # output even without a Python-generated ExecutorOutput entry.
                typ = contract["artifactType"]
                outputs[name] = self.artifact(
                    {
                        "artifact_id": name,
                        "type": {
                            "schema_title": typ["schemaTitle"],
                            "schema_version": typ.get("schemaVersion", "0.0.1"),
                        },
                        "metadata": {},
                    },
                    expected,
                )
            if Path(outputs[name].path).resolve() != expected.resolve():
                raise UnsupportedCapability(
                    f"Output {name} changed its supplied artifact path"
                )
        return outputs, observation


def resource_limits(
    container: dict[str, Any], configured: dict[str, Any]
) -> dict[str, Any]:
    """Map admitted KFP cores/decimal GB and configured byte caps to Docker."""
    resources = container.get("resources", {})
    cpu = configured.get("cpu_limit")
    memory = configured.get("memory_limit_bytes")
    for names in (
        ("cpuLimit", "resourceCpuLimit"),
        ("memoryLimit", "resourceMemoryLimit"),
    ):
        if all(name in resources for name in names):
            raise DefinitionError("Conflicting compiled resource aliases")
    for field in ("cpuLimit", "resourceCpuLimit"):
        if field in resources:
            value = resource_value(field, resources[field])
            cpu = min(float(cpu), value) if cpu is not None else value
    for field in ("memoryLimit", "resourceMemoryLimit"):
        if field in resources:
            value = int(resource_value(field, resources[field]))
            memory = min(int(memory), value) if memory is not None else value
    result: dict[str, Any] = {}
    if configured.get("task_mounts"):
        result["dockflow_mounts"] = configured["task_mounts"]
    # The single owner and trusted task processes share a writable POSIX
    # execution tree. Matching the owner's identity keeps files removable and
    # gives arbitrary prepared images the same direct/service path contract.
    if hasattr(os, "getuid") and hasattr(os, "getgid"):
        result["user"] = f"{os.getuid()}:{os.getgid()}"
    if cpu is not None:
        result["nano_cpus"] = int(float(cpu) * 1_000_000_000)
    if memory is not None:
        result["mem_limit"] = int(memory)
    return result


def task_volumes(
    supplied: dict[str, Any], mounts: list[dict[str, Any]]
) -> dict[str, Any]:
    """Merge owner-configured mounts without masking KFP execution paths."""
    from .artifacts import _no_links

    result = dict(supplied)
    destinations = [Path(value["bind"]) for value in supplied.values()]
    for mount in mounts:
        source, target = Path(mount["source"]), Path(mount["target"])
        _no_links(source)
        if not source.is_file() and not source.is_dir():
            raise DefinitionError(
                "Configured task mount source must exist as a regular file/directory: "
                f"{source}"
            )
        if str(source) in result or any(
            target == other or target in other.parents or other in target.parents
            for other in destinations
        ):
            raise DefinitionError(
                "Configured task mounts cannot overlap execution or other mount targets"
            )
        result[str(source)] = {
            "bind": str(target),
            "mode": "ro" if mount["read_only"] else "rw",
        }
        destinations.append(target)
    return result


def execute_run(
    store: Any, artifacts: Any, settings: Any, run: dict[str, Any]
) -> dict[str, Any]:
    """Public lazy boundary used by the core and its isolated service worker."""
    from .engine import execute_run as execute

    return execute(store, artifacts, settings, run)
