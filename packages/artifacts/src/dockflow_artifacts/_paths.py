"""Private path and content helpers shared by storage implementations."""

from __future__ import annotations

import hashlib
import re
import stat
from pathlib import Path
from typing import Any

from dockflow_core.canonical import stable_json_bytes
from dockflow_core.filesystem import hash_stream, reject_symlinks

from .errors import ArtifactError, IntegrityError


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
    try:
        reject_symlinks(path)
    except ValueError:
        raise ArtifactError("Artifact paths cannot contain symlinks") from None


def canonical(value: Any) -> bytes:
    try:
        return stable_json_bytes(value)
    except (TypeError, ValueError) as exc:
        raise ArtifactError("Metadata must contain finite JSON values") from exc


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
