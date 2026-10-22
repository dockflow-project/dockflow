"""Immutable typed artifact snapshots with filesystem and S3-compatible storage."""

from __future__ import annotations

import hashlib
import importlib
import os
import re
import shutil
import stat
import tempfile
import uuid
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

from .canonical import digest, json_bytes, loads, validate_json
from .errors import DockflowError
from .metadata import ControlStore, atomic_write, new_id, utc_now

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
    path = path.absolute()
    for candidate in (path, *path.parents):
        if candidate.is_symlink():
            raise DockflowError(
                "Artifact paths cannot contain symlinks", code="INVALID_ARGUMENT"
            )


def _hash_file(path: Path) -> tuple[int, str]:
    _no_links(path)
    before = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):
        raise DockflowError("Artifact payloads must be regular files/directories")
    hasher = hashlib.sha256()
    size = 0
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
        while chunk := stream.read(1024 * 1024):
            hasher.update(chunk)
            size += len(chunk)
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
    return size, hasher.hexdigest()


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
                config=config(s3={"addressing_style": "path"}),
            )
        return self._client

    def managed_paths(self, descriptor: dict[str, Any]) -> tuple[str, str]:
        """Content and recovery paths relative to the configured managed root.

        Old descriptors remain readable/restorable without rewriting their URIs.
        S3's old implicit managed/ child was part of that historical layout.
        """
        artifact_id = _storage_segment(descriptor["artifact_id"])
        layout = descriptor.get("storage_layout")
        if layout in {"kfp-v1", "kfp-v2"}:
            content = str(_relative_path(descriptor["managed_path"]))
            namespace = "artifacts" if layout == "kfp-v1" else "dockflow-pipelines"
            return content, f".dockflow/{namespace}/{artifact_id}/artifact.json"
        if descriptor.get("storage_layout") is not None:
            raise DockflowError("Unsupported managed artifact storage layout")
        parent = f"{'managed/' if self.backend == 's3' else ''}{artifact_id}"
        return f"{parent}/payload", f"{parent}/artifact.json"

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
        descriptor.update(storage_layout="kfp-v2", managed_path=relative)

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
        descriptor_uri = (
            self.control.state / "artifacts" / f"{artifact_id}.json"
        ).as_uri()
        return {
            "schema_version": 1,
            "kind": "artifact",
            "project_id": self.control.project_id,
            "artifact_id": artifact_id,
            "type": dict(artifact_type),
            "origin": origin,
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
        self._set_managed_path(descriptor)
        artifact_id = descriptor["artifact_id"]
        content_path, recovery_path = self.managed_paths(descriptor)
        if self.backend == "filesystem":
            destination = self.managed_root / content_path
            recovery = self.managed_root / recovery_path
            parent = destination.parent
            _no_links(destination)
            _no_links(recovery)
            if source is not None and (
                source == destination
                or destination.is_relative_to(source)
                or source.is_relative_to(destination)
            ):
                raise DockflowError("Managed artifact destination overlaps its source")
            if destination.exists() or recovery.exists():
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
                    os.rename(temporary, destination)
                atomic_write(recovery, json_bytes(descriptor), exclusive=True)
                if os.name != "nt":
                    fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                    try:
                        os.fsync(fd)
                    finally:
                        os.close(fd)
            finally:
                if temporary.is_dir():
                    shutil.rmtree(temporary)
                else:
                    temporary.unlink(missing_ok=True)
        elif self.backend == "s3":
            client = self._s3()
            bucket = self.options["bucket"]
            key = self.object_key(content_path)
            recovery_key = self.object_key(recovery_path)
            if any(
                item["Key"] == key or item["Key"].startswith(key + "/")
                for page in client.get_paginator("list_objects_v2").paginate(
                    Bucket=bucket, Prefix=key
                )
                for item in page.get("Contents", [])
            ) or client.list_objects_v2(
                Bucket=bucket, Prefix=recovery_key, MaxKeys=1
            ).get("KeyCount", 0):
                raise DockflowError(
                    "Managed S3 artifact prefix already exists",
                    code="CONFLICT",
                    status=409,
                )
            if source is not None:
                descriptor["content_uri"] = f"s3://{bucket}/{key}"
                if descriptor["payload_kind"] == "file":
                    client.upload_file(str(source), bucket, key)
                else:
                    for entry in descriptor["inventory"]:
                        if entry["kind"] == "file":
                            client.upload_file(
                                str(source / entry["path"]),
                                bucket,
                                key + "/" + entry["path"],
                            )
            # This recognized recovery descriptor carries directory/empty-root kind.
            client.put_object(
                Bucket=bucket,
                Key=recovery_key,
                Body=json_bytes(descriptor),
                ContentType="application/json",
            )
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
        else:
            raise DockflowError(f"Unsupported artifact backend: {self.backend}")

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
        if (
            self.backend == "filesystem"
            and destination.is_relative_to(self.managed_root)
        ) or destination.is_relative_to(self.control.state / "artifacts"):
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
