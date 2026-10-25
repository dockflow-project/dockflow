"""Publication records share the actual SQLite/PostgreSQL project database."""

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from dockflow_artifacts import ArtifactError, ConflictError, IntegrityError, Publisher
from dockflow_artifacts.persistence import ArtifactRecords
from dockflow_core import DockflowError
from dockflow_pipelines.artifacts import ArtifactStore
from dockflow_pipelines.database_schema import PROJECT_TABLES


def publisher_for(store, options, root):
    return Publisher(root, database=options, project_id=store.project_id)


def test_publisher_first_shares_schema_and_readonly_completion(
    database_state, tmp_path
):
    store, options = database_state
    root = tmp_path / "artifacts"
    source = tmp_path / "source"
    source.write_text("immutable payload")
    publisher = publisher_for(store, options, root)
    assert not root.exists()
    receipt = publisher.publish(source, "models/v1")
    assert receipt.manifest_uri.startswith(
        f"dockflow://{store.project_id}/publications/"
    )
    with store.owner():
        store.initialize()
        assert type(publisher.database) is type(store.database.adapter)
        snapshot = tmp_path / "snapshot.sqlite"
        store.export_database(snapshot)
    reader = publisher_for(
        store, {"backend": "sqlite", "database": str(snapshot)}, root
    )
    before = snapshot.read_bytes()
    assert reader.verify("models/v1") == receipt
    assert snapshot.read_bytes() == before
    files = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }
    assert files == {"models/v1", ".dockflow/storage.json"}
    with publisher.database.snapshot() as connection:
        rows = publisher.database.execute(
            connection,
            "SELECT namespace,record_key FROM dockflow_artifact_records WHERE project_id=?",
            (store.project_id,),
        ).fetchall()
    assert set(rows) == {
        ("publication-claims", "models"),
        ("publication-claims", "models/v1"),
        ("publication-manifests", "models/v1"),
    }


@pytest.mark.parametrize("committed", [False, True])
def test_completion_failure_retries_without_replacing_payload(
    database_state, tmp_path, monkeypatch, committed
):
    store, options = database_state
    source = tmp_path / "source"
    source.write_text("model")
    root = tmp_path / "artifacts"
    publisher = publisher_for(store, options, root)
    put = ArtifactRecords.put

    def fail(self, namespace, key, value):
        if namespace == "publication-manifests":
            if committed:
                put(self, namespace, key, value)
            raise DockflowError("Injected completion interruption", "UNAVAILABLE", 503)
        return put(self, namespace, key, value)

    with monkeypatch.context() as patch:
        patch.setattr(ArtifactRecords, "put", fail)
        with pytest.raises(ArtifactError, match="completion interruption"):
            publisher.publish(source, "model")
    assert (root / "model").read_text() == "model"
    restarted = publisher_for(store, options, root)
    if not committed:
        with pytest.raises(IntegrityError, match="completion"):
            restarted.verify("model")
    receipt = restarted.publish(source, "model")
    assert restarted.verify("model") == receipt
    source.write_text("different")
    with pytest.raises(ConflictError):
        restarted.publish(source, "model")


def test_database_failure_never_uploads_payload_or_leaks_driver_error(
    database_state, tmp_path, monkeypatch
):
    store, options = database_state
    publisher = publisher_for(store, options, tmp_path / "artifacts")
    source = tmp_path / "source"
    source.write_text("model")

    def fail(**kwargs):
        raise RuntimeError("synthetic-secret-driver-detail")

    monkeypatch.setattr(publisher.database, "connect", fail)
    with pytest.raises(ArtifactError) as raised:
        publisher.publish(source, "model")
    assert "synthetic-secret" not in str(raised.value)
    assert not (tmp_path / "artifacts/model").exists()


@pytest.mark.parametrize("conflicting", [False, True])
def test_independent_publication_processes(database_state, tmp_path, conflicting):
    store, options = database_state
    root = tmp_path / "artifacts"
    sources = [tmp_path / "source-a", tmp_path / "source-b"]
    sources[0].write_text("first")
    sources[1].write_text("second" if conflicting else "first")
    script = """
import json,sys
from dockflow_artifacts import Publisher,ConflictError
p=Publisher(sys.argv[1],database=json.loads(sys.argv[2]),project_id=sys.argv[3])
print('ready',flush=True)
sys.stdin.read(1)
try:
    result=p.publish(sys.argv[4],'models/result')
    print(json.dumps({'digest':result.digest}))
except ConflictError:
    print(json.dumps({'conflict':True}))
"""
    processes = []
    try:
        for index in range(6):
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        script,
                        str(root),
                        json.dumps(options),
                        store.project_id,
                        str(sources[index % 2]),
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        for process in processes:
            assert process.stdout.readline().strip() == "ready"
        for process in processes:
            process.stdin.write("x")
            process.stdin.flush()
        outcomes = []
        for process in processes:
            output, error = process.communicate(timeout=30)
            assert process.returncode == 0, error
            outcomes.append(json.loads(output))
        successes = [item["digest"] for item in outcomes if "digest" in item]
        assert len(set(successes)) == 1
        assert len(successes) == (3 if conflicting else 6)
        publisher = publisher_for(store, options, root)
        assert publisher.verify("models/result").digest == successes[0]
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.communicate()


def test_sql_records_and_payloads_survive_project_backup(database_state, tmp_path):
    store, options = database_state
    root = tmp_path / "artifacts"
    source = tmp_path / "source"
    source.write_text("standalone publication")
    publisher = publisher_for(store, options, root)
    receipt = publisher.publish(source, "model")
    artifacts = ArtifactStore(store, {"backend": "filesystem", "managed_root": root})
    with store.owner():
        store.initialize()
        backup = tmp_path / "backup"
        store.backup(backup, artifacts)
        assert (backup / "managed/model").read_text() == source.read_text()
        with store.database.transaction() as connection:
            for table in reversed(PROJECT_TABLES):
                predicate = (
                    "project_id=?"
                    if table.startswith("dockflow_") or table == "df_cache_scopes"
                    else "scope_id IN (SELECT scope_id FROM df_cache_scopes WHERE project_id=?)"
                )
                store.database.execute(
                    connection,
                    f"DELETE FROM {table} WHERE {predicate}",
                    (store.project_id,),
                )
        store.import_database(backup / "state.sqlite")
        store.initialize()
    assert publisher_for(store, options, root).verify("model") == receipt


def test_backup_refuses_corrupt_publication_and_omitted_roots(database_state, tmp_path):
    store, options = database_state
    source = tmp_path / "source"
    source.write_text("model")
    root = tmp_path / "artifacts"
    publisher = publisher_for(store, options, root)
    publisher.publish(source, "model")
    artifacts = ArtifactStore(store, {"backend": "filesystem", "managed_root": root})
    with store.owner():
        store.initialize()
        (root / "model").write_text("corrupted")
        with pytest.raises(DockflowError, match="publication contents"):
            store.backup(tmp_path / "corrupt-backup", artifacts)
        assert not (tmp_path / "corrupt-backup").exists()
        (root / "model").write_text("model")
        publisher_for(store, options, tmp_path / "another-root").publish(
            source, "model"
        )
        with pytest.raises(DockflowError, match="additional artifact roots"):
            store.backup(tmp_path / "incomplete-backup", artifacts)
        assert not (tmp_path / "incomplete-backup").exists()


def test_postgresql_maintenance_excludes_publication_commit(
    database_state, tmp_path, monkeypatch
):
    store, options = database_state
    if options["backend"] != "postgresql":
        pytest.skip("PostgreSQL independent publisher maintenance gate")
    source = tmp_path / "source"
    source.write_text("model")
    publisher = publisher_for(store, options, tmp_path / "artifacts")
    reached = Event()
    put = ArtifactRecords.put_many

    def observe(self, *args, **kwargs):
        reached.set()
        return put(self, *args, **kwargs)

    monkeypatch.setattr(ArtifactRecords, "put_many", observe)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with store.owner(exclusive=True):
            store.initialize()
            pending = pool.submit(publisher.publish, source, "model")
            assert reached.wait(5)
            assert not pending.done()
        receipt = pending.result(timeout=10)
    assert publisher.verify("model") == receipt
