"""Content and durability primitives with no storage or domain policy."""

import hashlib
import os
import uuid
from pathlib import Path
from typing import BinaryIO


def reject_symlinks(path: Path) -> None:
    path = path.absolute()
    for candidate in (path, *path.parents):
        if candidate.is_symlink():
            raise ValueError("Paths cannot contain symlinks")


def hash_stream(stream: BinaryIO) -> tuple[int, str]:
    count = 0
    digest = hashlib.sha256()
    while chunk := stream.read(1024 * 1024):
        count += len(chunk)
        digest.update(chunk)
    return count, digest.hexdigest()


def fsync_directory(path: Path) -> None:
    if os.name != "nt":
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def fsync_ancestors(path: Path) -> None:
    """Flush every potentially new directory entry, starting at the leaf."""
    for directory in (path, *path.parents):
        fsync_directory(directory)


def atomic_write(path: Path, data: bytes) -> None:
    """Replace a file and durably acknowledge its new directory entry."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)
