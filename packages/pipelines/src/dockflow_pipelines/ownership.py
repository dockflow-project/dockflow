"""OS-backed state ownership and bounded, non-authoritative owner diagnostics.

ControlStore serializes acquisition/release and nested coordinator participation.
This adapter handles only the stable lock file, never journals or MLMD state.
"""

from __future__ import annotations

import errno
import os
import re
import socket
import stat
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .canonical import json_bytes, loads
from .errors import DockflowError
from .records import utc_now

OWNER_METADATA_MAX_BYTES = 8192


def _owner_endpoint(value: Any) -> str | None:
    """Only expose a bounded credential-free HTTP endpoint in diagnostics."""
    if not isinstance(value, str) or not value or len(value) > 2048:
        return None
    if not value.isprintable() or any(character.isspace() for character in value):
        return None
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            return None
        _ = parsed.port
    except ValueError:
        return None
    return value


def _owner_metadata(stream: Any) -> tuple[str, dict[str, Any]]:
    """Read diagnostics without trusting their contents as ownership evidence."""
    try:
        stream.seek(0)
        raw = stream.read(OWNER_METADATA_MAX_BYTES + 1)
    except OSError:
        return "unavailable", {}
    if len(raw) > OWNER_METADATA_MAX_BYTES:
        return "oversized", {}
    try:
        value = loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        return "malformed", {}
    if not isinstance(value, dict):
        return "malformed", {}
    owner: dict[str, Any] = {}
    if type(value.get("schema_version")) is int and value["schema_version"] == 1:
        owner["schema_version"] = value["schema_version"]
    owner_id = value.get("owner_id")
    if isinstance(owner_id, str):
        try:
            identifier = uuid.UUID(owner_id)
            if identifier.version == 4 and str(identifier) == owner_id:
                owner["owner_id"] = owner_id
        except ValueError:
            pass
    hostname = value.get("hostname")
    if (
        isinstance(hostname, str)
        and 1 <= len(hostname) <= 255
        and hostname.isprintable()
        and hostname.strip()
    ):
        owner["hostname"] = hostname
    pid = value.get("pid")
    if type(pid) is int and 0 < pid <= 2**53 - 1:
        owner["pid"] = pid
    if isinstance(value.get("mode"), str) and value["mode"] in {"local", "service"}:
        owner["mode"] = value["mode"]
    project_id = value.get("project_id")
    if isinstance(project_id, str) and re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", project_id
    ):
        owner["project_id"] = project_id
    acquired_at = value.get("acquired_at")
    if (
        isinstance(acquired_at, str)
        and len(acquired_at) <= 64
        and re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)",
            acquired_at,
        )
    ):
        try:
            parsed = datetime.fromisoformat(acquired_at.replace("Z", "+00:00"))
            if parsed.utcoffset() == UTC.utcoffset(None):
                owner["acquired_at"] = acquired_at
        except ValueError:
            pass
    endpoint = value.get("endpoint")
    if "endpoint" in value and endpoint is None:
        owner["endpoint"] = None
    elif (endpoint := _owner_endpoint(endpoint)) is not None:
        owner["endpoint"] = endpoint
    if "schema_version" not in value:
        return "legacy", owner
    if type(value["schema_version"]) is not int:
        return "malformed", owner
    if value["schema_version"] != 1:
        return "unsupported_schema", owner
    required = {
        "schema_version",
        "owner_id",
        "hostname",
        "pid",
        "mode",
        "project_id",
        "acquired_at",
        "endpoint",
    }
    return ("valid" if owner.keys() >= required else "malformed"), owner


def _owner_lock(stream: Any, *, acquire: bool) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            # A byte-range lock may extend beyond EOF. Never write before exclusion.
            stream.seek(0)
            msvcrt.locking(
                stream.fileno(), msvcrt.LK_NBLCK if acquire else msvcrt.LK_UNLCK, 1
            )
        else:
            import fcntl

            fcntl.flock(
                stream.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB if acquire else fcntl.LOCK_UN,
            )
    except ImportError as exc:
        raise OSError(errno.ENOSYS, "OS locking backend unavailable") from exc


class StateOwnership:
    """One OS ownership handle; callers serialize its lifecycle transitions."""

    def __init__(self, state: Path, project_id: str):
        self.state = state
        self.project_id = project_id
        self._stream: Any = None

    @property
    def held(self) -> bool:
        return self._stream is not None

    def require_owner(self) -> None:
        if not self.held:
            raise DockflowError(
                "Mutating control state requires exclusive ownership",
                code="CONFLICT",
                status=409,
            )

    def acquire(self, endpoint: str | None = None) -> None:
        """Acquire and initialize the diagnostic handle before state mutation."""
        if self.held:
            raise RuntimeError("State ownership is already acquired")
        self._stream = self._acquire_owner(endpoint)

    def release(self) -> None:
        """Always close the handle, including after an OS unlock failure."""
        self.require_owner()
        stream, self._stream = self._stream, None
        try:
            _owner_lock(stream, acquire=False)
        except OSError as exc:
            raise self._ownership_error("release", exc) from exc
        finally:
            stream.close()

    def _ownership_error(self, operation: str, error: OSError) -> DockflowError:
        number = error.errno
        reason = (
            f"{errno.errorcode.get(number, 'OS_ERROR')} ({os.strerror(number)})"
            if number is not None
            else "OS locking operation failed"
        )
        return DockflowError(
            f"Cannot {operation} Dockflow state ownership lock for {self.state}: "
            f"{reason}. Use a local filesystem with working OS locking and permissions.",
            code="UNAVAILABLE",
            status=503,
            details=[
                {
                    "field": "state.directory",
                    "reason": "ownership_lock_unavailable",
                    "state_directory": str(self.state),
                    "operation": operation,
                    "errno": number,
                }
            ],
        )

    def _ownership_conflict(self, stream: Any) -> DockflowError:
        status, owner = _owner_metadata(stream)
        endpoint = owner.get("endpoint")
        action = (
            f"Use --endpoint {endpoint} explicitly, or stop the owner before retrying."
            if endpoint
            else "Stop the current owner before retrying; do not remove owner.lock."
        )
        identity = ", ".join(
            f"{field}={owner[field]}"
            for field in ("owner_id", "mode", "hostname", "pid")
            if field in owner
        )
        diagnostic = f" Owner: {identity}." if identity else ""
        return DockflowError(
            f"State is owned by another Dockflow coordinator: {self.state}."
            f"{diagnostic} {action}",
            code="CONFLICT",
            status=409,
            details=[
                {
                    "field": "state.directory",
                    "reason": "owner_conflict",
                    "state_directory": str(self.state),
                    "owner_metadata_status": status,
                    "owner": owner,
                }
            ],
        )

    def _open_owner_lock(self):
        path = self.state / "owner.lock"
        try:
            self.state.mkdir(parents=True, exist_ok=True)
            if path.is_symlink():
                raise OSError(errno.ELOOP, "Symlink ownership lock")
            flags = (
                os.O_RDWR
                | os.O_CREAT
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0)
                | getattr(os, "O_CLOEXEC", 0)
            )
            descriptor = os.open(path, flags, 0o600)
            try:
                if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                    raise OSError(errno.EINVAL, "Ownership lock is not a regular file")
                return os.fdopen(descriptor, "r+b")
            except BaseException:
                os.close(descriptor)
                raise
        except OSError as exc:
            raise self._ownership_error("open", exc) from exc

    def _acquire_owner(self, endpoint: str | None):
        stream = self._open_owner_lock()
        acquired = False
        try:
            try:
                _owner_lock(stream, acquire=True)
                acquired = True
            except OSError as exc:
                if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK}:
                    raise self._ownership_conflict(stream) from exc
                raise self._ownership_error("acquire", exc) from exc
            try:
                hostname = socket.gethostname()
                stream.seek(0)
                stream.truncate()
                stream.write(
                    json_bytes(
                        {
                            "schema_version": 1,
                            "owner_id": str(uuid.uuid4()),
                            "hostname": hostname
                            if 1 <= len(hostname) <= 255 and hostname.isprintable()
                            else "unknown",
                            "pid": os.getpid(),
                            "mode": "service" if endpoint else "local",
                            "project_id": self.project_id,
                            "acquired_at": utc_now(),
                            "endpoint": _owner_endpoint(endpoint),
                        }
                    )
                )
                stream.flush()
                os.fsync(stream.fileno())
            except OSError as exc:
                raise self._ownership_error("metadata_write", exc) from exc
            return stream
        except BaseException:
            try:
                if acquired:
                    try:
                        _owner_lock(stream, acquire=False)
                    except OSError as exc:
                        raise self._ownership_error("release", exc) from exc
            finally:
                stream.close()
            raise
