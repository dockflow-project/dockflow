"""Opt-in qualification against a real conditional S3-compatible service."""

import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from dockflow_artifacts import ConflictError, IntegrityError, Publisher

CONFIG = os.environ.get("DOCKFLOW_TEST_ARTIFACT_S3_CONFIG")
pytestmark = [
    pytest.mark.s3,
    pytest.mark.skipif(not CONFIG, reason="Set DOCKFLOW_TEST_ARTIFACT_S3_CONFIG"),
]


def test_live_conditional_publication(tmp_path, monkeypatch):
    """Create and remove only a unique test prefix inside the configured root."""
    config = json.loads(Path(CONFIG).read_text())
    root = config["root"].rstrip("/") + "/qualification-" + uuid.uuid4().hex
    publisher = Publisher(root, s3=config.get("s3"))
    store = publisher._store
    source = tmp_path / "bundle"
    source.mkdir()
    (source / "one.json").write_text('{"coefficient":2}')
    (source / "two.json").write_bytes(b"")
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            receipts = list(
                pool.map(
                    lambda _: publisher.publish(source, "models/v1"),
                    range(4),
                )
            )
        assert all(receipt == receipts[0] for receipt in receipts)
        assert publisher.verify("models/v1") == receipts[0]
        (source / "one.json").write_text("conflict")
        with pytest.raises(ConflictError):
            publisher.publish(source, "models/v1")
        assert publisher.verify("models/v1") == receipts[0]

        put = store.put

        def interrupt(key, body):
            if key.endswith("/two.json"):
                raise OSError("simulated connection interruption")
            return put(key, body)

        monkeypatch.setattr(store, "put", interrupt)
        with pytest.raises(OSError):
            publisher.publish(source, "models/v2")
        with pytest.raises(IntegrityError):
            publisher.verify("models/v2")
        monkeypatch.setattr(store, "put", put)
        resumed = publisher.publish(source, "models/v2")
        assert publisher.verify("models/v2") == resumed
        store.client.put_object(
            Bucket=store.bucket,
            Key=store.key("models/v2/one.json"),
            Body=b"tampered",
        )
        with pytest.raises(IntegrityError):
            publisher.verify("models/v2")
    finally:
        pages = store.client.get_paginator("list_objects_v2").paginate(
            Bucket=store.bucket, Prefix=store.prefix + "/"
        )
        for page in pages:
            objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if objects:
                store.client.delete_objects(
                    Bucket=store.bucket, Delete={"Objects": objects, "Quiet": True}
                )
