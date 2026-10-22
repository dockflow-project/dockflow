"""Bounded Docker log transport; only the calling thread invokes persistence."""

from __future__ import annotations

import codecs
import contextlib
import hashlib
import queue
import threading
import time
from collections.abc import Callable
from typing import Any

CHUNK_SIZE = 16384


class ContainerLogs:
    """Attach before start and forward output while the coordinator polls Docker.

    A final retained-log pass verifies the streamed prefix and recovers any tail
    lost to a disconnected attach socket. It does not emit the prefix twice.
    """

    def __init__(self, container: Any, on_log: Callable[[str, str], None]):
        self.container, self.on_log = container, on_log
        self.pending: queue.Queue[tuple[str, bytes]] = queue.Queue(maxsize=64)
        self.stopping = threading.Event()
        self.done = threading.Event()
        self.closed = False
        self.decoders = {
            name: codecs.getincrementaldecoder("utf-8")(errors="replace")
            for name in ("stdout", "stderr")
        }
        self.sizes = dict.fromkeys(self.decoders, 0)
        self.hashes = {name: hashlib.sha256() for name in self.decoders}
        self.stream = container.attach(stream=True, logs=True, demux=True)
        self.thread = threading.Thread(
            target=self._read, name="dockflow-container-logs", daemon=True
        )
        self.thread.start()

    def _read(self) -> None:
        try:
            for output in self.stream:
                for name, payload in zip(self.decoders, output, strict=True):
                    if not payload:
                        continue
                    for offset in range(0, len(payload), CHUNK_SIZE):
                        while not self.stopping.is_set():
                            try:
                                self.pending.put(
                                    (name, payload[offset : offset + CHUNK_SIZE]),
                                    timeout=0.1,
                                )
                                break
                            except queue.Full:
                                continue
                        if self.stopping.is_set():
                            return
        except Exception:
            # Docker's cancellable stream can also silently end on disconnect.
            # The verified retained-log pass below handles both cases.
            pass
        finally:
            self.done.set()

    def _emit(self, name: str, payload: bytes) -> None:
        self.sizes[name] += len(payload)
        self.hashes[name].update(payload)
        text = self.decoders[name].decode(payload)
        if text:
            self.on_log(name, text)

    def pump(self, timeout: float = 0.0) -> None:
        """Bound work per call so noisy tasks cannot starve cancellation."""
        for index in range(16):
            try:
                name, payload = self.pending.get(timeout=timeout if index == 0 else 0)
            except queue.Empty:
                break
            self._emit(name, payload)

    def finish(self) -> None:
        deadline = time.monotonic() + 5
        while not self.done.is_set() and time.monotonic() < deadline:
            self.pump(0.1)
        self.close()
        while not self.pending.empty():
            self.pump()
        for name in self.decoders:
            remaining = self.sizes[name]
            prefix = hashlib.sha256()
            expected = self.hashes[name].digest()
            retained = self.container.logs(
                stdout=name == "stdout",
                stderr=name == "stderr",
                stream=True,
                follow=False,
            )
            try:
                for payload in retained:
                    take = min(remaining, len(payload))
                    if take:
                        prefix.update(payload[:take])
                        remaining -= take
                    if not remaining and prefix.digest() != expected:
                        raise RuntimeError(
                            "Docker retained logs changed during capture"
                        )
                    if tail := payload[take:]:
                        for offset in range(0, len(tail), CHUNK_SIZE):
                            self._emit(name, tail[offset : offset + CHUNK_SIZE])
                if remaining or prefix.digest() != expected:
                    raise RuntimeError("Docker retained logs are incomplete")
            finally:
                retained.close()
            if text := self.decoders[name].decode(b"", final=True):
                self.on_log(name, text)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.stopping.set()
        if not self.done.is_set():
            with contextlib.suppress(Exception):
                self.stream.close()
        self.thread.join(timeout=1)
        # Docker SDK 7.1's attach iterator reads the upgraded socket directly;
        # its public close() shuts the socket but leaves the HTTP response open.
        # Close that response after the reader stops, also avoiding Python 3.13
        # finalizer warnings from a response wrapping an already closed socket.
        response = getattr(self.stream, "_response", None)
        if response is not None and not self.thread.is_alive():
            with contextlib.suppress(OSError, ValueError):
                response.close()
            response.raw.release_conn()
        elif response is None:
            self.stream.close()

    def __enter__(self) -> ContainerLogs:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
