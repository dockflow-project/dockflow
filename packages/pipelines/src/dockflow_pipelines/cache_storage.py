"""Portable complete output manifests over Dockflow's immutable managed store."""

from __future__ import annotations

import copy
import re
import uuid
from typing import Any

from dockflow_database.errors import DockflowError

from .canonical import digest, validate_json

MANIFEST_FORMAT = "dockflow-cache-manifest-v1"
VALIDATION_VERSION = "dockflow-output-set-v1"
CACHE_PREFIX = ".dockflow/dockflow-pipelines/cache-v1/"


def validate_manifest(manifest: dict, storage_identity: str, attempt_id: str) -> None:
    from .artifacts import _relative_path, validate_metadata, validate_type

    try:
        validate_json(manifest)
        if (
            set(manifest)
            != {
                "format",
                "validation_version",
                "artifact_id",
                "storage_identity",
                "producer",
                "outputs",
                "parameters",
                "contract",
                "signature",
            }
            or manifest["format"] != MANIFEST_FORMAT
            or manifest["validation_version"] != VALIDATION_VERSION
            or manifest["storage_identity"] != storage_identity
            or manifest["producer"]["attempt_id"] != attempt_id
            or manifest["artifact_id"]
            != "artifact_"
            + str(uuid.UUID(manifest["artifact_id"].removeprefix("artifact_")))
            or uuid.UUID(manifest["artifact_id"].removeprefix("artifact_")).version != 4
            or set(manifest["outputs"])
            != set(manifest["contract"].get("artifacts", {}))
            or set(manifest["parameters"])
            != set(manifest["contract"].get("parameters", {}))
            or not re.fullmatch(r"[0-9a-f]{64}", manifest["signature"])
        ):
            raise ValueError("Manifest identity or complete output contract differs")
        for field in ("run_id", "task_id", "attempt_id"):
            value = manifest["producer"][field]
            prefix = field.removesuffix("_id") + "_"
            if (
                not value.startswith(prefix)
                or uuid.UUID(value[len(prefix) :]).version != 4
            ):
                raise ValueError("Invalid producer identity")
        ids = set()
        for name, descriptor in manifest["outputs"].items():
            if descriptor["artifact_id"] in ids:
                raise ValueError("Duplicate output identity")
            ids.add(descriptor["artifact_id"])
            path = str(_relative_path(descriptor["managed_path"]))
            if (
                not path.startswith(CACHE_PREFIX)
                or str(uuid.UUID(attempt_id.removeprefix("attempt_")))
                not in path.split("/")
                or descriptor["storage_layout"] != "cache-v1"
                or descriptor["publication_state"] != "committed"
                or descriptor["ownership"] != "managed"
                or descriptor["producer"]["output_name"] != name
                or any(
                    descriptor["producer"][field] != manifest["producer"][field]
                    for field in ("run_id", "task_id", "attempt_id")
                )
                or any(
                    descriptor.get(field)
                    for field in ("uri", "content_uri", "descriptor_uri", "source_uri")
                )
                or descriptor["payload_kind"] not in {"file", "directory", "metadata"}
                or not re.fullmatch(r"[0-9a-f]{64}", descriptor["fingerprint"]["value"])
            ):
                raise ValueError("Unsafe or inconsistent cache output descriptor")
            validate_type(descriptor["type"])
            expected = manifest["contract"]["artifacts"][name]["artifactType"]
            if descriptor["type"] != {
                "schema_title": expected["schemaTitle"],
                "schema_version": expected.get("schemaVersion", "0.0.1"),
            }:
                raise ValueError("Cache output type differs from contract")
            validate_metadata(descriptor["metadata"])
            for item in descriptor["inventory"]:
                if item.get("path"):
                    _relative_path(item["path"])
        from .definitions import validate_parameter

        for name, value in manifest["parameters"].items():
            validate_parameter(value, manifest["contract"]["parameters"][name], name)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise DockflowError(
            "Invalid complete cache manifest", "CACHE_VALIDATION_FAILED", 409
        ) from exc


def make_manifest(
    published: dict[str, dict[str, Any]],
    parameters: dict,
    contract: dict,
    producer: dict,
    signature: str,
    storage_identity: str,
) -> dict:
    outputs = copy.deepcopy(published)
    for descriptor in outputs.values():
        # A shared descriptor carries a storage-relative locator. Each owner
        # reconstructs its own URI view; registry records never embed local roots.
        for field in ("uri", "descriptor_uri", "content_uri"):
            descriptor.pop(field, None)
        descriptor.update(publication_state="committed")
    manifest = {
        "format": MANIFEST_FORMAT,
        "validation_version": VALIDATION_VERSION,
        "artifact_id": "artifact_" + str(uuid.uuid4()),
        "storage_identity": storage_identity,
        "producer": producer,
        "outputs": outputs,
        "parameters": parameters,
        "contract": contract,
        "signature": signature,
    }
    validate_manifest(manifest, storage_identity, producer["attempt_id"])
    return manifest


def local_descriptors(manifest: dict, artifact_store) -> dict:
    descriptors = copy.deepcopy(manifest["outputs"])
    for descriptor in descriptors.values():
        path = artifact_store.managed_content_path(descriptor)
        uri = f"dockflow://{artifact_store.control.project_id}/artifacts/{descriptor['artifact_id']}"
        descriptor.update(descriptor_uri=uri, uri=uri)
        descriptor["content_uri"] = (
            None
            if descriptor["payload_kind"] == "metadata"
            else (
                (artifact_store.managed_root / path).as_uri()
                if artifact_store.backend == "filesystem"
                else "s3://"
                + artifact_store.options["bucket"]
                + "/"
                + artifact_store.object_key(path)
            )
        )
        descriptor["cache_origin"] = {
            "artifact_id": manifest["artifact_id"],
            "manifest_digest": digest(manifest),
            "producer_attempt_id": manifest["producer"]["attempt_id"],
        }
    return descriptors
