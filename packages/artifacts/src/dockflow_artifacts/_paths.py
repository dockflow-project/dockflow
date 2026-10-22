"""Private path and content helpers shared by storage implementations."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from pathlib import Path
from typing import Any, BinaryIO

from .errors import ArtifactError, IntegrityError

CONTROL = ".dockflow/dockflow-artifacts"


def relative(value: str, *, internal: bool = False) -> str:
    if not isinstance(value, str) or not value or len(value.encode()) > 1024:
        raise ArtifactError(
            "Destination must be a nonempty relative path of at most 1024 bytes"
        )
    for part in value.split("/"):
        if (
            part in {"", ".", ".."}
            or not re.fullmatch(r"[A-Za-z0-9_.-]+", part)
            or part.endswith(".")
            or (part in {".dockflow", ".dockflow-artifacts"} and not internal)
        ):
            raise ArtifactError(
                "Paths require safe relative segments (letters, digits, _, - and .)"
            )
    return value


def no_links(path: Path) -> None:
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ArtifactError("Artifact paths cannot contain symlinks")


def canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    except (TypeError, ValueError) as exc:
        raise ArtifactError("Metadata must contain finite JSON values") from exc


def hash_stream(stream: BinaryIO) -> tuple[int, str]:
    count = 0
    digest = hashlib.sha256()
    while chunk := stream.read(1024 * 1024):
        count += len(chunk)
        digest.update(chunk)
    return count, digest.hexdigest()


def file_info(path: Path) -> tuple[int, str]:
    no_links(path)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ArtifactError("Only regular files are supported")
    with path.open("rb") as stream:
        result = hash_stream(stream)
    after = path.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise IntegrityError("Artifact source changed while reading")
    return result


def inventory(source: Path) -> tuple[str, list[dict[str, Any]], str]:
    no_links(source)
    if source.is_file():
        size, digest = file_info(source)
        return "file", [{"path": "", "size": size, "sha256": digest}], digest
    if not source.is_dir():
        raise ArtifactError(
            "Artifact source must be an existing regular file or directory"
        )
    entries = []
    for path in sorted(source.rglob("*")):
        no_links(path)
        name = relative(path.relative_to(source).as_posix())
        if path.is_dir():
            if not any(path.iterdir()):
                raise ArtifactError(
                    "Empty directories are not supported by portable publication"
                )
            continue
        size, digest = file_info(path)
        entries.append({"path": name, "size": size, "sha256": digest})
    if not entries:
        raise ArtifactError(
            "Empty directories are not supported by portable publication"
        )
    return "directory", entries, hashlib.sha256(canonical(entries)).hexdigest()
