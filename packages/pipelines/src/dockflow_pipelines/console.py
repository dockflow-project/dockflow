"""Foreground run presentation; never changes stored records or component logs."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
from collections.abc import Iterator
from enum import StrEnum
from typing import TextIO


class OutputMode(StrEnum):
    none = "none"
    trimmed = "trimmed"
    full = "full"


DEFAULT_OUTPUT_LIMIT = 2000
_DOCKER_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T[\d:.]+Z ")
_EXECUTOR_INPUT = re.compile(r"^\[KFP Executor [^\n]+ INFO\]: Got executor_input:\s*$")
# Match KFP 2.17's executor_main bookkeeping, not its formatter alone: component
# logging can inherit the same root handler. Unknown messages stay visible.
_EXECUTOR_BOOKKEEPING = re.compile(
    r"^\[KFP Executor [^\n]+ INFO\]: (?:"
    r"Looking for component `[^`\n]+` in --component_module_path `[^`\n]+`"
    r"|--component_module_path is not specified\. Looking for component "
    r"`[^`\n]+` in config file `kfp_config\.ini` instead"
    r'|Loading KFP component "[^"\n]+" from [^\n]+ '
    r'\(directory "[^"\n]*" and module name "[^"\n]+"\)'
    r"|Wrote executor output file to [^\n]+\."
    r"|Did not write output file\."
    r")$"
)
_ANSI_COLOR = re.compile(r"\x1b\[[0-9;:]*m")
_PRESENTATION_BUFFER = 1024 * 1024


def trim(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return (
        text[:limit]
        + f"\n… {len(text) - limit} characters omitted; use --output full.\n"
    )


def component_log(
    text: str, mode: OutputMode, limit: int, *, executor_output: bool = True
) -> str:
    """Present recognized KFP bookkeeping without changing ordinary user logs."""
    if not executor_output:
        mode = OutputMode.none
    if mode == OutputMode.full:
        return text
    lines = text.splitlines(keepends=True)
    rendered: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        plain = _DOCKER_TIMESTAMP.sub("", line).rstrip()
        if not executor_output and _EXECUTOR_BOOKKEEPING.fullmatch(plain):
            index += 1
            continue
        if _EXECUTOR_INPUT.fullmatch(plain):
            end = index + 1
            # KFP 2.17 emits a pretty-printed JSON object whose root closing
            # brace is unindented. Validate it before changing its display;
            # malformed/incomplete messages remain visible in full.
            while end < len(lines):
                if _DOCKER_TIMESTAMP.sub("", lines[end]).rstrip() == "}":
                    block = "".join(
                        _DOCKER_TIMESTAMP.sub("", part)
                        for part in lines[index + 1 : end + 1]
                    )
                    try:
                        value = json.loads(block)
                    except ValueError:
                        break
                    if not isinstance(value, dict):
                        break
                    if mode == OutputMode.trimmed:
                        rendered.append(line + trim(block, limit))
                    index = end + 1
                    break
                end += 1
            else:
                end = len(lines)
            if index == end + 1:
                continue
        rendered.append(line)
        index += 1
    return "".join(rendered)


def run_summary(run: dict, mode: OutputMode, limit: int) -> str:
    """Keep run identity/outcome visible even when result details are disabled."""
    if mode == OutputMode.full:
        return json.dumps(run, ensure_ascii=False, indent=2, allow_nan=False)
    lines = [f"Run {run['run_id']}: {run['state']}"]
    if run.get("idempotency_key"):
        lines.append(f"Submission key: {run['idempotency_key']}")
    if mode == OutputMode.trimmed:
        outputs = {}
        if run.get("outputs"):
            outputs["artifacts"] = run["outputs"]
        if run.get("output_parameters"):
            outputs["parameters"] = run["output_parameters"]
        if outputs:
            lines.append(
                "Outputs:\n"
                + trim(json.dumps(outputs, ensure_ascii=False, indent=2), limit)
            )
    if run.get("error"):
        lines.append(
            "Error:\n"
            + trim(json.dumps(run["error"], ensure_ascii=False, indent=2), limit)
        )
    return "\n".join(lines)


class LogPresentation:
    """Assemble lines/recognized metadata across arbitrary Docker chunks."""

    def __init__(self, mode: OutputMode, limit: int, *, executor_output: bool = True):
        self.mode, self.limit = mode, limit
        self.executor_output = executor_output
        self.partial = ""
        self.block = ""

    def feed(self, text: str, *, final: bool = False) -> str:
        self.partial += text
        rendered: list[str] = []
        while "\n" in self.partial:
            line, self.partial = self.partial.split("\n", 1)
            line += "\n"
            plain = _DOCKER_TIMESTAMP.sub("", line).rstrip()
            if self.block:
                self.block += line
                if plain == "}":
                    rendered.append(self._present(self.block))
                    self.block = ""
            elif (
                self.mode != OutputMode.full or not self.executor_output
            ) and _EXECUTOR_INPUT.fullmatch(plain):
                self.block = line
            else:
                rendered.append(self._present(line))
            if len(self.block) > _PRESENTATION_BUFFER:
                # Never hide unvalidated/incomplete JSON or grow without bound.
                rendered.append(self.block)
                self.block = ""
        if final or len(self.partial) > _PRESENTATION_BUFFER:
            # Incomplete metadata and oversized partial lines fail open.
            rendered.append(
                self.block + self.partial
                if self.block or not final
                else self._present(self.partial)
            )
            self.block = self.partial = ""
        return "".join(rendered)

    def _present(self, text: str) -> str:
        return component_log(
            text, self.mode, self.limit, executor_output=self.executor_output
        )


class RunConsole:
    def __init__(
        self,
        mode: OutputMode,
        limit: int,
        stream: TextIO,
        *,
        dockflow_output: bool = True,
        component_output: bool = True,
    ):
        self.mode, self.limit, self.stream = mode, limit, stream
        self.dockflow_output = dockflow_output
        self.component_output = component_output
        self.closed = False
        self.colors = (
            bool(getattr(stream, "isatty", lambda: False)())
            and "NO_COLOR" not in os.environ
        )
        self.presentations: dict[str, LogPresentation] = {}
        self.last_stream: str | None = None

    def log(self, stream: str, text: str) -> None:
        """Called after durable capture, with the original stream attribution."""
        if not self.component_output:
            return
        presentation = self.presentations.setdefault(
            stream,
            LogPresentation(
                self.mode, self.limit, executor_output=self.dockflow_output
            ),
        )
        self._write(stream, presentation.feed(text))

    def flush(self) -> None:
        for stream, presentation in self.presentations.items():
            self._write(stream, presentation.feed("", final=True))
        self.presentations.clear()
        self.last_stream = None

    def _write(self, stream: str, rendered: str) -> None:
        if not rendered or self.closed:
            return
        if not self.colors:
            rendered = _ANSI_COLOR.sub("", rendered)
        try:
            if stream != self.last_stream:
                self.stream.write(f"[{stream}]\n")
                self.last_stream = stream
            self.stream.write(rendered)
            if not rendered.endswith("\n"):
                self.stream.write("\n")
            self.stream.flush()
        except OSError:
            # Losing the terminal must not turn a successful container into a
            # failed attempt or prevent publication. Durable logs remain intact.
            self.closed = True

    @contextlib.contextmanager
    def kfp_logging(self) -> Iterator[None]:
        """Scope KFP 2.17's human task summaries to this foreground invocation."""
        try:
            from kfp.local import logging_utils
        except ImportError:
            # The normal executor boundary owns the missing-runtime diagnostic.
            try:
                yield
            finally:
                self.flush()
            return
        from unittest.mock import patch

        original = logging_utils.local_logger_context
        mode, limit, console = self.mode, self.limit, self

        class DisplayFilter(logging.Filter):
            def filter(self, record: logging.LogRecord) -> bool:
                message = record.getMessage()
                if message.startswith("Task ") and " finished with status " in message:
                    # Flush the component's trailing line even if task progress
                    # itself is hidden.
                    console.flush()
                if not console.dockflow_output and record.levelno < logging.WARNING:
                    return False
                if message == "Streamed logs:\n":
                    if not console.component_output:
                        return False
                    message = "Live task logs:"
                elif message.startswith("Task ") and " outputs:\n" in message:
                    if mode == OutputMode.none:
                        return False
                    if mode == OutputMode.trimmed:
                        message = trim(message, limit)
                if not console.colors:
                    message = _ANSI_COLOR.sub("", message)
                record.msg, record.args = message, ()
                return True

        @contextlib.contextmanager
        def logger_context():
            with original():
                handlers = list(logging.getLogger().handlers)
                display_filter = DisplayFilter()
                for handler in handlers:
                    handler.addFilter(display_filter)
                try:
                    yield
                finally:
                    for handler in handlers:
                        handler.removeFilter(display_filter)

        with (
            patch.object(logging_utils, "local_logger_context", logger_context),
            patch.object(
                logging_utils,
                "print_horizontal_line",
                logging_utils.print_horizontal_line
                if self.dockflow_output
                else lambda: None,
            ),
        ):
            try:
                yield
            finally:
                self.flush()
