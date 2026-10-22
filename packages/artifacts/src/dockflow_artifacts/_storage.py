"""Immutable conditional storage primitives, with lazy optional S3 imports."""

from __future__ import annotations

import io
import os
import tempfile
from functools import cached_property
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import unquote, urlsplit

from ._paths import CONTROL, file_info, hash_stream, no_links, relative
from .errors import ArtifactError, ConflictError, IntegrityError


class FileStore:
    def __init__(self, root: Path):
        self.root = root.absolute()
        no_links(self.root)
        self.uri = self.root.as_uri()

    def path(self, key: str) -> Path:
        path = self.root / relative(key, internal=True)
        no_links(path)
        return path

    def get(self, key: str) -> bytes | None:
        path = self.path(key)
        if not path.exists():
            return None
        if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
            raise IntegrityError("Invalid or oversized publication record")
        return path.read_bytes()

    def has_prefix(self, prefix: str) -> bool:
        return self.path(prefix).exists()

    def put(self, key: str, body: BinaryIO) -> bool:
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        no_links(path)
        staging = self.path(f"{CONTROL}/staging")
        staging.mkdir(parents=True, exist_ok=True)
        no_links(staging)
        descriptor, temporary = tempfile.mkstemp(prefix=".publication-", dir=staging)
        try:
            with os.fdopen(descriptor, "wb") as output:
                while chunk := body.read(1024 * 1024):
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                return False
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            return True
        finally:
            Path(temporary).unlink(missing_ok=True)

    def info(self, key: str) -> tuple[int, str]:
        try:
            return file_info(self.path(key))
        except FileNotFoundError as exc:
            raise IntegrityError("Published payload is missing") from exc

    def files(self, prefix: str) -> list[str]:
        root = self.path(prefix)
        if not root.is_dir():
            raise IntegrityError("Published directory is missing")
        result = []
        for path in root.rglob("*"):
            no_links(path)
            if path.is_dir():
                continue
            if not path.is_file():
                raise IntegrityError("Published tree contains a nonregular entry")
            result.append(path.relative_to(self.root).as_posix())
        return sorted(result)


class S3Store:
    def __init__(self, root: str, options: dict[str, Any]):
        parsed = urlsplit(root)
        self.bucket = parsed.netloc
        self.prefix = parsed.path.strip("/")
        if self.prefix:
            relative(self.prefix)
        self.uri = root.rstrip("/")
        self.options = dict(options)

    @cached_property
    def client(self) -> Any:
        # Client creation can consult network credential providers. Defer it
        # until an explicit publication/verification operation reaches storage.
        try:
            import boto3
            import certifi
            from botocore.config import Config
            from botocore.session import get_session
        except ImportError as exc:
            raise ArtifactError(
                "Install dockflow-artifacts[s3] to use object storage"
            ) from exc
        options = dict(self.options)
        verify = options.get("verify")
        if verify is None or verify is True:
            # Use the maintained bundle; botocore vendors a separate older copy.
            options["verify"] = (
                get_session().get_config_variable("ca_bundle")
                if verify is None
                else None
            ) or certifi.where()
        return boto3.client(
            "s3", config=Config(s3={"addressing_style": "path"}), **options
        )

    def key(self, key: str) -> str:
        return "/".join(filter(None, (self.prefix, relative(key, internal=True))))

    @staticmethod
    def code(error: Exception) -> str:
        return str(
            getattr(error, "response", {}).get("Error", {}).get("Code", "unknown")
        )

    def get(self, key: str) -> bytes | None:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self.key(key))
            with response["Body"] as stream:
                result = stream.read(16 * 1024 * 1024 + 1)
            if len(result) > 16 * 1024 * 1024:
                raise IntegrityError("Oversized publication record")
            return result
        except ArtifactError:
            raise
        except Exception as exc:
            if self.code(exc) in {"NoSuchKey", "404"}:
                return None
            raise ArtifactError(
                "Cannot read publication record from object storage"
            ) from None

    def put(self, key: str, body: BinaryIO) -> bool:
        body.seek(0, os.SEEK_END)
        size = body.tell()
        body.seek(0)
        if size > 5 * 1024**3:
            raise ArtifactError("Conditional S3 publication supports files up to 5 GiB")
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=self.key(key),
                Body=body,
                ContentLength=size,
                IfNoneMatch="*",
            )
            return True
        except ArtifactError:
            raise
        except Exception as exc:
            if self.code(exc) in {"PreconditionFailed", "412"}:
                return False
            raise ArtifactError(
                "Conditional object creation failed; verify storage access and If-None-Match support"
            ) from None

    def info(self, key: str) -> tuple[int, str]:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self.key(key))
            with response["Body"] as stream:
                return hash_stream(stream)
        except ArtifactError:
            raise
        except Exception:
            raise IntegrityError("Cannot verify published object contents") from None

    def files(self, prefix: str) -> list[str]:
        try:
            pages = self.client.get_paginator("list_objects_v2").paginate(
                Bucket=self.bucket, Prefix=self.key(prefix) + "/"
            )
            offset = len(self.prefix) + 1 if self.prefix else 0
            return sorted(
                item["Key"][offset:]
                for page in pages
                for item in page.get("Contents", [])
            )
        except ArtifactError:
            raise
        except Exception:
            raise ArtifactError("Cannot inventory published objects") from None

    def has_prefix(self, prefix: str) -> bool:
        return bool(self.files(prefix))


def make_store(root: str | Path, options: dict[str, Any]) -> FileStore | S3Store:
    text = str(root)
    parsed = urlsplit(text)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ArtifactError(
            "Artifact roots cannot contain credentials, queries or fragments"
        )
    if parsed.scheme in {"s3", "minio"}:
        if not parsed.netloc or ":" in parsed.netloc or "%" in text:
            raise ArtifactError(
                "Object storage requires a bucket and an optional safe prefix"
            )
        return S3Store(text, options)
    if options:
        raise ArtifactError("S3 configuration cannot be used with a filesystem root")
    if parsed.scheme == "file":
        if parsed.netloc not in {"", "localhost"}:
            raise ArtifactError("File URIs must refer to the local filesystem")
        path = Path(unquote(parsed.path))
    elif not parsed.scheme:
        path = Path(text)
    else:
        raise ArtifactError(
            "Supported roots are absolute paths, file://, s3:// and minio://"
        )
    if not path.is_absolute():
        raise ArtifactError("Filesystem publication roots must be absolute")
    return FileStore(path)


def put_record(store: FileStore | S3Store, key: str, value: bytes) -> None:
    if not store.put(key, io.BytesIO(value)) and store.get(key) != value:
        raise ConflictError(
            "Destination is already reserved for different contents or metadata"
        )
