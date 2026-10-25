"""Portable local database file ownership and path validation."""

import errno
import os
from typing import Any


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
