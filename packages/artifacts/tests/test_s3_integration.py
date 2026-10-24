"""Opt-in qualification against a real conditional S3-compatible service."""

import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from dockflow_artifacts import ArtifactError, ConflictError, IntegrityError, Publisher

CONFIG = os.environ.get("DOCKFLOW_TEST_ARTIFACT_S3_CONFIG")
ENDPOINT = os.environ.get("DOCKFLOW_TEST_CACHE_S3_ENDPOINT")
pytestmark = [
    pytest.mark.s3,
    pytest.mark.skipif(
        not (CONFIG or ENDPOINT), reason="Set DOCKFLOW_TEST_ARTIFACT_S3_CONFIG"
    ),
]


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_live_conditional_publication(tmp_path, monkeypatch, backend):
    """Create and remove only a unique test prefix inside the configured root."""
    import boto3

    owned_bucket = None
    if CONFIG:
        config = json.loads(Path(CONFIG).read_text())
    else:
        owned_bucket = "dockflow-publications-" + uuid.uuid4().hex
        client = boto3.client("s3", endpoint_url=ENDPOINT)
        client.create_bucket(Bucket=owned_bucket)
        config = {"root": "s3://" + owned_bucket, "s3": {"endpoint_url": ENDPOINT}}
    options = {"backend": "sqlite", "database": str(tmp_path / "state.sqlite")}
    if backend == "postgresql":
        if not os.environ.get("DOCKFLOW_TEST_STATE_POSTGRES_DSN"):
            if owned_bucket:
                client.delete_bucket(Bucket=owned_bucket)
            pytest.skip("Requires disposable PostgreSQL database")
        options = {
            "backend": "postgresql",
            "dsn_env": "DOCKFLOW_TEST_STATE_POSTGRES_DSN",
        }
    root = config["root"].rstrip("/") + "/qualification-" + uuid.uuid4().hex
    publisher = Publisher(
        root,
        s3=config.get("s3"),
        database=options,
        project_id="dockflow-publication-" + uuid.uuid4().hex,
    )
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
        with pytest.raises(ArtifactError, match="durability"):
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
        control_keys = [
            item["Key"][len(store.prefix) + 1 :]
            for page in store.client.get_paginator("list_objects_v2").paginate(
                Bucket=store.bucket, Prefix=store.prefix + "/.dockflow/"
            )
            for item in page.get("Contents", [])
        ]
        assert control_keys == [".dockflow/storage.json"]
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
        if owned_bucket:
            store.client.delete_bucket(Bucket=owned_bucket)
        if backend == "postgresql":
            with publisher.database.connect() as connection:
                publisher.database.execute(
                    connection,
                    "DELETE FROM dockflow_artifact_records WHERE project_id=?",
                    (publisher.project_id,),
                )
