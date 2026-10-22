"""Transport probes for chunk boundaries, backpressure and socket loss."""

import io
import threading
from types import SimpleNamespace

import pytest
from dockflow_pipelines.container_logs import ContainerLogs


class Stream:
    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.closed = False

    def __iter__(self):
        return self

    def __next__(self):
        return next(self.chunks)

    def close(self):
        self.closed = True


def test_split_utf8_socket_loss_and_tail_are_preserved_once():
    raw = "early\n€ training\nlast line".encode()
    streamed = Stream([(raw[:7], None), (raw[7:8], b"warning\n")])
    container = SimpleNamespace(
        attach=lambda **_: streamed,
        logs=lambda **kw: Stream([raw[:9], raw[9:]])
        if kw["stdout"]
        else Stream([b"warning\n"]),
    )
    seen = {"stdout": "", "stderr": ""}
    owner = threading.get_ident()

    def capture(name, text):
        assert threading.get_ident() == owner
        seen[name] += text

    with ContainerLogs(container, capture) as logs:
        assert logs.done.wait(1)
        logs.pump()
        assert seen["stdout"].startswith("early\n")
        logs.finish()
        assert not logs.thread.is_alive()
    assert seen == {"stdout": raw.decode(), "stderr": "warning\n"}
    assert streamed.closed


@pytest.mark.parametrize("retained", [b"truncated", b"changed contents\n"])
def test_different_retained_logs_fail_instead_of_silent_success(retained):
    container = SimpleNamespace(
        attach=lambda **_: Stream([(b"original output\n", None)]),
        logs=lambda **_: Stream([retained]),
    )
    with ContainerLogs(container, lambda *_: None) as logs:
        assert logs.done.wait(1)
        logs.pump()
        with pytest.raises(RuntimeError, match="logs (changed|are incomplete)"):
            logs.finish()


def test_noisy_task_has_bounded_queue_and_pump_then_cleans_up():
    raw = b"x" * (16384 * 100)
    container = SimpleNamespace(
        attach=lambda **_: Stream([(raw, None)]),
        logs=lambda **kw: Stream([raw]) if kw["stdout"] else Stream([]),
    )
    output = io.StringIO()
    with ContainerLogs(container, lambda _, text: output.write(text)) as logs:
        logs.pump(1)
        assert len(output.getvalue()) <= 16 * 16384
        assert logs.pending.qsize() <= 64
        logs.finish()
        assert not logs.thread.is_alive()
    assert output.getvalue().encode() == raw
