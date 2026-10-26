"""Immutable typed artifact snapshots with filesystem and S3-compatible storage."""

from __future__ import annotations

import hashlib
import importlib
import os
import re
import shutil
import stat
import tempfile
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

from dockflow_artifacts.persistence import ArtifactRecords
from dockflow_core.canonical import digest, json_bytes, loads, validate_json
from dockflow_core.errors import DockflowError
from dockflow_core.filesystem import fsync_directory, hash_stream, reject_symlinks
from dockflow_core.time import utc_now

from .metadata import ControlStore
from .records import new_id

METADATA_TYPES = {"system.Metrics", "system.ClassificationMetrics"}
BUILTIN_TYPES = {
    "system.Artifact",
    "system.Dataset",
    "system.Model",
    "system.Metrics",
    "system.ClassificationMetrics",
    "system.HTML",
    "system.Markdown",
}


def _storage_segment(value: Any) -> str:
    """Admit portable names, never paths or URI escape sequences."""
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*", value)
        or value.endswith(".")
    ):
        raise DockflowError(f"Unsafe managed artifact path segment: {value!r}")
    return value


def validate_type(artifact_type: dict[str, Any]) -> dict[str, str]:
    if set(artifact_type) != {"schema_title", "schema_version"}:
        raise DockflowError(
            "Artifact type requires schema_title and schema_version only"
        )
    if any(not isinstance(value, str) or not value for value in artifact_type.values()):
        raise DockflowError("Artifact type title and version must be nonempty strings")
    return dict(artifact_type)


def validate_metadata(metadata: dict[str, Any]) -> None:
    if not isinstance(metadata, dict):
        raise DockflowError("Artifact metadata must be an object")
    if any(key == "dockflow" or key.startswith("dockflow.") for key in metadata):
        raise DockflowError("The dockflow metadata namespace is reserved")
    try:
        validate_json(metadata)
    except ValueError as exc:
        raise DockflowError(str(exc)) from exc


def _relative_path(value: str) -> PurePosixPath:
    if not value or "\\" in value or "\x00" in value:
        raise DockflowError(
            "Unsafe artifact inventory path", code="CONFLICT", status=409
        )
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise DockflowError(
            "Unsafe artifact inventory path", code="CONFLICT", status=409
        )
    return path


def _no_links(path: Path) -> None:
    try:
        reject_symlinks(path)
    except ValueError:
        raise DockflowError("Artifact paths cannot contain symlinks") from None


def _hash_file(path: Path) -> tuple[int, str]:
    _no_links(path)
    before = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):
        raise DockflowError("Artifact payloads must be regular files/directories")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
            before.st_dev,
            before.st_ino,
        ):
            raise DockflowError(
                "Artifact source changed while opening", code="CONFLICT", status=409
            )
        size, sha = hash_stream(stream)
        after = os.fstat(stream.fileno())
    observed = path.stat(follow_symlinks=False)

    def fields(item):
        return (
            item.st_dev,
            item.st_ino,
            item.st_size,
            item.st_mtime_ns,
            item.st_ctime_ns,
        )

    if (
        fields(before) != fields(after)
        or fields(before) != fields(observed)
        or size != before.st_size
    ):
        raise DockflowError(
            "Artifact source changed during fingerprinting", code="CONFLICT", status=409
        )
    return size, sha


def inventory(path: Path) -> dict[str, Any]:
    """Fingerprint the normative file/directory view without following links."""
    path = Path(path).absolute()
    _no_links(path)
    try:
        source_stat = path.stat(follow_symlinks=False)
    except FileNotFoundError as exc:
        raise DockflowError(
            "Artifact payload is missing", code="NOT_FOUND", status=404
        ) from exc
    except PermissionError as exc:
        raise DockflowError(
            "Artifact payload is inaccessible", code="PERMISSION_DENIED", status=403
        ) from exc
    if stat.S_ISREG(source_stat.st_mode):
        size, sha = _hash_file(path)
        return {
            "payload_kind": "file",
            "inventory": [],
            "size_bytes": size,
            "fingerprint": {"algorithm": "sha256", "format": "bytes", "value": sha},
        }
    if not stat.S_ISDIR(source_stat.st_mode):
        raise DockflowError("Artifact payloads must be regular files/directories")
    entries: list[dict[str, Any]] = []
    collision_keys: set[str] = set()
    for root, directories, files in os.walk(path, followlinks=False):
        root_path = Path(root)
        for name in [*directories, *files]:
            child = root_path / name
            relative = child.relative_to(path).as_posix()
            _relative_path(relative)
            key = os.path.normcase(relative)
            if key in collision_keys:
                raise DockflowError("Artifact paths collide on this filesystem")
            collision_keys.add(key)
            child_stat = child.stat(follow_symlinks=False)
            if not stat.S_ISREG(child_stat.st_mode) and not stat.S_ISDIR(
                child_stat.st_mode
            ):
                raise DockflowError(
                    "Symlinks and special artifact files are unsupported"
                )
        if not directories and not files and root_path != path:
            entries.append(
                {"path": root_path.relative_to(path).as_posix(), "kind": "directory"}
            )
        for name in files:
            child = root_path / name
            size, sha = _hash_file(child)
            entries.append(
                {
                    "path": child.relative_to(path).as_posix(),
                    "kind": "file",
                    "size_bytes": size,
                    "sha256": sha,
                }
            )
    entries.sort(key=lambda entry: entry["path"].encode("utf-8"))
    return {
        "payload_kind": "directory",
        "inventory": entries,
        "size_bytes": sum(entry.get("size_bytes", 0) for entry in entries),
        "fingerprint": {
            "algorithm": "sha256",
            "format": "dockflow-json-v1",
            "value": digest({"kind": "directory", "entries": entries}),
        },
    }


def _copy_payload(source: Path, destination: Path, snapshot: dict[str, Any]) -> None:
    if snapshot["payload_kind"] == "file":
        destination.parent.mkdir(parents=True, exist_ok=True)
        _no_links(source)
        source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with (
            os.fdopen(source_fd, "rb") as input_file,
            destination.open("xb") as output_file,
        ):
            if not stat.S_ISREG(os.fstat(input_file.fileno()).st_mode):
                raise DockflowError("Artifact copy source is not a regular file")
            shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
            output_file.flush()
            os.fsync(output_file.fileno())
    else:
        destination.mkdir(parents=True)
        for entry in snapshot["inventory"]:
            path = destination.joinpath(*_relative_path(entry["path"]).parts)
            if entry["kind"] == "directory":
                path.mkdir(parents=True, exist_ok=True)
            elif entry["kind"] == "file":
                _copy_payload(source / entry["path"], path, {"payload_kind": "file"})
            else:
                raise DockflowError(
                    "Unknown artifact inventory kind", code="CONFLICT", status=409
                )
    if "fingerprint" in snapshot and inventory(destination) != snapshot:
        raise DockflowError(
            "Artifact copy does not match registered fingerprint",
            code="CONFLICT",
            status=409,
        )


def _uri_parts(uri: str) -> tuple[str, str, tuple[str, ...]]:
    parsed = urlsplit(uri)
    if (
        parsed.scheme not in {"file", "s3"}
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise DockflowError(
            "Artifact URI must be an absolute file:// or s3:// URI without credentials/query/fragment"
        )
    decoded = unquote(parsed.path)
    if (
        "\\" in decoded
        or "\x00" in decoded
        or any(part in {".", ".."} for part in decoded.split("/"))
    ):
        raise DockflowError("Artifact URI contains unsafe path segments")
    if parsed.scheme == "file" and (
        parsed.netloc not in {"", "localhost"} or not decoded.startswith("/")
    ):
        raise DockflowError("file:// artifact URIs must identify absolute local paths")
    if parsed.scheme == "s3" and (
        not parsed.netloc or ":" in parsed.netloc or not decoded.strip("/")
    ):
        raise DockflowError("s3:// artifact URI requires bucket and object/prefix")
    return (
        parsed.scheme,
        parsed.netloc,
        tuple(part for part in decoded.split("/") if part),
    )


class ArtifactStore:
    def __init__(self, control: ControlStore, options: dict[str, Any]):
        self.control = control
        self.options = options
        self.backend = options.get("backend", "filesystem")
        self.root = Path(
            options.get("root") or control.state.parent / "artifacts"
        ).absolute()
        self.managed_root = Path(
            options.get("managed_root") or self.root / "managed"
        ).absolute()
        self._client: Any = None

    def _s3(self) -> Any:
        if self._client is None:
            try:
                boto3 = importlib.import_module("boto3")
                certifi = importlib.import_module("certifi")
                config = importlib.import_module("botocore.config").Config
            except ImportError as exc:
                raise DockflowError(
                    "Install dockflow-pipelines[s3] for S3-compatible artifacts",
                    code="UNAVAILABLE",
                    status=503,
                ) from exc
            endpoint = self.options.get("endpoint")
            if not endpoint:
                raise DockflowError("S3 artifacts require a configured endpoint")
            if urlsplit(endpoint).scheme == "http" and not self.options.get(
                "allow_insecure_http", False
            ):
                raise DockflowError(
                    "S3 HTTP endpoint requires allow_insecure_http=true"
                )
            verify = self.options.get("tls_verify", True)
            if verify is True:
                verify = certifi.where()
            self._client = boto3.client(
                "s3",
                endpoint_url=endpoint,
                verify=verify,
                config=config(
                    s3={"addressing_style": "path"},
                    connect_timeout=5,
                    read_timeout=10,
                    retries={"max_attempts": 2, "mode": "standard"},
                ),
            )
        return self._client

    def storage_identity(self, *, create: bool = True) -> str:
        """Resolve a persisted random store identity, independent of mount path."""
        relative = ".dockflow/storage.json"
        if self.backend == "filesystem":
            path = self.managed_root / relative
            _no_links(path)
            if create and not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_name(".storage-" + uuid.uuid4().hex)
                try:
                    with temporary.open("xb") as stream:
                        stream.write(
                            json_bytes(
                                {
                                    "format": "dockflow-artifact-store-v1",
                                    "identity": str(uuid.uuid4()),
                                }
                            )
                        )
                        stream.flush()
                        os.fsync(stream.fileno())
                    try:
                        os.link(temporary, path)
                    except FileExistsError:
                        pass

                    fsync_directory(path.parent)
                finally:
                    temporary.unlink(missing_ok=True)
            if create:
                with path.open("rb") as stream:
                    os.fsync(stream.fileno())
                for ancestor in (path.parent, *path.parent.parents):
                    fsync_directory(ancestor)
            try:
                content = loads(path.read_bytes())
            except OSError:
                raise DockflowError(
                    "Artifact storage is inaccessible or uninitialized",
                    "ARTIFACT_UNAVAILABLE",
                    503,
                ) from None
        else:
            client = self._s3()
            key = self.object_key(relative)
            if create:
                try:
                    client.put_object(
                        Bucket=self.options["bucket"],
                        Key=key,
                        Body=json_bytes(
                            {
                                "format": "dockflow-artifact-store-v1",
                                "identity": str(uuid.uuid4()),
                            }
                        ),
                        IfNoneMatch="*",
                    )
                except Exception as exc:
                    code = str(
                        getattr(exc, "response", {}).get("Error", {}).get("Code", "")
                    )
                    if code not in {
                        "412",
                        "PreconditionFailed",
                        "ConditionalRequestConflict",
                        "409",
                    }:
                        raise DockflowError(
                            "Cannot initialize artifact storage",
                            "ARTIFACT_UNAVAILABLE",
                            503,
                        ) from None
            try:
                response = client.get_object(Bucket=self.options["bucket"], Key=key)
                with response["Body"] as body:
                    content = loads(body.read(4097))
            except Exception:
                raise DockflowError(
                    "Artifact storage is inaccessible or uninitialized",
                    "ARTIFACT_UNAVAILABLE",
                    503,
                ) from None
        if content.get("format") != "dockflow-artifact-store-v1" or not isinstance(
            content.get("identity"), str
        ):
            raise DockflowError(
                "Artifact store identity is incompatible", "CACHE_CONFLICT", 409
            )
        try:
            return str(uuid.UUID(content["identity"]))
        except ValueError:
            raise DockflowError(
                "Artifact store identity is incompatible", "CACHE_CONFLICT", 409
            ) from None

    def artifact_records(self, *, create: bool = True) -> ArtifactRecords:
        return ArtifactRecords(
            self.control.database.adapter,
            self.control.project_id,
            self.storage_identity(create=create),
            writer=self.control.database.transaction,
        )

    def recovery_descriptor(self, artifact_id: str) -> dict:
        raw = self.artifact_records(create=False).get(
            "pipeline-descriptors", artifact_id
        )
        if raw is None:
            raise DockflowError(
                "Artifact recovery descriptor is missing", "NOT_FOUND", 404
            )
        descriptor = loads(raw)
        content = self.managed_content_path(descriptor)
        uri = f"dockflow://{self.control.project_id}/artifacts/{artifact_id}"
        descriptor.update(
            uri=uri,
            descriptor_uri=uri,
            content_uri=(
                None
                if descriptor["payload_kind"] == "metadata"
                else (self.managed_root / content).as_uri()
                if self.backend == "filesystem"
                else "s3://" + self.options["bucket"] + "/" + self.object_key(content)
            ),
        )
        return descriptor

    def managed_content_path(self, descriptor: dict[str, Any]) -> str:
        """Resolve a current immutable payload locator relative to the managed root."""
        if descriptor.get("storage_layout") not in {"kfp-v2", "cache-v1"}:
            raise DockflowError("Unsupported managed artifact storage layout")
        return str(_relative_path(descriptor["managed_path"]))

    def object_key(self, relative: str) -> str:
        return "/".join(
            part
            for part in (
                self.options.get("prefix", "").strip("/"),
                str(_relative_path(relative)),
            )
            if part
        )

    def _set_managed_path(self, descriptor: dict[str, Any]) -> None:
        producer = descriptor["producer"]
        if producer is None:
            # Administrative imports have no computational producer or run.
            relative = (
                f".dockflow/dockflow-pipelines/{descriptor['artifact_id']}/payload"
            )
        else:
            attempt = _storage_segment(producer["attempt_id"])
            salt = str(uuid.UUID(attempt.removeprefix("attempt_")))
            parts = [
                _storage_segment(producer["pipeline_name"]),
                _storage_segment(producer["run_id"]),
                _storage_segment(producer["task_name"]),
                salt,
                _storage_segment(producer["output_name"]),
            ]
            relative = "/".join(parts)
        layout = "kfp-v2"
        if producer and producer.get("cache_namespace") == "cache-v1":
            relative = ".dockflow/dockflow-pipelines/cache-v1/" + relative
            layout = "cache-v1"
        descriptor.update(storage_layout=layout, managed_path=relative)

    def _admit(self, uri: str) -> tuple[str, str, tuple[str, ...]]:
        scheme, authority, parts = _uri_parts(uri)
        if scheme == "file":
            path = Path(unquote(urlsplit(uri).path))
            _no_links(path)
            roots = [
                Path(value).absolute()
                for value in self.options.get("external_roots", [])
            ]
            if self.backend == "filesystem":
                roots.append(self.managed_root)
            if not any(path.absolute().is_relative_to(root) for root in roots):
                raise DockflowError(
                    "File artifact URI is outside artifacts.external_roots",
                    code="PERMISSION_DENIED",
                    status=403,
                )
            if (
                path.absolute() == self.control.state
                or self.control.state.is_relative_to(path.absolute())
            ):
                raise DockflowError("Artifact source overlaps durable control state")
        else:
            allowed = list(self.options.get("allowed_uri_prefixes", []))
            if self.backend == "s3":
                prefix = self.options.get("prefix", "").strip("/")
                if authority == self.options["bucket"] and (
                    not prefix
                    or parts[: len(prefix.split("/"))] == tuple(prefix.split("/"))
                ):
                    return scheme, authority, parts
            if not any(
                (
                    lambda candidate: candidate[0] == scheme
                    and candidate[1] == authority
                    and parts[: len(candidate[2])] == candidate[2]
                )(_uri_parts(candidate))
                for candidate in allowed
            ):
                raise DockflowError(
                    "S3 artifact URI is outside artifacts.allowed_uri_prefixes",
                    code="PERMISSION_DENIED",
                    status=403,
                )
        return scheme, authority, parts

    def _download_source(
        self, uri: str, destination: Path
    ) -> tuple[dict[str, Any], Any]:
        _, bucket, parts = _uri_parts(uri)
        key = "/".join(parts)
        client = self._s3()
        for descriptor in self.control.list("artifacts"):
            if (
                descriptor.get("ownership") == "managed"
                and descriptor.get("publication_state") == "committed"
                and descriptor.get("content_uri")
                and _uri_parts(descriptor["content_uri"]) == _uri_parts(uri)
            ):
                self._download_descriptor(descriptor, destination)
                snapshot = inventory(destination)
                expected = {
                    name: descriptor[name]
                    for name in (
                        "payload_kind",
                        "inventory",
                        "size_bytes",
                        "fingerprint",
                    )
                }
                if snapshot != expected:
                    raise DockflowError(
                        "Recognized managed source differs from its registered fingerprint",
                        code="CONFLICT",
                        status=409,
                    )
                return snapshot, None
        try:
            head = client.head_object(Bucket=bucket, Key=key)
        except client.exceptions.ClientError as exc:
            if str(exc.response.get("Error", {}).get("Code")) not in {
                "404",
                "NoSuchKey",
                "NotFound",
            }:
                raise
            head = None
        if head is not None:
            provider = {
                "version_id": head.get("VersionId"),
                "etag": head.get("ETag"),
                "size_bytes": head["ContentLength"],
            }
            client.download_file(
                bucket,
                key,
                str(destination),
                ExtraArgs={"VersionId": head["VersionId"]}
                if head.get("VersionId")
                else None,
            )
            after = client.head_object(Bucket=bucket, Key=key)
            if provider != {
                "version_id": after.get("VersionId"),
                "etag": after.get("ETag"),
                "size_bytes": after["ContentLength"],
            }:
                raise DockflowError(
                    "S3 source changed during registration", code="CONFLICT", status=409
                )
            return inventory(destination), provider
        prefix = key.rstrip("/") + "/"

        def listing() -> list[dict[str, Any]]:
            return sorted(
                [
                    {
                        "key": item["Key"],
                        "etag": item.get("ETag"),
                        "size_bytes": item["Size"],
                    }
                    for page in client.get_paginator("list_objects_v2").paginate(
                        Bucket=bucket, Prefix=prefix
                    )
                    for item in page.get("Contents", [])
                ],
                key=lambda item: item["key"].encode("utf-8"),
            )

        before = listing()
        if not before:
            raise DockflowError(
                "Empty S3 prefix is not a recognized directory snapshot",
                code="NOT_FOUND",
                status=404,
            )
        destination.mkdir()
        for item in before:
            relative = item["key"][len(prefix) :]
            if not relative:
                raise DockflowError(
                    "S3 directory marker objects require a recognized artifact descriptor"
                )
            child = destination.joinpath(*_relative_path(relative).parts)
            child.parent.mkdir(parents=True, exist_ok=True)
            client.download_file(bucket, item["key"], str(child))
        if before != listing():
            raise DockflowError(
                "S3 prefix changed during registration", code="CONFLICT", status=409
            )
        return inventory(destination), before

    def register(
        self,
        uri: str,
        type: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        managed: bool = False,
        version: str | None = None,
    ) -> dict[str, Any]:
        self.control.require_owner()
        artifact_type = validate_type(type)
        metadata = metadata or {}
        validate_metadata(metadata)
        scheme, _, _ = self._admit(uri)
        with tempfile.TemporaryDirectory(prefix="dockflow-register-") as directory:
            if scheme == "file":
                source = Path(unquote(urlsplit(uri).path))
                snapshot = inventory(source)
                provider_version = None
            else:
                source = Path(directory) / "source"
                snapshot, provider_version = self._download_source(uri, source)
            descriptor = self._descriptor(
                artifact_type,
                metadata,
                snapshot,
                "external",
                "managed" if managed else "reference",
                None,
                version,
            )
            descriptor.update(
                creation_origin="manual",
                source_uri=uri,
                source_provider_version=provider_version,
                publication_state="committed",
                registered_at=utc_now(),
            )
            if managed:
                self._publish_managed(source, descriptor)
                if scheme == "file" and inventory(source) != snapshot:
                    raise DockflowError(
                        "External source changed during import",
                        code="CONFLICT",
                        status=409,
                    )
                if scheme == "s3":
                    again = Path(directory) / "source-again"
                    second_snapshot, second_provider = self._download_source(uri, again)
                    if (
                        second_snapshot != snapshot
                        or second_provider != provider_version
                    ):
                        raise DockflowError(
                            "External S3 source changed during import",
                            code="CONFLICT",
                            status=409,
                        )
            else:
                descriptor["content_uri"] = uri
                if scheme == "file" and inventory(source) != snapshot:
                    raise DockflowError(
                        "External source changed during registration",
                        code="CONFLICT",
                        status=409,
                    )
            descriptor["published_at"] = utc_now()
            self.control.put("artifacts", descriptor)
            return descriptor

    def _descriptor(
        self,
        artifact_type: dict[str, Any],
        metadata: dict[str, Any],
        snapshot: dict[str, Any],
        origin: str,
        ownership: str,
        producer: dict[str, Any] | None,
        version: str | None = None,
    ) -> dict[str, Any]:
        artifact_id = new_id("artifact")
        descriptor_uri = f"dockflow://{self.control.project_id}/artifacts/{artifact_id}"
        return {
            "schema_version": 1,
            "kind": "artifact",
            "project_id": self.control.project_id,
            "artifact_id": artifact_id,
            "type": dict(artifact_type),
            "origin": origin,
            "creation_origin": "execution" if origin == "produced" else "manual",
            "ownership": ownership,
            "storage_backend": self.backend if ownership == "managed" else "external",
            "descriptor_uri": descriptor_uri,
            "uri": descriptor_uri,
            "content_uri": None,
            "source_uri": None,
            "source_provider_version": None,
            "version": version,
            "metadata": loads(json_bytes(metadata)),
            "producer": loads(json_bytes(producer)),
            "created_at": utc_now(),
            "registered_at": None,
            "published_at": None,
            "publication_state": "staged",
            "availability": "available",
            "pinned": False,
            "revision": 1,
            **snapshot,
        }

    def publish(
        self,
        path: Path | None,
        type: dict[str, Any],
        producer: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.control.require_owner()
        artifact_type = validate_type(type)
        metadata = metadata or {}
        validate_metadata(metadata)
        if path is None or not Path(path).exists():
            if artifact_type["schema_title"] not in METADATA_TYPES:
                raise DockflowError(
                    "Required artifact payload is missing", code="CONFLICT", status=409
                )
            snapshot = {
                "payload_kind": "metadata",
                "inventory": [],
                "size_bytes": 0,
                "fingerprint": {
                    "algorithm": "sha256",
                    "format": "dockflow-json-v1",
                    "value": digest(
                        {
                            "kind": "metadata",
                            "type": artifact_type,
                            "metadata": metadata,
                        }
                    ),
                },
            }
            path = None
        else:
            path = Path(path).absolute()
            snapshot = inventory(path)
        descriptor = self._descriptor(
            artifact_type, metadata, snapshot, "produced", "managed", producer
        )
        self._publish_managed(path, descriptor)
        self.control.put("artifacts", descriptor)
        return descriptor

    def _publish_managed(self, source: Path | None, descriptor: dict[str, Any]) -> None:
        coordinated = (descriptor.get("producer") or {}).get(
            "cache_namespace"
        ) == "cache-v1"
        for ordinal in range(3 if coordinated else 1):
            try:
                self._publish_managed_once(source, descriptor)
                return
            except Exception as exc:
                provider_code = str(
                    getattr(exc, "response", {}).get("Error", {}).get("Code", "")
                )
                transient = (
                    isinstance(exc, PermissionError | TimeoutError | ConnectionError)
                    or isinstance(exc, OSError)
                    and not isinstance(exc, FileNotFoundError)
                    or isinstance(exc, DockflowError)
                    and exc.code in {"UNAVAILABLE", "ARTIFACT_UNAVAILABLE"}
                    or provider_code
                    in {
                        "500",
                        "503",
                        "SlowDown",
                        "ServiceUnavailable",
                        "RequestTimeout",
                        "409",
                        "ConditionalRequestConflict",
                    }
                    or type(exc).__name__
                    in {
                        "EndpointConnectionError",
                        "ConnectionClosedError",
                        "ReadTimeoutError",
                        "ConnectTimeoutError",
                    }
                )
                if not coordinated or not transient:
                    raise
                if ordinal == 2:
                    raise DockflowError(
                        "Cache storage finalization is unavailable",
                        "ARTIFACT_UNAVAILABLE",
                        503,
                    ) from None
                time.sleep(0.05 * 2**ordinal)

    def _put_cache_object(
        self, client, bucket: str, key: str, body, checksum: str
    ) -> None:
        """Recover an ambiguous conditional PUT by verifying identical bytes."""
        try:
            client.put_object(Bucket=bucket, Key=key, Body=body, IfNoneMatch="*")
        except Exception as exc:
            code = str(getattr(exc, "response", {}).get("Error", {}).get("Code", ""))
            if code not in {"412", "PreconditionFailed"}:
                raise
            response = client.get_object(Bucket=bucket, Key=key)
            observed = hashlib.sha256()
            with response["Body"] as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    observed.update(chunk)
            if observed.hexdigest() != checksum:
                raise DockflowError(
                    "Immutable cache object differs", "CACHE_CONFLICT", 409
                ) from None

    def _publish_managed_once(
        self, source: Path | None, descriptor: dict[str, Any]
    ) -> None:
        self._set_managed_path(descriptor)
        artifact_id = descriptor["artifact_id"]
        content_path = self.managed_content_path(descriptor)
        recovery_key = artifact_id
        records = self.artifact_records()
        records.put(
            "pipeline-claims", content_path, json_bytes({"artifact_id": artifact_id})
        )
        completed = records.get("pipeline-descriptors", recovery_key)

        def complete():
            portable = {
                key: value
                for key, value in descriptor.items()
                if key not in {"uri", "content_uri", "descriptor_uri"}
            }
            records.put("pipeline-descriptors", recovery_key, json_bytes(portable))

        if self.backend == "filesystem":
            destination = self.managed_root / content_path
            parent = destination.parent
            _no_links(destination)
            if source is not None and (
                source == destination
                or destination.is_relative_to(source)
                or source.is_relative_to(destination)
            ):
                raise DockflowError("Managed artifact destination overlaps its source")
            coordinated = descriptor.get("storage_layout") == "cache-v1"
            if coordinated and (destination.exists() or completed is not None):
                descriptor["content_uri"] = (
                    destination.as_uri() if source is not None else None
                )
                if source is not None and inventory(destination) != {
                    key: descriptor[key]
                    for key in (
                        "payload_kind",
                        "inventory",
                        "size_bytes",
                        "fingerprint",
                    )
                }:
                    raise DockflowError(
                        "Finalized cache bytes differ", "CACHE_CONFLICT", 409
                    )
                if os.name != "nt":
                    for ancestor in (parent, *parent.parents):
                        if not ancestor.is_relative_to(self.managed_root):
                            break
                        fsync_directory(ancestor)
                complete()
                return
            if destination.exists() or completed is not None:
                raise DockflowError(
                    "Artifact destination already exists", code="CONFLICT", status=409
                )
            parent.mkdir(parents=True, exist_ok=True)
            temporary = parent / f".staging-{artifact_id}-{uuid.uuid4().hex}"
            try:
                if source is not None:
                    _copy_payload(
                        source,
                        temporary,
                        {
                            key: descriptor[key]
                            for key in (
                                "payload_kind",
                                "inventory",
                                "size_bytes",
                                "fingerprint",
                            )
                        },
                    )
                    descriptor["content_uri"] = destination.as_uri()
                    if descriptor.get("storage_layout") == "cache-v1":
                        paths = (
                            [temporary, *temporary.rglob("*")]
                            if temporary.is_dir()
                            else [temporary]
                        )
                        for item in paths:
                            item.chmod(0o555 if item.is_dir() else 0o444)

                        for item in sorted(
                            paths, key=lambda item: len(item.parts), reverse=True
                        ):
                            if item.is_dir():
                                fsync_directory(item)
                            else:
                                with item.open("rb") as stream:
                                    os.fsync(stream.fileno())
                    os.rename(temporary, destination)
                if os.name != "nt":
                    fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                    try:
                        os.fsync(fd)
                    finally:
                        os.close(fd)
                    if descriptor.get("storage_layout") == "cache-v1":
                        for ancestor in parent.parents:
                            if not ancestor.is_relative_to(self.managed_root):
                                break
                            fsync_directory(ancestor)
                complete()
            finally:
                if temporary.is_dir():
                    shutil.rmtree(temporary)
                else:
                    temporary.unlink(missing_ok=True)
        elif self.backend == "s3":
            client = self._s3()
            bucket = self.options["bucket"]
            key = self.object_key(content_path)
            occupied = (
                any(
                    item["Key"] == key or item["Key"].startswith(key + "/")
                    for page in client.get_paginator("list_objects_v2").paginate(
                        Bucket=bucket, Prefix=key
                    )
                    for item in page.get("Contents", [])
                )
                or completed is not None
            )
            if occupied and descriptor.get("storage_layout") != "cache-v1":
                raise DockflowError(
                    "Managed S3 artifact prefix already exists",
                    code="CONFLICT",
                    status=409,
                )

            def upload(path, object_key):
                if descriptor.get("storage_layout") != "cache-v1":
                    client.upload_file(str(path), bucket, object_key)
                    return
                if path.stat().st_size > 5 * 1024**3:
                    raise DockflowError(
                        "Coordinated S3 cache files are limited to 5 GiB; disable caching for larger outputs",
                        "CACHE_VALIDATION_FAILED",
                        409,
                    )
                with path.open("rb") as stream:
                    self._put_cache_object(
                        client, bucket, object_key, stream, _hash_file(path)[1]
                    )

            if source is not None:
                descriptor["content_uri"] = f"s3://{bucket}/{key}"
                if descriptor["payload_kind"] == "file":
                    upload(source, key)
                else:
                    for entry in descriptor["inventory"]:
                        if entry["kind"] == "file":
                            upload(source / entry["path"], key + "/" + entry["path"])
            with tempfile.TemporaryDirectory(
                prefix="dockflow-verify-upload-"
            ) as directory:
                if source is not None:
                    target = Path(directory) / "payload"
                    self._download_descriptor(descriptor, target)
                    if inventory(target) != {
                        key: descriptor[key]
                        for key in (
                            "payload_kind",
                            "inventory",
                            "size_bytes",
                            "fingerprint",
                        )
                    }:
                        raise DockflowError(
                            "Managed S3 publication failed integrity verification",
                            code="CONFLICT",
                            status=409,
                        )
            complete()
        else:
            raise DockflowError(f"Unsupported artifact backend: {self.backend}")

    def verify_cache(self, manifest: dict, storage_identity: str) -> dict:
        """Verify the entire portable output set before binding any local output."""
        from .cache_storage import local_descriptors, validate_manifest

        validate_manifest(
            manifest, storage_identity, manifest["producer"]["attempt_id"]
        )
        descriptors = local_descriptors(manifest, self)
        for descriptor in descriptors.values():
            self._validate_inventory(descriptor)
            try:
                if descriptor["payload_kind"] == "metadata":
                    expected = digest(
                        {
                            "kind": "metadata",
                            "type": descriptor["type"],
                            "metadata": descriptor["metadata"],
                        }
                    )
                    if descriptor["fingerprint"]["value"] != expected:
                        raise DockflowError(
                            "Cache metadata digest differs", "CACHE_CORRUPT", 409
                        )
                else:
                    with tempfile.TemporaryDirectory(
                        prefix="dockflow-cache-read-"
                    ) as directory:
                        target = Path(directory) / "payload"
                        self._download_descriptor(descriptor, target)
                        if inventory(target) != {
                            key: descriptor[key]
                            for key in (
                                "payload_kind",
                                "inventory",
                                "size_bytes",
                                "fingerprint",
                            )
                        }:
                            raise DockflowError(
                                "Cache content digest differs", "CACHE_CORRUPT", 409
                            )
            except FileNotFoundError:
                raise DockflowError(
                    "Published cache bytes are missing", "CACHE_CORRUPT", 409
                ) from None
            except DockflowError as exc:
                if exc.code in {"NOT_FOUND", "CACHE_CORRUPT", "CONFLICT"}:
                    raise DockflowError(
                        "Published cache bytes failed verification",
                        "CACHE_CORRUPT",
                        409,
                    ) from None
                raise DockflowError(
                    "Cache storage is inaccessible", "ARTIFACT_UNAVAILABLE", 503
                ) from None
            except Exception as exc:
                code = str(
                    getattr(exc, "response", {}).get("Error", {}).get("Code", "")
                )
                if code in {"404", "NoSuchKey", "NotFound"}:
                    raise DockflowError(
                        "Published cache bytes are missing", "CACHE_CORRUPT", 409
                    ) from None
                raise DockflowError(
                    "Cache storage is inaccessible", "ARTIFACT_UNAVAILABLE", 503
                ) from None
        return descriptors

    def get(self, artifact_id: str) -> dict[str, Any]:
        descriptor = self.control.get("artifacts", artifact_id)
        validate_type(descriptor["type"])
        validate_metadata(descriptor["metadata"])
        if (
            descriptor.get("project_id") != self.control.project_id
            or descriptor.get("schema_version") != 1
        ):
            raise DockflowError(
                "Incompatible artifact descriptor", code="CONFLICT", status=409
            )
        self._validate_inventory(descriptor)
        return descriptor

    def list(self) -> list[dict[str, Any]]:
        return self.control.list("artifacts")

    def _validate_inventory(self, descriptor: dict[str, Any]) -> None:
        seen: set[str] = set()
        paths: list[PurePosixPath] = []
        for entry in descriptor["inventory"]:
            path = _relative_path(entry["path"])
            key = os.path.normcase(str(path))
            if key in seen or any(
                path == ancestor or ancestor in path.parents and old["kind"] == "file"
                for ancestor, old in zip(paths, descriptor["inventory"], strict=False)
            ):
                raise DockflowError(
                    "Artifact inventory has duplicate/colliding paths",
                    code="CONFLICT",
                    status=409,
                )
            seen.add(key)
            paths.append(path)
            if entry["kind"] not in {"file", "directory"}:
                raise DockflowError(
                    "Invalid artifact inventory kind", code="CONFLICT", status=409
                )

    def _download_descriptor(
        self, descriptor: dict[str, Any], destination: Path
    ) -> None:
        uri = descriptor["content_uri"]
        scheme, bucket, parts = _uri_parts(uri)
        if scheme == "file":
            source = Path(unquote(urlsplit(uri).path))
            snapshot = {
                key: descriptor[key]
                for key in ("payload_kind", "inventory", "size_bytes", "fingerprint")
            }
            _copy_payload(source, destination, snapshot)
            return
        key = "/".join(parts)
        client = self._s3()
        if descriptor["payload_kind"] == "file":
            destination.parent.mkdir(parents=True, exist_ok=True)
            client.download_file(bucket, key, str(destination))
        else:
            destination.mkdir(parents=True)
            for entry in descriptor["inventory"]:
                target = destination.joinpath(*_relative_path(entry["path"]).parts)
                if entry["kind"] == "directory":
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    client.download_file(
                        bucket, key.rstrip("/") + "/" + entry["path"], str(target)
                    )

    def materialize(self, artifact_id: str, destination: Path) -> dict[str, Any]:
        descriptor = self.get(artifact_id)
        if descriptor["publication_state"] != "committed":
            raise DockflowError(
                "Artifact output set has not been committed",
                code="CONFLICT",
                status=409,
            )
        if descriptor["payload_kind"] == "metadata":
            return descriptor
        destination = Path(destination).absolute()
        _no_links(destination)
        if destination.exists():
            raise DockflowError(
                "Artifact materialization destination already exists",
                code="CONFLICT",
                status=409,
            )
        if self.backend == "filesystem" and destination.is_relative_to(
            self.managed_root
        ):
            raise DockflowError(
                "Materialization destination overlaps durable artifact storage"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(
            f".{destination.name}.staging-{uuid.uuid4().hex}"
        )
        try:
            self._download_descriptor(descriptor, temporary)
            snapshot = inventory(temporary)
            if snapshot != {
                key: descriptor[key]
                for key in ("payload_kind", "inventory", "size_bytes", "fingerprint")
            }:
                raise DockflowError(
                    "Artifact payload is corrupt or its external source has changed",
                    code="CONFLICT",
                    status=409,
                )
            os.rename(temporary, destination)
            return descriptor
        finally:
            if temporary.is_dir():
                shutil.rmtree(temporary)
            else:
                temporary.unlink(missing_ok=True)

    def verify(
        self, artifact_id: str | dict[str, Any], verify_contents: bool = True
    ) -> dict[str, Any]:
        public_id: str = (
            artifact_id if isinstance(artifact_id, str) else artifact_id["artifact_id"]
        )
        descriptor = self.get(public_id)
        result = {
            "artifact_id": public_id,
            "availability": "unknown",
            "verified": False,
            "reason": None,
        }
        if descriptor["payload_kind"] == "metadata":
            fingerprint = digest(
                {
                    "kind": "metadata",
                    "type": descriptor["type"],
                    "metadata": descriptor["metadata"],
                }
            )
            result.update(
                availability="available"
                if fingerprint == descriptor["fingerprint"]["value"]
                else "corrupt",
                verified=True,
            )
            return result
        try:
            if verify_contents:
                with tempfile.TemporaryDirectory(
                    prefix="dockflow-check-artifact-"
                ) as directory:
                    target = Path(directory) / "payload"
                    self._download_descriptor(descriptor, target)
                    if inventory(target) != {
                        key: descriptor[key]
                        for key in (
                            "payload_kind",
                            "inventory",
                            "size_bytes",
                            "fingerprint",
                        )
                    }:
                        raise DockflowError(
                            "Artifact fingerprint mismatch", code="CONFLICT", status=409
                        )
                result.update(availability="available", verified=True)
            else:
                scheme, bucket, parts = _uri_parts(descriptor["content_uri"])
                if scheme == "file":
                    Path(unquote(urlsplit(descriptor["content_uri"]).path)).stat(
                        follow_symlinks=False
                    )
                elif descriptor["payload_kind"] == "file":
                    self._s3().head_object(Bucket=bucket, Key="/".join(parts))
                else:
                    # The known descriptor inventories exactly the intended snapshot.
                    for entry in descriptor["inventory"]:
                        if entry["kind"] == "file":
                            self._s3().head_object(
                                Bucket=bucket, Key="/".join(parts) + "/" + entry["path"]
                            )
                result["availability"] = "available"
        except FileNotFoundError:
            result.update(availability="missing", reason="Artifact payload is missing")
        except PermissionError:
            result.update(
                availability="inaccessible", reason="Artifact payload is inaccessible"
            )
        except DockflowError as exc:
            result.update(
                availability="missing"
                if exc.code == "NOT_FOUND"
                else "inaccessible"
                if exc.code in {"PERMISSION_DENIED", "UNAVAILABLE"}
                else "corrupt",
                reason=str(exc),
            )
        except Exception as exc:
            response = getattr(exc, "response", {})
            code = str(response.get("Error", {}).get("Code", ""))
            result.update(
                availability="missing"
                if code in {"404", "NoSuchKey", "NotFound"}
                else "inaccessible",
                reason="Object storage content is missing"
                if code in {"404", "NoSuchKey", "NotFound"}
                else "Object storage is inaccessible",
            )
        return result

    def pin(self, artifact_id: str, pinned: bool = True) -> dict[str, Any]:
        self.control.require_owner()
        descriptor = self.get(artifact_id)
        if descriptor.get("pinned", False) != pinned:
            descriptor = {**descriptor, "pinned": pinned}
            self.control.put("artifacts", descriptor)
        return descriptor
