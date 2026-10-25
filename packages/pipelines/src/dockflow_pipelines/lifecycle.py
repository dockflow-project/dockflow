"""Pure control-intent and terminal Task transitions for normal/recovered Runs."""

from dockflow_core.errors import DockflowError

IMMUTABLE_RUN_FIELDS = {
    "definition_id",
    "experiment_id",
    "pipeline_spec",
    "source_text",
    "definition_sha256",
    "component_ids",
    "parameters",
    "inputs",
    "selection",
    "bindings",
    "use_executions",
    "reuse",
    "effective_configuration",
    "execution_choices",
    "selected_tasks",
    "resolved_plan",
    "idempotency_key",
    "request_digest",
    "submitted_request_digest",
    "acceptance_sequence",
    "created_at",
}
TASK_TERMINAL = {
    "succeeded",
    "failed",
    "cancelled",
    "interrupted",
    "blocked",
    "reused",
    "skipped",
}


def stop_reason(run):
    if run.get("interruption_requested") or run.get("state") == "interrupted":
        return "interrupted"
    if run.get("cancellation_requested") or run.get("state") in {
        "cancelling",
        "cancelled",
    }:
        return "cancelled"
    return None


def merge_run(current, proposed):
    result = dict(proposed)
    for field in IMMUTABLE_RUN_FIELDS:
        if field in current:
            if field in proposed and proposed[field] != current[field]:
                raise DockflowError(
                    f"Accepted Run field is immutable: {field}", "CONFLICT", 409
                )
            result[field] = current[field]
    for field in ("cancellation_requested", "interruption_requested", "stop_intent"):
        if current.get(field):
            result[field] = current[field]
    reason = stop_reason(current)
    if reason:
        if result.get("state") in {"running", "queued"}:
            result["state"] = "cancelling"
        elif result.get("state") == "succeeded":
            result["state"] = reason
    return result


def terminal_task(task, attempts, outcome, *, recovering=False):
    if task.get("state") in TASK_TERMINAL:
        return None
    if outcome == "succeeded":
        return None
    latest = max(
        attempts,
        key=lambda item: (
            item.get("finished_at") or item.get("started_at") or "",
            item["attempt_id"],
        ),
        default=None,
    )
    if (
        latest
        and latest.get("state") == "succeeded"
        and latest.get("publication_state") == "committed"
    ):
        return {
            **task,
            "state": "succeeded",
            "disposition": "executed",
            "outputs": latest.get("outputs", {}),
            "output_parameters": latest.get("output_parameters", {}),
            "reconciliation_required": False,
            "error": None,
        }
    state = (
        "blocked"
        if task.get("state") == "pending"
        else latest["state"]
        if latest and latest.get("state") in {"failed", "cancelled", "interrupted"}
        else "interrupted"
        if recovering
        else outcome
    )
    return {
        **task,
        "state": state,
        "reconciliation_required": any(
            item.get("reconciliation_required") for item in attempts
        ),
        "error": task.get("error")
        or {"reason": "worker_lost" if recovering else "upstream_stopped"},
    }
