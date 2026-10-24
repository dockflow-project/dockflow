"""Deadline-aware cache waiting and independently supervised producer leases."""

from __future__ import annotations

import random
import threading
import time
import uuid
from collections.abc import Callable

from dockflow_database.errors import DockflowError

from .cache_registry import Ownership, Registry, Resolution, cache_error


class Lease:
    """A local conservative stop window supplements authoritative DB fencing.

    A response received after our original safe deadline cannot restore local
    confidence. Publication always checks current database authority as well.
    """

    def __init__(self, registry: Registry, ownership: Ownership, claim_started: float):
        self.registry, self.ownership = registry, ownership
        self.margin = min(
            registry.options["heartbeat_seconds"], ownership.remaining_seconds / 4
        )
        self.safe_until = claim_started + ownership.remaining_seconds - self.margin
        self.stopped = threading.Event()
        self.lost = threading.Event()
        self.thread = threading.Thread(
            target=self._heartbeat, name="dockflow-cache-heartbeat", daemon=True
        )

    def __enter__(self):
        self.thread.start()
        return self

    def _heartbeat(self):
        delay = self.registry.options["heartbeat_seconds"]
        while not self.stopped.wait(
            min(delay, max(0, self.safe_until - time.monotonic()))
        ):
            started = time.monotonic()
            if started >= self.safe_until:
                self.lost.set()
                return
            try:
                renewed = self.registry.renew_lease(self.ownership)
            except DockflowError as exc:
                if exc.code == "OWNERSHIP_LOST":
                    self.lost.set()
                    return
                delay = min(0.25, self.registry.options["heartbeat_seconds"])
                continue
            if time.monotonic() >= self.safe_until:
                self.lost.set()
                return
            self.safe_until = (
                started
                + min(renewed.remaining_seconds, self.registry.options["lease_seconds"])
                - self.margin
            )
            delay = self.registry.options["heartbeat_seconds"]

    def check(self) -> None:
        if self.lost.is_set() or time.monotonic() >= self.safe_until:
            self.lost.set()
            raise cache_error("OWNERSHIP_LOST")

    def should_stop(self) -> str | None:
        try:
            self.check()
        except DockflowError:
            return "cache_ownership_lost"
        return None

    def __exit__(self, *args):
        self.stopped.set()
        self.thread.join()


def wait_for_resolution(
    registry: Registry,
    key: str,
    owner: str,
    run_id: str,
    step_id: str,
    should_stop: Callable[[], str | None],
    on_wait: Callable[[Resolution], None],
    *,
    deadline: float | None = None,
    allow_claim: bool = True,
) -> tuple[Resolution, float]:
    deadline = (
        deadline
        if deadline is not None
        else time.monotonic() + registry.options["wait_seconds"]
    )
    interval = registry.options["poll_seconds"]
    while True:
        if should_stop():
            raise cache_error("CACHE_CANCELLED")
        if time.monotonic() >= deadline:
            raise cache_error("CACHE_WAIT_TIMEOUT")
        started = time.monotonic()
        # Retained within a transaction retry, including ambiguous COMMIT. A new
        # resolution after WAIT is a deliberate new claim request.
        result = registry.resolve_or_claim(
            key, owner, str(uuid.uuid4()), run_id, step_id, allow_claim=allow_claim
        )
        if result.kind in {"PRODUCE", "REUSE", "PUBLISHED", "MISS"}:
            return result, started
        if result.kind == "BLOCKED":
            registry.event("retry_exhaustion", key, reason=result.reason)
            raise cache_error(result.reason or "CACHE_BLOCKED")
        on_wait(result)
        remaining = deadline - time.monotonic()
        duration = min(
            interval * random.uniform(0.8, 1.0),
            result.recheck_after or interval,
            remaining,
        )
        until = time.monotonic() + max(0, duration)
        while time.monotonic() < until:
            if should_stop():
                raise cache_error("CACHE_CANCELLED")
            time.sleep(min(0.1, max(0, until - time.monotonic())))
        interval = min(registry.options["poll_max_seconds"], interval * 1.5)
