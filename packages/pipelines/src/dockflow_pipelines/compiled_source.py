"""Bounded capture of stable, explicitly selected compiled definition files."""

from __future__ import annotations

import os
import stat
from pathlib import Path


def _no_links(path: Path) -> None:
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError("Compiled definition sources cannot contain symlinks")


def _identity(value: os.stat_result) -> tuple:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def read_compiled_source(path: Path, maximum: int) -> bytes:
    path = Path(os.path.abspath(path))
    _no_links(path)
    before = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("Compiled definition source must be a regular file")
    if before.st_size > maximum:
        raise ValueError(f"Compiled definition exceeds {maximum} bytes")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or _identity(before) != _identity(opened):
            raise ValueError("Compiled definition source changed while opening")
        data = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    _no_links(path)
    observed = path.stat(follow_symlinks=False)
    if _identity(before) != _identity(after) or _identity(after) != _identity(observed):
        raise ValueError("Compiled definition source changed during capture")
    if len(data) > maximum or len(data) != after.st_size:
        raise ValueError("Compiled definition source is oversized or incomplete")
    return data
