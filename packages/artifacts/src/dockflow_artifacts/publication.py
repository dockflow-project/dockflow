"""Public publication API and versioned completion records."""

from __future__ import annotations

import functools
import hashlib
import io
import json
import re
import shutil
import string
import tempfile
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from dockflow_core import Database, DockflowError
from dockflow_core.database import configured_database

from ._paths import canonical, file_info, inventory, no_links, relative
from ._storage import FileStore, make_store
from .errors import ArtifactError, ConflictError, IntegrityError
from .persistence import ArtifactRecords


@dataclass(frozen=True)
class Publication:
    """Completed artifact address and integrity/provenance metadata."""

    uri: str
    manifest_uri: str
    digest: str
    kind: str
    artifact_type: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a detached JSON-compatible receipt, without credentials."""
        return asdict(self)


def format_path(template: str, **values: str | int) -> str:
    """Expand simple named fields; each value must be a single safe path segment."""
    for _, field, spec, conversion in string.Formatter().parse(template):
        if field is None:
            continue
        if not field.isidentifier() or spec or conversion or field not in values:
            raise ArtifactError("Path templates require provided, simple named fields")
        value = str(values[field])
        if "/" in relative(value):
            raise ArtifactError("Template values must each be a single path segment")
    return relative(template.format(**values))


def step_path(
    filename: str,
    *,
    step_number: int,
    component_name: str,
    pipeline_name: str,
    publication_id: str,
    step_digits: int,
    exploration_id: str = "global",
) -> str:
    """Name an output by context, padded step and deterministic publication ID.

    The pipeline supplies execution order; the component wrapper supplies its
    name and filename. This helper does not inspect a graph or allocate counters.
    """
    if type(step_number) is not int or step_number < 1:
        raise ArtifactError("Step number must be a positive integer")
    if type(step_digits) is not int or not 1 <= step_digits <= 12:
        raise ArtifactError("Step digits must be an integer from 1 to 12")
    if not isinstance(publication_id, str) or not re.fullmatch(
        r"[a-f0-9]{64}", publication_id
    ):
        raise ArtifactError("Publication ID must be a full lowercase SHA-256 digest")
    for value in (filename, component_name, exploration_id, pipeline_name):
        if not isinstance(value, str) or "/" in relative(value):
            raise ArtifactError("Step path values must each be a single path segment")
    return format_path(
        "{exploration}/{pipeline}/step_{number}__{component}__{identity}/{filename}",
        exploration=exploration_id,
        pipeline=pipeline_name,
        number=str(step_number).zfill(step_digits),
        component=component_name,
        identity=publication_id,
        filename=filename,
    )


def _publication_errors(method):
    @functools.wraps(method)
    def call(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except DockflowError as error:
            exception = ConflictError if error.code == "CONFLICT" else ArtifactError
            raise exception(error.message) from None
        except OSError:
            raise ArtifactError(
                "Artifact publication I/O failed; check storage access and durability"
            ) from None

    return call


class Publisher:
    """Publish immutable local contents below an explicitly configured storage root."""

    @_publication_errors
    def __init__(
        self,
        root: str | Path,
        *,
        s3: dict[str, Any] | None = None,
        database: dict | Database | None = None,
        project_id: str = "default",
    ):
        if not isinstance(project_id, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", project_id
        ):
            raise ArtifactError(
                "Project ID must contain safe letters, digits, _, - or ."
            )
        options = dict(s3 or {})
        allowed = {
            "endpoint_url",
            "region_name",
            "aws_access_key_id",
            "aws_secret_access_key",
            "aws_session_token",
            "verify",
        }
        if set(options) - allowed:
            raise ArtifactError("Unknown S3 configuration field")
        for key, value in options.items():
            if key == "verify":
                if not isinstance(value, bool | str):
                    raise ArtifactError(
                        "S3 verify must be a boolean or certificate path"
                    )
            elif not isinstance(value, str) or not value:
                raise ArtifactError("S3 configuration fields must be nonempty strings")
        if "endpoint_url" in options:
            endpoint = urlsplit(options["endpoint_url"])
            if (
                endpoint.scheme not in {"http", "https"}
                or not endpoint.hostname
                or endpoint.username
                or endpoint.password
                or endpoint.query
                or endpoint.fragment
            ):
                raise ArtifactError(
                    "S3 endpoint must be HTTP(S) without credentials or query"
                )
        self._store = make_store(root, options)
        if database is None:
            if not isinstance(self._store, FileStore):
                raise ArtifactError(
                    "Remote artifact storage requires explicit database configuration"
                )
            database = {
                "backend": "sqlite",
                "database": str(self._store.root.parent / ".dockflow/state.sqlite"),
            }
        self.database = configured_database(database)
        if (
            isinstance(self._store, FileStore)
            and self.database.backend == "sqlite"
            and Path(self.database.options["database"]).is_relative_to(self._store.root)
        ):
            raise ArtifactError("SQLite database must be outside the artifact root")
        self.project_id = project_id

    @classmethod
    def from_config(cls, path: str | Path) -> Publisher:
        """Read schema-version 2 JSON configuration explicitly at invocation time."""
        raw = Path(path).read_bytes()
        if len(raw) > 1024 * 1024:
            raise ArtifactError("Publication configuration is too large")
        try:
            config = json.loads(raw)
        except (ValueError, UnicodeError):
            raise ArtifactError(
                "Publication configuration must be valid JSON"
            ) from None
        if (
            not isinstance(config, dict)
            or set(config) - {"schema_version", "root", "s3", "database", "project_id"}
            or type(config.get("schema_version")) is not int
            or config["schema_version"] != 2
            or not isinstance(config.get("root"), str)
            or ("s3" in config and not isinstance(config["s3"], dict))
        ):
            raise ArtifactError(
                "Expected schema_version=2, root, database and optional s3/project_id configuration"
            )
        options = config.get("database")
        if (
            isinstance(options, dict)
            and options.get("backend") == "sqlite"
            and isinstance(options.get("database"), str)
        ):
            options = {
                **options,
                "database": str(
                    (Path(path).absolute().parent / options["database"]).absolute()
                ),
            }
        return cls(
            config["root"],
            s3=config.get("s3"),
            database=options,
            project_id=config.get("project_id", "default"),
        )

    def _records(self, *, create: bool) -> ArtifactRecords:
        marker = ".dockflow/storage.json"
        raw = self._store.get(marker)
        if raw is None and create:
            self._store.put(
                marker,
                io.BytesIO(
                    canonical(
                        {
                            "format": "dockflow-artifact-store-v1",
                            "identity": str(uuid.uuid4()),
                        }
                    )
                ),
            )
            raw = self._store.get(marker)
        try:
            value = json.loads(raw or b"null")
            if value["format"] != "dockflow-artifact-store-v1":
                raise ValueError
            identity = str(uuid.UUID(value["identity"]))
        except (ValueError, TypeError, KeyError, AttributeError):
            raise IntegrityError(
                "Artifact storage identity is missing or invalid"
            ) from None
        if create and isinstance(self._store, FileStore):
            self._store.sync(marker)
        return ArtifactRecords(self.database, self.project_id, identity)

    def _receipt(self, manifest: dict[str, Any]) -> Publication:
        base = self._store.uri
        return Publication(
            uri=base + "/" + manifest["destination"],
            manifest_uri=f"dockflow://{self.project_id}/publications/{self._records(create=False).storage_id}/{hashlib.sha256(manifest['destination'].encode()).hexdigest()}",
            digest=manifest["digest"],
            kind=manifest["kind"],
            artifact_type=manifest["artifact_type"],
            metadata=json.loads(canonical(manifest["metadata"])),
        )

    def _check_layout(self) -> None:
        if self._store.has_prefix(".dockflow-artifacts") or self._store.has_prefix(
            ".dockflow/dockflow-artifacts"
        ):
            raise ArtifactError(
                "Legacy .dockflow-artifacts records found; use a fresh publication "
                "root or reset disposable artifacts before using the new layout"
            )

    def _verify_contents(self, manifest: dict[str, Any]) -> None:
        destination = relative(manifest["destination"])
        expected = []
        for item in manifest["entries"]:
            suffix = relative(item["path"]) if item["path"] else ""
            key = destination + ("/" + suffix if suffix else "")
            expected.append(key)
            if self._store.info(key) != (item["size"], item["sha256"]):
                raise IntegrityError(
                    "Published contents do not match their recorded SHA-256"
                )
        if manifest["kind"] == "directory" and self._store.files(destination) != sorted(
            expected
        ):
            raise IntegrityError("Published directory inventory changed")

    @_publication_errors
    def verify(self, destination: str) -> Publication:
        """Verify all payload bytes of a completed publication and return its receipt."""
        destination = relative(destination)
        self._check_layout()
        raw = self._records(create=False).get("publication-manifests", destination)
        if raw is None:
            raise IntegrityError("Publication has no completion manifest")
        try:
            manifest = json.loads(raw)
            if (
                manifest["schema_version"] != 1
                or manifest["destination"] != destination
                or manifest["kind"] not in {"file", "directory"}
                or not manifest["entries"]
                or not re.fullmatch(r"[a-f0-9]{64}", manifest["digest"])
            ):
                raise ValueError
            for entry in manifest["entries"]:
                if type(entry["size"]) is not int or entry["size"] < 0:
                    raise ValueError
                if not re.fullmatch(r"[a-f0-9]{64}", entry["sha256"]):
                    raise ValueError
            if manifest["kind"] == "file":
                if (
                    len(manifest["entries"]) != 1
                    or manifest["entries"][0]["path"] != ""
                ):
                    raise ValueError
                digest = manifest["entries"][0]["sha256"]
            else:
                if any(not entry["path"] for entry in manifest["entries"]):
                    raise ValueError
                digest = hashlib.sha256(canonical(manifest["entries"])).hexdigest()
            if digest != manifest["digest"]:
                raise ValueError
            self._verify_contents(manifest)
            return self._receipt(manifest)
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, ArtifactError):
                raise
            raise IntegrityError("Invalid publication manifest") from None

    @_publication_errors
    def publish(
        self,
        source: str | Path,
        destination: str,
        *,
        artifact_type: str = "system.Artifact",
        metadata: dict[str, Any] | None = None,
    ) -> Publication:
        """Publish once, resume an identical incomplete write, or verify an identical result."""
        destination = relative(destination)
        self._check_layout()
        source = Path(source).absolute()
        no_links(source)
        if isinstance(self._store, FileStore):
            target = self._store.path(destination)
            if source == target or source in target.parents or target in source.parents:
                raise ArtifactError("Source and destination cannot overlap")
        if not isinstance(artifact_type, str) or not artifact_type:
            raise ArtifactError("Artifact type must be a nonempty schema title")
        if metadata is not None and not isinstance(metadata, dict):
            raise ArtifactError("Artifact metadata must be a JSON object")
        kind, entries, digest = inventory(source)
        manifest = {
            "schema_version": 1,
            "destination": destination,
            "kind": kind,
            "entries": entries,
            "digest": digest,
            "artifact_type": artifact_type,
            "metadata": json.loads(canonical(metadata or {})),
        }
        encoded = canonical(manifest)
        if len(encoded) > 16 * 1024 * 1024:
            raise ArtifactError("Publication inventory exceeds the 16 MiB record limit")
        # The whole namespace reservation is atomic; no SQL transaction spans uploads.
        records = self._records(create=True)
        parts = destination.split("/")
        claims = {
            "/".join(parts[:index]): canonical(
                {
                    "schema_version": 1,
                    "kind": "namespace",
                    "path": "/".join(parts[:index]),
                }
            )
            for index in range(1, len(parts))
        }
        claims[destination] = encoded
        records.put_many("publication-claims", claims)
        completed = records.get("publication-manifests", destination)
        if completed is not None:
            if completed != encoded:
                raise IntegrityError(
                    "Completion manifest differs from the reserved publication"
                )
            return self.verify(destination)
        for entry in entries:
            path = source / entry["path"] if kind == "directory" else source
            key = destination + ("/" + entry["path"] if entry["path"] else "")
            no_links(path)
            # Snapshot one file at a time; conditional uploads never stream from
            # a mutable producer file or buffer a whole model in memory.
            with tempfile.TemporaryDirectory(prefix="dockflow-artifacts-") as temporary:
                staged = Path(temporary) / "content"
                shutil.copyfile(path, staged, follow_symlinks=False)
                if file_info(staged) != (entry["size"], entry["sha256"]):
                    raise IntegrityError("Source changed during publication")
                with staged.open("rb") as stream:
                    self._store.put(key, stream)
                if self._store.info(key) != (entry["size"], entry["sha256"]):
                    raise IntegrityError(
                        "Destination has different bytes; nothing was overwritten"
                    )
        if inventory(source) != (kind, entries, digest):
            raise IntegrityError("Source changed during publication")
        self._verify_contents(manifest)
        records.put("publication-manifests", destination, encoded)
        return self._receipt(manifest)
