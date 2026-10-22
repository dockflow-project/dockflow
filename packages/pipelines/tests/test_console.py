"""Human presentation must preserve logs, persisted data and machine output."""

import contextlib
import io
import json
import logging

import pytest
from dockflow_pipelines.cli import app
from dockflow_pipelines.config import load_settings
from dockflow_pipelines.console import (
    LogPresentation,
    OutputMode,
    RunConsole,
    component_log,
    run_summary,
)
from dockflow_pipelines.core import Core
from test_interfaces import fixture_definition
from typer.testing import CliRunner


def executor_logs():
    payload = json.dumps({"inputs": {"large": "dataset-entry-" * 100}}, indent=4)
    raw = (
        "[KFP Executor 2026-10-20 10:00:00,000 INFO]: Looking for component "
        "`train` in --component_module_path `/tmp/ephemeral_component.py`\n"
        "[KFP Executor 2026-10-20 10:00:00,000 INFO]: Loading KFP component "
        '"train" from /tmp/ephemeral_component.py '
        '(directory "/tmp" and module name "ephemeral_component")\n'
        "[KFP Executor 2026-10-20 10:00:00,000 INFO]: Got executor_input:\n"
        + payload
        + "\n[trace/train] Training...\n[trace/train] Training complete.\n"
        "[KFP Executor 2026-10-20 10:00:00,000 INFO]: "
        "Wrote executor output file to /tmp/executor_output.json.\n"
    )
    return "".join(
        "2026-10-20T10:00:00.123456789Z " + line for line in raw.splitlines(True)
    )


@pytest.mark.parametrize("mode", list(OutputMode))
def test_only_recognized_kfp_json_is_hidden_or_trimmed(mode):
    raw = executor_logs()
    result = component_log(raw, mode, 128)
    assert "[trace/train] Training..." in result
    assert "[trace/train] Training complete." in result
    if mode == OutputMode.full:
        assert result == raw
    elif mode == OutputMode.none:
        assert "executor_input" not in result
        assert "dataset-entry" not in result
    else:
        assert "characters omitted; use --output full" in result
        assert len(result) < len(raw)
    # User output and malformed upstream messages are never silently discarded.
    ordinary = 'Component result: {"arbitrary": "' + "x" * 5000 + '"}\n'
    assert component_log(ordinary, mode, 128) == ordinary
    broken = raw.replace('"inputs"', '"inputs')
    assert component_log(broken, mode, 128) == broken


@pytest.mark.parametrize("mode", list(OutputMode))
@pytest.mark.parametrize("timestamps", [False, True])
def test_hidden_executor_bookkeeping_preserves_component_logs(mode, timestamps):
    raw = executor_logs()
    if not timestamps:
        raw = raw.replace("2026-10-20T10:00:00.123456789Z ", "")
    expected = "".join(line for line in raw.splitlines(True) if "[trace/" in line)
    # Both complete logs and arbitrary transport chunks obey the visibility
    # switch even with --output full.
    assert component_log(raw, mode, 128, executor_output=False) == expected
    presentation = LogPresentation(mode, 128, executor_output=False)
    assert "".join(presentation.feed(char) for char in raw) == expected
    assert presentation.feed("", final=True) == ""


@pytest.mark.parametrize("mode", list(OutputMode))
def test_executor_filter_preserves_unknown_user_and_error_messages(mode):
    messages = [
        "Training...",
        '{"user_json": "must remain visible"}',
        "[KFP Executor 2026-10-20 10:00:00,000 INFO]: Training with Python logging",
        "[KFP Executor 2026-10-20 10:00:00,000 INFO]: Looking for component data",
        "Wrote executor output file to /tmp/user-output.json.",
        "[KFP Executor 2026-10-20 10:00:00,000 WARNING]: Did not write output file.",
        "[KFP Executor 2026-10-20 10:00:00,000 ERROR]: Did not write output file.",
        "Traceback (most recent call last):",
        "RuntimeError: task failed",
    ]
    raw = "\n".join(messages)  # Include a partial final line.
    presentation = LogPresentation(mode, 128, executor_output=False)
    assert presentation.feed(raw, final=True) == raw
    assert component_log(raw, mode, 128, executor_output=False) == raw


@pytest.mark.parametrize(
    "message",
    [
        "--component_module_path is not specified. Looking for component "
        "`train` in config file `kfp_config.ini` instead",
        "Did not write output file.",
    ],
)
def test_executor_config_lookup_and_no_output_bookkeeping(message):
    raw = "[KFP Executor 2026-10-20 10:00:00,000 INFO]: " + message
    presentation = LogPresentation(OutputMode.full, 128, executor_output=False)
    assert presentation.feed(raw, final=True) == ""


@pytest.mark.parametrize("suffix", ['{\n"invalid":\n}\n', '{\n"partial":', "x" * 256])
def test_hidden_executor_metadata_fails_open_when_unvalidated(monkeypatch, suffix):
    from dockflow_pipelines import console

    monkeypatch.setattr(console, "_PRESENTATION_BUFFER", 128)
    raw = "[KFP Executor 2026-10-20 10:00:00,000 INFO]: Got executor_input:\n" + suffix
    presentation = LogPresentation(OutputMode.full, 128, executor_output=False)
    output = "".join(presentation.feed(char) for char in raw)
    output += presentation.feed("", final=True)
    assert output == raw
    assert presentation.block == presentation.partial == ""


@pytest.mark.parametrize("mode", list(OutputMode))
@pytest.mark.parametrize("dockflow_output", [False, True])
@pytest.mark.parametrize("component_output", [False, True])
def test_scoped_kfp_filter_keeps_progress_and_errors(
    mode, dockflow_output, component_output
):
    from kfp.local import logging_utils

    stream = io.StringIO()
    console = RunConsole(
        mode,
        128,
        stream,
        dockflow_output=dockflow_output,
        component_output=component_output,
    )
    original = logging_utils.local_logger_context
    original_separator = logging_utils.print_horizontal_line
    handlers = list(logging.getLogger().handlers)
    with contextlib.redirect_stdout(stream), console.kfp_logging():
        with logging_utils.local_logger_context():
            logging.info("Executing task '\x1b[36mtrain\x1b[0m'")
            logging.info("Streamed logs:\n")
            console.log("stdout", "A component's partial line")
            logging.info("Task 'train' finished with status SUCCESS")
            assert not console.presentations
            logging.info("Task 'train' outputs:\n" + "metadata-value " * 100)
            logging_utils.print_horizontal_line()
            logging.warning("Host warning")
            logging.error("Task failed: useful diagnostic")
    output = stream.getvalue()
    assert ("Executing task 'train'" in output) == dockflow_output
    assert "\x1b[" not in output
    assert ("Live task logs:" in output) == (dockflow_output and component_output)
    assert ("A component's partial line" in output) == component_output
    assert ("----------" in output) == dockflow_output
    assert "Host warning" in output
    assert "Task failed: useful diagnostic" in output
    assert (" outputs:" in output) == (dockflow_output and mode != OutputMode.none)
    assert ("characters omitted" in output) == (
        dockflow_output and mode == OutputMode.trimmed
    )
    assert logging_utils.local_logger_context is original
    assert logging_utils.print_horizontal_line is original_separator
    assert logging.getLogger().handlers == handlers


def test_disconnected_terminal_does_not_fail_execution():
    class ClosedPipe:
        def write(self, text):
            raise BrokenPipeError()

    console = RunConsole(OutputMode.full, 128, ClosedPipe())
    console.log("stdout", "Component completed\n")
    console.log("stderr", "Another retained message\n")
    assert console.closed


@pytest.mark.parametrize("mode", list(OutputMode))
@pytest.mark.parametrize("machine", [False, True])
@pytest.mark.parametrize("dockflow_output", [False, True])
@pytest.mark.parametrize("component_output", [False, True])
def test_local_run_modes_and_json_keep_logs_on_stderr(
    tmp_path, monkeypatch, mode, machine, dockflow_output, component_output
):
    (tmp_path / "pipeline.json").write_text(json.dumps(fixture_definition()))
    config = tmp_path / "dockflow.toml"
    config.write_text(
        'schema_version=1\n[project]\nid="console-test"\n'
        '[definitions.pipelines]\ntest="pipeline.json"\n'
    )
    retained = []

    def execute(self, run, *, on_log=None):
        assert on_log is not None
        for stream, text in [
            ("stdout", executor_logs()),
            ("stderr", "A component warning\n"),
        ]:
            self.store.log(run["run_id"], text, stream=stream)
            on_log(stream, text)
        completed = {
            **run,
            "state": "succeeded",
            "outputs": {"model": "artifact_model"},
            "output_parameters": {"large": "result-value-" * 1000},
        }
        retained.append(self.store.put("runs", completed))
        return retained[-1]

    monkeypatch.setattr(Core, "execute", execute)
    options = ["--config", str(config), "--local"]
    if machine:
        options.append("--json")
    flags = [
        "--dockflow-output" if dockflow_output else "--no-dockflow-output",
        "--component-output" if component_output else "--no-component-output",
    ]
    result = CliRunner().invoke(
        app,
        options
        + ["run", "test", "--output", mode.value, "--output-limit", "128", *flags],
    )
    assert result.exit_code == 0, result.output
    assert ("Training..." in result.stderr) == component_output
    assert (
        "[stdout]" in result.stderr and "[stderr]" in result.stderr
    ) == component_output
    assert ("A component warning" in result.stderr) == component_output
    assert ("Looking for component" in result.stderr) == (
        dockflow_output and component_output
    )
    assert ("Wrote executor output" in result.stderr) == (
        dockflow_output and component_output
    )
    assert ("dataset-entry" in result.stderr) == (
        dockflow_output and component_output and mode != OutputMode.none
    )
    if not component_output:
        assert result.stderr == ""
    assert "Training..." not in result.stdout
    store = Core(load_settings(config)).store
    stored = store.get("runs", retained[0]["run_id"])
    assert stored == retained[0]
    assert "".join(entry["text"] for entry in store.log_entries(stored["run_id"])) == (
        executor_logs() + "A component warning\n"
    )
    if machine:
        assert json.loads(result.stdout)["result"] == retained[0]
    elif not dockflow_output:
        assert result.stdout == ""
    elif mode == OutputMode.full:
        assert json.loads(result.stdout) == retained[0]
    else:
        assert retained[0]["run_id"] in result.stdout
        assert "succeeded" in result.stdout
        assert "pipeline_spec" not in result.stdout
        assert ("artifact_model" in result.stdout) == (mode == OutputMode.trimmed)
        assert ("characters omitted" in result.stdout) == (mode == OutputMode.trimmed)
        assert len(result.stdout) < 400


@pytest.mark.parametrize("state", ["failed", "cancelled", "interrupted"])
@pytest.mark.parametrize("machine", [False, True])
def test_hidden_output_keeps_failure_exit_status_and_diagnostics(
    tmp_path, monkeypatch, state, machine
):
    definition = tmp_path / "pipeline.json"
    definition.write_text(json.dumps(fixture_definition()))
    config = tmp_path / "dockflow.toml"
    config.write_text('schema_version=1\n[project]\nid="failed-console-test"\n')

    def execute(self, run, *, on_log=None):
        return {
            **run,
            "state": state,
            "error": {"message": "Actionable failure reason"},
            "outputs": {"model": "artifact_not_to_display"},
        }

    monkeypatch.setattr(Core, "execute", execute)
    options = ["--config", str(config), "--local"]
    if machine:
        options.append("--json")
    result = CliRunner().invoke(
        app,
        [
            *options,
            "run",
            str(definition),
            "--no-dockflow-output",
            "--no-component-output",
            "--output",
            "full",
        ],
    )
    assert result.exit_code == 1
    if machine:
        record = json.loads(result.stdout)["result"]
        assert record["state"] == state
        assert record["error"]["message"] == "Actionable failure reason"
    else:
        assert result.stdout == ""
        assert f": {state}" in result.stderr
        assert "Actionable failure reason" in result.stderr
        assert "artifact_not_to_display" not in result.stderr


@pytest.mark.parametrize("machine", [False, True])
def test_remote_visibility_does_not_change_submission_or_start_log_requests(
    tmp_path, monkeypatch, machine
):
    from dockflow_pipelines.client import Client

    definition = tmp_path / "pipeline.json"
    definition.write_text(json.dumps(fixture_definition()))
    calls = []
    accepted = {
        "run_id": "run_remote",
        "state": "queued",
        "idempotency_key": "test-key",
    }

    def request(self, method, path, body=None, **kwargs):
        calls.append((method, path, body, kwargs))
        return accepted

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Client, "request", request)
    result = CliRunner().invoke(
        app,
        [
            "--endpoint",
            "http://127.0.0.1:8080",
            *(["--json"] if machine else []),
            "run",
            str(definition),
            "--no-wait",
            "--idempotency-key",
            "test-key",
            "--no-dockflow-output",
            "--no-component-output",
        ],
    )
    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    if machine:
        assert json.loads(result.stdout)["result"] == accepted
    else:
        assert result.stdout == ""
    assert len(calls) == 1
    method, path, body, options = calls[0]
    assert (method, path, options) == ("POST", "/dockflow/v1/runs", {"key": "test-key"})
    assert set(body) == {
        "pipeline_spec",
        "source_text",
        "parameters",
        "inputs",
        "bindings",
        "use_executions",
    }


def test_suppressed_details_still_show_run_failure_and_submission_key():
    text = run_summary(
        {
            "run_id": "run_failure",
            "state": "failed",
            "idempotency_key": "retry-key",
            "error": {"message": "Model failed"},
            "outputs": {"model": "artifact_partial"},
        },
        OutputMode.none,
        128,
    )
    assert "run_failure: failed" in text
    assert "Model failed" in text
    assert "retry-key" in text
    assert "artifact_partial" not in text


def test_output_option_validation_is_offline():
    runner = CliRunner()
    assert runner.invoke(app, ["run", "--help"]).exit_code == 0
    for options in (["--output", "unknown"], ["--output-limit", "0"]):
        assert runner.invoke(app, ["run", "test", *options]).exit_code == 2


@pytest.mark.parametrize("mode", list(OutputMode))
def test_streamed_metadata_matches_complete_presentation(mode):
    raw = executor_logs()
    presentation = LogPresentation(mode, 128)
    output = "".join(presentation.feed(char) for char in raw)
    output += presentation.feed("", final=True)
    assert output == component_log(raw, mode, 128)
    assert presentation.feed("Partial final line", final=True) == "Partial final line"


@pytest.mark.parametrize(
    "tty,no_color,expected",
    [
        (True, False, True),
        (True, True, False),
        (False, False, False),
    ],
)
def test_trace_colors_depend_on_terminal_without_changing_input(
    monkeypatch, tty, no_color, expected
):
    monkeypatch.delenv("NO_COLOR", raising=False)
    if no_color:
        monkeypatch.setenv("NO_COLOR", "1")
    stream = io.StringIO()
    stream.isatty = lambda: tty
    console = RunConsole(OutputMode.none, 128, stream)
    raw = "\x1b[90m[train/fit/>]\x1b[0m \x1b[32mTraining...\x1b[0m\n"
    for char in raw:
        console.log("stdout", char)
    assert "Training..." in stream.getvalue()
    assert ("\x1b[" in stream.getvalue()) is expected
