"""Serial execution of a plan derived exclusively from accepted native KFP IR."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dockflow_database.errors import DockflowError

from .cache import Lease, wait_for_resolution
from .cache_registry import Registry, cache_error
from .cache_storage import make_manifest
from .canonical import digest, loads
from .definitions import (
    Definition,
    DefinitionError,
    TaskSpec,
    evaluate_condition,
    load_definition,
    validate_parameter,
    validate_parameters,
    validate_selection,
)
from .execution_choices import ExecutionChoices
from .executor import ContainerFailed, ExecutionStopped, KFPAdapter, resource_limits
from .lifecycle import stop_reason
from .reuse import candidates, resolve_policy, task_signature


def _id(kind: str) -> str:
    return kind + "_" + str(uuid.uuid4())


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _error(exc: BaseException, phase: str) -> dict[str, Any]:
    return {
        "code": getattr(exc, "code", type(exc).__name__),
        "message": str(exc),
        "phase": phase,
    }


def _type(contract: dict[str, Any]) -> dict[str, str]:
    typ = contract.get("artifactType", contract)
    return {
        "schema_title": typ.get("schemaTitle", typ.get("schema_title")),
        "schema_version": typ.get("schemaVersion", typ.get("schema_version", "0.0.1")),
    }


def _check_type(
    descriptor: dict[str, Any], contract: dict[str, Any], name: str
) -> None:
    expected = _type(contract)
    actual = descriptor["type"]
    # system.Artifact is the KFP generic supertype. Concrete contracts remain exact.
    if expected["schema_title"] != "system.Artifact" and actual != expected:
        raise DefinitionError(
            f"Artifact input {name} has type {actual}, expected {expected}"
        )


def _ordering_dependencies(task: dict[str, Any]) -> set[str]:
    data = set()
    for mapping in task.get("inputs", {}).values():
        for binding in mapping.values():
            for source in binding.values():
                if isinstance(source, dict) and source.get("producerTask"):
                    data.add(source["producerTask"])
    return set(task.get("dependentTasks", [])) - data


class _Execution:
    def __init__(
        self,
        store: Any,
        artifacts: Any,
        settings: Any,
        run: dict[str, Any],
        on_log: Callable[[str, str], None] | None = None,
    ):
        self.choices = ExecutionChoices.from_record(run.get("execution_choices"))
        settings = self.choices.bind(settings)
        self.store, self.artifacts, self.settings, self.run = (
            store,
            artifacts,
            settings,
            run,
        )
        document = run.get("pipeline_spec")
        if document is None:
            record = store.get("definitions", run["definition_id"])
            document = record["pipeline_spec"]
        self.definition: Definition = load_definition(document)
        self.selected = validate_selection(self.definition, run.get("selection"))
        self.records: dict[str, dict[str, Any]] = {}
        self.started = time.monotonic()
        self.deadline = settings.execution.get("timeout_seconds", 0)
        self.pipeline_root = settings.work_directory / "runs" / run["run_id"]
        self.workspace = settings.work_directory / "workspaces" / run["run_id"]
        self.adapter: KFPAdapter | None = None
        self.on_log = on_log
        self.policies = self._policies()
        self.sequence = 0
        self.failed = False
        self.stop_reason: str | None = None
        self.cache_registry: Registry | None = None
        self.cache_owner = str(uuid.uuid4())
        self.cache_lease: Lease | None = None
        self.cache_deadline: float | None = None

    def _policies(self) -> dict[str, Any]:
        return self.choices.task_policies

    def put(self, kind: str, record: dict[str, Any]) -> None:
        stored = self.store.put(kind, record)
        if kind == "runs":
            record.update(stored)
            if reason := stop_reason(stored):
                self.stop_reason = reason

    def stop(self) -> str | None:
        if self.settings.state_storage["backend"] == "postgresql":
            if reason := self.store.check_execution():
                return reason
        if self.stop_reason:
            return self.stop_reason
        current = self.store.get("runs", self.run["run_id"])
        if (
            current.get("interruption_requested")
            or current.get("state") == "interrupted"
        ):
            self.stop_reason = "interrupted"
        elif current.get("cancellation_requested") or current.get("state") in {
            "cancelling",
            "cancelled",
        }:
            self.stop_reason = "cancelled"
        elif self.deadline and time.monotonic() - self.started >= self.deadline:
            self.stop_reason = "deadline_exceeded"
        if self.stop_reason:
            self.store.append(
                "stop_intent",
                {"run_id": self.run["run_id"], "reason": self.stop_reason},
            )
        return self.stop_reason

    def make_task(self, spec: TaskSpec) -> dict[str, Any]:
        record = {
            "task_id": _id("task"),
            "run_id": self.run["run_id"],
            "name": spec.name,
            "component_id": self.run.get("component_ids", {}).get(spec.component_key),
            "definition_id": self.run["definition_id"],
            "state": "pending",
            "inputs": {},
            "outputs": {},
            "parameters": {},
            "output_parameters": {},
            "attempt_ids": [],
            "reuse": None,
            "error": None,
            "created_at": _now(),
        }
        self.records[spec.name] = record
        self.put("tasks", record)
        self.run.setdefault("task_ids", []).append(record["task_id"])
        self.put("runs", self.run)
        return record

    def log(self, attempt: dict[str, Any], stream: str, text: str) -> None:
        # The owner assigns a durable journal sequence. Per-stream order remains
        # intact; separate Docker streams do not imply cross-stream ordering.
        self.store.log(
            self.run["run_id"],
            text,
            stream=stream,
            task_id=attempt["task_id"],
            attempt_id=attempt["attempt_id"],
        )
        if self.on_log is not None:
            self.on_log(stream, text)

    def request_interruption(self) -> None:
        if self.stop_reason == "interrupted":
            return
        self.stop_reason = "interrupted"
        self.store.append(
            "stop_intent",
            {"run_id": self.run["run_id"], "reason": "interrupted"},
        )
        self.run["interruption_requested"] = True
        self.put("runs", self.run)

    def skip(self, name: str, reason: str) -> None:
        for path, record in self.records.items():
            if path == name or path.startswith(name + "/"):
                record.update(state="skipped", disposition=reason)
                self.put("tasks", record)

    def dependencies(self, task: dict[str, Any]) -> set[str]:
        result = set(task.get("dependentTasks", []))
        for mapping in task.get("inputs", {}).values():
            for binding in mapping.values():
                for source in binding.values():
                    if isinstance(source, dict) and source.get("producerTask"):
                        result.add(source["producerTask"])
        return result

    def arguments(
        self,
        task: dict[str, Any],
        component: dict[str, Any],
        parent: dict[str, dict[str, Any]],
        results: dict[str, dict[str, dict[str, Any]]],
        path: str,
    ) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {"parameters": {}, "artifacts": {}}
        for kind in ("parameters", "artifacts"):
            contracts = component.get("inputDefinitions", {}).get(kind, {})
            supplied = task.get("inputs", {}).get(kind, {})
            for name in set(contracts) | set(supplied):
                manual = (
                    self.run.get("bindings", {}).get(path + "." + name)
                    if kind == "artifacts"
                    else None
                )
                if manual:
                    value = manual
                elif name in supplied:
                    binding = supplied[name]
                    if "runtimeValue" in binding:
                        value = binding["runtimeValue"]["constant"]
                        if name in contracts:
                            value = validate_parameter(
                                value, contracts[name], path + "." + name, compiled=True
                            )
                    elif (
                        "componentInputParameter" in binding
                        or "componentInputArtifact" in binding
                    ):
                        source = binding.get(
                            "componentInputParameter",
                            binding.get("componentInputArtifact"),
                        )
                        if source not in parent[kind]:
                            if contracts.get(name, {}).get("isOptional"):
                                continue
                            raise DefinitionError(
                                f"{path}.{name}: parent input {source} is missing"
                            )
                        value = parent[kind][source]
                    else:
                        source = binding.get(
                            "taskOutputParameter", binding.get("taskOutputArtifact")
                        )
                        producer = source["producerTask"]
                        output_key = source.get(
                            "outputParameterKey", source.get("outputArtifactKey")
                        )
                        try:
                            value = results[producer][kind][output_key]
                        except KeyError as exc:
                            raise DefinitionError(
                                f"{path}.{name}: omitted/inactive prerequisite {producer}.{output_key}; supply a binding or compatible historical producer"
                            ) from exc
                elif "defaultValue" in contracts[name]:
                    value = validate_parameter(
                        contracts[name]["defaultValue"],
                        contracts[name],
                        path + "." + name,
                        compiled=True,
                    )
                elif contracts[name].get("isOptional"):
                    continue
                else:
                    raise DefinitionError(f"{path}.{name}: required input is missing")
                if kind == "artifacts":
                    _check_type(
                        self.artifacts.get(value), contracts[name], path + "." + name
                    )
                result[kind][name] = value
        return result

    def reusable(
        self,
        signature: dict[str, Any],
        component: dict[str, Any],
        record: dict[str, Any],
        *,
        explicit: str | None = None,
        planned: dict[str, Any] | None = None,
    ) -> dict[str, dict[str, Any]] | None:
        fixed = explicit or (planned or {}).get("attempt_id")
        if fixed:
            possible = [self.store.get("attempts", fixed)]
        else:
            possible = candidates(
                self.store.query(
                    "attempts",
                    filters={
                        "signature.value": signature["value"],
                        "state": "succeeded",
                    },
                ),
                signature,
            )
        rejections = []
        contracts = component.get("outputDefinitions", {})
        for attempt in possible:
            if (
                planned
                and not explicit
                and attempt.get("signature", {}).get("value") != signature["value"]
            ):
                rejections.append(
                    {
                        "attempt_id": attempt["attempt_id"],
                        "reason": "accepted_producer_signature_changed",
                    }
                )
                continue
            integrity = self.store.verify_output_set(attempt["attempt_id"])
            if not integrity["valid"]:
                rejections.append(
                    {"attempt_id": attempt["attempt_id"], "reason": integrity["reason"]}
                )
                continue
            if (
                attempt.get("state") != "succeeded"
                or attempt.get("publication_state") != "committed"
            ):
                rejections.append(
                    {
                        "attempt_id": attempt["attempt_id"],
                        "reason": "not_committed_success",
                    }
                )
                continue
            output_ids = attempt.get("outputs", {})
            params = attempt.get("output_parameters", {})
            if set(output_ids) != set(contracts.get("artifacts", {})) or set(
                params
            ) != set(contracts.get("parameters", {})):
                rejections.append(
                    {
                        "attempt_id": attempt["attempt_id"],
                        "reason": "output_contract_differs",
                    }
                )
                continue
            try:
                for name, artifact_id in output_ids.items():
                    descriptor = self.artifacts.get(artifact_id)
                    _check_type(descriptor, contracts["artifacts"][name], name)
                    observation = self.artifacts.verify(artifact_id)
                    if observation.get("availability") != "available":
                        raise DefinitionError(
                            "Artifact is " + observation.get("availability", "unknown")
                        )
                for name, value in params.items():
                    validate_parameter(value, contracts["parameters"][name], name)
            except Exception as exc:
                rejections.append(
                    {"attempt_id": attempt["attempt_id"], "reason": str(exc)}
                )
                continue
            record.update(
                outputs=output_ids,
                output_parameters=params,
                state="reused",
                disposition="manual" if explicit else "reused",
                reuse={
                    "producer_attempt_id": attempt["attempt_id"],
                    "reason": "manual_historical_input"
                    if explicit
                    else "equivalent_committed_result",
                    "rejections": rejections,
                },
            )
            self.put("tasks", record)
            return {"parameters": params, "artifacts": output_ids}
        record["reuse"] = {
            "rejections": rejections,
            "reason": "no_compatible_available_result",
        }
        if fixed:
            raise DefinitionError(
                "Accepted historical producer is unavailable or no longer satisfies the exact task contract"
            )
        return None

    def registry(self) -> Registry:
        if self.cache_registry is None:
            options = self.settings.cache
            options = {
                **options,
                "storage_token": self.artifacts.storage_identity(),
            }
            self.cache_registry = Registry(options, self.settings.project_id)
            self.cache_registry.initialize()
        return self.cache_registry

    def primitive(self, spec, arguments, record):
        self.cache_deadline = None
        while True:
            self.cache_lease = None
            retry_shared = False
            try:
                return self._primitive(spec, arguments, record)
            except BaseException as exc:
                if self.cache_lease is not None:
                    registry = self.registry()
                    storage_unavailable = (
                        isinstance(exc, DockflowError)
                        and exc.code == "ARTIFACT_UNAVAILABLE"
                    )
                    retry_shared = isinstance(exc, ContainerFailed) and record.get(
                        "policy", {}
                    ).get("retry_safe", False)
                    try:
                        registry.finish_failed(
                            self.cache_lease.ownership,
                            "PRODUCER_CANCELLED"
                            if isinstance(exc, ExecutionStopped | KeyboardInterrupt)
                            else "EXECUTION_FAILED"
                            if isinstance(exc, ContainerFailed)
                            else "ARTIFACT_UNAVAILABLE"
                            if storage_unavailable
                            else "VALIDATION_FAILED",
                            retryable=retry_shared
                            or storage_unavailable
                            or isinstance(exc, ExecutionStopped | KeyboardInterrupt),
                            cancelled=isinstance(
                                exc, ExecutionStopped | KeyboardInterrupt
                            ),
                        )
                    except DockflowError as failure:
                        if failure.code != "OWNERSHIP_LOST":
                            raise failure from exc
                if not retry_shared:
                    if (
                        isinstance(exc, DockflowError)
                        and exc.code == "CACHE_CANCELLED"
                        and (reason := self.stop())
                    ):
                        raise ExecutionStopped(reason) from exc
                    raise
            finally:
                if self.cache_lease is not None:
                    self.cache_lease.__exit__(None, None, None)
            # The next claim observes the persisted shared budget/cooldown.

    def _resolve_cache(self, signature, spec, record, *, allow_claim=True):
        registry = self.registry()
        if self.cache_deadline is None:
            self.cache_deadline = time.monotonic() + registry.options["wait_seconds"]
        key = signature["value"]

        def waiting(result):
            if record.get("disposition") != "cache_wait":
                record.update(
                    disposition="cache_wait",
                    cache={
                        "key": key,
                        "scope_id": registry.scope_id,
                        "reason": result.reason,
                    },
                )
                self.put("tasks", record)

        while True:
            result, started = wait_for_resolution(
                registry,
                key,
                self.cache_owner,
                self.run["run_id"],
                record["task_id"],
                self.stop,
                waiting,
                deadline=self.cache_deadline,
                allow_claim=allow_claim,
            )
            if result.kind == "MISS":
                return None
            if result.kind == "PRODUCE":
                assert result.ownership is not None
                self.cache_lease = Lease(registry, result.ownership, started)
                self.cache_lease.__enter__()
                self.cache_lease.check()
                record["cache"] = {
                    "key": key,
                    "scope_id": registry.scope_id,
                    "attempt_id": result.ownership.attempt_id,
                    "fence": result.ownership.fencing_token,
                }
                return None
            artifact = result.artifact
            assert artifact is not None
            manifest = artifact["manifest"]
            if (
                digest(manifest) != artifact["manifest_digest"]
                or manifest["signature"] != key
                or manifest["contract"] != spec.component.get("outputDefinitions", {})
            ):
                raise cache_error(
                    "CACHE_CONFLICT", "Cache manifest or output contract differs"
                )
            try:
                descriptors = self.artifacts.verify_cache(
                    manifest, registry.options["storage_identity"]
                )
            except DockflowError as exc:
                if exc.code != "CACHE_CORRUPT":
                    raise
                registry.event("validation_failure", key, reason="CACHE_CORRUPT")
                try:
                    registry.invalidate(
                        key, artifact["artifact_id"], "CONFIRMED_MISSING_OR_CORRUPT"
                    )
                except DockflowError as conflict:
                    if conflict.code != "CACHE_CONFLICT":
                        raise
                continue
            producer = self.store.import_cache_result(manifest, descriptors)
            record.update(
                outputs=producer["outputs"],
                output_parameters=producer["output_parameters"],
                state="reused",
                disposition="reused",
                reuse={
                    "producer_attempt_id": producer["attempt_id"],
                    "reason": "verified_registry_artifact",
                    "rejections": [],
                },
                cache={
                    "key": key,
                    "scope_id": registry.scope_id,
                    "artifact_id": artifact["artifact_id"],
                    "manifest_digest": artifact["manifest_digest"],
                },
            )
            self.put("tasks", record)
            registry.event("hit", key, attempt_id=producer["attempt_id"])
            return {
                "parameters": producer["output_parameters"],
                "artifacts": producer["outputs"],
            }

    def _primitive(
        self,
        spec: TaskSpec,
        arguments: dict[str, dict[str, Any]],
        record: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        self.store.ensure_reconciled()
        if reason := self.stop():
            raise ExecutionStopped(reason)
        executor = self.definition.document["deploymentSpec"]["executors"][
            spec.executor_label
        ]
        policy = resolve_policy(
            self.settings.reuse,
            self.run.get("reuse"),
            self.policies.get(spec.name),
            run_id=self.run["run_id"],
        )
        record.update(
            inputs=arguments["artifacts"],
            parameters=arguments["parameters"],
            policy=policy,
        )
        if "importer" in executor:
            return self.importer(spec, arguments, record, executor["importer"])
        assert self.adapter is not None
        image = self.adapter.resolve_image(executor["container"]["image"])
        limits = resource_limits(executor["container"], self.settings.execution)
        input_descriptors = {
            name: self.artifacts.get(artifact_id)
            for name, artifact_id in arguments["artifacts"].items()
        }
        signature = task_signature(
            project_id=self.settings.project_id,
            component=spec.component,
            executor=executor,
            parameters=arguments["parameters"],
            artifacts=input_descriptors,
            image=image,
            policy=policy,
            resources=limits,
        )
        record["signature"] = signature
        # Missing cache policy follows the pinned KFP 2.17 default: disabled.
        enabled = spec.task.get("cachingOptions", {}).get("enableCache", False)
        can_reuse = enabled and policy["cache_safe"] and policy["scope"] != "none"
        explicit = self.run.get("use_executions", {}).get(spec.name)
        planned = (
            self.run.get("resolved_plan", {})
            .get("resolved_prerequisites", {})
            .get(spec.name)
            if spec.name not in self.selected
            else None
        )
        if planned and not explicit:
            # A preflight historical choice does not override later registry
            # invalidation, replacement or freshness expiry.
            view = self.registry().inspect(signature["value"])
            selected = next(
                (
                    item
                    for item in view["artifacts"]
                    if item["artifact_id"] == view["entry"]["published_artifact_id"]
                ),
                None,
            )
            if (
                not selected
                or selected["producer_attempt_id"] != planned.get("attempt_id")
                or selected["state"] != "AVAILABLE"
                or (
                    selected["valid_until"] is not None
                    and selected["valid_until"] <= view["registry_now"]
                )
            ):
                raise DefinitionError(
                    "Accepted historical cache producer is no longer eligible"
                )
        if explicit or planned:
            if reused := self.reusable(
                signature, spec.component, record, explicit=explicit, planned=planned
            ):
                return reused
        if can_reuse:
            reused = self._resolve_cache(
                signature, spec, record, allow_claim=spec.name in self.selected
            )
            if reused is not None:
                return reused
        if spec.name not in self.selected:
            record.update(state="skipped", disposition="omitted", error=None)
            self.put("tasks", record)
            return {"parameters": {}, "artifacts": {}}
        retry = spec.task.get("retryPolicy", {})
        count = retry.get("maxRetryCount", 0)
        if count and not policy["retry_safe"]:
            raise DefinitionError(
                f"{spec.name}: automatic retry requires a definition-keyed retry_safe policy"
            )
        if self.cache_lease is not None:
            count = 0  # Registry episodes, rather than nested Run-local budgets.
        for ordinal in range(count + 1):
            attempt = {
                "attempt_id": self.cache_lease.ownership.attempt_id
                if self.cache_lease
                else _id("attempt"),
                "run_id": self.run["run_id"],
                "task_id": record["task_id"],
                "state": "running",
                "created_at": _now(),
                "started_at": _now(),
                "finished_at": None,
                "image": image,
                "signature": signature,
                "parameters": arguments["parameters"],
                "inputs": arguments["artifacts"],
                "outputs": {},
                "output_parameters": {},
                "publication_state": "uncommitted",
                "exit_status": None,
                "error": None,
                "logs_reference": {"run_id": self.run["run_id"], "attempt_id": None},
            }
            attempt["logs_reference"]["attempt_id"] = attempt["attempt_id"]
            record["attempt_ids"].append(attempt["attempt_id"])
            record.update(state="running", disposition="executed")
            self.put("attempts", attempt)
            self.put("tasks", record)
            phase = "materialization"
            staged: dict[str, Any] = dict(arguments["parameters"])
            staged_paths: dict[str, Path] = {}
            try:
                for name, descriptor in input_descriptors.items():
                    destination = (
                        self.pipeline_root / "inputs" / attempt["attempt_id"] / name
                    )
                    self.artifacts.materialize(descriptor["artifact_id"], destination)
                    staged_paths[name] = destination
                    attempt.setdefault("materializations", {})[name] = {
                        "artifact_id": descriptor["artifact_id"],
                        "canonical_uri": descriptor.get("content_uri"),
                        "runtime_uri": str(destination),
                        "path": str(destination),
                    }
                    staged[name] = self.adapter.artifact(descriptor, destination)
                phase = "execution"

                def created(
                    observation: dict[str, Any], attempt: dict[str, Any] = attempt
                ) -> None:
                    attempt.update(observation)
                    self.put("attempts", attempt)

                outputs, observation = self.adapter.run_task(
                    component=spec.component,
                    executor=executor,
                    arguments=staged,
                    attempt_id=attempt["attempt_id"],
                    task_name=spec.name,
                    image=image,
                    resources=limits,
                    labels={
                        "dockflow.project": self.settings.project_id,
                        "dockflow.run": self.run["run_id"],
                        "dockflow.task": record["task_id"],
                        "dockflow.attempt": attempt["attempt_id"],
                    },
                    on_created=created,
                    on_log=lambda stream, text, attempt=attempt: self.log(
                        attempt, stream, text
                    ),
                    should_stop=lambda: self.stop()
                    or (self.cache_lease.should_stop() if self.cache_lease else None),
                    on_interrupt=self.request_interruption,
                    shutdown_grace=self.settings.execution.get(
                        "shutdown_grace_seconds", 30
                    ),
                )
                attempt.update(observation)
                phase = "validation"
                if self.cache_lease is not None:
                    self.cache_lease.check()
                    self.registry().begin_validation(self.cache_lease.ownership)
                # Tasks get isolated copies, then consistency is checked before
                # accepting any outputs. No hard links into published inputs.
                from .artifacts import inventory

                for name, path in staged_paths.items():
                    if input_descriptors[name].get("payload_kind") == "metadata":
                        continue
                    observed = inventory(path)
                    expected = input_descriptors[name]["fingerprint"]
                    actual = (
                        observed.get("fingerprint", observed)
                        if isinstance(observed, dict)
                        else None
                    )
                    if actual != expected:
                        raise DefinitionError(f"Task modified immutable input {name}")
                contracts = spec.component.get("outputDefinitions", {})
                parameters = {
                    name: validate_parameter(
                        outputs[name], contract, spec.name + "." + name
                    )
                    for name, contract in contracts.get("parameters", {}).items()
                }
                phase = "publication"
                attempt.update(state="publishing")
                self.put("attempts", attempt)
                published = {}
                for name, contract in contracts.get("artifacts", {}).items():
                    artifact = outputs[name]
                    path = Path(artifact.path)
                    typ = _type(contract)
                    if (
                        typ["schema_title"]
                        in {"system.Metrics", "system.ClassificationMetrics"}
                        and not path.exists()
                    ):
                        path = None
                    published[name] = self.artifacts.publish(
                        path,
                        typ,
                        {
                            "pipeline_name": self.definition.name,
                            "task_name": spec.name.rsplit("/", 1)[-1],
                            "run_id": self.run["run_id"],
                            "task_id": record["task_id"],
                            "attempt_id": attempt["attempt_id"],
                            "definition_id": self.run["definition_id"],
                            "output_name": name,
                            **(
                                {"cache_namespace": "cache-v1"}
                                if self.cache_lease
                                else {}
                            ),
                        },
                        metadata=artifact.metadata,
                    )
                if reason := self.stop():
                    raise ExecutionStopped(reason)
                if self.cache_lease is not None:
                    self.cache_lease.check()
                    registry = self.registry()
                    manifest = make_manifest(
                        published,
                        parameters,
                        contracts,
                        {
                            "run_id": self.run["run_id"],
                            "task_id": record["task_id"],
                            "attempt_id": attempt["attempt_id"],
                            "finished_at": _now(),
                        },
                        signature["value"],
                        registry.options["storage_identity"],
                    )
                    # The store verifies sealed bytes before the registry can
                    # select this descriptor. No database transaction spans I/O.
                    self.artifacts.verify_cache(
                        manifest, registry.options["storage_identity"]
                    )
                    self.cache_lease.check()
                    committed_cache = self.store.publish_cache_result(
                        registry.options, self.cache_lease.ownership, manifest
                    )
                    for descriptor in published.values():
                        descriptor["cache_origin"] = {
                            "artifact_id": committed_cache["artifact_id"],
                            "manifest_digest": committed_cache["manifest_digest"],
                            "producer_attempt_id": attempt["attempt_id"],
                        }
                        self.store.put("artifacts", descriptor)
                phase = "commit"
                self.store.commit_output_set(
                    self.run["run_id"],
                    record["task_id"],
                    attempt["attempt_id"],
                    published,
                    parameters,
                )
                output_ids = {
                    name: descriptor["artifact_id"]
                    for name, descriptor in published.items()
                }
                attempt.update(
                    state="succeeded",
                    publication_state="committed",
                    outputs=output_ids,
                    output_parameters=parameters,
                    finished_at=_now(),
                )
                self.put("attempts", attempt)
                record.update(
                    state="succeeded", outputs=output_ids, output_parameters=parameters
                )
                self.put("tasks", record)
                return {"parameters": parameters, "artifacts": output_ids}
            except BaseException as exc:
                # Once committed, recovery reconciles this attempt; computation
                # is never repeated because a projection write failed.
                if phase == "commit":
                    if self.store.has_output_set(attempt["attempt_id"]):
                        attempt.update(
                            reconciliation_required=True, error=_error(exc, phase)
                        )
                        self.put("attempts", attempt)
                        raise
                    if reason := self.stop():
                        exc = ExecutionStopped(reason)
                if not isinstance(exc, KeyboardInterrupt) and (reason := self.stop()):
                    exc = ExecutionStopped(reason)
                if isinstance(exc, KeyboardInterrupt):
                    self.request_interruption()
                    confirmed = self.adapter.stop(
                        self.settings.execution.get("shutdown_grace_seconds", 30)
                    )
                    exc = ExecutionStopped("interrupted", confirmed=confirmed)
                elif phase == "execution" and not isinstance(
                    exc, ContainerFailed | ExecutionStopped | DefinitionError
                ):
                    if not self.adapter.stop(
                        self.settings.execution.get("shutdown_grace_seconds", 30)
                    ):
                        exc = ExecutionStopped(str(exc), confirmed=False)
                state = "failed"
                if isinstance(exc, ExecutionStopped):
                    state = "cancelled" if exc.reason == "cancelled" else "interrupted"
                    if exc.reason == "deadline_exceeded":
                        state = "failed"
                    attempt["reconciliation_required"] = not exc.confirmed
                attempt.update(
                    state=state, error=_error(exc, phase), finished_at=_now()
                )
                if isinstance(exc, ContainerFailed):
                    attempt["exit_status"] = exc.exit_code
                self.put("attempts", attempt)
                if ordinal < count and isinstance(exc, ContainerFailed):
                    cap = min(
                        float(str(retry.get("backoffMaxDuration", "300s"))[:-1]), 300
                    )
                    duration = min(
                        float(str(retry.get("backoffDuration", "0s"))[:-1]), cap
                    )
                    # Clamp each multiplication to avoid exponent overflow,
                    # including zero-duration retries with a large valid factor.
                    for _ in range(ordinal):
                        duration = min(
                            duration * float(retry.get("backoffFactor", 2)), cap
                        )
                    until = time.monotonic() + duration
                    while time.monotonic() < until:
                        if reason := self.stop():
                            raise ExecutionStopped(reason) from exc
                        time.sleep(min(0.2, max(0, until - time.monotonic())))
                    continue
                record.update(state=state, error=attempt["error"])
                self.put("tasks", record)
                raise exc
        raise AssertionError("Unreachable retry exhaustion")

    def importer(
        self,
        spec: TaskSpec,
        arguments: dict[str, dict[str, Any]],
        record: dict[str, Any],
        importer: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        if spec.name not in self.selected:
            record.update(state="skipped", disposition="omitted")
            self.put("tasks", record)
            return {"parameters": {}, "artifacts": {}}
        binding = importer["artifactUri"]
        uri = binding.get(
            "constant", arguments["parameters"].get(binding.get("runtimeParameter"))
        )
        if not isinstance(uri, str):
            raise DefinitionError(f"{spec.name}: importer URI is missing")
        typ = _type(importer.get("typeSchema", {}))
        metadata = importer.get("metadata", {})
        # An importer can bind an existing managed result without inventing an
        # external producer. URI equality only nominates a candidate: verify its
        # committed content and contract before preserving its logical identity.
        descriptor = None
        source_artifact_id = None
        if not importer.get("reimport", False):
            registered = sorted(
                self.artifacts.list(),
                key=lambda item: (item.get("created_at", ""), item["artifact_id"]),
                reverse=True,
            )
            for candidate in registered:
                if (
                    candidate.get("content_uri") != uri
                    or candidate.get("type") != typ
                    or candidate.get("publication_state") != "committed"
                    or metadata
                    and candidate.get("metadata") != metadata
                ):
                    continue
                if (
                    self.artifacts.verify(candidate["artifact_id"]).get("availability")
                    == "available"
                ):
                    descriptor = candidate
                    source_artifact_id = candidate["artifact_id"]
                    break
        if descriptor is None:
            # A mutable external URI must be fingerprinted afresh before matching
            # a previously registered snapshot. Changed bytes get a new identity.
            descriptor = self.artifacts.register(
                uri, typ, metadata=metadata, managed=False
            )
            if not importer.get("reimport", False):
                matching = [
                    item
                    for item in self.artifacts.list()
                    if item["artifact_id"] != descriptor["artifact_id"]
                    and item.get("source_uri") == uri
                    and item.get("fingerprint") == descriptor["fingerprint"]
                    and item.get("type") == typ
                    and item.get("metadata") == metadata
                    and item.get("publication_state") == "committed"
                ]
                if matching:
                    matching.sort(
                        key=lambda item: (
                            item.get("created_at", ""),
                            item["artifact_id"],
                        )
                    )
                    descriptor = matching[-1]
                    source_artifact_id = descriptor["artifact_id"]
        names = list(spec.component.get("outputDefinitions", {}).get("artifacts", {}))
        if len(names) != 1:
            raise DefinitionError("Importer requires exactly one output artifact")
        outputs = {names[0]: descriptor["artifact_id"]}
        record.update(
            state="succeeded",
            disposition="imported",
            outputs=outputs,
            import_event={
                "source_uri": uri,
                "source_artifact_id": source_artifact_id,
                "reimport": importer.get("reimport", False),
            },
        )
        self.put("tasks", record)
        return {"parameters": {}, "artifacts": outputs}

    def graph(
        self,
        component: dict[str, Any],
        parent: dict[str, dict[str, Any]],
        prefix: str = "",
    ) -> dict[str, dict[str, Any]]:
        tasks = component["dag"].get("tasks", {})
        pending = set(tasks)
        results: dict[str, dict[str, dict[str, Any]]] = {}
        while pending:
            ready = sorted(
                name for name in pending if not self.dependencies(tasks[name]) & pending
            )
            if not ready:
                raise DefinitionError("No runnable task: dependency cycle")
            for name in ready[:1]:
                path = prefix + name
                spec = self.definition.tasks[path]
                record = self.records[path]
                if reason := self.stop():
                    raise ExecutionStopped(reason)
                # Explicit after edges need a real successful producer even when
                # omitted inputs are manually supplied.
                needed = path in self.selected or any(
                    item.startswith(path + "/") for item in self.selected
                )
                for prerequisite in _ordering_dependencies(spec.task) if needed else ():
                    producer_record = self.records[prefix + prerequisite]
                    if producer_record["state"] not in {"succeeded", "reused"}:
                        raise DefinitionError(
                            f"{path}: ordering prerequisite {prefix + prerequisite} is not satisfied"
                        )
                try:
                    try:
                        arguments = self.arguments(
                            spec.task, spec.component, parent, results, path
                        )
                    except DefinitionError:
                        if needed:
                            raise
                        self.skip(path, "omitted")
                        results[name] = {"parameters": {}, "artifacts": {}}
                        pending.remove(name)
                        continue
                    condition = spec.task.get("triggerPolicy", {}).get("condition")
                    if condition and not evaluate_condition(
                        condition, arguments["parameters"]
                    ):
                        self.skip(path, "inactive_branch")
                        results[name] = {"parameters": {}, "artifacts": {}}
                    elif "dag" in spec.component:
                        record.update(
                            state="running",
                            inputs=arguments["artifacts"],
                            parameters=arguments["parameters"],
                        )
                        self.put("tasks", record)
                        results[name] = self.graph(
                            spec.component, arguments, path + "/"
                        )
                        record.update(
                            state="succeeded",
                            disposition="graph",
                            outputs=results[name]["artifacts"],
                            output_parameters=results[name]["parameters"],
                        )
                        self.put("tasks", record)
                    else:
                        results[name] = self.primitive(spec, arguments, record)
                except BaseException as exc:
                    if record["state"] in {"pending", "running"}:
                        record.update(state="failed", error=_error(exc, "planning"))
                        self.put("tasks", record)
                    raise
                pending.remove(name)
        resolved: dict[str, dict[str, Any]] = {"parameters": {}, "artifacts": {}}
        for kind, outputs in component["dag"].get("outputs", {}).items():
            for name, output in outputs.items():
                if kind == "artifacts":
                    selectors = output.get("artifactSelectors", [])
                elif "valueFromOneof" in output:
                    selectors = output["valueFromOneof"].get("parameterSelectors", [])
                else:
                    selectors = [output["valueFromParameter"]]
                selected = []
                for selector in selectors:
                    if selector.get("condition") and not evaluate_condition(
                        selector["condition"], parent["parameters"]
                    ):
                        continue
                    values = results[selector["producerSubtask"]][kind]
                    key = selector.get(
                        "outputParameterKey", selector.get("outputArtifactKey")
                    )
                    if key in values:
                        selected.append(values[key])
                if len(selected) == 1:
                    resolved[kind][name] = selected[0]
                elif len(selected) > 1:
                    raise DefinitionError(
                        f"{prefix}{name}: multiple active OneOf producers"
                    )
                elif self.run.get("selection", {}).get("mode", "full") == "full":
                    raise DefinitionError(
                        f"{prefix}{name}: required graph output has no active producer"
                    )
        return resolved

    def execute(self) -> dict[str, Any]:
        self.store.ensure_reconciled()
        self.run.update(state="running", started_at=_now())
        self.put("runs", self.run)
        for spec in self.definition.tasks.values():
            self.make_task(spec)
        try:
            self.adapter = KFPAdapter(
                self.pipeline_root,
                self.workspace,
                pull_policy=self.settings.images.get("pull_policy", "if-missing"),
            )
            self.adapter.load(self.definition.document)
            root = {
                "parameters": validate_parameters(
                    self.definition, self.run.get("parameters", {})
                ),
                "artifacts": self.run.get("inputs", {}),
            }
            if self.definition.kind == "component":
                outputs = self.primitive(
                    self.definition.tasks["root"], root, self.records["root"]
                )
            else:
                outputs = self.graph(self.definition.root, root)
            self.run.update(
                state="succeeded",
                outputs=outputs["artifacts"],
                output_parameters=outputs["parameters"],
                error=None,
            )
        except BaseException as exc:
            if isinstance(exc, KeyboardInterrupt):
                self.store.append(
                    "stop_intent",
                    {"run_id": self.run["run_id"], "reason": "interrupted"},
                )
                self.stop_reason = "interrupted"
                if self.adapter is not None and not self.adapter.stop(
                    self.settings.execution.get("shutdown_grace_seconds", 30)
                ):
                    self.run["reconciliation_required"] = True
            state = "failed"
            if isinstance(exc, ExecutionStopped):
                state = "cancelled" if exc.reason == "cancelled" else "interrupted"
                if exc.reason == "deadline_exceeded":
                    state = "failed"
                self.run["reconciliation_required"] = not exc.confirmed
            elif isinstance(exc, KeyboardInterrupt):
                state = "interrupted"
            self.run.update(state=state, error=_error(exc, "execution"))
            if any(
                attempt.get("reconciliation_required")
                for attempt in self.store.query(
                    "attempts",
                    filters={
                        "run_id": self.run["run_id"],
                        "reconciliation_required": True,
                    },
                )
            ):
                self.run["reconciliation_required"] = True
        finally:
            if self.adapter is not None:
                self.adapter.close()
            self.run["finished_at"] = _now()
            self.run.update(self.store.finish_run(self.run))
        return self.run


def execute_run(
    store: Any,
    artifacts: Any,
    settings: Any,
    run: dict[str, Any],
    *,
    on_log: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    from .metadata import ControlStore

    def execute():
        try:
            execution = _Execution(store, artifacts, settings, run, on_log=on_log)
        except (DockflowError, DefinitionError, ValueError) as exc:
            return store.finish_run(
                {
                    **run,
                    "state": "failed",
                    "finished_at": _now(),
                    "error": _error(exc, "execution_configuration"),
                }
            )
        return execution.execute()

    if isinstance(store, ControlStore):
        with store.run_owner(run["run_id"], settings.execution):
            return execute()
    return execute()


def validate_invocation(
    definition: Definition,
    request: dict[str, Any],
    settings: Any,
    store: Any,
    artifacts: Any,
) -> dict[str, Any]:
    """Preflight bindings, policy safety and static omitted prerequisites.

    This function never creates a Run or work directory. Docker image preflight
    is needed only when historical results must satisfy an omitted computation.
    It returns the chosen prerequisite producers for immutable admission evidence.
    """
    selected = validate_selection(definition, request.get("selection"))
    parameters = validate_parameters(definition, request.get("parameters", {}))
    root_artifacts = definition.root.get("inputDefinitions", {}).get("artifacts", {})
    inputs = request.get("inputs", {})
    if set(inputs) - root_artifacts.keys():
        raise DefinitionError("Unknown root artifact input")
    for name, contract in root_artifacts.items():
        if name not in inputs:
            if contract.get("isOptional"):
                continue
            raise DefinitionError(f"Missing root artifact input: {name}")
        descriptor = artifacts.get(inputs[name])
        _check_type(descriptor, contract, name)
        if artifacts.verify(inputs[name]).get("availability") != "available":
            raise DefinitionError(f"Root artifact input {name} is unavailable")
    for selector, artifact_id in request.get("bindings", {}).items():
        if "." not in selector:
            raise DefinitionError("Artifact bindings require TASK.INPUT")
        task, name = selector.rsplit(".", 1)
        if task not in definition.tasks:
            raise DefinitionError(f"Unknown task binding: {task}")
        contract = (
            definition.tasks[task]
            .component.get("inputDefinitions", {})
            .get("artifacts", {})
            .get(name)
        )
        if contract is None:
            raise DefinitionError(f"Unknown artifact binding: {selector}")
        _check_type(artifacts.get(artifact_id), contract, selector)
        if artifacts.verify(artifact_id).get("availability") != "available":
            raise DefinitionError(f"Artifact binding {selector} is unavailable")
    policy_tasks = {}
    if file := settings.policies.get("file"):
        policy = loads(Path(file).read_text())
        if (
            set(policy) - {"schema_version", "definition_sha256", "tasks"}
            or policy.get("schema_version") != 1
            or policy.get("definition_sha256") != definition.sha256
        ):
            raise DefinitionError(
                "Invalid or stale definition-keyed local policies file"
            )
        policy_tasks = policy.get("tasks", {})
    policies = {}
    for task, policy in policy_tasks.items():
        if task not in definition.tasks or set(policy) - {
            "scope",
            "scope_key",
            "cache_safe",
            "retry_safe",
        }:
            raise DefinitionError(f"Invalid task policy: {task}")
        if any(
            name in policy and type(policy[name]) is not bool
            for name in ("cache_safe", "retry_safe")
        ):
            raise DefinitionError(f"{task}: cache_safe/retry_safe must be booleans")
    for name, spec in definition.tasks.items():
        policies[name] = resolve_policy(
            settings.reuse, request.get("reuse"), policy_tasks.get(name)
        )
        if (
            spec.task.get("retryPolicy", {}).get("maxRetryCount", 0)
            and not policies[name]["retry_safe"]
        ):
            raise DefinitionError(
                f"{name}: automatic retry requires a definition-keyed retry_safe policy"
            )
    explicit = request.get("use_executions", {})
    if set(explicit) - definition.tasks.keys():
        raise DefinitionError("Unknown task in use_executions")
    resolved = {}

    def check_attempt(
        attempt: dict[str, Any], spec: TaskSpec
    ) -> dict[str, dict[str, Any]]:
        integrity = store.verify_output_set(attempt["attempt_id"])
        if not integrity["valid"]:
            raise DefinitionError(
                "Historical output-set integrity failed: " + integrity["reason"]
            )
        contracts = spec.component.get("outputDefinitions", {})
        output_ids, values = (
            attempt.get("outputs", {}),
            attempt.get("output_parameters", {}),
        )
        if (
            attempt.get("state") != "succeeded"
            or attempt.get("publication_state") != "committed"
        ):
            raise DefinitionError(
                "Historical producer is not a committed successful attempt"
            )
        if set(output_ids) != set(contracts.get("artifacts", {})) or set(values) != set(
            contracts.get("parameters", {})
        ):
            raise DefinitionError("Historical producer output contract differs")
        for name, artifact_id in output_ids.items():
            _check_type(artifacts.get(artifact_id), contracts["artifacts"][name], name)
            if artifacts.verify(artifact_id).get("availability") != "available":
                raise DefinitionError(
                    "Historical producer has unavailable/corrupt output"
                )
        for name, value in values.items():
            validate_parameter(value, contracts["parameters"][name], name)
        return {"parameters": values, "artifacts": output_ids}

    for name, attempt_id in explicit.items():
        if "dag" in definition.tasks[name].component:
            raise DefinitionError("use_executions requires a primitive task path")
        if any(
            selector.rsplit(".", 1)[0] == name
            for selector in request.get("bindings", {})
        ):
            raise DefinitionError(
                "use_executions conflicts with explicit bindings on the same task"
            )
        check_attempt(store.get("attempts", attempt_id), definition.tasks[name])
        resolved[name] = {"attempt_id": attempt_id, "reason": "manual_historical_input"}
    if request.get("selection", {}).get("mode", "full") == "full":
        return {
            "selected_tasks": sorted(selected),
            "resolved_prerequisites": resolved,
            "task_policies": policy_tasks,
        }

    # A placeholder represents a value that will be produced in this new Run.
    # It can flow through selected tasks, but cannot assert a historical result
    # for an omitted computation whose actual invocation is not yet known.
    class Pending:
        pass

    adapter: KFPAdapter | None = None

    def graph(
        component: dict[str, Any], parent: dict[str, dict[str, Any]], prefix: str = ""
    ) -> dict[str, dict[str, Any]]:
        nonlocal adapter
        tasks = component["dag"].get("tasks", {})
        pending = set(tasks)
        results = {}
        successful = set()
        while pending:
            ready = sorted(
                name for name in pending if not dependencies(tasks[name]) & pending
            )
            if not ready:
                raise DefinitionError("Cyclic partial selection")
            for name in ready[:1]:
                path = prefix + name
                spec = definition.tasks[path]
                needed = path in selected or any(
                    item.startswith(path + "/") for item in selected
                )
                args: dict[str, dict[str, Any]] = {"parameters": {}, "artifacts": {}}
                unavailable = False
                for kind in ("parameters", "artifacts"):
                    contracts = spec.component.get("inputDefinitions", {}).get(kind, {})
                    for input_name, contract in contracts.items():
                        try:
                            binding = (
                                tasks[name]
                                .get("inputs", {})
                                .get(kind, {})
                                .get(input_name, {})
                            )
                            manual = (
                                request.get("bindings", {}).get(path + "." + input_name)
                                if kind == "artifacts"
                                else None
                            )
                            if manual:
                                value = manual
                            elif "runtimeValue" in binding:
                                value = validate_parameter(
                                    binding["runtimeValue"]["constant"],
                                    contract,
                                    path + "." + input_name,
                                    compiled=True,
                                )
                            elif (
                                "componentInputParameter" in binding
                                or "componentInputArtifact" in binding
                            ):
                                value = parent[kind][
                                    binding.get(
                                        "componentInputParameter",
                                        binding.get("componentInputArtifact"),
                                    )
                                ]
                            elif (
                                "taskOutputParameter" in binding
                                or "taskOutputArtifact" in binding
                            ):
                                source = binding.get(
                                    "taskOutputParameter",
                                    binding.get("taskOutputArtifact"),
                                )
                                value = results[source["producerTask"]][kind][
                                    source.get(
                                        "outputParameterKey",
                                        source.get("outputArtifactKey"),
                                    )
                                ]
                            elif "defaultValue" in contract:
                                value = validate_parameter(
                                    contract["defaultValue"],
                                    contract,
                                    input_name,
                                    compiled=True,
                                )
                            elif contract.get("isOptional"):
                                continue
                            else:
                                raise KeyError(input_name)
                            args[kind][input_name] = value
                        except KeyError:
                            unavailable = True
                            if needed:
                                raise DefinitionError(
                                    f"{path}.{input_name}: unresolved omitted prerequisite"
                                ) from None
                controls = _ordering_dependencies(tasks[name])
                if needed and any(
                    dep not in successful and prefix + dep not in selected
                    for dep in controls
                ):
                    raise DefinitionError(
                        f"{path}: omitted ordering prerequisite has no compatible successful producer"
                    )
                output: dict[str, dict[str, Any]] = {"parameters": {}, "artifacts": {}}
                if path in explicit:
                    output = check_attempt(store.get("attempts", explicit[path]), spec)
                    successful.add(name)
                elif "dag" in spec.component:
                    output = graph(spec.component, args, path + "/")
                    if needed:
                        successful.add(name)
                elif needed:
                    output = {
                        kind: {
                            key: Pending()
                            for key in spec.component.get("outputDefinitions", {}).get(
                                kind, {}
                            )
                        }
                        for kind in ("parameters", "artifacts")
                    }
                    successful.add(name)
                elif not unavailable and not any(
                    isinstance(value, Pending)
                    for mapping in args.values()
                    for value in mapping.values()
                ):
                    executor = definition.document["deploymentSpec"]["executors"][
                        spec.executor_label
                    ]
                    policy = policies[path]
                    if (
                        "container" in executor
                        and policy["scope"] not in {"none", "run"}
                        and policy["cache_safe"]
                        and spec.task.get("cachingOptions", {}).get(
                            "enableCache", False
                        )
                    ):
                        if adapter is None:
                            adapter = KFPAdapter(
                                settings.work_directory / "preflight",
                                settings.work_directory / "preflight-workspace",
                                pull_policy=settings.images.get(
                                    "pull_policy", "if-missing"
                                ),
                                initialize=False,
                            )
                        signature = task_signature(
                            project_id=settings.project_id,
                            component=spec.component,
                            executor=executor,
                            parameters=args["parameters"],
                            artifacts={
                                key: artifacts.get(value)
                                for key, value in args["artifacts"].items()
                            },
                            image=adapter.resolve_image(executor["container"]["image"]),
                            policy=policy,
                            resources=resource_limits(
                                executor["container"], settings.execution
                            ),
                        )
                        for attempt in candidates(
                            store.query(
                                "attempts",
                                filters={
                                    "signature.value": signature["value"],
                                    "state": "succeeded",
                                },
                            ),
                            signature,
                        ):
                            try:
                                output = check_attempt(attempt, spec)
                            except DefinitionError:
                                continue
                            resolved[path] = {
                                "attempt_id": attempt["attempt_id"],
                                "reason": "equivalent_committed_result",
                            }
                            successful.add(name)
                            break
                results[name] = output
                pending.remove(name)
        output = {"parameters": {}, "artifacts": {}}
        for kind, values in component["dag"].get("outputs", {}).items():
            for name, source in values.items():
                selectors = (
                    source.get("artifactSelectors", [])
                    if kind == "artifacts"
                    else [source.get("valueFromParameter", {})]
                )
                for selector in selectors:
                    key = selector.get(
                        "outputParameterKey", selector.get("outputArtifactKey")
                    )
                    value = (
                        results.get(selector.get("producerSubtask"), {})
                        .get(kind, {})
                        .get(key)
                    )
                    if value is not None:
                        output[kind][name] = value
        return output

    def dependencies(task: dict[str, Any]) -> set[str]:
        values = set(task.get("dependentTasks", []))
        for mapping in task.get("inputs", {}).values():
            for source in mapping.values():
                for value in source.values():
                    if isinstance(value, dict) and value.get("producerTask"):
                        values.add(value["producerTask"])
        return values

    try:
        if definition.kind == "pipeline":
            graph(definition.root, {"parameters": parameters, "artifacts": inputs})
    finally:
        if adapter:
            adapter.close()
    return {
        "selected_tasks": sorted(selected),
        "resolved_prerequisites": resolved,
        "task_policies": policy_tasks,
    }
