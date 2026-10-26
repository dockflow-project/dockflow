"""Bounded client-file ingestion and safe ZIP-to-directory artifact staging."""

from __future__ import annotations

import contextlib
import os
import re
import stat
import struct
import tempfile
import unicodedata
import zipfile
import zlib
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

from dockflow_core.canonical import json_bytes
from dockflow_core.errors import DockflowError
from dockflow_core.time import utc_now

from .artifacts import ArtifactStore, inventory, validate_metadata, validate_type

EXPANDED_BYTES = 256 * 1024**2
ZIP_ENTRIES = 10_000
OPTIONS_BYTES = 64 * 1024
BLOCK_BYTES = 1024 * 1024


def too_large(message: str) -> None:
    raise DockflowError(message, "REQUEST_TOO_LARGE", 413)


def filename(value: str) -> str:
    """A portable display basename, never a destination supplied by the client."""
    try:
        length = len(value.encode("utf-8")) if isinstance(value, str) else 0
    except UnicodeError:
        raise DockflowError("Upload filename must be valid Unicode") from None
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or length > 255
        or any(c in value for c in '/\\:<>"|?*')
        or any(unicodedata.category(c).startswith("C") for c in value)
        or value.endswith((".", " "))
        or re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", value, re.I)
    ):
        raise DockflowError("Upload requires a portable filename without paths")
    return value


def validate_options(options: dict) -> dict:
    if not isinstance(options, dict) or set(options) - {
        "type",
        "metadata",
        "version",
        "archive_mode",
    }:
        raise DockflowError("Unknown artifact upload options")
    if not isinstance(options.get("type"), dict):
        raise DockflowError("Artifact upload requires a type object")
    validate_type(options["type"])
    validate_metadata(options.get("metadata", {}))
    if "version" in options and (
        not isinstance(options["version"], str)
        or not options["version"]
        or len(options["version"]) > 256
    ):
        raise DockflowError("Artifact data revision must be 1–256 characters")
    if options.get("archive_mode", "keep") not in ("keep", "extract"):
        raise DockflowError("archive_mode must be keep or extract")
    if len(json_bytes(options)) > OPTIONS_BYTES:
        too_large("Artifact upload options exceed 64 KiB")
    return options


@contextlib.contextmanager
def open_source(path: Path) -> Iterator[BinaryIO]:
    """Never block on a FIFO or follow a final symlink supplied to the CLI."""
    path = Path(path)
    if not stat.S_ISREG(path.stat(follow_symlinks=False).st_mode):
        raise DockflowError("Upload source must be a regular file")
    fd = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    )
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise DockflowError("Upload source must be a regular file")
        yield stream


def _check_zip_directory(source: Path) -> None:
    """Count central entries without allocating ZipInfo objects for an oversized ZIP."""
    with source.open("rb") as stream:
        size = source.stat().st_size
        stream.seek(max(0, size - 65557))
        tail = stream.read(65557)
        end = len(tail)
        while True:
            end = tail.rfind(b"PK\x05\x06", 0, end)
            if end < 0:
                raise DockflowError("Invalid or truncated ZIP directory")
            if end + 22 <= len(tail) and end + 22 + struct.unpack_from(
                "<H", tail, end + 20
            )[0] == len(tail):
                break
        _, disk, directory_disk, disk_entries, entries, directory_size, _, _ = (
            struct.unpack_from("<4s4H2LH", tail, end)
        )
        if disk or directory_disk or disk_entries != entries:
            raise DockflowError("Multi-volume ZIP archives are unsupported")
        if entries > ZIP_ENTRIES:
            too_large("ZIP exceeds 10,000 entries")
        directory_end = size - len(tail) + end
        start = directory_end - directory_size
        if start < 0:
            raise DockflowError("Invalid ZIP directory size")
        stream.seek(start)
        count = 0
        while stream.tell() < directory_end:
            header = stream.read(46)
            if len(header) != 46 or header[:4] != b"PK\x01\x02":
                raise DockflowError("Invalid or unsupported ZIP directory")
            name_size, extra_size, comment_size = struct.unpack_from("<3H", header, 28)
            count += 1
            if count > ZIP_ENTRIES:
                too_large("ZIP exceeds 10,000 entries")
            stream.seek(name_size + extra_size + comment_size, os.SEEK_CUR)
        if count != entries or stream.tell() != directory_end:
            raise DockflowError("ZIP directory entry count or size differs")


def _extract(source: Path, target: Path) -> None:
    _check_zip_directory(source)
    try:
        with zipfile.ZipFile(source) as archive:
            entries = archive.infolist()
            if len(entries) > ZIP_ENTRIES:
                too_large("ZIP exceeds 10,000 entries")
            total = 0
            paths: dict[str, tuple[str, bool, bool]] = {}
            admitted = []
            for entry in entries:
                name = entry.orig_filename
                directory = entry.is_dir()
                path = name[:-1] if directory else name
                parts = path.split("/")
                if (
                    name != entry.filename
                    or len(parts) > 32
                    or len(path.encode("utf-8")) > 1024
                ):
                    raise DockflowError("Unsafe or excessive ZIP entry path")
                for part in parts:
                    filename(part)
                mode = stat.S_IFMT(entry.external_attr >> 16)
                if (
                    entry.flag_bits & 1
                    or entry.compress_type
                    not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                    or mode not in {0, stat.S_IFDIR if directory else stat.S_IFREG}
                    or directory
                    and entry.file_size != 0
                ):
                    raise DockflowError(
                        "ZIP has encrypted, special or unsupported entries"
                    )
                for depth in range(1, len(parts) + 1):
                    original = "/".join(parts[:depth])
                    key = unicodedata.normalize("NFC", original).casefold()
                    is_dir = depth < len(parts) or directory
                    explicit = depth == len(parts)
                    old = paths.get(key)
                    if old and (
                        old[0] != original or old[1] != is_dir or explicit and old[2]
                    ):
                        raise DockflowError("ZIP has duplicate or conflicting paths")
                    paths[key] = (original, is_dir, explicit or bool(old and old[2]))
                total += entry.file_size
                if total > EXPANDED_BYTES:
                    too_large("Expanded ZIP exceeds 256 MiB")
                admitted.append((entry, parts, directory))
            target.mkdir()
            actual = 0
            for entry, parts, directory in admitted:
                destination = target.joinpath(*parts)
                if directory:
                    destination.mkdir(parents=True, exist_ok=True)
                    # Read directories too, so invalid CRC/truncation is rejected.
                    with archive.open(entry) as stream:
                        if stream.read(1):
                            raise DockflowError("ZIP directory contains file bytes")
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                count = 0
                with archive.open(entry) as stream, destination.open("xb") as output:
                    while block := stream.read(BLOCK_BYTES):
                        actual += len(block)
                        count += len(block)
                        if actual > EXPANDED_BYTES or count > entry.file_size:
                            too_large("Expanded ZIP exceeds its size limit")
                        output.write(block)
                if count != entry.file_size:
                    raise DockflowError("ZIP entry size differs from its declared size")
    except (
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        EOFError,
        zlib.error,
        NotImplementedError,
        RuntimeError,
        UnicodeError,
    ) as exc:
        raise DockflowError("Invalid, corrupt or unsupported ZIP archive") from exc


def upload_stream(
    store: ArtifactStore, stream: BinaryIO, name: str, options: dict, maximum: int
) -> dict:
    store.control.require_owner()
    filename(name)
    validate_options(options)
    mode = options.get("archive_mode", "keep")
    if mode == "extract" and not name.lower().endswith(".zip"):
        raise DockflowError("Extract requires a .zip file")
    with tempfile.TemporaryDirectory(prefix="dockflow-upload-") as temporary:
        source = Path(temporary) / "source"
        size = 0
        with source.open("xb") as output:
            while block := stream.read(min(BLOCK_BYTES, maximum - size + 1)):
                size += len(block)
                if size > maximum:
                    too_large("Upload exceeds service.request_max_bytes")
                output.write(block)
        payload = source
        if mode == "extract":
            payload = Path(temporary) / "directory"
            _extract(source, payload)
        snapshot = inventory(payload)
        descriptor = store._descriptor(
            options["type"],
            options.get("metadata", {}),
            snapshot,
            "external",
            "managed",
            None,
            options.get("version"),
        )
        descriptor.update(
            upload={"filename": name, "archive_mode": mode},
            registered_at=utc_now(),
            publication_state="committed",
        )
        store._publish_managed(payload, descriptor)
        descriptor["published_at"] = utc_now()
        store.control.put("artifacts", descriptor)
        return descriptor


def upload_path(store: ArtifactStore, path: Path, options: dict, maximum: int) -> dict:
    with open_source(path) as stream:
        return upload_stream(store, stream, Path(path).name, options, maximum)
