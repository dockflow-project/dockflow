"""Portable local database file ownership and path validation."""

import errno
import os
from pathlib import Path
from typing import Any

from .errors import DockflowError


def no_links(path: Path) -> None:
    path = path.absolute()
    for candidate in (path, *path.parents):
        if candidate.is_symlink():
            raise DockflowError("Database paths cannot contain symlinks")


def owner_lock(stream: Any, *, acquire: bool) -> None:
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
