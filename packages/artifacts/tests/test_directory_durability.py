"""Publication acknowledges file and every potentially new directory boundary."""

import io
from pathlib import Path

import pytest
from dockflow_artifacts import ArtifactError, Publisher
from dockflow_artifacts._storage import FileStore
from dockflow_database.errors import DockflowError


@pytest.mark.parametrize("retry", [False, True])
def test_file_store_syncs_new_ancestors_and_identical_retry(
    tmp_path, monkeypatch, retry
):
    import dockflow_artifacts._storage as storage

    root = tmp_path / "new" / "root"
    store = FileStore(root)
    key = "nested/deep/content"
    if retry:
        assert store.put(key, io.BytesIO(b"content"))
    synchronized = []
    original_open = storage.os.open
    original_fsync = storage.os.fsync
    directories = {}

    def opened(path, flags, *args, **kwargs):
        descriptor = original_open(path, flags, *args, **kwargs)
        if flags & storage.os.O_DIRECTORY:
            directories[descriptor] = Path(path)
        return descriptor

    def synced(descriptor):
        if descriptor in directories:
            synchronized.append(directories.pop(descriptor))
        return original_fsync(descriptor)

    monkeypatch.setattr(storage.os, "open", opened)
    monkeypatch.setattr(storage.os, "fsync", synced)
    assert store.put(key, io.BytesIO(b"content")) is not retry
    assert synchronized == [
        (root / key).parent,
        *(root / key).parent.parents,
    ]


@pytest.mark.parametrize("boundary", ["identity", "payload_leaf", "root_parent"])
def test_failed_directory_sync_never_completes_and_retry_repairs(
    tmp_path, monkeypatch, boundary
):
    import dockflow_artifacts._storage as storage

    root = tmp_path / "new" / "published"
    source = tmp_path / "source"
    source.write_bytes(b"content")
    publisher = Publisher(root)
    if boundary != "identity":
        publisher._records(create=True)
    original = storage._sync_ancestors
    observed = []

    def fail(path):
        observed.append(path)
        if boundary == "identity" or path == root / "nested" / "deep":
            # Exercise the actual ancestor loop, failing after any earlier
            # directories were flushed rather than before the durable write.
            failing = root.parent if boundary == "root_parent" else path
            original_open = storage.os.open

            def opened(directory, flags, *args, **kwargs):
                if Path(directory) == failing and flags & storage.os.O_DIRECTORY:
                    raise OSError("injected directory sync failure")
                return original_open(directory, flags, *args, **kwargs)

            with monkeypatch.context() as patch:
                patch.setattr(storage.os, "open", opened)
                return original(path)
        return original(path)

    with monkeypatch.context() as patch:
        patch.setattr(storage, "_sync_ancestors", fail)
        with pytest.raises(ArtifactError, match="durability"):
            publisher.publish(source, "nested/deep/content")
    assert observed
    records = publisher._records(create=False)
    if boundary == "identity":
        with pytest.raises(DockflowError, match="missing"):
            records.get("publication-manifests", "nested/deep/content")
    else:
        assert records.get("publication-manifests", "nested/deep/content") is None
    repaired = []

    def record(path):
        repaired.append(path)
        return original(path)

    monkeypatch.setattr(storage, "_sync_ancestors", record)
    receipt = publisher.publish(source, "nested/deep/content")
    assert root / ".dockflow" in repaired
    assert root / "nested" / "deep" in repaired
    assert publisher.verify("nested/deep/content") == receipt
