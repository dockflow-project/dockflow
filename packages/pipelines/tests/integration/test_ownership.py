"""Real local-filesystem exclusion and bounded, non-authoritative diagnostics."""

from __future__ import annotations

import contextlib
import errno
import io
import json
import os
import select
import subprocess
import sys
import threading
import uuid

import pytest
from dockflow_pipelines import ownership
from dockflow_pipelines.errors import DockflowError
from dockflow_pipelines.metadata import ControlStore, new_id

PROJECT = "owner-contract-tests"
ENDPOINT = "http://127.0.0.1:18080"
POSIX = pytest.mark.skipif(os.name != "posix", reason="Real POSIX flock qualification")
HOLDER = r"""
import json, socket, sys
from pathlib import Path
from dockflow_pipelines.metadata import ControlStore

state = Path(sys.argv[1])
socket.gethostname = lambda: sys.argv[3]
store = ControlStore(state, "owner-contract-tests")
with store.owner(endpoint=json.loads(sys.argv[2])):
    store.initialize(require_mlmd=False)
    print(json.dumps({"owner": json.loads((state / "owner.lock").read_text()),
                      "inode": (state / "owner.lock").stat().st_ino}), flush=True)
    sys.stdin.readline()
"""


@contextlib.contextmanager
def holder(state, endpoint=None, hostname="coordinator-fixture"):
    process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-c",
            HOLDER,
            str(state),
            json.dumps(endpoint),
            hostname,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert select.select([process.stdout], [], [], 5)[0], (
            "Owner child did not start"
        )
        line = process.stdout.readline()
        assert line, process.stderr.read()
        yield process, json.loads(line)
        if process.poll() is None:
            process.stdin.write("release\n")
            process.stdin.flush()
            process.wait(timeout=5)
            assert process.returncode == 0, process.stderr.read()
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)


def snapshot(state):
    return {
        path.relative_to(state).as_posix(): path.read_bytes()
        for path in state.rglob("*")
        if path.is_file()
    }


@POSIX
@pytest.mark.parametrize(
    "endpoint,hostname", [(None, "local-shell"), (ENDPOINT, "api-container")]
)
@pytest.mark.parametrize("alias", [False, True])
def test_real_competing_coordinators_report_owner_without_touching_state(
    tmp_path, endpoint, hostname, alias
):
    state = tmp_path / "state"
    with holder(state, endpoint, hostname) as (process, accepted):
        original = snapshot(state)
        path = tmp_path / "state-alias" if alias else state
        if alias:
            path.symlink_to(state, target_is_directory=True)
        contender = ControlStore(path, PROJECT)
        with pytest.raises(DockflowError) as failure:
            with contender.owner():
                contender.initialize(require_mlmd=False)
                pytest.fail("Competing owner entered the mutation boundary")
        error = failure.value
        assert (error.code, error.status) == ("CONFLICT", 409)
        detail = error.details[0]
        assert detail == {
            "field": "state.directory",
            "reason": "owner_conflict",
            "state_directory": str(path),
            "owner_metadata_status": "valid",
            "owner": accepted["owner"],
        }
        owner = detail["owner"]
        identifier = uuid.UUID(owner["owner_id"])
        assert identifier.version == 4 and str(identifier) == owner["owner_id"]
        assert owner["pid"] == process.pid
        assert owner["hostname"] == hostname
        assert owner["project_id"] == PROJECT
        assert owner["mode"] == ("service" if endpoint else "local")
        assert owner["endpoint"] == endpoint
        assert owner["schema_version"] == 1
        assert (
            "--endpoint " + endpoint in error.message
            if endpoint
            else "Stop" in error.message
        )
        assert snapshot(state) == original
        assert (state / "owner.lock").stat().st_ino == accepted["inode"]
        with pytest.raises(DockflowError, match="exclusive ownership"):
            contender.require_owner()


@POSIX
def test_release_and_crash_reacquire_keep_inode_but_allocate_new_owner_instances(
    tmp_path,
):
    state = tmp_path / "state"
    with holder(state, ENDPOINT) as (_, accepted):
        previous = accepted["owner"]["owner_id"]
        inode = accepted["inode"]
    assert (state / "owner.lock").stat().st_ino == inode
    assert json.loads((state / "owner.lock").read_text())["owner_id"] == previous
    store = ControlStore(state, PROJECT)
    with store.owner():
        first = json.loads((state / "owner.lock").read_text())
        assert first["owner_id"] != previous
    with store.owner():
        second = json.loads((state / "owner.lock").read_text())
        assert first["pid"] == second["pid"] == os.getpid()
        assert first["owner_id"] != second["owner_id"]
    with holder(state, None) as (process, crashed):
        process.kill()
        process.wait(timeout=5)
    assert (
        json.loads((state / "owner.lock").read_text())["owner_id"]
        == crashed["owner"]["owner_id"]
    )
    with store.owner():
        assert (
            json.loads((state / "owner.lock").read_text())["owner_id"]
            != crashed["owner"]["owner_id"]
        )
        assert (state / "owner.lock").stat().st_ino == inode


@POSIX
@pytest.mark.parametrize(
    "contents,status",
    [
        (b"not JSON: private diagnostic content", "malformed"),
        (b"\xff\xfeprivate", "malformed"),
        (b'[{"pid":12}]', "malformed"),
        (b'{"schema_version":2,"pid":12}', "unsupported_schema"),
        (
            b'{"pid":1,"hostname":"old-host","acquired_at":"2000-01-01T00:00:00Z"}',
            "legacy",
        ),
        (b'{"pid":1,"endpoint":"http://127.0.0.1:18080"}', "legacy"),
        (b"private-overlong-data" * 1000, "oversized"),
    ],
)
def test_stale_legacy_or_malformed_metadata_never_permits_takeover(
    tmp_path, contents, status
):
    state = tmp_path / "state"
    with holder(state) as (_, accepted):
        (state / "owner.lock").write_bytes(contents)
        original = snapshot(state)
        with (
            pytest.raises(DockflowError) as failure,
            ControlStore(state, PROJECT).owner(),
        ):
            pytest.fail("Metadata was used to steal an OS lock")
        detail = failure.value.details[0]
        assert detail["owner_metadata_status"] == status
        assert failure.value.status == 409
        assert "private" not in json.dumps(failure.value.as_dict())
        assert snapshot(state) == original
        assert (state / "owner.lock").stat().st_ino == accepted["inode"]


@POSIX
def test_owner_error_whitelists_fields_and_excludes_endpoint_credentials(tmp_path):
    state = tmp_path / "state"
    with holder(state, ENDPOINT) as (_, accepted):
        (state / "owner.lock").write_text(
            json.dumps(
                {
                    **accepted["owner"],
                    "endpoint": "https://user:secret@host/?token=secret",
                    "token": "secret",
                    "hostname": "host\nsecret",
                    "mode": {"secret": True},
                }
            )
        )
        with (
            pytest.raises(DockflowError) as failure,
            ControlStore(state, PROJECT).owner(),
        ):
            pass
        serialized = json.dumps(failure.value.as_dict())
        assert "secret" not in serialized
        detail = failure.value.details[0]
        assert detail["owner_metadata_status"] == "malformed"
        assert "endpoint" not in detail["owner"]
        assert "hostname" not in detail["owner"]
        assert "mode" not in detail["owner"]


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-10-19T12:00Z",
        "2026-10-19 12:00:00Z",
        "2026-10-19T12:00:00+01:00",
        "yesterday",
    ],
)
def test_metadata_diagnostics_omit_non_rfc3339_utc_timestamps(timestamp):
    status, owner = ownership._owner_metadata(
        io.BytesIO(json.dumps({"acquired_at": timestamp}).encode())
    )
    assert status == "legacy"
    assert "acquired_at" not in owner


def test_metadata_reads_are_bounded_and_read_failure_is_not_takeover_evidence():
    class Bounded(io.BytesIO):
        def read(self, size):
            assert size == ownership.OWNER_METADATA_MAX_BYTES + 1
            return super().read(size)

    assert ownership._owner_metadata(Bounded(b"x" * 100_000)) == ("oversized", {})

    class Unavailable(io.BytesIO):
        def read(self, size):
            raise PermissionError(errno.EACCES, "Unreadable locked diagnostic byte")

    assert ownership._owner_metadata(Unavailable()) == ("unavailable", {})


@pytest.mark.parametrize(
    "number", [errno.ENOSYS, errno.ENOLCK, errno.EIO, errno.EINVAL]
)
def test_unavailable_locking_is_distinguished_from_an_existing_owner(
    tmp_path, monkeypatch, number
):
    state = tmp_path / "state"
    state.mkdir()
    (state / "owner.lock").write_bytes(b"retained legacy diagnostic bytes")
    store = ControlStore(state, PROJECT)

    def unavailable(stream, *, acquire):
        assert acquire
        raise OSError(number, "untrusted error detail must not be copied")

    monkeypatch.setattr(ownership, "_owner_lock", unavailable)
    with pytest.raises(DockflowError) as failure, store.owner():
        pytest.fail("Unsupported locking allowed ownership")
    error = failure.value
    assert (error.code, error.status) == ("UNAVAILABLE", 503)
    assert error.details == [
        {
            "field": "state.directory",
            "reason": "ownership_lock_unavailable",
            "state_directory": str(state),
            "operation": "acquire",
            "errno": number,
        }
    ]
    assert "another" not in error.message and "untrusted" not in error.message
    assert (state / "owner.lock").read_bytes() == b"retained legacy diagnostic bytes"
    with pytest.raises(DockflowError, match="exclusive ownership"):
        store.require_owner()


def test_open_permission_error_is_not_reported_as_lock_contention(
    tmp_path, monkeypatch
):
    store = ControlStore(tmp_path / "state", PROJECT)

    def forbidden_open(*args, **kwargs):
        raise PermissionError(errno.EACCES, "fixture permission denied")

    with monkeypatch.context() as patch:
        patch.setattr(ownership.os, "open", forbidden_open)
        with pytest.raises(DockflowError) as failure, store.owner():
            pass
    assert (failure.value.code, failure.value.status) == ("UNAVAILABLE", 503)
    assert failure.value.details[0]["operation"] == "open"
    assert failure.value.details[0]["errno"] == errno.EACCES


@pytest.mark.parametrize("kind", ["symlink", "directory", "fifo"])
@POSIX
def test_unsafe_lock_file_types_are_refused_without_touching_targets(tmp_path, kind):
    state = tmp_path / "state"
    state.mkdir()
    target = tmp_path / "preserved"
    target.write_bytes(b"external data must survive")
    lock = state / "owner.lock"
    if kind == "symlink":
        lock.symlink_to(target)
    elif kind == "directory":
        lock.mkdir()
    else:
        os.mkfifo(lock)
    with pytest.raises(DockflowError) as failure, ControlStore(state, PROJECT).owner():
        pass
    assert failure.value.status == 503
    assert failure.value.details[0]["operation"] == "open"
    assert target.read_bytes() == b"external data must survive"


@POSIX
@pytest.mark.parametrize("operation", ["metadata_write", "release"])
def test_failure_after_acquisition_closes_lock_and_allows_a_clean_retry(
    tmp_path, monkeypatch, operation
):
    store = ControlStore(tmp_path / "state", PROJECT)
    real_lock = ownership._owner_lock

    def fail_release(stream, *, acquire):
        if not acquire:
            raise OSError(errno.EIO, "fixture release failure")
        real_lock(stream, acquire=True)

    with monkeypatch.context() as patch:
        if operation == "metadata_write":

            def fail_sync(descriptor):
                raise OSError(errno.ENOSPC, "fixture disk full")

            patch.setattr(ownership.os, "fsync", fail_sync)
        else:
            patch.setattr(ownership, "_owner_lock", fail_release)
        with pytest.raises(DockflowError) as failure, store.owner():
            pass
    assert failure.value.status == 503
    assert failure.value.details[0]["operation"] == operation
    with pytest.raises(DockflowError, match="exclusive ownership"):
        store.require_owner()
    with ControlStore(store.state, PROJECT).owner():
        pass


@POSIX
def test_nested_cross_thread_context_retains_one_acquisition_until_last_exit(tmp_path):
    store = ControlStore(tmp_path / "state", PROJECT)
    outer = store.owner(ENDPOINT)
    outer.__enter__()
    store.initialize(require_mlmd=False)
    original = json.loads((store.state / "owner.lock").read_text())
    entered, finish = threading.Event(), threading.Event()
    failures = []
    run_id = new_id("run")

    def participant():
        try:
            with store.owner():
                entered.set()
                assert finish.wait(5)
                store.put("runs", {"run_id": run_id, "state": "succeeded"})
        except BaseException as exc:
            failures.append(exc)

    thread = threading.Thread(target=participant)
    thread.start()
    try:
        assert entered.wait(5)
        outer.__exit__(None, None, None)
        assert json.loads((store.state / "owner.lock").read_text()) == original
        with pytest.raises(DockflowError), ControlStore(store.state, PROJECT).owner():
            pass
    finally:
        finish.set()
        thread.join(5)
    assert not thread.is_alive() and not failures
    with pytest.raises(DockflowError, match="exclusive ownership"):
        store.require_owner()
    assert store.get("runs", run_id)["state"] == "succeeded"
    with store.owner():
        assert (
            json.loads((store.state / "owner.lock").read_text())["owner_id"]
            != original["owner_id"]
        )


@POSIX
def test_simultaneous_threads_join_one_shared_coordinator_acquisition(tmp_path):
    store = ControlStore(tmp_path / "state", PROJECT)
    entered = threading.Barrier(3, timeout=5)
    finish = threading.Event()
    identifiers, failures = [], []

    def participant():
        try:
            with store.owner():
                identifiers.append(
                    json.loads((store.state / "owner.lock").read_text())["owner_id"]
                )
                entered.wait()
                assert finish.wait(5)
        except BaseException as exc:
            failures.append(exc)

    threads = [threading.Thread(target=participant) for _ in range(2)]
    for thread in threads:
        thread.start()
    try:
        entered.wait()
        assert len(identifiers) == 2 and len(set(identifiers)) == 1
        with pytest.raises(DockflowError), ControlStore(store.state, PROJECT).owner():
            pass
    finally:
        finish.set()
        for thread in threads:
            thread.join(5)
    assert not failures and all(not thread.is_alive() for thread in threads)
    with pytest.raises(DockflowError, match="exclusive ownership"):
        store.require_owner()
